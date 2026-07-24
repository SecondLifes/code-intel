"""Code-Intel Yönetim Paneli v1 — FastAPI arka ucu.
Çalıştır:  .venv/Scripts/python.exe -m uvicorn src.panel:app --port 8500
Özellikler: hibrit arama (dense+BM25/RRF), CPU/GPU seçimi, klasörden yeni
indeksleme (chunk→embed), Ollama model seçimi, koleksiyon yönetimi.
"""
import gzip, json, os, pathlib, re, subprocess, sys, threading, time, urllib.request, uuid, zlib
from datetime import datetime, timezone

import onnxruntime as ort
ort.preload_dlls()

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from qdrant_client import models

try:
    from . import retrieval
    from .retrieval import cl, dense_model, sparse_model, gpu_available, ollama_generate  # noqa: F401
    from . import mcp_server
    from .chunker import extract_calls
except ImportError:
    # `uvicorn src.panel:app` proje kökünden çalıştırıldığında paket-göreli import
    # işe yarar; ama doğrudan `python src/panel.py` gibi çalıştırılırsa (paketsiz) düşülür.
    import retrieval
    from retrieval import cl, dense_model, sparse_model, gpu_available, ollama_generate  # noqa: F401
    import mcp_server
    from chunker import extract_calls

ROOT = pathlib.Path(__file__).resolve().parent.parent
QDRANT, OLLAMA = retrieval.QDRANT, retrieval.OLLAMA
HISTORY_COLL = "_index_history"    # indeksleme geçmişi
PROFILE_COLL = "_index_profiles"   # koleksiyon başına TEK nokta (versiyon gibi kullanıcı alanları) — hepsi Qdrant'ın kendisinde, ayrı bir dosya yok
SEARCH_LOG_COLL = retrieval.SEARCH_LOG_COLL   # arama telemetrisi (Analitik sekmesi okur)
SYMBOL_COLL = retrieval.SYMBOL_COLL           # tip kalıtım/interface kenarları
INTERNAL_COLLS = {HISTORY_COLL, PROFILE_COLL, SEARCH_LOG_COLL, SYMBOL_COLL}
STATE = {"index_job": None}
WATCH_INTERVAL_SEC = 600   # auto_refresh açık koleksiyonlar için kaynak klasör tarama aralığı

# uzantı -> dil etiketi (gerçek ayrıştırma DEĞİL — sadece klasördeki dosyaları etiketlemek için;
# şu an chunker sadece .pas dosyalarını gerçekten ayrıştırıyor)
LANG_EXT = {
    ".pas": "Pascal/Delphi", ".dpr": "Pascal/Delphi", ".dpk": "Pascal/Delphi", ".inc": "Pascal/Delphi",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".h": "C/C++", ".hpp": "C++",
    ".c": "C", ".cs": "C#", ".java": "Java", ".py": "Python",
    ".js": "JavaScript", ".ts": "TypeScript", ".go": "Go", ".rs": "Rust",
}

def detect_language(path: str) -> str:
    counts: dict[str, int] = {}
    try:
        for p in pathlib.Path(path).rglob("*"):
            if p.is_file():
                lang = LANG_EXT.get(p.suffix.lower())
                if lang:
                    counts[lang] = counts.get(lang, 0) + 1
    except Exception:
        return "Bilinmiyor"
    if not counts:
        return "Bilinmiyor"
    total = sum(counts.values())
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:2]
    return ", ".join(f"{lang} (%{round(100*n/total)})" for lang, n in top)

def profile_id(collection: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, collection))

def get_profile(collection: str) -> dict:
    if not cl.collection_exists(PROFILE_COLL):
        return {}
    pts = cl.retrieve(PROFILE_COLL, ids=[profile_id(collection)], with_payload=True)
    return pts[0].payload if pts else {}

def set_profile(collection: str, **fields):
    if not cl.collection_exists(PROFILE_COLL):
        cl.create_collection(PROFILE_COLL, vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT))
    payload = get_profile(collection)
    payload.update({k: v for k, v in fields.items() if v is not None})
    payload["collection"] = collection
    cl.upsert(PROFILE_COLL, points=[models.PointStruct(id=profile_id(collection), vector=[0.0], payload=payload)])

def ensure_history_collection():
    if not cl.collection_exists(HISTORY_COLL):
        cl.create_collection(HISTORY_COLL, vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT))

def record_history(collection: str, path: str, vectors: list[str], chunks: int, extra: dict | None = None):
    ensure_history_collection()
    payload = {"collection": collection, "path": path, "vectors": vectors, "chunks": chunks,
               "date": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)   # örn. new/changed/unchanged/deleted sayaçları
    cl.upsert(HISTORY_COLL, points=[models.PointStruct(id=str(uuid.uuid4()), vector=[0.0], payload=payload)])

def get_history(collection: str | None = None) -> dict:
    """collection -> [ {path, vectors, chunks, date, new, changed, unchanged, deleted}, ... ] , en yeni önce."""
    if not cl.collection_exists(HISTORY_COLL):
        return {}
    flt = models.Filter(must=[models.FieldCondition(key="collection", match=models.MatchValue(value=collection))]) if collection else None
    out: dict = {}
    next_page = None
    while True:
        batch, next_page = cl.scroll(HISTORY_COLL, scroll_filter=flt, limit=1000, offset=next_page, with_payload=True)
        for p in batch:
            out.setdefault(p.payload["collection"], []).append(
                {k: p.payload.get(k) for k in ("path", "vectors", "chunks", "date", "new", "changed", "unchanged", "deleted", "language")})
        if next_page is None:
            break
    for entries in out.values():
        entries.sort(key=lambda e: e["date"], reverse=True)
    return out

app = FastAPI(title="Code-Intel Panel")

# ---------------- opsiyonel API-key katmanı ----------------
# CODEINTEL_API_KEY ortam değişkeni AYARLIYSA, localhost DIŞINDAN gelen tüm /api/*
# istekleri X-API-Key başlığı ister. Localhost muaf — panelin kendi tarayıcı
# arayüzü anahtar bilmeden çalışmaya devam eder; katman yalnızca panel ağa
# açıldığında (örn. LAN'daki başka bir makineden) devreye girer.
API_KEY = os.environ.get("CODEINTEL_API_KEY", "")

@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    if API_KEY and request.url.path.startswith("/api/"):
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost") and request.headers.get("x-api-key") != API_KEY:
            return JSONResponse({"error": "geçersiz veya eksik X-API-Key"}, status_code=401)
    return await call_next(request)

