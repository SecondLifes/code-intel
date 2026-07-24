"""Code-Intel'in çekirdek arama/açıklama/inceleme mantığı — panel.py (FastAPI web
paneli) VE mcp_server.py (MCP sunucusu) TARAFINDAN ORTAK kullanılır. Hibrit RRF
arama, chunk getirme, Türkçe açıklama ve kod inceleme mantığı burada TEK yerde
yaşar; iki yerde ayrı ayrı yazılmaz.
"""
import json
import math
import os
import pathlib
import re
import time
import urllib.request
import uuid
from datetime import datetime, timezone

import onnxruntime as ort
ort.preload_dlls()

from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient, models

_ROOT = pathlib.Path(__file__).resolve().parent.parent

def _load_cfg() -> dict:
    try:
        return json.loads((_ROOT / "mcp-config.json").read_text(encoding="utf-8"))
    except Exception:
        return {}

_CFG = _load_cfg()
# Tek yapılandırma kaynağı: env > mcp-config.json > varsayılan.
# (Önceden mcp-config'teki qdrant_url/ollama_url fiilen ETKİSİZDİ — burası sabit
# 127.0.0.1 kullanıyordu; dış analizde yakalanan gerçek bir kopukluk.)
QDRANT = os.environ.get("CODEINTEL_QDRANT_URL") or _CFG.get("qdrant_url") or "http://127.0.0.1:6333"
OLLAMA = os.environ.get("CODEINTEL_OLLAMA_URL") or _CFG.get("ollama_url") or "http://127.0.0.1:11434"
SEARCH_LOG_COLL = "_search_log"
INTERNAL_COLLS = {"_index_history", "_index_profiles", SEARCH_LOG_COLL}

# Cross-encoder reranker: çok dilli (Türkçe sorgu + İngilizce kod çalışır).
# İlk kullanımda (~1.1GB) indirilir, sonra kalıcı önbellekten yüklenir.
RERANK_MODEL = "jinaai/jina-reranker-v2-base-multilingual"
RERANK_POOL = 50    # yalnızca en iyi N aday rerank edilir — kalite/gecikme dengesi
RERANK_PRIOR_K = 5  # füzyon-sırası prior'ının gücü: skor *= K/(K+füzyon_sırası).
                    # Golden set üzerinde grid ile seçildi: K yok=0.678, K=20=0.900,
                    # K=10=0.950, K=5=1.000 MRR — K=5, isim-boost'lu füzyonun zaten
                    # doğru bulduğu sırayı korurken cross-encoder'a yalnızca GÜÇLÜ
                    # kanıt varsa (rank-10 bir adayın öne geçmesi için ~3x olasılık
                    # gerekir) sırayı değiştirme yetkisi bırakır.

_dense: dict[str, TextEmbedding] = {}
_sparse: SparseTextEmbedding | None = None
_reranker = None

def dense_model(device: str) -> TextEmbedding:
    if device not in _dense:
        _dense[device] = TextEmbedding("intfloat/multilingual-e5-large", cuda=(device == "gpu"))
    return _dense[device]

def sparse_model() -> SparseTextEmbedding:
    global _sparse
    if _sparse is None:
        _sparse = SparseTextEmbedding("Qdrant/bm25")
    return _sparse

def reranker():
    global _reranker
    if _reranker is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        try:
            _reranker = TextCrossEncoder(RERANK_MODEL, cuda=gpu_available())
        except Exception:
            _reranker = TextCrossEncoder(RERANK_MODEL)   # cuda başarısızsa CPU'ya düş
    return _reranker

def gpu_available() -> bool:
    return "CUDAExecutionProvider" in ort.get_available_providers()

cl = QdrantClient(QDRANT, timeout=120)

def ollama_generate(model: str, prompt: str, num_predict: int = 500, timeout: int = 600) -> str:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                        "options": {"num_predict": num_predict}, "think": False}).encode()
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(OLLAMA + "/api/generate", body, {"Content-Type": "application/json"}),
        timeout=timeout).read()).get("response", "").strip()

