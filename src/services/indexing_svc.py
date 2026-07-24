"""İndeksleme hattı: chunk→diff→embed→upsert, çağrı grafiği, watcher, kopya-kod taraması."""
import json
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone

from pydantic import BaseModel
from qdrant_client import models

try:
    from .. import retrieval
    from ..chunker import extract_calls
    from ..retrieval import dense_model, sparse_model, gpu_available
    from .common import (cl, ROOT, INTERNAL_COLLS, STATE, WATCH_INTERVAL_SEC,
                          BACKUP_DIR, BACKUP_INTERVAL_SEC, detect_language, JOB_COLL)
    from .profiles import get_profile, set_profile, get_history, record_history
    from .collections_svc import _run_backup
except ImportError:
    import retrieval
    from chunker import extract_calls
    from retrieval import dense_model, sparse_model, gpu_available
    from services.common import (cl, ROOT, INTERNAL_COLLS, STATE, WATCH_INTERVAL_SEC,
                                  BACKUP_DIR, BACKUP_INTERVAL_SEC, detect_language, JOB_COLL)
    from services.profiles import get_profile, set_profile, get_history, record_history
    from services.collections_svc import _run_backup

# ---------------- indeksleme ----------------
class IndexReq(BaseModel):
    path: str = ""                    # boşsa: kayıtlı kaynak veya mevcut chunk dosyası kullanılır
    lib: str = ""                     # boşsa: collection adı
    collection: str = "unidac"
    vectors: list[str] = ["dense", "sparse"]   # bu çalıştırmada hesaplanacak vektör türleri
    device: str = "gpu"                        # gpu | cpu (yalnız dense için)
    patterns: str = "*.pas"                    # virgülle ayrılmış glob desen(ler)i — hangi dosyalar taransın

# Bu isimler o kadar jenerik/yaygın (RTL yerleşik rutinleri veya kütüphane
# genelinde onlarca sınıfta ayrı ayrı tekrarlanan sıradan üye adları) ki
# isim-tabanlı çözümleme neredeyse her zaman YANLIŞ (alakasız) bir hedefe
# bağlanır — canlı testte doğrulandı: "SplitString" kodundaki bir "Length("
# çağrısı, aynı korpustaki "AnsiString.Length" / "IMetadataBuilder.setLength" /
# "MemoryStream.SetLength" gibi tamamen ilgisiz metodlara "çağrı adayı" olarak
# bağlanıyordu. Bu isimler ÇÖZÜMLEME aşamasında atlanır (extract_calls'ın kendisi
# hâlâ hepsini çıkarır — sadece bu fonksiyon korpus-içi kenar üretmez).
GENERIC_CALL_NAMES = frozenset("""
length setlength copy free create add delete insert remove clear exit inc dec
trim uppercase lowercase inttostr strtoint strtofloat floattostr assigned
freeandnil format pos new dispose getmem freemem write writeln read readln
move fillchar comparestr sametext contains indexof tostring getenumerator
first last count value name text execute open close destroy release update
""".split())