# ---------------- sağlık / listeler ----------------
@app.get("/api/health")
def health():
    out = {"qdrant": False, "ollama": False, "gpu": "CUDAExecutionProvider" in ort.get_available_providers(), "collections": []}
    try:
        cols = []
        for c in cl.get_collections().collections:
            if c.name in INTERNAL_COLLS:
                continue
            info = cl.get_collection(c.name)
            v = info.config.params.vectors
            vecs = list(v.keys()) if isinstance(v, dict) else (["default"] if v else [])
            sv = info.config.params.sparse_vectors
            svecs = list(sv.keys()) if isinstance(sv, dict) else []
            prof = get_profile(c.name)
            cols.append({"name": c.name, "points": info.points_count, "vectors": vecs + [f"{s}(sparse)" for s in svecs],
                         "owner": prof.get("owner", ""), "group": prof.get("group", "")})
        out["collections"] = cols
        out["qdrant"] = True
    except Exception: pass
    try:
        urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3); out["ollama"] = True
    except Exception: pass
    return out

# ---------------- indeksleme geçmişi (koleksiyon -> [{yol, tarih, vektörler, chunk}]) ----------------
@app.get("/api/history")
def history_get(collection: str = ""):
    return get_history(collection or None)

# ---------------- indeks profili (versiyon, klasör, dil gibi kullanıcı alanları) ----------------
class ProfileReq(BaseModel):
    collection: str
    version: str | None = None
    path: str | None = None       # reindex'e gerek KALMADAN düzeltilebilsin diye (disk/klasör taşındığında)
    language: str | None = None   # otomatik etiketi elle düzeltebilmek için
    priority: int | None = None   # 0-5 yıldız — çoklu koleksiyon aramasında skor boost'u için
    owner: str | None = None      # örn. "viniciussanchez" — bir kişinin/kuruluşun birden fazla kütüphanesini gruplamak için
    group: str | None = None      # serbest metin ikinci seviye etiket — örn. "REST İstemcileri"
    auto_refresh: bool | None = None   # açıksa watcher kaynak klasörü periyodik tarayıp değişiklikte artımlı reindex tetikler

@app.get("/api/profile")
def profile_get(collection: str):
    return get_profile(collection)

@app.post("/api/profile")
def profile_set(r: ProfileReq):
    # yalnızca gönderilen alanlar güncellenir — None olanlara dokunulmaz (set_profile zaten filtreler)
    if r.priority is not None and not (0 <= r.priority <= 5):
        return JSONResponse({"error": "priority 0-5 aralığında olmalı"}, status_code=400)
    set_profile(r.collection, version=r.version, path=r.path, language=r.language, priority=r.priority,
                owner=r.owner, group=r.group, auto_refresh=r.auto_refresh)
    return {"ok": True}

# ---------------- koleksiyon silme (kendisi + geçmiş + profil kayıtları) ----------------
@app.delete("/api/collection")
def collection_delete(collection: str):
    if collection in INTERNAL_COLLS:
        return JSONResponse({"error": "iç sistem koleksiyonu silinemez"}, status_code=400)
    if not cl.collection_exists(collection):
        return JSONResponse({"error": f"koleksiyon yok: {collection}"}, status_code=404)
    cl.delete_collection(collection)
    if cl.collection_exists(HISTORY_COLL):
        hist_ids = [p.id for p in cl.scroll(HISTORY_COLL, limit=10000,
                    scroll_filter=models.Filter(must=[models.FieldCondition(key="collection", match=models.MatchValue(value=collection))]))[0]]
        if hist_ids:
            cl.delete(HISTORY_COLL, points_selector=models.PointIdsList(points=hist_ids))
    if cl.collection_exists(PROFILE_COLL):
        cl.delete(PROFILE_COLL, points_selector=models.PointIdsList(points=[profile_id(collection)]))
    jsonl = ROOT / f"data/chunks-{collection}.jsonl"
    if jsonl.exists():
        jsonl.unlink()
    return {"ok": True}

def _copy_all_points(src: str, dst: str, skip_ids: set[int] | None = None) -> tuple[int, int]:
    """src koleksiyonundaki TÜM noktaları (vektör+payload) dst'ye kopyalar. Qdrant'ın
    kendi rename/copy API'si yok — bu yüzden scroll+upsert ile elle yapılıyor.
    skip_ids verilirse o id'ler atlanır (merge'de hedefte zaten var olan id'lerle
    çakışmayı önlemek için). (kopyalanan, atlanan) sayılarını döndürür — atlananlar
    merge'de ID ÇAKIŞMASI demektir ve sessizce yutulmamalı (dış analizde bulunan
    veri kaybı riski: iki kütüphanede aynı göreli yol+imza aynı 48-bit ID'yi üretir)."""
    n = skipped = 0
    next_page = None
    while True:
        batch, next_page = cl.scroll(src, limit=1000, offset=next_page, with_payload=True, with_vectors=True)
        if batch:
            pts = []
            for p in batch:
                if skip_ids and p.id in skip_ids:
                    skipped += 1
                    continue
                pts.append(models.PointStruct(id=p.id, vector=p.vector or {}, payload=p.payload))
            if pts:
                cl.upsert(dst, points=pts)
                n += len(pts)
        if next_page is None:
            break
    return n, skipped

# ---------------- koleksiyon yeniden adlandırma ----------------
class RenameReq(BaseModel):
    old_name: str; new_name: str

@app.post("/api/collection/rename")
def collection_rename(r: RenameReq):
    if r.old_name in INTERNAL_COLLS or r.new_name in INTERNAL_COLLS:
        return JSONResponse({"error": "iç sistem koleksiyonu adı kullanılamaz"}, status_code=400)
    if not cl.collection_exists(r.old_name):
        return JSONResponse({"error": f"koleksiyon yok: {r.old_name}"}, status_code=404)
    if cl.collection_exists(r.new_name):
        return JSONResponse({"error": f"'{r.new_name}' zaten mevcut"}, status_code=409)
    # Qdrant'ta collection rename yoktur: aynı vektör şemasıyla yeni koleksiyon
    # açılır, tüm noktalar kopyalanır, geçmiş/profil taşınır, en son eski silinir —
    # büyük koleksiyonlarda zaman alır ama tek yol bu.
    info = cl.get_collection(r.old_name)
    cl.create_collection(r.new_name, vectors_config=info.config.params.vectors,
                          sparse_vectors_config=info.config.params.sparse_vectors)
    retrieval.ensure_payload_indexes(r.new_name)
    n, _ = _copy_all_points(r.old_name, r.new_name)
    if cl.collection_exists(HISTORY_COLL):
        cl.set_payload(HISTORY_COLL, payload={"collection": r.new_name},
                        points=models.Filter(must=[models.FieldCondition(key="collection", match=models.MatchValue(value=r.old_name))]))
    prof = get_profile(r.old_name)
    if prof:
        set_profile(r.new_name, **{k: v for k, v in prof.items() if k != "collection"})
        if cl.collection_exists(PROFILE_COLL):
            cl.delete(PROFILE_COLL, points_selector=models.PointIdsList(points=[profile_id(r.old_name)]))
    cl.delete_collection(r.old_name)
    old_jsonl = ROOT / f"data/chunks-{r.old_name}.jsonl"
    if old_jsonl.exists():
        old_jsonl.rename(ROOT / f"data/chunks-{r.new_name}.jsonl")
    return {"ok": True, "points_copied": n}