_WORD_RE = re.compile(r"[a-zA-Z0-9]+")

def _tokenize(s: str) -> set[str]:
    """camelCase/PascalCase-aware tokenizer, e.g. 'SplitString' -> {'split','string'}.
    Used to boost hits whose identifier name literally matches the query words —
    plain rank-based RRF alone lets a rare-token BM25 fluke in a short, unrelated
    chunk (e.g. a record decl with a stray comment containing "String") outrank the
    actual named function the user is looking for."""
    if not s:
        return set()
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    return set(_WORD_RE.findall(s.lower()))

def _dense_query(collection: str, dv: list[float], limit: int, flt=None):
    return cl.query_points(collection_name=collection, query=dv, using="dense", limit=limit,
                            with_payload=True, query_filter=flt).points

def _sparse_query(collection: str, sq, limit: int, flt=None):
    return cl.query_points(collection_name=collection, query=sq, using="sparse", limit=limit,
                            with_payload=True, query_filter=flt).points

def _search_one(collection: str, dv: list[float], sq, mode: str, limit: int, flt=None):
    """Returns a list of (source_label, weight, points) for this collection. Dense
    and sparse are always fetched and fused OURSELVES (not via Qdrant's built-in
    FusionQuery) so we can weight them and apply the name-match boost below —
    verified live that dense alone is much cleaner than sparse alone on this corpus
    for natural-language-ish queries, so sparse gets a lower weight in hybrid mode
    rather than being trusted equally."""
    if mode == "dense":
        return [("dense", 1.0, _dense_query(collection, dv, limit, flt))]
    if mode == "sparse":
        return [("sparse", 1.0, _sparse_query(collection, sq, limit, flt))]
    return [("dense", 1.0, _dense_query(collection, dv, limit, flt)),
            ("sparse", 0.6, _sparse_query(collection, sq, limit, flt))]

def _fuse_collection(collection: str, sources, query_tokens: set[str]):
    """Weighted rank-RRF across the given (label, weight, points) sources for ONE
    collection, plus a name-match boost. Returns {id: (score, point)}."""
    K = 60
    scores: dict[int, float] = {}
    points: dict[int, object] = {}
    for _label, weight, pts in sources:
        for rank, p in enumerate(pts):
            scores[p.id] = scores.get(p.id, 0.0) + weight * (1.0 / (K + rank + 1))
            points[p.id] = p
    for pid, p in points.items():
        name_tokens = _tokenize(p.payload.get("name") or "")
        if query_tokens and query_tokens.issubset(name_tokens):
            scores[pid] *= 3.0    # every query word literally in the identifier name
        elif query_tokens & name_tokens:
            scores[pid] *= 1.5    # partial overlap
    return {pid: (scores[pid], (collection, points[pid])) for pid in points}

def get_collection_priority(collection: str) -> int:
    """panel.py'nin _index_profiles'a set_profile ile yazdığı 0-5 yıldız önceliği
    okur. Sadece BİRDEN FAZLA koleksiyonda BİRLİKTE arama yaparken skor
    ağırlıklandırması için anlamlıdır — tek koleksiyonlu aramada etkisizdir
    (koleksiyon içi sıralamayı değiştirmez, sadece koleksiyonlar arası göreli
    ağırlığı etkiler)."""
    try:
        if not cl.collection_exists("_index_profiles"):
            return 0
        pid = str(uuid.uuid5(uuid.NAMESPACE_DNS, collection))
        pts = cl.retrieve("_index_profiles", ids=[pid], with_payload=["priority"])
        return (pts[0].payload.get("priority") or 0) if pts else 0
    except Exception:
        return 0