def _link_call_graph(collection: str, st: dict | None = None):
    """Tüm koleksiyonu tarayıp her "method" (impl) chunk'ının halihazırda Qdrant'ta
    duran 'code' payload'ından çağrı adaylarını (extract_calls) YENİDEN hesaplar,
    gerçek chunk kimliklerine çözer ve tersini (called_by) hesaplayıp payload olarak
    yazar. Kaynak dosyalara ihtiyaç YOKTUR; her seferinde 'code'dan taze hesaplar
    (idempotent). İsim-tabanlı bir SEZGİDİR — tip/overload çözümlemesi yapılmaz.

    BELLEK/YAZMA NOTU (dış analizde işaret edilen ölçek riski üzerine yeniden
    yazıldı): eski sürüm TÜM koleksiyonu payload+VEKTÖRLERLE RAM'e alıp HER noktayı
    yeniden upsert ediyordu — 375K'lık Jedi'da GB'larca bellek ve tamamen gereksiz
    yazma yükü. Yeni akış üç geçişli ve batch-sınırlı:
      A) hafif scroll (isim/tür) -> aday indeksi;
      B) batch'li scroll (kod dahil, vektörsüz) -> calls/called_by haritaları
         (kod RAM'de TUTULMAZ, batch bitince düşer);
      C) batch'li scroll ile mevcut calls/called_by KARŞILAŞTIRILIR, yalnız
         DEĞİŞENLER yazılır (vektörleri o an retrieve edilip tam upsert —
         per-point set_payload değil; o yol daha önce ölçülmüştü, ~5x yavaştı).
    İlişkisi değişmeyen nokta hiç yazılmaz — artımlı indekslemede tipik olarak
    noktaların büyük çoğunluğu."""
    MAX_CAND = 8
    total = cl.count(collection).count
    if st is not None:
        st.update(phase="linking", total=total, done=0)

    # ---- GEÇİŞ A: aday indeksi (hafif payload; bellek ~isim listesi kadar) ----
    # (bare_name, unit) -> en iyi aday; aynı (unit, isim) çiftinde method > decl
    # (canlı testte yakalanmıştı: çağrı hem decl hem impl kopyasına işaret ediyordu).
    best_by_unit_name: dict[tuple, dict] = {}
    next_page = None
    while True:
        batch, next_page = cl.scroll(collection, limit=10000, offset=next_page,
            with_payload=["name", "unit", "kind", "line_start"], with_vectors=False)
        for p in batch:
            name = p.payload.get("name") or ""
            bare = name.split(".")[-1].lower()
            if not bare:
                continue
            key = (p.payload.get("unit"), bare)
            cand = {"id": p.id, "name": name, "unit": p.payload.get("unit"),
                    "line_start": p.payload.get("line_start"), "kind": p.payload.get("kind")}
            existing = best_by_unit_name.get(key)
            if existing is None or (existing["kind"] != "method" and cand["kind"] == "method"):
                best_by_unit_name[key] = cand
        if next_page is None:
            break

    name_index: dict[str, list[dict]] = {}
    for (_unit, bare), cand in best_by_unit_name.items():
        name_index.setdefault(bare, []).append(cand)

    # ---- GEÇİŞ B: çağrı çözümü (kod batch'le okunur, biriktirilmez) ----
    calls_map: dict[int, list[dict]] = {}
    called_by_map: dict[int, list[dict]] = {}
    next_page = None
    while True:
        batch, next_page = cl.scroll(collection, limit=2000, offset=next_page,
            with_payload=["name", "unit", "kind", "line_start", "code"], with_vectors=False)
        for p in batch:
            if p.payload.get("kind") != "method":
                continue   # decl/type gövde içermez, çağrı adayı yok
            raw = extract_calls(p.payload.get("code", ""), p.payload.get("name", ""))
            resolved, seen = [], set()
            for called_name in raw:
                if called_name in GENERIC_CALL_NAMES:
                    continue
                for c in name_index.get(called_name, [])[:MAX_CAND]:
                    if c["id"] == p.id or c["id"] in seen:
                        continue
                    seen.add(c["id"]); resolved.append(c)
            if resolved:
                calls_map[p.id] = resolved
            caller_ref = {"id": p.id, "name": p.payload.get("name"), "unit": p.payload.get("unit"),
                          "line_start": p.payload.get("line_start")}
            for callee in resolved:
                called_by_map.setdefault(callee["id"], []).append(caller_ref)
        if next_page is None:
            break

    # ---- GEÇİŞ C: yalnız değişen ilişkileri yaz ----
    done = written = 0
    next_page = None
    while True:
        batch, next_page = cl.scroll(collection, limit=1000, offset=next_page,
                                      with_payload=True, with_vectors=False)
        changed = [p for p in batch
                   if (p.payload.get("calls") or []) != calls_map.get(p.id, [])
                   or (p.payload.get("called_by") or []) != called_by_map.get(p.id, [])[:MAX_CAND * 2]]
        if changed:
            vecs = {pp.id: (pp.vector or {}) for pp in
                    cl.retrieve(collection, ids=[p.id for p in changed], with_payload=False, with_vectors=True)}
            structs = [models.PointStruct(id=p.id, vector=vecs.get(p.id, {}),
                        payload={**p.payload, "calls": calls_map.get(p.id, []),
                                 "called_by": called_by_map.get(p.id, [])[:MAX_CAND * 2]})
                       for p in changed]
            cl.upsert(collection, points=structs)
            written += len(structs)
        done += len(batch)
        if st is not None:
            st.update(done=done)
        if next_page is None:
            break
    if st is not None:
        st["link_written"] = written   # kaçının ilişkisi gerçekten değişti (gözlemlenebilirlik)

