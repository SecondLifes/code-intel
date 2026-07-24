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
import subprocess
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
SYMBOL_COLL = "_symbol_graph"   # tip kalıtım/interface kenarları — AYRI koleksiyon,
                                # ana koleksiyon payload'ına liste gömme yaklaşımı
                                # bilinçli olarak KULLANILMIYOR (375K'lık koleksiyonlarda
                                # ölçeklenmez; birleşik analiz kararı)
WORKSPACE_COLL = "_workspaces"  # kayıtlı çalışma alanları (arama tercihleri paketi)
UNITDOC_COLL = "_unit_docs"     # oto-üretilmiş unit dokümantasyonu önbelleği
ANSWER_COLL = "_answer_cache"   # RAG sohbet yanıt önbelleği
OWNER_COLL = "_owners"          # owner kayıt defteri (Owner→Collection modeli)
GROUP_COLL = "_groups"          # group kayıt defteri (fonksiyonel/konu etiketi)
APIKEY_COLL = "_api_keys"       # API anahtarı kayıt defteri (Sıra 11a — rol ayrımlı: read|admin)
JOB_COLL = "_index_jobs"        # kalıcı iş kaydı (Sıra 26) — panel çökerse/yeniden başlarsa devam edebilsin
INTERNAL_COLLS = {"_index_history", "_index_profiles", SEARCH_LOG_COLL, SYMBOL_COLL,
                  WORKSPACE_COLL, UNITDOC_COLL, ANSWER_COLL, OWNER_COLL, GROUP_COLL, APIKEY_COLL, JOB_COLL}

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
    collection, plus a name-match boost. Returns {id: (score, point, why)} —
    `why` sıralama AÇIKLANABİLİRLİĞİ için: bu sonucun dense/sparse kollarındaki
    ham sırası ve aldığı isim-boost çarpanı (UI'da "neden geldi" olarak gösterilir,
    kullanıcı geri bildirimiyle birlikte sıralama ayıklamasının temel verisi)."""
    K = 60
    scores: dict[int, float] = {}
    points: dict[int, object] = {}
    why: dict[int, dict] = {}
    for label, weight, pts in sources:
        for rank, p in enumerate(pts):
            scores[p.id] = scores.get(p.id, 0.0) + weight * (1.0 / (K + rank + 1))
            points[p.id] = p
            why.setdefault(p.id, {})[f"{label}_rank"] = rank + 1
    for pid, p in points.items():
        name_tokens = _tokenize(p.payload.get("name") or "")
        if query_tokens and query_tokens.issubset(name_tokens):
            scores[pid] *= 3.0    # every query word literally in the identifier name
            why[pid]["name_boost"] = 3.0
        elif query_tokens & name_tokens:
            scores[pid] *= 1.5    # partial overlap
            why[pid]["name_boost"] = 1.5
    return {pid: (scores[pid], (collection, points[pid]), why[pid]) for pid in points}

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

def log_feedback(collection: str, id: int, q: str, verdict: str, name: str = "") -> dict:
    """Kullanıcı geri bildirimi (👍/👎) — _search_log koleksiyonuna type=feedback
    kaydı olarak yazılır. Analitik panosu bunları arama sayımından AYRI tutar.
    Bu veri otomatik sıralama eğitimine DOĞRUDAN verilmez (dış analiz uyarısı:
    dar veriyle overfit riski) — önce golden set büyütme için insan onaylı aday
    kaynağı olarak kullanılır."""
    if verdict not in ("up", "down"):
        return {"error": "verdict 'up' veya 'down' olmalı"}
    try:
        if not cl.collection_exists(SEARCH_LOG_COLL):
            cl.create_collection(SEARCH_LOG_COLL,
                vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT))
        cl.upsert(SEARCH_LOG_COLL, points=[models.PointStruct(
            id=str(uuid.uuid4()), vector=[0.0],
            payload={"type": "feedback", "collection": collection, "chunk_id": id,
                     "q": q[:300], "verdict": verdict, "name": name[:200],
                     "date": datetime.now(timezone.utc).isoformat()})])
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)[:200]}

def ensure_payload_indexes(collection: str):
    """unit/kind/name/lang alanlarına keyword payload index — kind/lang filtresi
    ve get_relations'ın unit scroll'u için. İdempotent (varsa hata yutulur)."""
    for field in ("unit", "kind", "name", "lang"):
        try:
            cl.create_payload_index(collection, field_name=field,
                                     field_schema=models.PayloadSchemaType.KEYWORD)
        except Exception:
            pass

def search(q: str, collections: list[str], mode: str = "hybrid", top_k: int = 8, offset: int = 0,
           kind: str = "", unit: str = "", rerank: bool = False, log: bool = True,
           expand: bool = False, diversify: bool = True, lang: str = "") -> dict:
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
    # SORGU GENİŞLETME (opsiyonel, A2 pilotu): Türkçe sorguyu hızlı modelle EN
    # kod terimlerine çevirip yalnız BM25 koluna + isim-boost token'larına ekler
    # (dense zaten çok dilli — ona dokunulmaz). Başarısızlıkta sorgu aynen kalır.
    q_sparse, expanded_kw = q, ""
    if expand:
        try:
            kw = ollama_generate(_CFG.get("fast_model", "gemma4:12b"),
                "Asagidaki kod arama sorgusu icin Ingilizce 3-6 teknik anahtar kelime uret "
                "(fonksiyon/kavram adlari). YALNIZCA kelimeleri boslukla ayirip yaz:\n" + q,
                num_predict=40, timeout=30)
            expanded_kw = " ".join(re.findall(r"[A-Za-z0-9_]+", kw))[:120]
            if expanded_kw:
                q_sparse = f"{q} {expanded_kw}"
        except Exception:
            pass
    dv = list(dense_model("gpu" if gpu_available() else "cpu").embed([f"query: {q}"]))[0].tolist()
    sv = list(sparse_model().query_embed(q_sparse))[0]
    sq = models.SparseVector(indices=sv.indices.tolist(), values=sv.values.tolist())
    # Sabit bir üst sınır (offset'e göre BÜYÜMEZ) — aksi halde sayfa 2'de daha
    # fazla aday çekilip `total` sayısı sayfa sayfa değişir (gerçekte test edilip
    # yakalanan bir tutarsızlık: aynı sorgu ilk sayfada total=273, ikinci sayfada
    # total=351 döndürüyordu). 200, bu korpus ölçeğinde ~25 sayfa sayfalama için
    # yeterli ve ek gecikmesi ölçülebilir değil.
    per_coll_limit = max(200, offset + top_k)
    query_tokens = _tokenize(q_sparse)   # genişletilmiş EN terimler isim-boost'a da girer
    flt_conds = []
    if kind:
        flt_conds.append(models.FieldCondition(key="kind", match=models.MatchValue(value=kind)))
    if lang:
        # 'pascal' özel: v1/v2 Pascal payload'ında lang alanı hiç yazılmaz (dil
        # tablosu Pascal'ı kapsamıyor) — bu yüzden "IsEmpty" ile eşleniyor.
        flt_conds.append(models.IsEmptyCondition(is_empty=models.PayloadField(key="lang"))
                         if lang.lower() == "pascal" else
                         models.FieldCondition(key="lang", match=models.MatchValue(value=lang.lower())))
    flt = models.Filter(must=flt_conds) if flt_conds else None

    # Koleksiyon önceliği (yıldız) yalnızca birden fazla koleksiyon birlikte
    # arandığında anlamlıdır — tek koleksiyonda hepsi aynı çarpanı alır, sıralama
    # değişmez, bu yüzden gereksiz Qdrant çağrısından kaçınmak için atlanır.
    priority_boost = {c: 1.0 + 0.08 * get_collection_priority(c) for c in collections} if len(collections) > 1 else {}

    all_scored: dict[tuple, tuple] = {}   # (collection, id) -> (score, (collection, point))
    all_why: dict[tuple, dict] = {}       # (collection, id) -> sıralama açıklaması
    errors = {}
    for c in collections:
        try:
            sources = _search_one(c, dv, sq, mode, per_coll_limit, flt)
        except Exception as e:
            errors[c] = str(e)[:200]
            continue
        fused = _fuse_collection(c, sources, query_tokens)
        boost = priority_boost.get(c, 1.0)
        for pid, (score, cp, w) in fused.items():
            all_scored[(c, pid)] = (score * boost, cp)
            if boost != 1.0:
                w["priority_boost"] = round(boost, 2)
            all_why[(c, pid)] = w
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
            for i, (_s, (c_, p)) in enumerate(pool):
                prob = 1.0 / (1.0 + math.exp(-rr[i]))
                all_why.setdefault((c_, p.id), {})["rerank_prob"] = round(prob, 3)
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

    # MMR-lite çeşitlilik: ilk pencerede tek dosyanın baskınlığını yumuşat —
    # aynı unit'ten en fazla 3 sonuç ilk 24 pozisyonda kalır, fazlası aşağı iner
    # (dedup sonrası bile tek dosya ilk sayfayı doldurabiliyordu). Sıra korunur,
    # sonuç ATILMAZ; eval ile doğrulandı (isim-boost'lu ilk isabetler etkilenmez).
    if diversify and ranked:
        MAX_PER_UNIT, WINDOW = 3, 24
        head_list, tail_list, per_unit = [], [], {}
        for item in ranked:
            u = item[1][1].payload.get("unit")
            if len(head_list) < WINDOW and per_unit.get(u, 0) >= MAX_PER_UNIT:
                tail_list.append(item)
            else:
                head_list.append(item)
                per_unit[u] = per_unit.get(u, 0) + 1
        ranked = head_list + tail_list

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
            **({"expanded": expanded_kw} if expanded_kw else {}),
            "hits": [
        {"collection": c, "score": round(fscore, 4), "id": h.id,
         **{k: h.payload.get(k) for k in ("lib", "unit", "kind", "name", "line_start", "line_end", "doc", "lang")},
         "code": h.payload.get("code", "")[:1800], "tr": h.payload.get("tr"),
         "why": all_why.get((c, h.id), {})} for fscore, (c, h) in page]}

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

def propose_edit(collection: str, id: int, instruction: str, model: str = "") -> dict:
    """Sıra 11c — YALNIZ-GÖSTER agentic edit: bir chunk + doğal-dilde talimat alır,
    Ollama'dan unified diff (`--- / +++ / @@`) üretir. HİÇBİR dosyaya YAZMAZ, kaynak
    diskine ASLA dokunmaz, indeksi DEĞİŞTİRMEZ — yalnızca "bu değişiklik nasıl
    görünürdü" önerisi döner; uygulamak (varsa) tamamen çağıran ajanın/insanın
    sorumluluğu. get_chunk(full_code=True) ile TAM kod kullanılır (huge/kırpık
    chunk'larda bile diskten tam hâli okunur) — kesik koda göre üretilen bir diff
    yanlış satır/bağlamla eşleşirdi."""
    ch = get_chunk(collection, id, full_code=True)
    if ch is None:
        return {"error": f"chunk bulunamadı: {id}"}
    if not instruction or not instruction.strip():
        return {"error": "instruction boş olamaz"}
    mdl = model or _CFG.get("deep_model", "qwen3.6")
    code = ch.get("code", "")
    unit = ch.get("unit", "")
    prompt = (
        "Asagidaki Delphi/Pascal kod parcasi icin istenen degisikligi UYGULA ve "
        "SADECE unified diff formatinda (--- eski\\n+++ yeni\\n@@ ... @@ satirlariyla) "
        "cikti ver. Aciklama, giris cumlesi, kod bloğu isaretleyici (```) veya baska "
        "hicbir metin EKLEME — yalniz diff. Satir numaralarini ORIJINAL koda gore ver. "
        "Yalnizca istenen degisikligi yap, alakasiz bicimlendirme/yeniden duzenleme YAPMA.\n\n"
        f"DOSYA: {unit} (satir {ch.get('line_start')}-{ch.get('line_end')})\n"
        f"ISTENEN DEGISIKLIK: {instruction.strip()}\n\n"
        f"MEVCUT KOD:\n{code}")
    t0 = time.time()
    diff = ollama_generate(mdl, prompt, num_predict=1200)
    return {"id": id, "collection": collection, "unit": unit, "name": ch.get("name"),
            "line_start": ch.get("line_start"), "line_end": ch.get("line_end"),
            "instruction": instruction.strip(), "model": mdl, "sec": round(time.time() - t0, 1),
            "diff": diff, "note": "Bu yalnızca bir ÖNERİ — hiçbir dosya değiştirilmedi/yazılmadı."}

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
             **{k: p.payload.get(k) for k in ("lib", "unit", "kind", "name", "line_start", "line_end", "doc", "lang")},
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

# ---------------- sembol grafiği (kalıtım / interface kenarları) ----------------
# Delphi tip bildirimi: "TFoo = class(TBar, IBaz)" / "IX = interface(IBase)".
# "class of TFoo" (metaclass) ve "class helper for ..." bilerek dışlanır.
_TYPE_DECL_RE = re.compile(
    r"(\w+)\s*=\s*(?:packed\s+)?(class|interface|object)\b(?!\s*(?:of|helper)\b)"
    r"\s*(?:sealed\b|abstract\b)?\s*(?:\(([^)]*)\))?", re.I)

def _symbol_edge_id(collection: str, child: str, parent: str, kind: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{collection}|{child}|{parent}|{kind}"))

def _ensure_symbol_coll():
    if not cl.collection_exists(SYMBOL_COLL):
        cl.create_collection(SYMBOL_COLL, vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT))
    for field in ("src_collection", "child_name", "parent_name", "edge"):
        try:
            cl.create_payload_index(SYMBOL_COLL, field_name=field,
                                     field_schema=models.PayloadSchemaType.KEYWORD)
        except Exception:
            pass

def build_symbol_graph(collection: str, st: dict | None = None) -> dict:
    """Koleksiyondaki 'type' chunk'larının KOD payload'ından kalıtım/interface
    kenarlarını çıkarır ve _symbol_graph iç koleksiyonuna yazar. _link_call_graph
    gibi kaynak dosyalara ihtiyaç duymaz, idempotenttir: önce bu koleksiyonun
    eski kenarları silinir, sonra taze kenarlar yazılır. İsim-tabanlı çözümleme —
    parent adı koleksiyonda bir type chunk'ına denk gelirse parent_id bağlanır,
    gelmezse (örn. RTL/harici sınıf: TObject, TComponent) parent_id null kalır
    ama kenar yine kaydedilir (hiyerarşi harici köke kadar izlenebilir)."""
    _ensure_symbol_coll()
    # tip adı -> chunk id çözümleme indeksi + kenar çıkarımı tek taramada
    type_ids: dict[str, list] = {}
    edges = []   # (child, parent, edge_kind, unit, child_chunk_id)
    n_types = 0
    next_page = None
    while True:
        batch, next_page = cl.scroll(collection, limit=5000, offset=next_page,
            with_payload=["code", "unit", "kind", "name", "lang", "extends"],
            scroll_filter=models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="type"))]))
        for p in batch:
            lang = p.payload.get("lang")   # yoksa Pascal (v1/v2 Pascal payload'ında bu alan hiç yok)
            if lang:
                # ÇOK DİLLİ (Sıra 10): chunker zaten extends listesini çıkarmış —
                # burada regex YOK. Sözleşme Pascal'la aynı: ilk öğe kalıtım
                # (inherits), kalanlar interface (implements) — dil-özel çıkarıcılar
                # (chunker.py:_extract_extends) bu sırayı üretecek şekilde yazıldı.
                child = p.payload.get("name") or ""
                plist = p.payload.get("extends") or []
                if not child or not plist:
                    if child:
                        n_types += 1
                        type_ids.setdefault(child.lower(), []).append(p.id)
                    continue
                n_types += 1
                type_ids.setdefault(child.lower(), []).append(p.id)
                for i, parent in enumerate(plist):
                    # Rust'ta gerçek sınıf kalıtımı YOK — yalnız trait implementasyonu
                    # var; "impl Trait for Tip" HER ZAMAN implements'tir, ilk-öğe=
                    # inherits kuralı (Pascal/Java/C# için doğru) burada yanlış
                    # sınıflandırma yapardı (canlı testte fark edildi).
                    edge = "implements" if lang == "rust" else ("inherits" if i == 0 else "implements")
                    edges.append((child, parent, edge, p.payload.get("unit"), p.id))
                continue
            code = p.payload.get("code", "")
            m = _TYPE_DECL_RE.search(code[:400])
            if not m:
                continue
            child, decl_kind, parents = m.group(1), m.group(2).lower(), m.group(3)
            n_types += 1
            type_ids.setdefault(child.lower(), []).append(p.id)
            if parents:
                plist = [x.strip() for x in parents.split(",") if x.strip()]
                for i, parent in enumerate(plist):
                    # class'ta ilk ebeveyn kalıtım, kalanlar interface; interface'te hepsi kalıtım
                    edge = "inherits" if (decl_kind != "class" or i == 0) else "implements"
                    edges.append((child, parent, edge, p.payload.get("unit"), p.id))
        if next_page is None:
            break
    # ---- uses kenarları (chunker v2 unithead chunk'larından; unit-düzeyi bağımlılık) ----
    uses_edges = []   # (child_unit_path, child_unit_name, used_name)
    next_page = None
    while True:
        batch, next_page = cl.scroll(collection, limit=5000, offset=next_page,
            with_payload=["unit", "name", "uses"],
            scroll_filter=models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchValue(value="unithead"))]))
        for p in batch:
            for used in (p.payload.get("uses") or []):
                uses_edges.append((p.payload.get("unit"), p.payload.get("name") or "", used, p.id))
        if next_page is None:
            break

    if st is not None:
        st.update(phase="symbols", total=len(edges) + len(uses_edges), done=0)
    # bu koleksiyonun eski kenarlarını temizle (idempotency)
    cl.delete(SYMBOL_COLL, points_selector=models.Filter(must=[
        models.FieldCondition(key="src_collection", match=models.MatchValue(value=collection))]))
    B = 500
    pts = []
    for child, parent, edge, unit, child_id in edges:
        parent_ids = type_ids.get(parent.lower(), [])
        pts.append(models.PointStruct(
            id=_symbol_edge_id(collection, child.lower(), parent.lower(), edge), vector=[0.0],
            payload={"src_collection": collection, "edge": edge,
                     "child_name": child.lower(), "child_display": child, "child_id": child_id,
                     "parent_name": parent.lower(), "parent_display": parent,
                     "parent_id": parent_ids[0] if parent_ids else None,
                     "unit": unit}))
        if len(pts) >= B:
            cl.upsert(SYMBOL_COLL, points=pts); pts = []
    for unit_path, unit_name, used, chunk_id in uses_edges:
        pts.append(models.PointStruct(
            id=_symbol_edge_id(collection, f"{unit_path}", used.lower(), "uses"), vector=[0.0],
            payload={"src_collection": collection, "edge": "uses",
                     "child_name": unit_name.lower(), "child_display": unit_name,
                     "child_id": chunk_id, "unit": unit_path,
                     "parent_name": used.lower(), "parent_display": used, "parent_id": None}))
        if len(pts) >= B:
            cl.upsert(SYMBOL_COLL, points=pts); pts = []
    if pts:
        cl.upsert(SYMBOL_COLL, points=pts)
    if st is not None:
        st.update(done=len(edges) + len(uses_edges))
    return {"types_seen": n_types, "edges": len(edges), "uses_edges": len(uses_edges)}

def get_unit_deps(collection: str, unit: str) -> dict:
    """Unit-düzeyi bağımlılıklar (chunker v2 uses kenarlarından): `uses` (bu
    dosyanın kullandığı unit'ler) ve `used_by` (bu unit'i uses'ına yazan dosyalar).
    `unit` tam göreli yol ("Core/Utils.pas") ya da unit adı ("Utils") olabilir.
    Kenarlar indekslemede tazelenir; eski (v2 öncesi indekslenmiş) koleksiyonlarda
    reindex yapılana kadar boş döner."""
    if not cl.collection_exists(SYMBOL_COLL):
        return {"error": "sembol grafiği henüz kurulmamış"}
    stem = pathlib.Path(unit).stem.lower()
    coll_f = models.FieldCondition(key="src_collection", match=models.MatchValue(value=collection))
    uses_f = models.FieldCondition(key="edge", match=models.MatchValue(value="uses"))
    out_edges = _edge_scroll([coll_f, uses_f,
        models.FieldCondition(key="child_name", match=models.MatchValue(value=stem))], limit=300)
    if "/" in unit or "\\" in unit:   # tam yol verildiyse yola göre daralt
        out_edges = [e for e in out_edges if e.get("unit") == unit.replace("\\", "/")] or out_edges
    in_edges = _edge_scroll([coll_f, uses_f,
        models.FieldCondition(key="parent_name", match=models.MatchValue(value=stem))], limit=300)
    return {"unit": unit, "collection": collection,
            "uses": sorted({e["parent_display"] for e in out_edges}),
            "used_by": sorted({(e.get("unit") or e["child_display"]) for e in in_edges}),
            "note": "unit-düzeyi graf; uses listeleri kaynak dosyalardaki bildirimlerden gelir"}

def _edge_scroll(flt_must: list, limit: int = 500) -> list:
    out, next_page = [], None
    while True:
        batch, next_page = cl.scroll(SYMBOL_COLL, limit=min(limit, 1000), offset=next_page,
                                      with_payload=True, scroll_filter=models.Filter(must=flt_must))
        out.extend(p.payload for p in batch)
        if next_page is None or len(out) >= limit:
            break
    return out[:limit]

def get_type_hierarchy(collection: str, type_name: str) -> dict:
    """Bir tipin kalıtım zinciri: ancestors (yukarı, köke doğru), descendants
    (doğrudan + bir seviye torun), implements (bu tipin uyguladığı interface'ler),
    implementers (bu interface'i uygulayan sınıflar). Kenarlar build_symbol_graph
    tarafından indeksleme sırasında yazılır; isim-tabanlıdır (overload/scope
    çözümlemesi yok). parent_id null ise tip korpus DIŞINDA demektir (örn. TObject)."""
    if not cl.collection_exists(SYMBOL_COLL):
        return {"error": "sembol grafiği henüz kurulmamış — bir koleksiyonu yeniden indeksleyin veya /api/symbols/rebuild çağırın"}
    bare = type_name.split(".")[-1].lower()
    coll_f = models.FieldCondition(key="src_collection", match=models.MatchValue(value=collection))

    ancestors, cur, seen = [], bare, set()
    while cur and cur not in seen and len(ancestors) < 12:
        seen.add(cur)
        e = _edge_scroll([coll_f, models.FieldCondition(key="child_name", match=models.MatchValue(value=cur)),
                          models.FieldCondition(key="edge", match=models.MatchValue(value="inherits"))], limit=1)
        if not e:
            break
        ancestors.append({"name": e[0]["parent_display"], "chunk_id": e[0].get("parent_id"),
                          "in_corpus": e[0].get("parent_id") is not None})
        cur = e[0]["parent_name"]

    def children_of(name: str, limit: int = 40):
        return [{"name": e["child_display"], "chunk_id": e.get("child_id"), "unit": e.get("unit")}
                for e in _edge_scroll([coll_f, models.FieldCondition(key="parent_name", match=models.MatchValue(value=name)),
                                        models.FieldCondition(key="edge", match=models.MatchValue(value="inherits"))], limit)]

    descendants = children_of(bare)
    for d in list(descendants)[:15]:
        d["children"] = children_of(d["name"].lower(), limit=15)

    implements = [{"name": e["parent_display"], "chunk_id": e.get("parent_id")}
                  for e in _edge_scroll([coll_f, models.FieldCondition(key="child_name", match=models.MatchValue(value=bare)),
                                          models.FieldCondition(key="edge", match=models.MatchValue(value="implements"))])]
    implementers = [{"name": e["child_display"], "chunk_id": e.get("child_id"), "unit": e.get("unit")}
                    for e in _edge_scroll([coll_f, models.FieldCondition(key="parent_name", match=models.MatchValue(value=bare)),
                                            models.FieldCondition(key="edge", match=models.MatchValue(value="implements"))])]
    if not (ancestors or descendants or implements or implementers):
        return {"type": type_name, "collection": collection,
                "note": "bu ad için kenar bulunamadı — tip korpusta olmayabilir ya da sembol grafiği bu koleksiyon için henüz kurulmamış olabilir",
                "ancestors": [], "descendants": [], "implements": [], "implementers": []}
    return {"type": type_name, "collection": collection, "ancestors": ancestors,
            "descendants": descendants, "implements": implements, "implementers": implementers}

def find_references(collection: str, name: str, top_k: int = 30) -> dict:
    """Bir sembol adının korpustaki izleri — TAM statik analiz DEĞİL, üç kaynağın
    birleşimi: (1) definitions: bare adı birebir eşleşen chunk'lar (decl/method/type),
    (2) callers: bu tanımların called_by kayıtları (isim-sezgili çağrı grafiği),
    (3) textual: BM25 kelime aramasında adı geçen diğer chunk'lar (yorum/string
    dahil olabilir). Tip ise kalıtım bilgisi için ayrıca get_type_hierarchy çağırın."""
    bare = name.split(".")[-1].lower()
    sr = search(name, [collection], mode="sparse", top_k=max(top_k, 30), log=False)
    if "error" in sr:
        return sr
    definitions, textual = [], []
    for h in sr["hits"]:
        hbare = (h["name"] or "").split(".")[-1].lower()
        entry = {k: h[k] for k in ("id", "name", "unit", "kind", "line_start", "line_end")}
        if hbare == bare:
            definitions.append(entry)
        else:
            textual.append(entry)
    callers, seen_c = [], set()
    for d in definitions:
        if d["kind"] != "method":
            continue
        pts = cl.retrieve(collection, ids=[d["id"]], with_payload=["called_by"])
        for c in (pts[0].payload.get("called_by") or []) if pts else []:
            if c["id"] not in seen_c:
                seen_c.add(c["id"]); callers.append(c)
    return {"name": name, "collection": collection,
            "definitions": definitions[:top_k], "callers": callers[:top_k],
            "textual": textual[:top_k]}

# ---------------- Git provenance + değişiklik etki analizi (Faz 3) ----------------
def git_info(path: str) -> dict:
    """Verilen klasörün içinde bulunduğu git deposunun kimliği: kök, commit,
    branch, kirli mi (commit'lenmemiş değişiklik var mı), origin URL'i.
    Git deposu değilse / git yoksa boş dict — çağıran taraf zarifçe düşer
    (provenance alanları boş kalır, özellik hata üretmez)."""
    try:
        def g(*args):
            r = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=15)
            return r.stdout.strip() if r.returncode == 0 else ""
        root = g("rev-parse", "--show-toplevel")
        if not root:
            return {}
        return {"git_root": root, "commit": g("rev-parse", "HEAD"),
                "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
                "dirty": bool(g("status", "--porcelain")),
                "remote": g("remote", "get-url", "origin")}
    except Exception:
        return {}

def _git_changed_files(git_root: str, base: str, head: str = "HEAD") -> list[str] | None:
    """base..head arası değişen dosyalar (git-köküne göre yollar). head=HEAD ise
    çalışma ağacındaki (commit'lenmemiş + untracked) değişiklikler de dahil —
    başka bir head verilirse yalnız iki revizyon arası fark (revizyon-karşılaştırma
    modu). Hata halinde None."""
    try:
        def g(*args):
            r = subprocess.run(["git", "-C", git_root, *args], capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip()[:200] or "git hatası")
            return r.stdout
        changed: set[str] = set()
        if base:
            changed.update(l.strip() for l in g("diff", "--name-only", base, head).splitlines() if l.strip())
        if head == "HEAD":
            changed.update(l.strip() for l in g("diff", "--name-only", "HEAD").splitlines() if l.strip())
            changed.update(l.strip() for l in g("ls-files", "--others", "--exclude-standard").splitlines() if l.strip())
        return sorted(changed)
    except Exception:
        return None

def analyze_impact(collection: str, base: str = "", head: str = "HEAD", max_items: int = 100) -> dict:
    """Değişiklik etki analizi: kaynak depoda base'ten (verilmezse SON İNDEKSLENEN
    commit'ten) bu yana değişen dosyaları bulur ve indeksteki izdüşümünü çıkarır —
    hangi chunk'lar değişti, onları KİM çağırıyor (called_by), değişen tiplerin
    ALT SINIFLARI neler (sembol grafiği). "Bu değişiklik neyi kırar?" sorusunun
    ilk yanıtı. Kaynak klasör bir git deposu değilse zarifçe hata döner.

    Sınırlar: isim-sezgili çağrı grafiği ve tip kenarları ne kadar iyiyse etki
    listesi o kadar iyidir; satır-düzeyi değil DOSYA-düzeyi değişiklik izlenir."""
    prof = get_profile_payload(collection)
    src = prof.get("path")
    if not src or not pathlib.Path(src).exists():
        return {"error": "koleksiyonun kayıtlı kaynak klasörü yok ya da diskte bulunamadı"}
    gi = git_info(src)
    if not gi:
        return {"error": f"kaynak klasör bir git deposunda değil: {src} (etki analizi git gerektirir)"}
    base_ref = base or prof.get("last_commit") or ""
    if head == "HEAD" and base_ref == gi.get("commit") and not gi.get("dirty"):
        return {"base": base_ref[:12], "head": gi["commit"][:12], "dirty": False,
                "changed_units": [], "impacted_callers": [], "impacted_subtypes": [],
                "note": "son indekslemeden bu yana değişiklik yok"}
    files = _git_changed_files(gi["git_root"], base_ref, head)
    if files is None:
        return {"error": f"git diff başarısız — base/head geçerli mi: {base_ref!r}..{head!r}"}

    # git-kökü göreli yol -> kaynak-kökü göreli unit yolu (indeksin 'unit' alanı)
    src_p, root_p = pathlib.Path(src).resolve(), pathlib.Path(gi["git_root"]).resolve()
    pats = [p.strip().lstrip("*").lower() for p in (prof.get("patterns") or "*.pas").split(",") if p.strip()]
    units = []
    for f in files:
        full = root_p / f
        if not any(f.lower().endswith(suf) for suf in pats):
            continue
        try:
            units.append(full.resolve().relative_to(src_p).as_posix())
        except ValueError:
            continue   # kaynak kökün dışındaki dosya (depoda ama indekslenmeyen bölge)

    changed_chunks, callers, subtypes = [], {}, {}
    changed_ids = set()
    for unit in units:
        pts, _ = cl.scroll(collection, limit=500, with_payload=["name", "kind", "line_start", "called_by"],
            scroll_filter=models.Filter(must=[models.FieldCondition(key="unit", match=models.MatchValue(value=unit))]))
        for p in pts:
            changed_ids.add(p.id)
            changed_chunks.append({"id": p.id, "unit": unit, "name": p.payload.get("name"),
                                    "kind": p.payload.get("kind")})
    for ch in changed_chunks:
        if ch["kind"] == "type":
            h = get_type_hierarchy(collection, (ch["name"] or "").split("=")[0].strip())
            for d in h.get("descendants", []):
                subtypes.setdefault(d["name"], d)
        # called_by tekrar çekmek yerine ilk scroll'da alındı — ama changed_chunks'a
        # koymadık; ucuz ikinci erişim yerine retrieve ile toplu al
    for i in range(0, len(changed_chunks), 500):
        ids = [c["id"] for c in changed_chunks[i:i + 500]]
        for p in cl.retrieve(collection, ids=ids, with_payload=["called_by"]):
            for c in (p.payload.get("called_by") or []):
                if c["id"] not in changed_ids:   # değişen kümenin DIŞINDAN çağıranlar = gerçek etki
                    callers.setdefault(c["id"], c)
    return {"base": (base_ref or "(yok)")[:12], "head": (head if head != "HEAD" else gi["commit"])[:12],
            "branch": gi.get("branch"), "dirty": gi.get("dirty"),
            "changed_units": units[:max_items], "chunks_changed": len(changed_chunks),
            "impacted_callers": list(callers.values())[:max_items],
            "impacted_subtypes": list(subtypes.values())[:max_items],
            "note": "etki listesi isim-sezgili çağrı grafiği + tip kenarlarına dayanır (dosya-düzeyi diff)"}

# ---------------- agent bağlam paketi (get_context_pack) ----------------
def get_context_pack(task: str, collections: list[str] | None = None, token_budget: int = 8000,
                     include_relations: bool = True) -> dict:
    """Bir görev/soru için TOKEN BÜTÇELİ bağlam paketi — CodeIntel'i "arama
    aracı"ndan "ajan bağlam motoruna" çeviren çağrı (üç bağımsız analizin ortak
    #1-2 önerisi). Tek çağrıda: ana sembolün TAM kodu + ikincil eşleşmeler +
    çağıranlar/çağrılanlar + tip hiyerarşisi + unit bağımlılıkları, bütçeye
    sığacak şekilde önem sırasıyla seçilir (bütçe ~4 karakter/token varsayımıyla
    uygulanır). `sections` sırası önem sırasıdır; `omitted` bütçeye sığmayanları
    listeler — ajan gerekirse onları ayrı çağrılarla derinleştirir."""
    colls = collections or [c["name"] for c in list_collections()][:4]
    sr = search(task, colls, "hybrid", top_k=10, rerank=True, log=False)
    if "error" in sr:
        return sr
    hits = sr["hits"]
    if not hits:
        return {"task": task, "sections": [], "note": "eşleşme yok"}
    budget_chars = token_budget * 4
    sections, omitted, used = [], [], 0

    def add(kind: str, title: str, text: str, meta: dict | None = None):
        nonlocal used
        if not text:
            return
        if used + len(text) > budget_chars:
            omitted.append({"kind": kind, "title": title, "chars": len(text)})
            return
        sections.append({"kind": kind, "title": title, **(meta or {}), "text": text})
        used += len(text)

    primary = hits[0]
    full = get_chunk(primary["collection"], primary["id"], full_code=True) or {}
    add("primary", f"{primary['name']} ({primary['unit']})",
        full.get("code", primary["code"]),
        {"collection": primary["collection"], "id": primary["id"], "unit": primary["unit"],
         "line_start": primary["line_start"], "truncated": full.get("truncated", False)})

    if include_relations:
        rel = get_relations(primary["collection"], primary["id"])
        if "error" not in rel:
            callers = rel.get("called_by") or []
            if callers:
                add("callers", f"{primary['name']} çağıranlar",
                    "\n".join(f"- {c['name']} ({c['unit']}:{c.get('line_start')}) id={c['id']}" for c in callers[:12]))
            callees = rel.get("calls") or []
            if callees:
                add("callees", f"{primary['name']} çağırdıkları",
                    "\n".join(f"- {c['name']} ({c['unit']}:{c.get('line_start')}) id={c['id']}" for c in callees[:12]))
        # tip bağlamı: ana sembol bir metotsa sınıfının hiyerarşisi de değerli
        cls = (primary["name"] or "").split(".")[0].strip()
        if cls and cls[:1].upper() == cls[:1]:
            h = get_type_hierarchy(primary["collection"], cls)
            if h.get("ancestors") or h.get("descendants"):
                add("hierarchy", f"{cls} hiyerarşisi",
                    "atalar: " + (" <- ".join(a["name"] for a in h.get("ancestors", [])) or "(yok)") +
                    "\nalt sınıflar: " + (", ".join(d["name"] for d in h.get("descendants", [])[:15]) or "(yok)"))
        ud = get_unit_deps(primary["collection"], primary["unit"])
        if "error" not in ud and (ud.get("uses") or ud.get("used_by")):
            add("unit_deps", f"{primary['unit']} bağımlılıkları",
                "uses: " + (", ".join(ud["uses"][:20]) or "(yok)") +
                f"\nused_by ({len(ud.get('used_by', []))}): " + ", ".join(ud.get("used_by", [])[:15]))

    for h in hits[1:6]:
        add("related", f"{h['name']} ({h['unit']})", h["code"][:1500],
            {"collection": h["collection"], "id": h["id"], "unit": h["unit"], "score": h["score"]})

    return {"task": task, "collections": colls, "token_budget": token_budget,
            "used_tokens_est": used // 4, "sections": sections, "omitted": omitted,
            "guidance": "sections önem sıralıdır; id'lerle get_chunk/get_relations üzerinden derinleşilebilir"}

# ---------------- otomatik unit dokümantasyonu (önbellekli) ----------------
def document_unit(collection: str, unit: str, model: str = "", force: bool = False) -> dict:
    """Bir dosyanın (unit) teknik dokümantasyonunu Markdown olarak üretir ve
    _unit_docs iç koleksiyonunda KALICI önbellekler (aynı unit için tekrar çağrı
    anında döner; force=True yeniden üretir). Girdi: unit'in decl/type chunk'ları
    (public API), unithead uses listesi ve /// doc özetleri. Üretim yereldeki
    Ollama modeliyle yapılır — kod dışarı çıkmaz."""
    key = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{collection}|{unit}"))
    try:
        if not force and cl.collection_exists(UNITDOC_COLL):
            pts = cl.retrieve(UNITDOC_COLL, ids=[key], with_payload=True)
            if pts and pts[0].payload.get("md"):
                return {"cached": True, "unit": unit, "collection": collection,
                        "model": pts[0].payload.get("model"), "md": pts[0].payload["md"]}
    except Exception:
        pass
    ru = read_unit(collection, unit, max_chars=24_000)
    if "error" in ru:
        return ru
    # bağlam: decl/type + doc'lar öncelikli (public yüzey), gövdelerden kısa örnek
    pts, _ = cl.scroll(collection, limit=400, with_payload=["name", "kind", "doc", "uses", "code"],
        scroll_filter=models.Filter(must=[models.FieldCondition(key="unit", match=models.MatchValue(value=unit))]))
    uses = next((p.payload.get("uses") for p in pts if p.payload.get("kind") == "unithead"), None) or []
    decls = [f"- {p.payload.get('name')}" + (f" — {p.payload.get('doc')}" if p.payload.get("doc") else "")
             for p in pts if p.payload.get("kind") in ("decl", "type")][:80]
    mdl = model or _CFG.get("deep_model", "qwen3.6")
    prompt = ("Asagidaki Delphi unit'i icin Markdown teknik dokumantasyon uret (Turkce). "
              "Bolumler: ## Amac (2-3 cumle), ## Bagimliliklar, ## Public API (imza + tek satir aciklama), "
              "## Onemli Tipler, ## Notlar (varsa riskler/desenler). Kod URETME, yalnizca dokumante et. "
              f"Kisa ve teknik yaz.\n\nUNIT: {unit}\nUSES: {', '.join(uses) or '(yok)'}\n"
              f"BILDIRIMLER:\n" + "\n".join(decls) + f"\n\nKOD (kirpilmis):\n{ru['code'][:12000]}")
    t0 = time.time()
    md = ollama_generate(mdl, prompt, num_predict=1200)
    try:
        if not cl.collection_exists(UNITDOC_COLL):
            cl.create_collection(UNITDOC_COLL, vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT))
        cl.upsert(UNITDOC_COLL, points=[models.PointStruct(id=key, vector=[0.0],
            payload={"collection": collection, "unit": unit, "md": md, "model": mdl,
                     "date": datetime.now(timezone.utc).isoformat()})])
    except Exception:
        pass
    return {"cached": False, "unit": unit, "collection": collection, "model": mdl,
            "sec": round(time.time() - t0, 1), "md": md}

def list_collections() -> list[dict]:
    out = []
    for c in cl.get_collections().collections:
        if c.name in INTERNAL_COLLS:
            continue
        info = cl.get_collection(c.name)
        out.append({"name": c.name, "points": info.points_count})
    return out
