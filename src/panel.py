"""Code-Intel Yönetim Paneli v1 — FastAPI arka ucu.
Çalıştır:  .venv/Scripts/python.exe -m uvicorn src.panel:app --port 8500
Özellikler: hibrit arama (dense+BM25/RRF), CPU/GPU seçimi, klasörden yeni
indeksleme (chunk→embed), Ollama model seçimi, koleksiyon yönetimi.
"""
import json, pathlib, subprocess, sys, threading, time, urllib.request

import onnxruntime as ort
ort.preload_dlls()

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient, models

ROOT = pathlib.Path(__file__).resolve().parent.parent
QDRANT, OLLAMA = "http://localhost:6333", "http://localhost:11434"
STATE = {"index_job": None}
_dense = {}          # device -> TextEmbedding
_sparse = None

def dense_model(device: str):
    if device not in _dense:
        _dense[device] = TextEmbedding("intfloat/multilingual-e5-large", cuda=(device == "gpu"))
    return _dense[device]

def sparse_model():
    global _sparse
    if _sparse is None:
        _sparse = SparseTextEmbedding("Qdrant/bm25")
    return _sparse

cl = QdrantClient(QDRANT, timeout=120)
app = FastAPI(title="Code-Intel Panel")

# ---------------- sağlık / listeler ----------------
@app.get("/api/health")
def health():
    out = {"qdrant": False, "ollama": False, "gpu": "CUDAExecutionProvider" in ort.get_available_providers(), "collections": []}
    try:
        out["collections"] = [{"name": c.name, "points": cl.get_collection(c.name).points_count}
                              for c in cl.get_collections().collections]
        out["qdrant"] = True
    except Exception: pass
    try:
        urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3); out["ollama"] = True
    except Exception: pass
    return out

@app.get("/api/ollama/models")
def ollama_models():
    try:
        d = json.loads(urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5).read())
        return {"models": [m["name"] for m in d.get("models", [])]}
    except Exception as e:
        return {"models": [], "error": str(e)[:120]}

# ---------------- arama ----------------
class SearchReq(BaseModel):
    q: str; collection: str = "unidac"; mode: str = "hybrid"; top_k: int = 8

@app.post("/api/search")
def search(r: SearchReq):
    t0 = time.time()
    dv = list(dense_model("gpu" if "CUDAExecutionProvider" in ort.get_available_providers() else "cpu")
              .embed([f"query: {r.q}"]))[0].tolist()
    sv = list(sparse_model().query_embed(r.q))[0]
    sq = models.SparseVector(indices=sv.indices.tolist(), values=sv.values.tolist())
    kw = dict(collection_name=r.collection, limit=r.top_k, with_payload=True)
    try:
        if r.mode == "dense":
            res = cl.query_points(query=dv, using="dense", **kw)
        elif r.mode == "sparse":
            res = cl.query_points(query=sq, using="sparse", **kw)
        else:
            res = cl.query_points(prefetch=[
                models.Prefetch(query=dv, using="dense", limit=max(25, r.top_k * 3)),
                models.Prefetch(query=sq, using="sparse", limit=max(25, r.top_k * 3))],
                query=models.FusionQuery(fusion=models.Fusion.RRF), **kw)
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=400)
    return {"ms": int((time.time() - t0) * 1000), "hits": [
        {"score": round(h.score, 3), "id": h.id,
         **{k: h.payload.get(k) for k in ("lib", "unit", "kind", "name", "line_start", "line_end")},
         "code": h.payload.get("code", "")[:1800], "tr": h.payload.get("tr")} for h in res.points]}

# ---------------- açıklama (cache'li) ----------------
class ExplainReq(BaseModel):
    collection: str; id: int; depth: str = "fast"; model: str = ""