# ---------------- kalıcı iş kaydı (Sıra 26 — checkpoint/resume) ----------------
# Model BASİT tutuldu: STATE["index_job"] zaten TEK seferde tek iş çalıştırıyor
# (index_start 409 ile kilitliyor) — "kuyruk" değil TEK slot yeter. Aşamalı
# ilerleme (hangi batch'te kalındığı) KAYDEDİLMİYOR — indeksleme zaten hash
# bazlı DIFF'li (yukarıdaki plan/old_hash mantığı): aynı IndexReq'i baştan
# yeniden çalıştırmak, değişmeyen noktaları otomatik atlayıp yalnız eksik
# kalanı işler — bu yüzden "devam etmek" = "aynı isteği yeniden tetiklemek".
# Checkpoint YALNIZCA başta yazılır, iş NORMAL bittiğinde (başarı VEYA
# yakalanmış hata) silinir — panel süreci sert şekilde kesilirse (kill/çökme,
# except bloğuna hiç girilmeden) kayıt SİLİNMEDEN kalır; bir sonraki panel
# açılışında bu, "yarıda kalmış iş" olarak algılanıp otomatik yeniden başlatılır.
_JOB_ID = "00000000-0000-0000-0000-000000000001"

def _save_job_checkpoint(r: "IndexReq"):
    try:
        if not cl.collection_exists(JOB_COLL):
            cl.create_collection(JOB_COLL, vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT))
        cl.upsert(JOB_COLL, points=[models.PointStruct(id=_JOB_ID, vector=[0.0],
            payload={"req": r.model_dump(), "started_at": datetime.now(timezone.utc).isoformat()})])
    except Exception:
        pass   # checkpoint yazımı asla asıl işi düşürmemeli

def _clear_job_checkpoint():
    try:
        if cl.collection_exists(JOB_COLL):
            cl.delete(JOB_COLL, points_selector=models.PointIdsList(points=[_JOB_ID]))
    except Exception:
        pass

def load_pending_job() -> "IndexReq | None":
    """Panel açılışında çağrılır: bir önceki çalıştırma yarıda mı kesilmiş?"""
    try:
        if not cl.collection_exists(JOB_COLL):
            return None
        pts = cl.retrieve(JOB_COLL, ids=[_JOB_ID], with_payload=True)
        return IndexReq(**pts[0].payload["req"]) if pts else None
    except Exception:
        return None