# ---------------- koleksiyonları birleştirme (kaynaklar SİLİNMEZ, sadece kopyalanır) ----------------
class MergeReq(BaseModel):
    sources: list[str]; target: str

@app.post("/api/collection/merge")
def collection_merge(r: MergeReq):
    if r.target in INTERNAL_COLLS or any(s in INTERNAL_COLLS for s in r.sources):
        return JSONResponse({"error": "iç sistem koleksiyonu kullanılamaz"}, status_code=400)
    missing = [s for s in r.sources if not cl.collection_exists(s)]
    if missing:
        return JSONResponse({"error": f"koleksiyon(lar) yok: {missing}"}, status_code=404)
    if not r.sources:
        return JSONResponse({"error": "en az bir kaynak koleksiyon gerekli"}, status_code=400)
    if not cl.collection_exists(r.target):
        info = cl.get_collection(r.sources[0])
        cl.create_collection(r.target, vectors_config=info.config.params.vectors,
                              sparse_vectors_config=info.config.params.sparse_vectors)
    retrieval.ensure_payload_indexes(r.target)
    existing_ids: set[int] = set()
    next_page = None
    while True:
        batch, next_page = cl.scroll(r.target, limit=10000, offset=next_page, with_payload=False, with_vectors=False)
        existing_ids.update(p.id for p in batch)
        if next_page is None:
            break
    # owner/group bilgisi: hedefte zaten yoksa İLK kaynağın profili kopyalanır —
    # kaynaklar farklı sahip/gruplarda olabilir, bunu sessizce "doğru" saymak yerine
    # yanıtta açıkça bildiriyoruz (kullanıcı isterse Ayarlar'dan elle düzeltir).
    owners = {get_profile(s).get("owner") for s in r.sources if get_profile(s).get("owner")}
    groups = {get_profile(s).get("group") for s in r.sources if get_profile(s).get("group")}
    target_prof = get_profile(r.target)
    owner_group_note = ""
    if not target_prof.get("owner") and not target_prof.get("group"):
        first_prof = get_profile(r.sources[0])
        set_profile(r.target, owner=first_prof.get("owner", ""), group=first_prof.get("group", ""))
        if len(owners) > 1 or len(groups) > 1:
            owner_group_note = (f" UYARI: kaynaklar farklı sahip/grup değerlerine sahip ({owners}, {groups}) — "
                                 f"hedefe yalnızca ilk kaynağınki ({r.sources[0]}) kopyalandı, gerekirse elle düzeltin.")

    total_copied = 0
    collisions: dict[str, int] = {}   # kaynak -> atlanan (ID çakışan) nokta sayısı
    for s in r.sources:
        copied, skipped = _copy_all_points(s, r.target, skip_ids=existing_ids)
        total_copied += copied
        if skipped:
            collisions[s] = skipped
        # bir sonraki kaynak için hedefteki id kümesini güncelle — aynı id birden
        # fazla kaynakta varsa yalnızca İLKİ kopyalanır, tekrarlanan atlanır
        next_page = None
        while True:
            batch, next_page = cl.scroll(r.target, limit=10000, offset=next_page, with_payload=False, with_vectors=False)
            existing_ids.update(p.id for p in batch)
            if next_page is None:
                break
    collision_note = ""
    if collisions:
        collision_note = (f" UYARI: ID çakışması nedeniyle atlanan noktalar var: {collisions} — aynı göreli "
                          f"yol+imzaya sahip chunk'lar aynı ID'yi üretir; atlananlar hedefe KOPYALANMADI "
                          f"(ilk gelen kazandı). Kaynaklar silinmediği için veri kaybı yok, ama birleşik "
                          f"koleksiyonda bu parçalar tek kopya olarak temsil ediliyor.")
    return {"ok": True, "target": r.target, "points_copied": total_copied, "collisions": collisions,
            "owner_group_note": owner_group_note,
            "note": "Kaynak koleksiyonlar SİLİNMEDİ — istemiyorsanız Ayarlar'dan elle silin." + collision_note}

# ---------------- koleksiyon dışa/içe aktarma (gzip, akışlı) ----------------
def _vector_to_json(val):
    if hasattr(val, "indices"):   # models.SparseVector
        return {"_sparse": True, "indices": list(val.indices), "values": list(val.values)}
    return val

def _export_line_iter(collection: str, with_vectors: bool = True):
    """Export satırlarını ÜRETEÇ olarak verir — eski sürüm tüm satırları listede
    biriktirip sonra gzip'liyordu (375K'lık koleksiyonlarda GB'larca RAM; dış
    analizde işaret edilen bellek baskısı). İç koleksiyonların adsız (default)
    vektörü '_default' anahtarıyla taşınır."""
    info = cl.get_collection(collection)
    v, sv = info.config.params.vectors, info.config.params.sparse_vectors
    manifest = {
        "_manifest": True, "collection": collection,
        "dense_vectors": {k: {"size": vp.size, "distance": vp.distance.value} for k, vp in v.items()} if isinstance(v, dict) else {},
        "default_vector": ({"size": v.size, "distance": v.distance.value} if not isinstance(v, dict) and v else None),
        "sparse_vectors": list(sv.keys()) if isinstance(sv, dict) else [],
        "with_vectors": with_vectors,
        "points_count": info.points_count,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile": get_profile(collection),
    }
    yield json.dumps(manifest, ensure_ascii=False)
    next_page = None
    while True:
        batch, next_page = cl.scroll(collection, limit=1000, offset=next_page,
                                      with_payload=True, with_vectors=with_vectors)
        for p in batch:
            if not with_vectors:
                vec_out = {}
            elif isinstance(p.vector, dict):
                vec_out = {k: _vector_to_json(val) for k, val in (p.vector or {}).items()}
            else:
                vec_out = {"_default": p.vector}   # iç koleksiyonlar (size-1 adsız vektör)
            yield json.dumps({"id": p.id, "payload": p.payload, "vector": vec_out}, ensure_ascii=False)
        if next_page is None:
            break

def _gzip_iter(lines):
    """Satır üretecini akışlı gzip'e çevirir (bellekte tam kopya tutulmaz)."""
    co = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)   # 16+: gzip başlığı
    for line in lines:
        chunk = co.compress((line + "\n").encode("utf-8"))
        if chunk:
            yield chunk
    tail = co.flush()
    if tail:
        yield tail