def _dedup_decl_impl(ranked: list) -> list:
    """Aynı rutinin hem interface bildirimi ("decl") hem gövdesi ("method") ayrı
    sonuç olarak dönebiliyor — kullanıcıya aynı şey iki kez gösterilmiş olur.
    Aday listesinde aynı (koleksiyon, unit, bare isim) için bir "method" varsa
    "decl" kopyası listeden düşürülür; decl'in /// doc'u varsa ve method'unki
    boşsa doc method'a taşınır (bilgi kaybolmasın). "type" chunk'ları etkilenmez."""
    has_method: set[tuple] = set()
    doc_of_decl: dict[tuple, str] = {}
    for _score, (c, p) in ranked:
        bare = (p.payload.get("name") or "").split(".")[-1].lower()
        key = (c, p.payload.get("unit"), bare)
        kind = p.payload.get("kind")
        if kind == "method":
            has_method.add(key)
        elif kind == "decl" and p.payload.get("doc"):
            doc_of_decl[key] = p.payload["doc"]
    out = []
    for score, (c, p) in ranked:
        bare = (p.payload.get("name") or "").split(".")[-1].lower()
        key = (c, p.payload.get("unit"), bare)
        kind = p.payload.get("kind")
        if kind == "decl" and key in has_method:
            continue
        if kind == "method" and not p.payload.get("doc") and key in doc_of_decl:
            p.payload["doc"] = doc_of_decl[key]
        out.append((score, (c, p)))
    return out

def _log_search(q: str, collections: list[str], mode: str, ms: int, total: int,
                rerank: bool, kind: str, unit: str):
    """Arama telemetrisi — _search_log iç koleksiyonuna yazılır (panel Ayarlar >
    Analitik bunu okur). Asla arama akışını bozamaz: her hata yutulur."""
    try:
        if not cl.collection_exists(SEARCH_LOG_COLL):
            cl.create_collection(SEARCH_LOG_COLL,
                vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT))
        cl.upsert(SEARCH_LOG_COLL, points=[models.PointStruct(
            id=str(uuid.uuid4()), vector=[0.0],
            payload={"q": q[:300], "collections": collections, "mode": mode, "ms": ms,
                     "total": total, "zero": total == 0, "rerank": rerank,
                     "kind": kind or "", "unit": unit or "",
                     "date": datetime.now(timezone.utc).isoformat()})])
    except Exception:
        pass

def ensure_payload_indexes(collection: str):
    """unit/kind/name alanlarına keyword payload index — kind filtresi ve
    get_relations'ın unit scroll'u için. İdempotent (varsa hata yutulur)."""
    for field in ("unit", "kind", "name"):
        try:
            cl.create_payload_index(collection, field_name=field,
                                     field_schema=models.PayloadSchemaType.KEYWORD)
        except Exception:
            pass