def _run_index(r: IndexReq):
    st = STATE["index_job"]
    _save_job_checkpoint(r)
    try:
        lib = r.lib or r.collection
        jsonl = ROOT / f"data/chunks-{r.collection}.jsonl"
        prev = get_history(r.collection).get(r.collection, [])
        prof = get_profile(r.collection)
        # elle düzeltilmiş yol (profil) geçmişteki son yoldan ÖNCELİKLİ — kullanıcı disk/klasör
        # taşındıktan sonra path'i Ayarlar'dan düzeltebilir, sonraki her "yenile" onu kullanır
        src_path = r.path or prof.get("path") or (prev[0]["path"] if prev else "")
        if not src_path:
            raise RuntimeError("kaynak klasör yok — bir yol verin")
        if r.path:
            # açıkça yeni bir yol verildi — profildeki (varsa eski/elle düzeltilmiş) yolu da
            # güncelle, yoksa bir sonraki "yenile" eski/durağan bir yolu kullanmaya devam ederdi
            set_profile(r.collection, path=r.path)

        # her seferinde yeniden chunk'la — chunker hızlıdır (~300 dosya/sn), asıl maliyetli
        # kısım embedding, ve hangi dosyaların gerçekten değiştiğini bilmek için önce
        # klasörün GÜNCEL halini görmemiz gerekir. Sadece yol artık diskte yoksa
        # (klasör taşınmış/silinmiş) elimizdeki son chunk dosyasına düşülür.
        if pathlib.Path(src_path).exists():
            st["phase"] = "chunking"
            p = subprocess.run([sys.executable, str(ROOT / "src/chunker.py"), src_path, lib, str(jsonl), r.patterns or "*.pas"],
                               capture_output=True, text=True, timeout=3600)
            if p.returncode != 0:
                raise RuntimeError("chunker: " + (p.stderr or p.stdout)[-250:])
        if not jsonl.exists():
            raise RuntimeError(f"chunk dosyası yok ve kaynak klasör bulunamadı: {src_path}")
        rows = [json.loads(l) for l in open(jsonl, encoding="utf-8")]
        row_by_id = {int(x["id"][:12], 16): x for x in rows}
        st.update(total=len(rows), phase="diffing", done=0)

        want_dense = "dense" in r.vectors
        want_sparse = "sparse" in r.vectors
        exists = cl.collection_exists(r.collection)
        if not exists:
            # her zaman iki vektör türünü de tanımla — hangisi bu turda hesaplanırsa hesaplansın,
            # diğeri daha sonra ayrı bir çalıştırmada update_vectors ile eklenebilsin.
            cl.create_collection(r.collection,
                vectors_config={"dense": models.VectorParams(size=1024, distance=models.Distance.COSINE)},
                sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)})
        retrieval.ensure_payload_indexes(r.collection)
        # kullanılan dosya deseni profile yazılır — auto_refresh watcher'ı aynı
        # desenle tarama yapabilsin (aksi halde *.pas varsayar, *.inc'i kaçırırdı)
        set_profile(r.collection, patterns=r.patterns or "*.pas")

        # BELLEK NOTU: eskiden buradaki scroll with_vectors=True ile TÜM vektörleri
        # RAM'e alıyordu — 375K noktalık Jedi'da GB'larca bellek (dış analizlerde
        # bağımsız iki kez işaret edilen OOM riski). Artık yalnızca hash + vektör
        # VARLIĞI (id kümeleri, HasVectorCondition filtreli id-only scroll) çekilir;
        # korunacak vektörlerin KENDİSİ embed döngüsünde batch başına tam o anda
        # retrieve edilir (bellek batch boyutuyla sınırlı kalır).
        # Tek tek set_payload/update_vectors HÂLÂ yapılmıyor (ölçülmüştü, çok yavaş) —
        # değişen/eksik nokta başına yine TEK tam upsert var, sadece kaynak vektörler
        # önceden değil tam zamanında okunuyor.
        # Vektör varlığı Qdrant'ın kendi deposundan okunuyor (kendi bayrağımıza
        # güvenmiyoruz — eski koleksiyonlarda öyle bir alan hiç yazılmadı, doğrulandı).
        old_hash: dict[int, str] = {}
        had_dense_ids: set[int] = set()
        had_sparse_ids: set[int] = set()
        if exists:
            next_page = None
            while True:
                batch, next_page = cl.scroll(r.collection, limit=10000, offset=next_page,
                                              with_payload=["hash"], with_vectors=False)
                for p_ in batch:
                    old_hash[p_.id] = p_.payload.get("hash")
                if next_page is None:
                    break
            for vec_name, target in (("dense", had_dense_ids), ("sparse", had_sparse_ids)):
                next_page = None
                while True:
                    batch, next_page = cl.scroll(r.collection, limit=10000, offset=next_page,
                        with_payload=False, with_vectors=False,
                        scroll_filter=models.Filter(must=[models.HasVectorCondition(has_vector=vec_name)]))
                    target.update(p_.id for p_ in batch)
                    if next_page is None:
                        break

        # kaynakta artık bulunmayan (silinmiş/yeniden adlandırılmış) eski noktalar —
        # SİLME İŞLEMİ BİLEREK BURADA YAPILMIYOR: embed/upsert bitmeden silinirse ve süreç
        # bu ikisi arasında çökerse (GPU/Ollama/ağ hatası), eskiler zaten gitmiş ama
        # yeni/değişen noktalar henüz yazılmamış olabilir — indeks olduğundan daha eksik
        # kalır. Silme, aşağıdaki embed/upsert döngüsü TAMAMEN bittikten sonra yapılıyor.
        stale_ids = [pid for pid in old_hash if pid not in row_by_id]

        plan = []          # (row, pid, need_dense, need_sparse, before_dense, before_sparse)
        n_new = n_changed = n_unchanged = 0
        for pid, x in row_by_id.items():
            is_new = pid not in old_hash
            changed = is_new or old_hash[pid] != x["hash"]
            had_dense = (not is_new) and (pid in had_dense_ids)
            had_sparse = (not is_new) and (pid in had_sparse_ids)
            before_dense = had_dense and not changed
            before_sparse = had_sparse and not changed
            if is_new:
                need_dense, need_sparse = want_dense, want_sparse
                n_new += 1
            elif changed:
                need_dense = want_dense or had_dense     # önceden varsa, yeni içerikle güncelle
                need_sparse = want_sparse or had_sparse
                n_changed += 1
            else:
                need_dense = want_dense and not had_dense
                need_sparse = want_sparse and not had_sparse
                n_unchanged += 1
            if need_dense or need_sparse:
                plan.append((x, pid, need_dense, need_sparse, before_dense, before_sparse))

        language = detect_language(src_path) if pathlib.Path(src_path).exists() else ""
        # Git provenance: bu indeks nesli HANGİ commit'ten üretildi — etki analizi
        # (analyze_impact) son indekslenen commit'i base alır. Depo değilse boş kalır.
        gi = retrieval.git_info(src_path) if pathlib.Path(src_path).exists() else {}
        hist_extra = {"new": n_new, "changed": n_changed, "unchanged": n_unchanged, "deleted": len(stale_ids),
                      "language": language, "status": "ok",
                      "commit": gi.get("commit", ""), "branch": gi.get("branch", ""), "git_dirty": gi.get("dirty", False)}
        if gi.get("commit"):
            set_profile(r.collection, last_commit=gi["commit"], git_root=gi.get("git_root", ""))
        # kaynak/url İLK-DOKUNUŞTA otomatik doldurulur (Owner→Collection modelinin bir
        # parçası — bkz. profiles.py registry'leri) — kullanıcı sonradan Ayarlar'dan elle
        # düzeltirse bir SONRAKI reindex bunu ASLA ezmez (prof, bu koşunun BAŞINDA okunmuş
        # eski durum; kaynak/url o zaman zaten boş değilse burası hiç dokunmaz).
        if not prof.get("kaynak") and not prof.get("url") and gi.get("git_root"):
            set_profile(r.collection, kaynak="git", url=gi.get("remote") or None)
        st.update(total=len(plan), phase="embedding", done=0,
                  skipped=n_unchanged, deleted=len(stale_ids))
        # plan boş değilse (gerçek içerik değişikliği) ya da silinen nokta varsa,
        # çağrı grafiği bağlantı geçişi gerekir — _link_call_graph 'code'dan taze
        # hesapladığı için (bkz. kendi docstring'i) burada calls_raw ile ilgili
        # ekstra bir tazelik kontrolüne gerek yok.
        changed_something = len(plan) > 0 or len(stale_ids) > 0
        if not plan:
            if stale_ids:
                cl.delete(r.collection, points_selector=models.PointIdsList(points=stale_ids))
            if changed_something:
                _link_call_graph(r.collection, st)
                retrieval.build_symbol_graph(r.collection, st)
            record_history(r.collection, src_path, r.vectors, len(rows), extra=hist_extra)
            st.update(phase="done", sec=0.0)
            _clear_job_checkpoint()
            return

        dm = dense_model(r.device) if any(pl[2] for pl in plan) else None
        sm = sparse_model() if any(pl[3] for pl in plan) else None
        t0 = time.time(); B = 128
        for i in range(0, len(plan), B):
            b = plan[i:i + B]
            texts = [f"passage: {x['unit']} {x['name']}\n{x['code'][:2000]}" for x, *_ in b]
            need_d_any = any(nd for _, _, nd, _, _, _ in b)
            need_s_any = any(ns for _, _, _, ns, _, _ in b)
            dvs = list(dm.embed(texts)) if (dm and need_d_any) else [None] * len(b)
            svs = list(sm.embed(texts)) if (sm and need_s_any) else [None] * len(b)
            # korunacak (yeniden hesaplanmayacak) mevcut vektörler TAM O ANDA, yalnız
            # bu batch için çekilir — bellek batch boyutuyla sınırlı (yukarıdaki not)
            preserve_ids = [pid for (_x, pid, _nd, _ns, bd, bs) in b if bd or bs]
            old_vecs: dict[int, dict] = {}
            if preserve_ids:
                for p_ in cl.retrieve(r.collection, ids=preserve_ids, with_payload=False, with_vectors=True):
                    old_vecs[p_.id] = p_.vector or {}
            pts = []
            for (x, pid, need_dense, need_sparse, before_dense, before_sparse), dv, sv in zip(b, dvs, svs):
                vec = {}
                if need_dense and dv is not None:
                    vec["dense"] = dv.tolist()
                elif before_dense and "dense" in old_vecs.get(pid, {}):
                    vec["dense"] = old_vecs[pid]["dense"]     # değişmedi — olduğu gibi yeniden yaz
                if need_sparse and sv is not None:
                    vec["sparse"] = models.SparseVector(indices=sv.indices.tolist(), values=sv.values.tolist())
                elif before_sparse and "sparse" in old_vecs.get(pid, {}):
                    vec["sparse"] = old_vecs[pid]["sparse"]
                pts.append(models.PointStruct(
                    id=pid, vector=vec,
                    payload={k: x[k] for k in ("lib", "unit", "kind", "name", "line_start", "line_end", "hash")}
                             | {"code": x["code"][:4000], "doc": x.get("doc", ""), "calls_raw": x.get("calls_raw", [])}
                             | ({"uses": x["uses"]} if x.get("uses") else {})      # unithead: uses-graf girdisi
                             | ({"huge": True} if x.get("huge") else {})           # dev metod: kod kırpık, tam hali diskte
                             | ({"lang": x["lang"]} if x.get("lang") else {})      # çok dilli (Sıra 10): Pascal'da yok
                             | ({"extends": x["extends"]} if x.get("extends") else {})))  # kalıtım/interface kenarları
            cl.upsert(r.collection, points=pts)   # her batch TEK çağrı — hem yeni hem değişen noktalar için
            st.update(done=i + len(b), rate=round((i + len(b)) / (time.time() - t0), 1))
        # yeni/değişen içerik güvenle yazıldıktan SONRA eskiler silinir (yukarıdaki not)
        if stale_ids:
            cl.delete(r.collection, points_selector=models.PointIdsList(points=stale_ids))
        if changed_something:
            _link_call_graph(r.collection, st)
            retrieval.build_symbol_graph(r.collection, st)
        record_history(r.collection, src_path, r.vectors, len(rows), extra=hist_extra)
        st.update(phase="done", sec=round(time.time() - t0, 1))
        _clear_job_checkpoint()
    except Exception as e:
        st.update(phase="error", error=str(e)[:300])
        _clear_job_checkpoint()   # işlenmiş/kayda geçmiş hata — bir sonraki panel açılışında SESSİZCE yeniden denenmesin
        # KALICI iş kaydı: hatalar da tarihçeye yazılır — eskiden yalnız başarılı
        # koşular kaydediliyordu, panel yeniden başlayınca hata bağlamı kayboluyordu
        # (dış analizde işaret edilen "iş geçmişi bellekte" sorununun ucuz yarısı).
        try:
            record_history(r.collection, r.path or "", r.vectors, 0,
                           extra={"status": "error", "error": str(e)[:300]})
        except Exception:
            pass