@app.get("/api/collection/export")
def collection_export(collection: str):
    if collection in INTERNAL_COLLS or not cl.collection_exists(collection):
        return JSONResponse({"error": f"koleksiyon yok: {collection}"}, status_code=404)
    return StreamingResponse(_gzip_iter(_export_line_iter(collection)), media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{collection}.jsonl.gz"'})

# ---------------- otomatik/elle yedekleme (rotasyonlu) ----------------
BACKUP_DIR = ROOT / "backups"
BACKUP_KEEP = 3                 # koleksiyon başına saklanan yedek sayısı
BACKUP_INTERVAL_SEC = 24 * 3600
BACKUP_AUTO_MAX_POINTS = 50_000  # otomatik TAM yedek üst sınırı — daha büyük koleksiyonlar
                                 # (örn. 375K'lık Jedi, vektörlerle GB'larca dosya) sessizce
                                 # diski doldurmasın diye yalnız ELLE yedeklenir

def _run_backup(full_all: bool = False):
    """Tüm koleksiyonları backups\\ altına <ad>-<zaman>.jsonl.gz olarak yazar,
    koleksiyon başına en yeni BACKUP_KEEP kopya kalır. İç koleksiyonlar (profil,
    geçmiş, telemetri — küçük ve yeri doldurulamaz) HER ZAMAN dahil. Kullanıcı
    koleksiyonlarında otomatik modda BACKUP_AUTO_MAX_POINTS üstü atlanır
    (full_all=True — elle tetikleme — hepsini alır). Önce .tmp'ye yazılır,
    başarıyla bitince adlandırılır — yarım dosya asla yedek sanılmaz."""
    st = STATE.get("backup_job") or {}
    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        names = [c.name for c in cl.get_collections().collections]
        skipped = []
        st.update(phase="running", total=len(names), done=0)
        for i, name in enumerate(names):
            st.update(collection=name, done=i)
            if name not in INTERNAL_COLLS and not full_all:
                if cl.get_collection(name).points_count > BACKUP_AUTO_MAX_POINTS:
                    skipped.append(name)
                    continue
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            tmp = BACKUP_DIR / f".tmp-{name}.gz"
            final = BACKUP_DIR / f"{name}-{ts}.jsonl.gz"
            with open(tmp, "wb") as f:
                for chunk in _gzip_iter(_export_line_iter(name)):
                    f.write(chunk)
            tmp.rename(final)
            for old in sorted(BACKUP_DIR.glob(f"{name}-*.jsonl.gz"))[:-BACKUP_KEEP]:
                old.unlink()
        st.update(phase="done", done=len(names), skipped=skipped,
                  finished=datetime.now(timezone.utc).isoformat())
    except Exception as e:
        st.update(phase="error", error=str(e)[:300])

@app.post("/api/backup/run")
def backup_run(full: bool = True):
    if STATE.get("backup_job") and STATE["backup_job"].get("phase") == "running":
        return JSONResponse({"error": "zaten çalışan yedekleme var"}, status_code=409)
    STATE["backup_job"] = {"phase": "starting"}
    threading.Thread(target=_run_backup, args=(full,), daemon=True).start()
    return {"ok": True}

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

@app.post("/api/duplicates/start")
def duplicates_start(r: DupScanReq):
    if STATE.get("dup_job") and STATE["dup_job"].get("phase") == "scanning":
        return JSONResponse({"error": "zaten çalışan tarama var"}, status_code=409)
    if r.collection in INTERNAL_COLLS or not cl.collection_exists(r.collection):
        return JSONResponse({"error": f"koleksiyon yok: {r.collection}"}, status_code=404)
    STATE["dup_job"] = {"phase": "starting", "collection": r.collection}
    threading.Thread(target=_run_dup_scan, args=(r,), daemon=True).start()
    return {"ok": True}

@app.get("/api/duplicates/status")
def duplicates_status():
    return STATE.get("dup_job") or {"phase": "idle"}

@app.get("/api/duplicates/report")
def duplicates_report(collection: str):
    f = ROOT / f"data/dup-report-{collection}.json"
    if not f.exists():
        return JSONResponse({"error": "bu koleksiyon için rapor yok — önce tarama başlatın"}, status_code=404)
    return json.loads(f.read_text(encoding="utf-8"))

@app.get("/api/backup/status")
def backup_status():
    files = []
    if BACKUP_DIR.exists():
        for f in sorted(BACKUP_DIR.glob("*.jsonl.gz"), key=lambda f: f.stat().st_mtime, reverse=True):
            files.append({"name": f.name, "mb": round(f.stat().st_size / 1e6, 1),
                          "date": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")})
    return {"job": STATE.get("backup_job") or {"phase": "idle"}, "files": files[:30],
            "keep": BACKUP_KEEP, "auto_max_points": BACKUP_AUTO_MAX_POINTS}

@app.post("/api/collection/import")
async def collection_import(file: UploadFile = File(...), overwrite: bool = False):
    try:
        raw = gzip.decompress(await file.read())
    except Exception as e:
        return JSONResponse({"error": f"dosya gzip olarak açılamadı: {str(e)[:150]}"}, status_code=400)
    lines = [l for l in raw.decode("utf-8", "replace").splitlines() if l.strip()]
    if not lines:
        return JSONResponse({"error": "dosya boş"}, status_code=400)
    try:
        manifest = json.loads(lines[0])
    except Exception:
        return JSONResponse({"error": "ilk satır geçerli bir manifest değil"}, status_code=400)
    if not manifest.get("_manifest"):
        return JSONResponse({"error": "bu dosya Code-Intel export formatında değil (manifest yok)"}, status_code=400)
    collection = manifest["collection"]
    if collection in INTERNAL_COLLS:
        return JSONResponse({"error": "iç sistem koleksiyonu adı kullanılamaz"}, status_code=400)
    if cl.collection_exists(collection):
        if not overwrite:
            return JSONResponse({"error": f'"{collection}" zaten var — üzerine yazmak için overwrite=true gönderin'}, status_code=409)
        cl.delete_collection(collection)

    if manifest.get("default_vector") and not manifest.get("dense_vectors"):
        # iç koleksiyon yedeği (adsız/size-1 vektör) — export '_default' anahtarıyla yazar
        dv = manifest["default_vector"]
        vectors_cfg = models.VectorParams(size=dv["size"], distance=models.Distance(dv["distance"]))
    else:
        vectors_cfg = {k: models.VectorParams(size=vc["size"], distance=models.Distance(vc["distance"]))
                       for k, vc in manifest.get("dense_vectors", {}).items()}
    sparse_names = manifest.get("sparse_vectors", [])
    sparse_cfg = {k: models.SparseVectorParams(modifier=models.Modifier.IDF) for k in sparse_names} if sparse_names else None
    cl.create_collection(collection, vectors_config=vectors_cfg, sparse_vectors_config=sparse_cfg)
    retrieval.ensure_payload_indexes(collection)

    B = 200; pts = []; count = 0
    for line in lines[1:]:
        row = json.loads(line)
        if "_default" in row["vector"]:
            vec = row["vector"]["_default"]   # adsız vektör: düz liste olarak geri yazılır
        else:
            vec = {}
            for k, val in row["vector"].items():
                vec[k] = models.SparseVector(indices=val["indices"], values=val["values"]) if isinstance(val, dict) and val.get("_sparse") else val
        pts.append(models.PointStruct(id=row["id"], vector=vec, payload=row["payload"]))
        if len(pts) >= B:
            cl.upsert(collection, points=pts); count += len(pts); pts = []
    if pts:
        cl.upsert(collection, points=pts); count += len(pts)

    if manifest.get("profile"):
        prof = {k: v for k, v in manifest["profile"].items() if k != "collection"}
        set_profile(collection, **prof)
    return {"ok": True, "collection": collection, "points": count}

# ---------------- ayarlar sayfası için zengin indeks özeti ----------------
def vector_state(collection: str, name: str, total: int) -> dict:
    if total == 0:
        return {"state": "none", "count": 0}
    n = cl.count(collection, count_filter=models.Filter(must=[models.HasVectorCondition(has_vector=name)])).count
    return {"state": "full" if n == total else ("partial" if n > 0 else "none"), "count": n}

@app.get("/api/indexes")
def indexes_get():
    try:
        hist_all = get_history()
        out = []
        for c in cl.get_collections().collections:
            if c.name in INTERNAL_COLLS:
                continue
            info = cl.get_collection(c.name)
            total = info.points_count
            v, sv = info.config.params.vectors, info.config.params.sparse_vectors
            has_dense_cfg = isinstance(v, dict) and "dense" in v
            has_sparse_cfg = isinstance(sv, dict) and "sparse" in sv
            prof = get_profile(c.name)
            hist = hist_all.get(c.name, [])
            latest = hist[0] if hist else {}
            path = prof.get("path") or latest.get("path", "")
            # ucuz doğrulama: yol diskte var mı; profildeki (elle girilmiş/son) yol son
            # GERÇEK reindex'te kullanılan yoldan farklı mı (reindex edilmemiş bir düzeltme mi)
            path_missing = bool(path) and not pathlib.Path(path).exists()
            path_pending = bool(prof.get("path")) and bool(latest.get("path")) and prof.get("path") != latest.get("path")
            out.append({
                "name": c.name,
                "version": prof.get("version", ""),
                # elle düzeltilmiş değer (profil) otomatik tespit edilenden ÖNCELİKLİ —
                # kullanıcı diski/klasörü taşıdığında reindex'e gerek kalmadan düzeltebilsin diye
                "language": prof.get("language") or latest.get("language", ""),
                "priority": prof.get("priority", 0),
                "owner": prof.get("owner", ""),
                "group": prof.get("group", ""),
                "auto_refresh": bool(prof.get("auto_refresh")),
                "patterns": prof.get("patterns", "*.pas"),
                "path": path,
                "path_missing": path_missing,   # yol şu an diskte yok
                "path_pending": path_pending,   # yol elle değiştirildi ama henüz bu yolla reindex edilmedi
                "points": total,
                "dense": vector_state(c.name, "dense", total) if has_dense_cfg else {"state": "n/a", "count": 0},
                "sparse": vector_state(c.name, "sparse", total) if has_sparse_cfg else {"state": "n/a", "count": 0},
                "last_indexed": latest.get("date"),
            })
        return {"indexes": out}
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=500)

# ---------------- yerel klasör seçim diyaloğu (aynı makinede çalıştığı için) ----------------
@app.get("/api/pick-folder")
def pick_folder():
    ps = ("Add-Type -AssemblyName System.Windows.Forms | Out-Null; "
          "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
          "$f.Description = 'Kaynak klasoru sec'; "
          "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                              capture_output=True, text=True, timeout=120)
        return {"path": out.stdout.strip()}
    except Exception as e:
        return {"path": "", "error": str(e)[:200]}

@app.get("/api/ollama/models")
def ollama_models():
    try:
        d = json.loads(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5).read())
        return {"models": [m["name"] for m in d.get("models", [])]}
    except Exception as e:
        return {"models": [], "error": str(e)[:120]}

# ---------------- donanım tarama + uyumlu Ollama modeli önerisi ----------------
def _ps(cmd: str, timeout: int = 15) -> str:
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                               capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""

@app.get("/api/hardware")
def hardware():
    out = {"cpu": "", "cores": 0, "ram_gb": 0.0, "gpu": "", "vram_gb": 0.0}
    out["cpu"] = _ps("(Get-CimInstance Win32_Processor).Name")
    try:
        out["cores"] = int(_ps("(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors") or 0)
    except ValueError:
        pass
    try:
        b = int(_ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory") or 0)
        out["ram_gb"] = round(b / (1024 ** 3), 1)
    except ValueError:
        pass
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            name, vram_mb = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
            out["gpu"], out["vram_gb"] = name, round(int(vram_mb) / 1024, 1)
    except Exception:
        pass
    if not out["gpu"]:
        out["gpu"] = _ps("(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name")
    return out

GEN_RE = re.compile(r"(\d+(?:\.\d+)?)")

def model_generation(tag: str) -> float:
    """Aile adındaki (etiketten ÖNCEKİ kısım — boyut değil) ilk sayı: qwen3-coder->3,
    qwen2.5-coder->2.5, deepseek-coder-v2->2, gemma4->4. Bulunamazsa 0 (bilinmiyor,
    en düşük öncelik, boyuta göre sıralanır)."""
    family = tag.split(":")[0]
    m = GEN_RE.search(family)
    return float(m.group(1)) if m else 0.0

@app.get("/api/hardware/suggest")
def hardware_suggest():
    hw = hardware()
    try:
        d = json.loads(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5).read())
        # Ollama'nın kendi bildirdiği GERÇEK boyut (byte) kullanılıyor — isimdeki "30b" gibi bir
        # rakamdan tahmin YOK: MoE modellerde bu tür isim-tabanlı tahminler yanıltıcı olabiliyor
        # (örn. qwen3-coder:30b adında "30" geçse de gerçek Q4_K_M dosyası 18.6GB).
        sized = [(m["name"], round(m.get("size", 0) / (1024 ** 3), 1)) for m in d.get("models", [])]
        sized = [(t, gb) for t, gb in sized if gb > 0]
    except Exception as e:
        return {"hardware": hw, "error": str(e)[:150]}
    if not sized:
        return {"hardware": hw, "fast": None, "deep": None, "reason": "Kurulu model bulunamadı."}

    vram = hw["vram_gb"]
    RESERVE_GB = 3.5     # embedding modeli + Qdrant + sistem için ayrılan pay
    budget = max(0.0, vram - RESERVE_GB)
    coder = [(t, gb) for t, gb in sized if "coder" in t.lower()]
    pool = coder or sized   # kodlamaya özel model yoksa genel modellerden seç

    # boyut TEK BAŞINA kalite göstergesi değil (örn. qwen2.5-coder:32b dosyası qwen3-coder:30b'den
    # büyük ama qwen3 daha yeni/güçlü nesil) — önce aynı ailenin en yeni nesli, sonra o nesil
    # içinde boyut kıyaslanıyor.
    by_gen_size = sorted(pool, key=lambda tg: (model_generation(tg[0]), tg[1]), reverse=True)
    top_gen = model_generation(by_gen_size[0][0])
    top_tier = [(t, gb) for t, gb in pool if model_generation(t) == top_gen]

    # derin: en yeni nesildeki en büyük model. VRAM'e tam sığmasa da olur (zaten 30-40sn
    # bekleniyor, Ollama gerekirse kısmen CPU'ya taşırır; sığmayınca sadece yavaşlar).
    deep = max(top_tier, key=lambda tg: tg[1])[0]
    deep_gb = dict(sized)[deep]

    # hızlı: en yeni nesilden VRAM'e sığan en küçük model; o nesilde hiçbiri sığmıyorsa
    # bir alt nesle düş — hâlâ yoksa kurulu en küçük modele düş (hız önceliği, sık çağrılıyor).
    fast = None
    for gen in sorted({model_generation(t) for t, _ in pool}, reverse=True):
        tier_fits = [(t, gb) for t, gb in pool if model_generation(t) == gen and gb <= budget]
        if tier_fits:
            fast = min(tier_fits, key=lambda tg: tg[1])[0]
            break
    if fast is None:
        fast = min(sized, key=lambda tg: tg[1])[0]

    fits_note = "VRAM'e tam sığıyor." if deep_gb <= budget else f"VRAM'e tam sığmıyor (~{deep_gb}GB > ~{budget:.1f}GB bütçe) — kısmen CPU'ya taşabilir, yavaş ama çalışır."
    reason = (f"GPU: {hw['gpu']} (~{vram}GB VRAM, ~{budget:.1f}GB kullanılabilir bütçe, {RESERVE_GB}GB rezerv). "
               f"Kodlamaya özel modeller önceliklendirildi{'' if coder else ' (kurulu böyle bir model bulunamadı, genel modellerden seçildi)'}, "
               f"aralarında en yeni nesil (v{top_gen:g}) tercih edildi. "
               f"Hızlı: o nesilden sığan en küçük model. Derin: o nesildeki en büyük model — {fits_note}")
    return {"hardware": hw, "fast": fast, "deep": deep, "reason": reason,
            "sized": [{"model": t, "gb": gb, "coder": "coder" in t.lower(), "gen": model_generation(t)}
                      for t, gb in sorted(sized, key=lambda tg: -tg[1])]}

# ---------------- arama (birden fazla koleksiyonda birlikte aranabilir) ----------------
# Çekirdek hibrit RRF arama mantığı retrieval.py'de — panel.py VE mcp_server.py ortak kullanır.
class SearchReq(BaseModel):
    q: str; collections: list[str] = ["unidac"]; mode: str = "hybrid"; top_k: int = 8; offset: int = 0
    kind: str = ""      # "" | method | decl | type
    unit: str = ""      # dosya yolu alt-dizesi filtresi (örn. "Providers/")
    rerank: bool = False

@app.post("/api/search")
def search(r: SearchReq):
    result = retrieval.search(r.q, r.collections, r.mode, r.top_k, r.offset,
                              kind=r.kind, unit=r.unit, rerank=r.rerank)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return result

# ---------------- açıklama (cache'li) ----------------
class ExplainReq(BaseModel):
    collection: str; id: int; depth: str = "fast"; model: str = ""

@app.post("/api/explain")
def explain(r: ExplainReq):
    result = retrieval.explain_chunk(r.collection, r.id, r.depth, r.model)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return result

# ---------------- ilişkiler (çağıran/çağırdığı/aynı dosya) ----------------
class RelationsReq(BaseModel):
    collection: str; id: int

@app.post("/api/relations")
def relations(r: RelationsReq):
    result = retrieval.get_relations(r.collection, r.id)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return result

# ---------------- dosyayı/klasörü aç (yalnızca kaynak yolu bu makinede varsa) ----------------
class RevealReq(BaseModel):
    collection: str; id: int; mode: str = "file"   # "file" | "folder" | "browser"

@app.post("/api/reveal")
def reveal(r: RevealReq):
    chunk = retrieval.get_chunk(r.collection, r.id, full_code=False)
    if not chunk:
        return JSONResponse({"error": f"chunk bulunamadı: {r.id}"}, status_code=404)
    prof = get_profile(r.collection)
    src_path = prof.get("path")
    if not src_path:
        return JSONResponse({"error": "bu koleksiyon için kayıtlı bir kaynak klasör yok"}, status_code=404)
    file_path = pathlib.Path(src_path) / chunk["unit"]
    if not file_path.exists():
        return JSONResponse({"error": f"kaynak dosya diskte bulunamadı: {file_path}"}, status_code=404)
    if r.mode == "folder":
        subprocess.run(["explorer.exe", f"/select,{file_path}"])
        return {"ok": True, "path": str(file_path)}
    if r.mode == "browser":
        # native uygulama yerine (os.startfile) tarayıcının kendisinde (panelin
        # bir sekmesinde) göstermek için — dosya boyutu sınırı view-file ile aynı
        if file_path.stat().st_size > 3_000_000:
            return JSONResponse({"error": "dosya çok büyük (>3MB) — panelde önizleme için değil"}, status_code=400)
        return {"content": file_path.read_text(encoding="utf-8", errors="replace"), "path": str(file_path), "name": file_path.name}
    os.startfile(str(file_path))
    return {"ok": True, "path": str(file_path)}

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

def _run_index(r: IndexReq):
    st = STATE["index_job"]
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
        hist_extra = {"new": n_new, "changed": n_changed, "unchanged": n_unchanged, "deleted": len(stale_ids), "language": language}
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
                             | {"code": x["code"][:4000], "doc": x.get("doc", ""), "calls_raw": x.get("calls_raw", [])}))
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
    except Exception as e:
        st.update(phase="error", error=str(e)[:300])

