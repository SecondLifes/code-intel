"""Code-Intel'in çekirdek arama/açıklama/inceleme mantığı — panel.py (FastAPI web
paneli) VE mcp_server.py (MCP sunucusu) TARAFINDAN ORTAK kullanılır. Hibrit RRF
arama, chunk getirme, Türkçe açıklama ve kod inceleme mantığı burada TEK yerde
yaşar; iki yerde ayrı ayrı yazılmaz.
"""
import json
import time
import urllib.request

import onnxruntime as ort
ort.preload_dlls()

from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient, models

QDRANT, OLLAMA = "http://127.0.0.1:6333", "http://127.0.0.1:11434"
INTERNAL_COLLS = {"_index_history", "_index_profiles"}

_dense: dict[str, TextEmbedding] = {}
_sparse: SparseTextEmbedding | None = None

def dense_model(device: str) -> TextEmbedding:
    if device not in _dense:
        _dense[device] = TextEmbedding("intfloat/multilingual-e5-large", cuda=(device == "gpu"))
    return _dense[device]

def sparse_model() -> SparseTextEmbedding:
    global _sparse
    if _sparse is None:
        _sparse = SparseTextEmbedding("Qdrant/bm25")
    return _sparse

def gpu_available() -> bool:
    return "CUDAExecutionProvider" in ort.get_available_providers()

cl = QdrantClient(QDRANT, timeout=120)

def ollama_generate(model: str, prompt: str, num_predict: int = 500, timeout: int = 600) -> str:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                        "options": {"num_predict": num_predict}, "think": False}).encode()
    return json.loads(urllib.request.urlopen(
        urllib.request.Request(OLLAMA + "/api/generate", body, {"Content-Type": "application/json"}),
        timeout=timeout).read()).get("response", "").strip()

def _search_one(collection: str, dv: list[float], sq, mode: str, limit: int):
    kw = dict(collection_name=collection, limit=limit, with_payload=True)
    if mode == "dense":
        return cl.query_points(query=dv, using="dense", **kw).points
    if mode == "sparse":
        return cl.query_points(query=sq, using="sparse", **kw).points
    return cl.query_points(prefetch=[
        models.Prefetch(query=dv, using="dense", limit=limit),
        models.Prefetch(query=sq, using="sparse", limit=limit)],
        query=models.FusionQuery(fusion=models.Fusion.RRF), **kw).points

def search(q: str, collections: list[str], mode: str = "hybrid", top_k: int = 8) -> dict:
    """Hibrit (dense+sparse+RRF) arama. Birden fazla koleksiyon verilirse, skorlar
    aralarında karşılaştırılamayacağı için RANK'e göre kendi RRF'imizle birleştirilir.
    Uyumsuz bir koleksiyon (örn. dense/sparse şeması yok) sessizce atlanır, diğerleri
    aramaya devam eder."""
    t0 = time.time()
    dv = list(dense_model("gpu" if gpu_available() else "cpu").embed([f"query: {q}"]))[0].tolist()
    sv = list(sparse_model().query_embed(q))[0]
    sq = models.SparseVector(indices=sv.indices.tolist(), values=sv.values.tolist())
    per_coll_limit = max(25, top_k * 3)
    by_coll, errors = {}, {}
    for c in collections:
        try:
            by_coll[c] = _search_one(c, dv, sq, mode, per_coll_limit)
        except Exception as e:
            errors[c] = str(e)[:200]
    if not by_coll:
        return {"error": "Hiçbir seçili koleksiyonda arama yapılamadı: " + json.dumps(errors, ensure_ascii=False)}

    if len(by_coll) == 1:
        chosen = [(c, h) for c, pts in by_coll.items() for h in pts][:top_k]
    else:
        K = 60
        scored = [(c, h, 1.0 / (K + rank + 1)) for c, pts in by_coll.items() for rank, h in enumerate(pts)]
        scored.sort(key=lambda t: t[2], reverse=True)
        chosen = [(c, h) for c, h, _ in scored[:top_k]]

    return {"ms": int((time.time() - t0) * 1000), "hits": [
        {"collection": c, "score": round(h.score, 3), "id": h.id,
         **{k: h.payload.get(k) for k in ("lib", "unit", "kind", "name", "line_start", "line_end", "doc")},
         "code": h.payload.get("code", "")[:1800], "tr": h.payload.get("tr")} for c, h in chosen]}

def get_chunk(collection: str, id: int, full_code: bool = True) -> dict | None:
    """Tek bir chunk'ın TAM kaydını (kısaltılmamış kod dahil) getirir."""
    pts = cl.retrieve(collection, ids=[id], with_payload=True)
    if not pts:
        return None
    p = pts[0]
    out = dict(p.payload)
    if not full_code:
        out["code"] = out.get("code", "")[:1800]
    out["id"] = p.id
    out["collection"] = collection
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

def list_collections() -> list[dict]:
    out = []
    for c in cl.get_collections().collections:
        if c.name in INTERNAL_COLLS:
            continue
        info = cl.get_collection(c.name)
        out.append({"name": c.name, "points": info.points_count})
    return out