# ---------------- otomatik artımlı yenileme (watch mode) ----------------
def _run_git_update_all():
    """"Tümünü Güncelle": kaynak=git olan (ve git_root'u profilde kayıtlı) TÜM
    koleksiyonları sırayla `git pull --ff-only` ile günceller, başarılı olanları
    mevcut artımlı _run_index'le yeniden indeksler. --ff-only bilinçli seçildi:
    asla merge/rebase yapmaz, sadece hızlı-ileri mümkünse günceller — yerelde
    commit'lenmemiş değişiklik varsa (dirty) o koleksiyon ATLANIR (pull'a hiç
    kalkışılmaz, git'in kendi reddine güvenmek yerine önden kontrol edilir —
    "yıkıcı olabilecek eylemi önce kontrol et" ilkesi). Tek seferde bir
    koleksiyon işlenir (aynı _run_index/STATE["index_job"] paylaşımı watcher'la
    aynı desende — bkz. _watch_loop)."""
    job = STATE["git_update_job"]
    results = []
    try:
        cands = []
        for c in cl.get_collections().collections:
            if c.name in INTERNAL_COLLS:
                continue
            prof = get_profile(c.name)
            if prof.get("kaynak") == "git" and prof.get("git_root"):
                cands.append((c.name, prof))
        job.update(phase="running", total=len(cands), done=0, results=[])
        for i, (name, prof) in enumerate(cands):
            job.update(current=name, done=i, results=results)
            entry = {"collection": name, "pulled": False, "reindexed": False, "output": ""}
            root = prof["git_root"]
            gi = retrieval.git_info(root)
            if gi.get("dirty"):
                entry["output"] = "atlandı: yerel çalışma ağacında commit'lenmemiş değişiklik var"
            else:
                try:
                    r = subprocess.run(["git", "-C", root, "pull", "--ff-only"],
                                       capture_output=True, text=True, timeout=300)
                    entry["output"] = ((r.stdout or "") + (r.stderr or ""))[-500:].strip()
                    entry["pulled"] = r.returncode == 0
                except Exception as e:
                    entry["output"] = str(e)[:300]
            if entry["pulled"]:
                hist = get_history(name).get(name, [])
                vectors = (hist[0].get("vectors") if hist else None) or ["dense", "sparse"]
                req = IndexReq(collection=name, vectors=vectors, device="gpu" if gpu_available() else "cpu",
                               patterns=prof.get("patterns", "*.pas"))
                STATE["index_job"] = {"collection": name, "mode": "+".join(req.vectors) + " (git-update)",
                                      "device": req.device, "total": 0, "done": 0, "rate": 0, "phase": "starting"}
                _run_index(req)
                entry["reindexed"] = STATE["index_job"].get("phase") == "done"
                if not entry["reindexed"]:
                    entry["output"] += f" | reindex hatası: {STATE['index_job'].get('error', '')}"
            results.append(entry)
        job.update(phase="done", done=len(cands), results=results)
    except Exception as e:
        job.update(phase="error", error=str(e)[:300], results=results)