@app.post("/api/index/start")
def index_start(r: IndexReq):
    # TÜM aktif fazlar sayılmalı — "diffing" ve "linking" eksikti ve o fazlardayken
    # ikinci bir iş başlatılıp STATE üzerine yazılabiliyordu (dış analizde bulunan,
    # kodda doğrulanan gerçek yarış durumu).
    if STATE["index_job"] and STATE["index_job"].get("phase") in ("starting", "chunking", "diffing", "embedding", "linking"):
        return JSONResponse({"error": "zaten çalışan iş var"}, status_code=409)
    STATE["index_job"] = {"collection": r.collection, "mode": "+".join(r.vectors), "device": r.device,
                          "total": 0, "done": 0, "rate": 0, "phase": "starting"}
    threading.Thread(target=_run_index, args=(r,), daemon=True).start()
    return {"ok": True}

@app.get("/api/index/status")
def index_status():
    return STATE["index_job"] or {"phase": "idle"}

# ---------------- otomatik artımlı yenileme (watch mode) ----------------
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

@app.on_event("startup")
def _startup():
    # payload index'leri geriye dönük tamamla (idempotent, eski koleksiyonlar için migrasyon)
    try:
        for c in cl.get_collections().collections:
            if c.name not in INTERNAL_COLLS:
                retrieval.ensure_payload_indexes(c.name)
    except Exception:
        pass
    threading.Thread(target=_watch_loop, daemon=True).start()