@app.post("/api/explain")
def explain(r: ExplainReq):
    pt = cl.retrieve(r.collection, ids=[r.id], with_payload=True)[0]
    key = "tr_deep" if r.depth == "deep" else "tr"
    if pt.payload.get(key):
        return {"cached": True, "text": pt.payload[key]}
    mdl = r.model or ("qwen3.6" if r.depth == "deep" else "gemma4:12b")
    prompt = ("Asagidaki Delphi metodunun ne yaptigini Turkce acikla. "
              + ("Derinlemesine: mantik akisi, kenar durumlar, olasi riskler. " if r.depth == "deep"
                 else "2-4 cumle, net ve sade. ") + f"\n\n{pt.payload.get('code','')}")
    body = json.dumps({"model": mdl, "prompt": prompt, "stream": False,
                       "options": {"num_predict": 500}, "think": False}).encode()
    t0 = time.time()
    txt = json.loads(urllib.request.urlopen(
        urllib.request.Request(OLLAMA + "/api/generate", body, {"Content-Type": "application/json"}),
        timeout=600).read()).get("response", "").strip()
    cl.set_payload(r.collection, payload={key: txt}, points=[r.id])
    return {"cached": False, "model": mdl, "sec": round(time.time() - t0, 1), "text": txt}

# ---------------- indeksleme ----------------
class IndexReq(BaseModel):
    path: str = ""            # boşsa: mevcut data/chunks-<collection>.jsonl kullanılır
    lib: str = ""             # boşsa: collection adı
    collection: str = "unidac"
    mode: str = "hybrid"      # hybrid | dense | sparse
    device: str = "gpu"       # gpu | cpu

def _run_index(r: IndexReq):
    st = STATE["index_job"]
    try:
        lib = r.lib or r.collection
        jsonl = ROOT / f"data/chunks-{r.collection}.jsonl"
        if r.path:
            st["phase"] = "chunking"
            p = subprocess.run([sys.executable, str(ROOT / "src/chunker.py"), r.path, lib, str(jsonl)],
                               capture_output=True, text=True, timeout=3600)
            if p.returncode != 0:
                raise RuntimeError("chunker: " + (p.stderr or p.stdout)[-250:])
        if not jsonl.exists():
            raise RuntimeError(f"chunk dosyası yok: {jsonl.name} — klasör yolu verin")
        rows = [json.loads(l) for l in open(jsonl, encoding="utf-8")]
        st.update(total=len(rows), phase="embedding")

        vec_cfg = {"dense": models.VectorParams(size=1024, distance=models.Distance.COSINE)} if r.mode != "sparse" else {}
        sp_cfg = {"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)} if r.mode != "dense" else None
        if cl.collection_exists(r.collection):
            cl.delete_collection(r.collection)
        cl.create_collection(r.collection, vectors_config=vec_cfg, sparse_vectors_config=sp_cfg)

        dm = dense_model(r.device) if r.mode != "sparse" else None
        sm = sparse_model() if r.mode != "dense" else None
        t0 = time.time(); B = 128
        for i in range(0, len(rows), B):
            b = rows[i:i + B]
            texts = [f"passage: {x['unit']} {x['name']}\n{x['code'][:2000]}" for x in b]
            dvs = list(dm.embed(texts)) if dm else [None] * len(b)
            svs = list(sm.embed(texts)) if sm else [None] * len(b)
            pts = []
            for x, dv, sv in zip(b, dvs, svs):
                vec = {}
                if dv is not None: vec["dense"] = dv.tolist()
                if sv is not None: vec["sparse"] = models.SparseVector(indices=sv.indices.tolist(), values=sv.values.tolist())
                pts.append(models.PointStruct(
                    id=int(x["id"][:12], 16), vector=vec,
                    payload={k: x[k] for k in ("lib", "unit", "kind", "name", "line_start", "line_end", "hash")} | {"code": x["code"][:4000]}))
            cl.upsert(r.collection, points=pts)
            st.update(done=i + len(b), rate=round((i + len(b)) / (time.time() - t0), 1))
        st.update(phase="done", sec=round(time.time() - t0, 1))
    except Exception as e:
        st.update(phase="error", error=str(e)[:300])

@app.post("/api/index/start")
def index_start(r: IndexReq):
    if STATE["index_job"] and STATE["index_job"].get("phase") in ("starting", "chunking", "embedding"):
        return JSONResponse({"error": "zaten çalışan iş var"}, status_code=409)
    STATE["index_job"] = {"collection": r.collection, "mode": r.mode, "device": r.device,
                          "total": 0, "done": 0, "rate": 0, "phase": "starting"}
    threading.Thread(target=_run_index, args=(r,), daemon=True).start()
    return {"ok": True}

@app.get("/api/index/status")
def index_status():
    return STATE["index_job"] or {"phase": "idle"}

@app.get("/")
def index_page():
    return FileResponse(ROOT / "static" / "index.html")
