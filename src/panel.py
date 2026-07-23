"""Code-Intel Yönetim Paneli — FastAPI arka ucu.
Çalıştır:  .venv/Scripts/python.exe -m uvicorn src.panel:app --port 8500
"""
import glob, json, os, pathlib, subprocess, sys, threading, time, urllib.request

import onnxruntime as ort
ort.preload_dlls()

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

ROOT = pathlib.Path(__file__).resolve().parent.parent
QDRANT = "http://localhost:6333"
OLLAMA = "http://localhost:11434"
STATE = {"index_job": None}  # {lib,total,done,rate,phase,error}

app = FastAPI(title="Code-Intel Panel")
_model = None
def model():
    global _model
    if _model is None:
        _model = TextEmbedding("intfloat/multilingual-e5-large", cuda=True)
    return _model

cl = QdrantClient(QDRANT, timeout=60)

# ---------- sağlık ----------
@app.get("/api/health")
def health():
    out = {"qdrant": False, "ollama": False, "gpu": False, "collections": []}
    try:
        cols = cl.get_collections().collections
        out["qdrant"] = True
        out["collections"] = [{"name": c.name, "points": cl.get_collection(c.name).points_count} for c in cols]
    except Exception: pass
    try:
        urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3); out["ollama"] = True
    except Exception: pass
    try:
        out["gpu"] = "CUDAExecutionProvider" in (model().model.model.get_providers() if _model else ort.get_available_providers())
    except Exception: pass
    return out

# ---------- arama ----------
class SearchReq(BaseModel):
    q: str
    collection: str = "unidac"
    top_k: int = 8

@app.post("/api/search")
def search(r: SearchReq):
    qv = list(model().embed([f"query: {r.q}"]))[0]
    t0 = time.time()
    hits = cl.query_points(r.collection, query=qv.tolist(), limit=r.top_k, with_payload=True).points
    return {"ms": int((time.time()-t0)*1000), "hits": [
        {"score": round(h.score, 3), "id": h.id, **{k: h.payload.get(k) for k in ("lib","unit","kind","name","line_start","line_end")},
         "code": h.payload.get("code","")[:1800], "tr": h.payload.get("tr")} for h in hits]}

# ---------- açıklama (katmanlı: fast=gemma4, deep=qwen3.6; cache=payload) ----------
class ExplainReq(BaseModel):
    collection: str; id: int; depth: str = "fast"   # fast|deep

@app.post("/api/explain")
def explain(r: ExplainReq):
    pt = cl.retrieve(r.collection, ids=[r.id], with_payload=True)[0]
    cache_key = "tr_deep" if r.depth == "deep" else "tr"
    if pt.payload.get(cache_key):
        return {"cached": True, "text": pt.payload[cache_key]}
    mdl = "qwen3.6" if r.depth == "deep" else "gemma4:12b"
    prompt = ("Asagidaki Delphi metodunun ne yaptigini Turkce acikla. "
              + ("Derinlemesine: mantik akisi, kenar durumlar, olasi riskler. " if r.depth=="deep" else "2-4 cumle, net ve sade. ")
              + f"\n\n{pt.payload.get('code','')}")
    body = json.dumps({"model": mdl, "prompt": prompt, "stream": False,
                       "options": {"num_predict": 500}, "think": False}).encode()
    req = urllib.request.Request(OLLAMA + "/api/generate", body, {"Content-Type": "application/json"})
    t0 = time.time()
    txt = json.loads(urllib.request.urlopen(req, timeout=600).read()).get("response", "").strip()
    cl.set_payload(r.collection, payload={cache_key: txt}, points=[r.id])   # kalıcı cache
    return {"cached": False, "model": mdl, "sec": round(time.time()-t0,1), "text": txt}

# ---------- indeksleme işi ----------
class IndexReq(BaseModel):
    jsonl: str = "data/chunks-unidac.jsonl"; collection: str = "unidac"

def _run_index(jsonl: str, coll: str):
    st = STATE["index_job"]
    try:
        rows = [json.loads(l) for l in open(ROOT/jsonl, encoding="utf-8")]
        st.update(total=len(rows), phase="embedding")
        if not cl.collection_exists(coll):
            cl.create_collection(coll, vectors_config=models.VectorParams(size=1024, distance=models.Distance.COSINE))
        t0 = time.time(); B = 128
        for i in range(0, len(rows), B):
            b = rows[i:i+B]
            vecs = list(model().embed([f"passage: {x['unit']} {x['name']}\n{x['code'][:2000]}" for x in b]))
            cl.upsert(coll, points=[models.PointStruct(
                id=int(x["id"][:12], 16), vector=v.tolist(),
                payload={k: x[k] for k in ("lib","unit","kind","name","line_start","line_end","hash")} | {"code": x["code"][:4000]}
            ) for x, v in zip(b, vecs)])
            st.update(done=i+len(b), rate=round((i+len(b))/(time.time()-t0), 1))
        st.update(phase="done", sec=round(time.time()-t0, 1))
    except Exception as e:
        st.update(phase="error", error=str(e)[:300])

@app.post("/api/index/start")
def index_start(r: IndexReq):
    if STATE["index_job"] and STATE["index_job"].get("phase") not in (None, "done", "error"):
        return JSONResponse({"error": "zaten çalışan iş var"}, status_code=409)
    STATE["index_job"] = {"collection": r.collection, "total": 0, "done": 0, "rate": 0, "phase": "starting"}
    threading.Thread(target=_run_index, args=(r.jsonl, r.collection), daemon=True).start()
    return {"ok": True}

@app.get("/api/index/status")
def index_status():
    return STATE["index_job"] or {"phase": "idle"}

# ---------- UI ----------
@app.get("/")
def index_page():
    return FileResponse(ROOT / "static" / "index.html")