@app.get("/")
def index_page():
    return FileResponse(ROOT / "static" / "index.html")

# ---------------- RAG sohbet (chat) ----------------
class AskReq(BaseModel):
    q: str; collections: list[str] = ["unidac"]; mode: str = "hybrid"; model: str = "gemma4:12b"; lang: str = "tr"
    # çok turlu sohbet: istemci önceki turları [{"q":..., "a":...}, ...] olarak
    # gönderir — sunucu tarafında oturum TUTULMAZ (stateless), geçmişin sahibi istemcidir
    history: list[dict] = []

def _build_ask_prompt(r: AskReq, hits: list) -> str:
    ctx = "\n\n".join(f"[{i+1}] {h['name']} ({h['unit']} L{h['line_start']}-{h['line_end']}):\n{h['code'][:1100]}"
                      for i, h in enumerate(hits[:5]))
    hist = ""
    for turn in r.history[-4:]:   # bağlam şişmesin: son 4 tur yeter
        hist += f"\nONCEKI SORU: {str(turn.get('q', ''))[:400]}\nONCEKI CEVAP: {str(turn.get('a', ''))[:800]}\n"
    if r.lang == "tr":
        return ("Sen bir Delphi kod tabanı asistanisin. Kullanicinin sorusunu SADECE asagidaki kod parcalarina "
                "dayanarak Turkce yanitla. Dayandigin parcalari [1] [2] gibi isaretle. Kod parcalari soruyu "
                "yanitlamaya yetmiyorsa bunu acikca soyle, uydurma."
                + (f"\n\nONCEKI KONUSMA (baglam icin):{hist}" if hist else "")
                + f"\n\nSORU: {r.q}\n\nKOD PARCALARI:\n{ctx}")
    return ("You are a Delphi codebase assistant. Answer the user's question ONLY from the code snippets "
            "below, citing them as [1] [2]. If they are insufficient, say so plainly."
            + (f"\n\nPREVIOUS CONVERSATION (context):{hist}" if hist else "")
            + f"\n\nQUESTION: {r.q}\n\nSNIPPETS:\n{ctx}")