def migrate_ids_v2(collection: str) -> dict:
    """Chunker v2'nin repo-kimlikli ID'sine GPU'SUZ geçiş: her noktanın yeni ID'si
    mevcut payload'dan hesaplanır (lib:unit:kind_key:code[:160] — payload code'u
    full_text[:4000] olduğu için ilk 160 karakter chunker'ın hash girdisiyle
    birebir aynı), nokta vektörleri ve TÜM payload'ıyla (tr/tr_deep çeviri
    önbelleği dahil!) yeni ID'ye kopyalanır, eskisi silinir. Yeniden embedding
    YOK — 513K noktalık korpus dakikalar içinde taşınır; ayrı yapılsaydı ~2 saat
    GPU gerekirdi. İdempotent: ikinci çağrıda moved=0.
    Sonda çağrı/sembol grafları yeniden kurulur (calls/called_by listeleri eski
    ID'lere işaret eder olurdu)."""
    import xxhash
    kind_to_key = {"method": "impl", "decl": "decl", "type": "type", "unithead": "unithead"}
    moved = same = skipped = 0
    next_page = None
    while True:
        batch, next_page = cl.scroll(collection, limit=500, offset=next_page,
                                      with_payload=True, with_vectors=True)
        news, dels = [], []
        for p in batch:
            pl = p.payload
            key = kind_to_key.get(pl.get("kind"))
            lib, unit = pl.get("lib"), pl.get("unit")
            if not (key and lib and unit):
                skipped += 1
                continue
            new_id = int(xxhash.xxh3_64(f"{lib}:{unit}:{key}:{pl.get('code', '')[:160]}".encode()).hexdigest()[:12], 16)
            if new_id == p.id:
                same += 1
                continue
            news.append(models.PointStruct(id=new_id, vector=p.vector or {}, payload=pl))
            dels.append(p.id)
        if news:
            cl.upsert(collection, points=news)      # önce yaz, sonra sil — çökme yarı-durumu eskiyi korur
            cl.delete(collection, points_selector=models.PointIdsList(points=dels))
            moved += len(news)
        if next_page is None:
            break
    if moved:
        _link_call_graph(collection)
        retrieval.build_symbol_graph(collection)
    return {"collection": collection, "moved": moved, "already_v2": same, "skipped": skipped}