def search(q: str, collections: list[str], mode: str = "hybrid", top_k: int = 8, offset: int = 0,
           kind: str = "", unit: str = "", rerank: bool = False, log: bool = True) -> dict:
    """Hibrit (dense+sparse, kendi ağırlıklı RRF'imiz + isim-eşleşme boost'u ile
    birleştirilmiş) arama. Birden fazla koleksiyon verilirse aralarında da aynı
    füzyon uygulanır. Uyumsuz bir koleksiyon (örn. dense/sparse şeması yok)
    sessizce atlanır, diğerleri aramaya devam eder.

    kind: "method" | "decl" | "type" — Qdrant tarafında filtrelenir (boş = hepsi).
    unit: dosya yolu alt-dizesi (örn. "Providers/") — aday kümesi üzerinde
    büyük/küçük harf duyarsız filtre (ANN sonrası uygulanır; per_coll_limit=200
    aday içinde arar, korpus genelinde kesin tarama değildir).
    rerank: True ise en iyi RERANK_POOL aday cross-encoder ile yeniden sıralanır
    (ilk çağrıda model indirildiği için yavaş olabilir, sonrası ~yüz ms'ler).
    log: telemetri kaydı (eval koşuları log=False verir, analitiği kirletmesin).

    offset/top_k sayfalama sağlar; `total` (bu çalıştırmada elenmiş aday sayısı,
    ANN arama olduğu için "korpustaki TÜM eşleşme sayısı" değildir) ve `has_more`
    döner."""
    t0 = time.time()
    dv = list(dense_model("gpu" if gpu_available() else "cpu").embed([f"query: {q}"]))[0].tolist()
    sv = list(sparse_model().query_embed(q))[0]
    sq = models.SparseVector(indices=sv.indices.tolist(), values=sv.values.tolist())
    # Sabit bir üst sınır (offset'e göre BÜYÜMEZ) — aksi halde sayfa 2'de daha
    # fazla aday çekilip `total` sayısı sayfa sayfa değişir (gerçekte test edilip
    # yakalanan bir tutarsızlık: aynı sorgu ilk sayfada total=273, ikinci sayfada
    # total=351 döndürüyordu). 200, bu korpus ölçeğinde ~25 sayfa sayfalama için
    # yeterli ve ek gecikmesi ölçülebilir değil.
    per_coll_limit = max(200, offset + top_k)
    query_tokens = _tokenize(q)
    flt = models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value=kind))]) if kind else None

    # Koleksiyon önceliği (yıldız) yalnızca birden fazla koleksiyon birlikte
    # arandığında anlamlıdır — tek koleksiyonda hepsi aynı çarpanı alır, sıralama
    # değişmez, bu yüzden gereksiz Qdrant çağrısından kaçınmak için atlanır.
    priority_boost = {c: 1.0 + 0.08 * get_collection_priority(c) for c in collections} if len(collections) > 1 else {}

    all_scored: dict[tuple, tuple] = {}   # (collection, id) -> (score, (collection, point))
    errors = {}
    for c in collections:
        try:
            sources = _search_one(c, dv, sq, mode, per_coll_limit, flt)
        except Exception as e:
            errors[c] = str(e)[:200]
            continue
        fused = _fuse_collection(c, sources, query_tokens)
        boost = priority_boost.get(c, 1.0)
        for pid, (score, cp) in fused.items():
            all_scored[(c, pid)] = (score * boost, cp)
    if not all_scored:
        return {"error": "Hiçbir seçili koleksiyonda arama yapılamadı: " + json.dumps(errors, ensure_ascii=False)}

    ranked = [(all_scored[k][0], all_scored[k][1])
              for k in sorted(all_scored, key=lambda k: all_scored[k][0], reverse=True)]
    if unit:
        u = unit.lower()
        ranked = [r for r in ranked if u in (r[1][1].payload.get("unit") or "").lower()]
    ranked = _dedup_decl_impl(ranked)

    if rerank and ranked:
        pool = ranked[:RERANK_POOL]
        docs = [f"{p.payload.get('name') or ''}\n{p.payload.get('code', '')[:1200]}" for _s, (_c, p) in pool]
        try:
            rr = list(reranker().rerank(q, docs))
            # Cross-encoder logit'i sigmoid ile (0,1) olasılığa çevrilir, _fuse_collection
            # ile AYNI isim-eşleşme boost'u ve füzyon-sırası prior'ı (RERANK_PRIOR_K)
            # uygulanır. İkisi de eval'de ölçülüp yakalanan GERÇEK gerilemelere karşı:
            # çıplak rerank skoru hem birebir isim eşleşen fonksiyonu aşağı itiyordu
            # (MRR 1.000 -> 0.587) hem de füzyonun 40. sıraya gömdüğü çöp chunk'ları
            # (örn. obfuscated 'OQC0OQC0Q0') öne fırlatabiliyordu. Boost+prior'lı
            # birleşimle golden set MRR'ı 1.000'de kalırken cross-encoder, güçlü kanıt
            # gösterdiği adayları hâlâ öne çekebilir.
            scores = []
            for i, (_s, (_c, p)) in enumerate(pool):
                prob = 1.0 / (1.0 + math.exp(-rr[i]))
                name_tokens = _tokenize(p.payload.get("name") or "")
                if query_tokens and query_tokens.issubset(name_tokens):
                    prob *= 3.0
                elif query_tokens & name_tokens:
                    prob *= 1.5
                prob *= RERANK_PRIOR_K / (RERANK_PRIOR_K + i)
                scores.append(prob)
            order = sorted(range(len(pool)), key=lambda i: scores[i], reverse=True)
            ranked = [pool[i] for i in order] + ranked[len(pool):]
        except Exception as e:
            errors["_rerank"] = str(e)[:200]   # rerank çökerse füzyon sırası korunur

    total = len(ranked)
    page = ranked[offset:offset + top_k]
    ms = int((time.time() - t0) * 1000)
    if log:
        _log_search(q, collections, mode, ms, total, rerank, kind, unit)

    # `score` shown is OUR fused rank score, not the point's raw native score —
    # a hit can come from dense (cosine, 0..1) or sparse (unbounded BM25); showing
    # whichever one happened to be attached to the point object last was a real
    # display bug found while fixing the ranking itself (a hit's shown "score"
    # could jump from ~0.8 to ~18 depending on which source last touched the
    # point dict, even though sort order was already correct).
    return {"ms": ms, "total": total, "has_more": total > offset + top_k, "rerank": bool(rerank),
            "hits": [
        {"collection": c, "score": round(fscore, 4), "id": h.id,
         **{k: h.payload.get(k) for k in ("lib", "unit", "kind", "name", "line_start", "line_end", "doc")},
         "code": h.payload.get("code", "")[:1800], "tr": h.payload.get("tr")} for fscore, (c, h) in page]}