@app.post("/api/ask")
def ask(r: AskReq):
    sr = search(SearchReq(q=r.q, collections=r.collections, mode=r.mode, top_k=6))
    if isinstance(sr, JSONResponse):
        return sr
    hits = sr["hits"]
    if not hits:
        return {"answer": "Bu soruyla eşleşen kod bulamadım." if r.lang == "tr" else "No matching code found.", "hits": []}
    prompt = _build_ask_prompt(r, hits)
    body = json.dumps({"model": r.model, "prompt": prompt, "stream": False,
                       "options": {"num_predict": 600}, "think": False}).encode()
    t0 = time.time()
    txt = json.loads(urllib.request.urlopen(
        urllib.request.Request(OLLAMA + "/api/generate", body, {"Content-Type": "application/json"}),
        timeout=600).read()).get("response", "").strip()
    return {"answer": txt, "sec": round(time.time() - t0, 1), "model": r.model, "ms_search": sr["ms"],
            "total": sr.get("total", len(hits)), "hits": hits}

@app.post("/api/ask/stream")
def ask_stream(r: AskReq):
    """SSE akışlı RAG sohbet — /api/ask ile aynı arama+prompt yolu, ama Ollama
    yanıtı token token akıtılır: önce `meta` olayı (kaynak hit'ler + arama süresi),
    sonra `data:` satırlarında {"t": parça}, en sonda `done` olayı. Panel arayüzü
    bunu kullanır; eski bloklayan /api/ask REST istemcileri için aynen durur."""
    sr = search(SearchReq(q=r.q, collections=r.collections, mode=r.mode, top_k=6))
    if isinstance(sr, JSONResponse):
        err = bytes(sr.body).decode("utf-8", "replace")
        def gen_err():
            yield f"event: error\ndata: {err}\n\n"
        return StreamingResponse(gen_err(), media_type="text/event-stream")
    hits = sr["hits"]

    def gen():
        meta = {"hits": hits, "ms_search": sr.get("ms"), "total": sr.get("total", len(hits)), "model": r.model}
        yield f"event: meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"
        if not hits:
            msg = "Bu soruyla eşleşen kod bulamadım." if r.lang == "tr" else "No matching code found."
            yield f"data: {json.dumps({'t': msg}, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"
            return
        prompt = _build_ask_prompt(r, hits)
        body = json.dumps({"model": r.model, "prompt": prompt, "stream": True,
                           "options": {"num_predict": 600}, "think": False}).encode()
        t0 = time.time()
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(OLLAMA + "/api/generate", body, {"Content-Type": "application/json"}),
                    timeout=600) as resp:
                for line in resp:
                    if not line.strip():
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    tok = d.get("response", "")
                    if tok:
                        yield f"data: {json.dumps({'t': tok}, ensure_ascii=False)}\n\n"
                    if d.get("done"):
                        break
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)[:200]}, ensure_ascii=False)}\n\n"
            return
        yield f"event: done\ndata: {json.dumps({'sec': round(time.time() - t0, 1)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ---------------- arama sonucu geri bildirimi (👍/👎) ----------------
class FeedbackReq(BaseModel):
    collection: str; id: int; q: str = ""; verdict: str; name: str = ""

@app.post("/api/feedback")
def feedback(r: FeedbackReq):
    result = retrieval.log_feedback(r.collection, r.id, r.q, r.verdict, r.name)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return result