def _source_dirty(path: str, patterns: str, last_iso: str | None) -> bool:
    """Son indekslemeden sonra değişmiş (mtime daha yeni) EN AZ BİR kaynak dosya
    var mı? Dosya silinmesini mtime yakalayamaz — o durum bir sonraki gerçek
    reindex'te stale_ids ile zaten temizlenir; watcher yalnızca 'değişiklik oldu mu'
    ucuz sinyaline bakar."""
    try:
        last_ts = datetime.fromisoformat(last_iso).timestamp() if last_iso else 0.0
    except Exception:
        last_ts = 0.0
    root = pathlib.Path(path)
    for pat in (p.strip() for p in (patterns or "*.pas").split(",") if p.strip()):
        for f in root.rglob(pat):
            try:
                if f.stat().st_mtime > last_ts:
                    return True
            except OSError:
                continue
    return False

def _watch_loop():
    """auto_refresh açık koleksiyonlar için arka plan döngüsü: kayıtlı kaynak
    klasörü WATCH_INTERVAL_SEC aralıkla tarar, son indekslemeden yeni bir mtime
    görürse mevcut artımlı _run_index'i tetikler (hash-diff sayesinde yalnızca
    değişen chunk'lar embed edilir). Aynı anda tek iş kuralına uyar — elle
    başlatılmış bir indeksleme sürerken hiçbir şey tetiklemez."""
    while True:
        time.sleep(WATCH_INTERVAL_SEC)
        try:
            job = STATE["index_job"]
            if job and job.get("phase") in ("starting", "chunking", "diffing", "embedding", "linking"):
                continue
            for c in cl.get_collections().collections:
                if c.name in INTERNAL_COLLS:
                    continue
                prof = get_profile(c.name)
                if not prof.get("auto_refresh"):
                    continue
                path = prof.get("path")
                if not path or not pathlib.Path(path).exists():
                    continue
                hist = get_history(c.name).get(c.name, [])
                last_iso = hist[0]["date"] if hist else None
                if not _source_dirty(path, prof.get("patterns", "*.pas"), last_iso):
                    continue
                vectors = hist[0].get("vectors") if hist else None
                req = IndexReq(collection=c.name, vectors=vectors or ["dense", "sparse"],
                               device="gpu" if gpu_available() else "cpu",
                               patterns=prof.get("patterns", "*.pas"))
                STATE["index_job"] = {"collection": c.name, "mode": "+".join(req.vectors) + " (auto)",
                                      "device": req.device, "total": 0, "done": 0, "rate": 0, "phase": "starting"}
                _run_index(req)   # watcher zaten arka plan thread'i — senkron çalıştırmak doğru
                break             # tur başına tek koleksiyon: GPU'yu uzun süre kilitlemeyelim

            # günlük otomatik yedek: en yeni yedek dosyası BACKUP_INTERVAL_SEC'ten
            # eskiyse (veya hiç yoksa) çalışır — küçük koleksiyonlar + iç kayıtlar
            # (ayrıntı: _run_backup docstring)
            bjob = STATE.get("backup_job")
            if not (bjob and bjob.get("phase") == "running"):
                newest = max((f.stat().st_mtime for f in BACKUP_DIR.glob("*.jsonl.gz")), default=0.0) \
                         if BACKUP_DIR.exists() else 0.0
                if time.time() - newest > BACKUP_INTERVAL_SEC:
                    STATE["backup_job"] = {"phase": "starting", "trigger": "auto"}
                    _run_backup(full_all=False)
        except Exception:
            pass                  # watcher asla ölmemeli — bir sonraki turda yeniden dener