PAYLOAD_CODE_CAP = 4000   # _run_index'in payload'a yazdığı üst sınır — bununla senkron

def get_profile_payload(collection: str) -> dict:
    """_index_profiles'taki profil kaydını okur (panel.py get_profile ile aynı
    veri; retrieval tarafında diskten-tam-kod okuma için gerekir)."""
    try:
        if not cl.collection_exists("_index_profiles"):
            return {}
        pid = str(uuid.uuid5(uuid.NAMESPACE_DNS, collection))
        pts = cl.retrieve("_index_profiles", ids=[pid], with_payload=True)
        return pts[0].payload if pts else {}
    except Exception:
        return {}

def get_chunk(collection: str, id: int, full_code: bool = True) -> dict | None:
    """Tek bir chunk'ın TAM kaydını getirir.

    ÖNEMLİ dürüstlük düzeltmesi: payload'daki kod PAYLOAD_CODE_CAP (4000) ile
    kesilmiş olabilir — eskiden bu fonksiyon adına rağmen kesik kodu "tam" diye
    döndürüyordu (dış analizde yakalandı). Artık: (1) kesikse `truncated: true`
    açıkça işaretlenir; (2) koleksiyonun kayıtlı kaynak klasörü diskte varsa
    gerçek dosyadan line_start..line_end aralığı okunup TAM kod döndürülür
    (`source: "disk"`). Disk yoksa kesik kod + bayrakla yetinilir."""
    pts = cl.retrieve(collection, ids=[id], with_payload=True)
    if not pts:
        return None
    p = pts[0]
    out = dict(p.payload)
    out["id"] = p.id
    out["collection"] = collection
    code = out.get("code", "")
    out["truncated"] = len(code) >= PAYLOAD_CODE_CAP
    out["source"] = "qdrant"
    if full_code and out["truncated"]:
        try:
            src = get_profile_payload(collection).get("path")
            unit, ls, le = out.get("unit"), out.get("line_start"), out.get("line_end")
            if src and unit and ls and le:
                f = pathlib.Path(src) / unit
                if f.exists():
                    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                    out["code"] = "\n".join(lines[ls - 1:le])
                    out["truncated"] = False
                    out["source"] = "disk"
        except Exception:
            pass   # disk okunamazsa kesik kod + truncated bayrağı zaten dönüyor
    if not full_code:
        out["code"] = out.get("code", "")[:1800]
    return out