# ---------------- arama analitiği (telemetri panosu) ----------------
@app.get("/api/analytics")
def analytics(limit: int = 5000):
    """_search_log iç koleksiyonundan özet: toplam/son-24s arama sayısı, ortalama
    süre, sıfır-sonuç sorgular (indeks açığı sinyali) ve en sık sorgular."""
    if not cl.collection_exists(SEARCH_LOG_COLL):
        return {"searches": 0, "last24h": 0, "avg_ms": 0, "zero_queries": [], "top_queries": [], "modes": {}}
    entries = []
    next_page = None
    while True:
        batch, next_page = cl.scroll(SEARCH_LOG_COLL, limit=1000, offset=next_page, with_payload=True)
        entries.extend(p.payload for p in batch)
        if next_page is None or len(entries) >= limit:
            break
    now = datetime.now(timezone.utc)
    # feedback kayıtları arama telemetrisinden AYRI sayılır (type=feedback)
    fb_entries = [e for e in entries if e.get("type") == "feedback"]
    entries = [e for e in entries if e.get("type") != "feedback"]
    total, last24, ms_sum = len(entries), 0, 0
    zero_counts: dict[str, int] = {}
    q_counts: dict[str, int] = {}
    modes: dict[str, int] = {}
    for e in entries:
        ms_sum += e.get("ms") or 0
        modes[e.get("mode", "?")] = modes.get(e.get("mode", "?"), 0) + 1
        q = (e.get("q") or "").strip()
        if q:
            q_counts[q] = q_counts.get(q, 0) + 1
            if e.get("zero"):
                zero_counts[q] = zero_counts.get(q, 0) + 1
        try:
            if (now - datetime.fromisoformat(e["date"])).total_seconds() < 86400:
                last24 += 1
        except Exception:
            pass
    top = sorted(q_counts.items(), key=lambda kv: -kv[1])[:20]
    zero = sorted(zero_counts.items(), key=lambda kv: -kv[1])[:20]
    fb_up = sum(1 for e in fb_entries if e.get("verdict") == "up")
    fb_down = [e for e in fb_entries if e.get("verdict") == "down"]
    return {"searches": total, "last24h": last24, "avg_ms": round(ms_sum / total) if total else 0,
            "zero_queries": [{"q": q, "n": n} for q, n in zero],
            "top_queries": [{"q": q, "n": n} for q, n in top],
            "modes": modes,
            "feedback": {"up": fb_up, "down": len(fb_down),
                          "recent_down": [{"q": e.get("q", ""), "name": e.get("name", ""),
                                            "collection": e.get("collection", "")}
                                           for e in sorted(fb_down, key=lambda e: e.get("date", ""), reverse=True)[:10]]}}

@app.get("/settings")
def settings_page():
    return FileResponse(ROOT / "static" / "settings.html")

@app.get("/api")
def api_page():
    return FileResponse(ROOT / "static" / "api.html")

@app.get("/viewer")
def viewer_page():
    return FileResponse(ROOT / "static" / "viewer.html")

_VIEWABLE_EXT = {".md": "md", ".markdown": "md", ".html": "html", ".htm": "html", ".txt": "text"}

@app.get("/api/view-file")
def view_file(path: str):
    p = pathlib.Path(path)
    ext = p.suffix.lower()
    if ext not in _VIEWABLE_EXT:
        return JSONResponse({"error": f"desteklenmeyen dosya türü: {ext or '(uzantısız)'} — sadece .md/.html/.txt"}, status_code=400)
    if not p.exists() or not p.is_file():
        return JSONResponse({"error": f"dosya bulunamadı: {path}"}, status_code=404)
    if p.stat().st_size > 3_000_000:
        return JSONResponse({"error": "dosya çok büyük (>3MB) — panelde önizleme için değil"}, status_code=400)
    return {"content": p.read_text(encoding="utf-8", errors="replace"), "type": _VIEWABLE_EXT[ext], "name": p.name}

# ---------------- MCP tool test uçları ----------------
# Bu uçlar mcp_server.py'deki @mcp.tool() fonksiyonlarını DOĞRUDAN çağırır (aynı
# kod yolu, kopya yok) — sadece stdio yerine tarayıcıdan/REST üzerinden test
# edilebilmelerini sağlar. Bir MCP client'ın (Claude Code, Codex CLI, ...)
# göreceğiyle birebir aynı davranış.

class McpSearchReq(BaseModel):
    query: str; collections: list[str] | None = None; mode: str = "hybrid"; top_k: int = 8; offset: int = 0
    kind: str = ""; unit: str = ""; rerank: bool = False

@app.post("/api/mcp/search_code")
def mcp_search_code(r: McpSearchReq):
    return mcp_server.search_code(r.query, r.collections, r.mode, r.top_k, r.offset,
                                   kind=r.kind, unit=r.unit, rerank=r.rerank)

class McpChunkReq(BaseModel):
    collection: str; id: int

@app.post("/api/mcp/get_chunk")
def mcp_get_chunk(r: McpChunkReq):
    return mcp_server.get_chunk(r.collection, r.id)

class McpExplainReq(BaseModel):
    collection: str; id: int; depth: str = "fast"

@app.post("/api/mcp/explain_chunk")
def mcp_explain_chunk(r: McpExplainReq):
    return mcp_server.explain_chunk(r.collection, r.id, r.depth)

@app.post("/api/mcp/review_code")
def mcp_review_code(r: McpChunkReq):
    return mcp_server.review_code(r.collection, r.id)

class McpDomainReq(BaseModel):
    question: str; domain: str; code_context: str = ""

@app.post("/api/mcp/ask_domain_model")
def mcp_ask_domain_model(r: McpDomainReq):
    return mcp_server.ask_domain_model(r.question, r.domain, r.code_context)

@app.get("/api/mcp/list_domain_models")
def mcp_list_domain_models():
    return mcp_server.list_domain_models()

@app.get("/api/mcp/list_collections")
def mcp_list_collections():
    return mcp_server.list_collections()

@app.post("/api/mcp/get_relations")
def mcp_get_relations(r: McpChunkReq):
    return mcp_server.get_relations(r.collection, r.id)

class McpSimilarReq(BaseModel):
    collection: str; id: int; top_k: int = 8

@app.post("/api/mcp/find_similar")
def mcp_find_similar(r: McpSimilarReq):
    return mcp_server.find_similar(r.collection, r.id, r.top_k)

class McpUnitReq(BaseModel):
    collection: str; unit: str

@app.post("/api/mcp/read_unit")
def mcp_read_unit(r: McpUnitReq):
    return mcp_server.read_unit(r.collection, r.unit)

# ---------------- sembol grafiği uçları ----------------
@app.post("/api/symbols/rebuild")
def symbols_rebuild(collection: str):
    """Var olan bir koleksiyon için sembol grafiğini (yeniden) kurar — normalde
    her indekslemede otomatik kurulur; bu uç eski koleksiyonların migrasyonu için."""
    if collection in INTERNAL_COLLS or not cl.collection_exists(collection):
        return JSONResponse({"error": f"koleksiyon yok: {collection}"}, status_code=404)
    return {"ok": True, **retrieval.build_symbol_graph(collection)}

class McpTypeReq(BaseModel):
    collection: str; type_name: str

@app.post("/api/mcp/get_type_hierarchy")
def mcp_get_type_hierarchy(r: McpTypeReq):
    return mcp_server.get_type_hierarchy(r.collection, r.type_name)

class McpRefsReq(BaseModel):
    collection: str; name: str; top_k: int = 30

@app.post("/api/mcp/find_references")
def mcp_find_references(r: McpRefsReq):
    return mcp_server.find_references(r.collection, r.name, r.top_k)