# ---------------- kopya/benzer kod taraması ----------------
# find_similar altyapısının koleksiyon-geneli ürünleştirilmesi (birleşik analizde
# "en hızlı teslim edilebilir yüksek görünürlüklü özellik"): her method chunk'ının
# kayıtlı dense vektörüyle eşik-üstü komşuları bulunur, çiftler tekilleştirilip
# skora göre raporlanır. Embedding HESAPLANMAZ — yalnız mevcut vektörlerle sorgu.
class DupScanReq(BaseModel):
    collection: str
    threshold: float = 0.93   # kosinüs eşiği — 0.93+ pratikte "neredeyse aynı mantık"
    min_chars: int = 300      # kısacık gövdeler (getter vb.) gürültü üretir, atlanır
    max_pairs: int = 300
    max_scan: int = 20000     # taranacak en fazla chunk (çok büyük koleksiyonlarda süre sınırı)

def _run_dup_scan(r: DupScanReq):
    st = STATE["dup_job"]
    try:
        flt = models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="method"))])
        meta: dict[int, dict] = {}
        next_page = None
        while len(meta) < r.max_scan:
            batch, next_page = cl.scroll(r.collection, limit=2000, offset=next_page,
                with_payload=["name", "unit", "line_start", "code"], scroll_filter=flt)
            for p in batch:
                if len(p.payload.get("code", "")) >= r.min_chars and len(meta) < r.max_scan:
                    meta[p.id] = {"name": p.payload.get("name"), "unit": p.payload.get("unit"),
                                  "line_start": p.payload.get("line_start"),
                                  "chars": len(p.payload.get("code", ""))}
            if next_page is None:
                break
        ids = list(meta)
        st.update(phase="scanning", total=len(ids), done=0)
        pairs: dict[tuple, float] = {}
        for i, pid in enumerate(ids):
            try:
                res = cl.query_points(r.collection, query=pid, using="dense", limit=4,
                                       query_filter=flt, score_threshold=r.threshold,
                                       with_payload=False).points
            except Exception:
                continue
            for p in res:
                if p.id == pid:
                    continue
                key = (min(pid, p.id), max(pid, p.id))
                if key not in pairs or p.score > pairs[key]:
                    pairs[key] = p.score
            if i % 200 == 0:
                st.update(done=i)
        ranked = sorted(pairs.items(), key=lambda kv: -kv[1])[:r.max_pairs]
        # eşleşen taraf tarama kümesinde olmayabilir (min_chars altında ya da
        # max_scan dışında) — meta'da yoksa o an tek tek getirilir
        missing = [pid for k, _s in ranked for pid in k if pid not in meta]
        if missing:
            for p in cl.retrieve(r.collection, ids=list(set(missing)), with_payload=["name", "unit", "line_start", "code"]):
                meta[p.id] = {"name": p.payload.get("name"), "unit": p.payload.get("unit"),
                              "line_start": p.payload.get("line_start"), "chars": len(p.payload.get("code", ""))}
        report = {
            "collection": r.collection, "threshold": r.threshold, "min_chars": r.min_chars,
            "scanned": len(ids), "generated_at": datetime.now(timezone.utc).isoformat(),
            "pairs": [{"score": round(s, 4),
                        "a": {"id": a, **meta.get(a, {})},
                        "b": {"id": b, **meta.get(b, {})},
                        "same_unit": meta.get(a, {}).get("unit") == meta.get(b, {}).get("unit")}
                       for (a, b), s in ranked]}
        out = ROOT / f"data/dup-report-{r.collection}.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        st.update(phase="done", done=len(ids), pairs=len(ranked), report=str(out.name))
    except Exception as e:
        st.update(phase="error", error=str(e)[:300])