def explain_chunk(collection: str, id: int, depth: str = "fast", model: str = "") -> dict:
    """Türkçe açıklama — doc yorumu varsa (fast'ta) doğrudan çevirir, yoksa/derin
    modda kodun kendisini analiz eder. Sonuç Qdrant payload'ında kalıcı önbelleklenir."""
    pt = cl.retrieve(collection, ids=[id], with_payload=True)
    if not pt:
        return {"error": f"chunk bulunamadı: {id}"}
    pt = pt[0]
    key = "tr_deep" if depth == "deep" else "tr"
    if pt.payload.get(key):
        return {"cached": True, "text": pt.payload[key]}
    mdl = model or ("qwen3.6" if depth == "deep" else "gemma4:12b")
    doc = pt.payload.get("doc", "")
    if depth == "fast" and doc:
        prompt = ("Asagidaki Ingilizce kod dokumantasyon ozetini dogal, net bir Turkceye cevir. "
                  "Sadece cevrilmis metni yaz, baska aciklama ekleme.\n\n" + doc)
    elif depth == "deep":
        ctx = f"Dokumantasyon ozeti (Ingilizce): {doc}\n\n" if doc else ""
        prompt = ("Asagidaki Delphi metodunun ne yaptigini Turkce acikla. "
                  "Derinlemesine: mantik akisi, kenar durumlar, olasi riskler. "
                  + ctx + pt.payload.get("code", ""))
    else:
        prompt = ("Asagidaki Delphi metodunun ne yaptigini Turkce acikla. 2-4 cumle, net ve sade. "
                  f"\n\n{pt.payload.get('code', '')}")
    t0 = time.time()
    txt = ollama_generate(mdl, prompt)
    cl.set_payload(collection, payload={key: txt}, points=[id])
    return {"cached": False, "model": mdl, "sec": round(time.time() - t0, 1), "text": txt}

def review_chunk(collection: str, id: int, model: str = "") -> dict:
    """İSTEK ÜZERİNE kod incelemesi — Ollama'ya bu kod parçasında hata/risk olup
    olmadığını sorar. Otonom DEĞİL (bir agent açıkça çağırınca çalışır), kod
    ÜRETMEZ (sadece mevcut kodu eleştirir). Sonuç önbelleklenmez (her seferinde
    en güncel model/bağlamla taze inceleme — kod değişmiş olabilir)."""
    pt = cl.retrieve(collection, ids=[id], with_payload=True)
    if not pt:
        return {"error": f"chunk bulunamadı: {id}"}
    pt = pt[0]
    mdl = model or "qwen3.6"
    prompt = ("Asagidaki Delphi kodunu bir kod incelemesi (code review) gozuyle incele. "
              "SADECE gercek/somut sorunlari (bellek sizintisi, null/nil kontrolu eksikligi, "
              "exception guvenligi, kaynak kapatma, mantik hatasi, race condition) rapor et. "
              "Sorun yoksa acikca 'Belirgin bir sorun bulunamadi.' de. Turkce, maddeler halinde, "
              "kisa ve somut yaz — kod URETME, sadece mevcut kodu degerlendir.\n\n"
              f"{pt.payload.get('code', '')}")
    t0 = time.time()
    txt = ollama_generate(mdl, prompt, num_predict=700)
    return {"model": mdl, "sec": round(time.time() - t0, 1), "review": txt}

def get_relations(collection: str, id: int) -> dict:
    """Bir chunk'ın önceden hesaplanmış (indeksleme sırasında panel.py'nin
    _link_call_graph'ı tarafından yazılan) çağrı ilişkilerini döndürür:
    calls (bu chunk'ın çağırdığı adaylar), called_by (bu chunk'ı çağıran adaylar,
    isim-tabanlı sezgiyle çözülmüş — kesin değil, birden fazla aday içerebilir),
    same_unit (aynı dosyadaki diğer chunk'lar — dosya içi gezinme için). Sorgu
    anında HESAPLAMA yapılmaz, hepsi indeksleme sırasında zaten hazırlanmıştır."""
    pts = cl.retrieve(collection, ids=[id], with_payload=["name", "unit", "calls", "called_by"])
    if not pts:
        return {"error": f"chunk bulunamadı: {id}"}
    p = pts[0]
    unit = p.payload.get("unit")
    same_unit_pts, _ = cl.scroll(collection, limit=200, with_payload=["name", "kind", "line_start"],
                                  scroll_filter=models.Filter(must=[
                                      models.FieldCondition(key="unit", match=models.MatchValue(value=unit))]))
    same_unit = sorted(
        ({"id": sp.id, "name": sp.payload.get("name"), "kind": sp.payload.get("kind"),
          "line_start": sp.payload.get("line_start")} for sp in same_unit_pts if sp.id != id),
        key=lambda h: h["line_start"] or 0)
    return {"name": p.payload.get("name"), "unit": unit,
            "calls": p.payload.get("calls") or [], "called_by": p.payload.get("called_by") or [],
            "same_unit": same_unit}

def find_similar(collection: str, id: int, top_k: int = 8) -> dict:
    """Bir chunk'ın kayıtlı dense vektörüyle en benzer diğer chunk'ları bulur
    ("buna benzer başka implementasyon var mı?"). Sorgu vektörü yeniden
    HESAPLANMAZ — Qdrant'ın Query API'sine doğrudan nokta ID'si verilir, kayıtlı
    vektör kullanılır. Chunk'ın kendisi sonuçlardan çıkarılır."""
    pts = cl.retrieve(collection, ids=[id], with_payload=["name"])
    if not pts:
        return {"error": f"chunk bulunamadı: {collection}/{id}"}
    res = cl.query_points(collection_name=collection, query=id, using="dense",
                           limit=top_k + 1, with_payload=True).points
    hits = [{"collection": collection, "score": round(p.score, 4), "id": p.id,
             **{k: p.payload.get(k) for k in ("lib", "unit", "kind", "name", "line_start", "line_end", "doc")},
             "code": p.payload.get("code", "")[:1800]}
            for p in res if p.id != id][:top_k]
    return {"source": {"id": id, "name": pts[0].payload.get("name")}, "hits": hits}

def read_unit(collection: str, unit: str, max_chars: int = 150_000) -> dict:
    """Bir dosyanın (unit) indekslenmiş TÜM chunk'larını satır sırasına dizip
    birleştirilmiş kodunu döndürür — bir agent'ın dosya bütününü tek çağrıda
    görmesi için. Bu bir YAKLAŞIK yeniden kurgudur: chunk'lanmamış aralar (uses
    listesi, global değişkenler vb.) dahil değildir; decl+method birlikte satır
    sırasında dizildiği için interface/implementation akışı korunur."""
    pts = []
    next_page = None
    while True:
        batch, next_page = cl.scroll(collection, limit=500, offset=next_page,
            with_payload=["name", "kind", "line_start", "line_end", "code"],
            scroll_filter=models.Filter(must=[
                models.FieldCondition(key="unit", match=models.MatchValue(value=unit))]))
        pts.extend(batch)
        if next_page is None:
            break
    if not pts:
        return {"error": f"unit bulunamadı: {collection}/{unit} (tam yol bekler, örn. 'Source/Utils.pas')"}
    pts.sort(key=lambda p: p.payload.get("line_start") or 0)
    parts, used, truncated = [], 0, False
    for p in pts:
        code = p.payload.get("code", "")
        if used + len(code) > max_chars:
            truncated = True
            break
        parts.append(f"// [{p.payload.get('kind')}] {p.payload.get('name')} "
                     f"(L{p.payload.get('line_start')}-{p.payload.get('line_end')}, id={p.id})\n{code}")
        used += len(code)
    return {"unit": unit, "collection": collection, "chunks": len(pts), "truncated": truncated,
            "code": "\n\n".join(parts)}

def list_collections() -> list[dict]:
    out = []
    for c in cl.get_collections().collections:
        if c.name in INTERNAL_COLLS:
            continue
        info = cl.get_collection(c.name)
        out.append({"name": c.name, "points": info.points_count})
    return out
