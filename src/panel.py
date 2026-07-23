"""Code-Intel Yönetim Paneli v1 — FastAPI arka ucu.
Çalıştır:  .venv/Scripts/python.exe -m uvicorn src.panel:app --port 8500
Özellikler: hibrit arama (dense+BM25/RRF), CPU/GPU seçimi, klasörden yeni
indeksleme (chunk→embed), Ollama model seçimi, koleksiyon yönetimi.
"""
import json, pathlib, subprocess, sys, threading, time, urllib.request, uuid
from datetime import datetime, timezone

import onnxruntime as ort
ort.preload_dlls()

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from fastembed import TextEmbedding, SparseTextEmbedding
from qdrant_client import QdrantClient, models

ROOT = pathlib.Path(__file__).resolve().parent.parent
QDRANT, OLLAMA = "http://127.0.0.1:6333", "http://127.0.0.1:11434"   # "localhost" yerine 127.0.0.1: Windows'ta IPv6->IPv4 fallback her istekte ~2sn gecikme yaratıyordu (ölçüldü, doğrulandı)
HISTORY_COLL = "_index_history"    # indeksleme geçmişi
PROFILE_COLL = "_index_profiles"   # koleksiyon başına TEK nokta (versiyon gibi kullanıcı alanları) — hepsi Qdrant'ın kendisinde, ayrı bir dosya yok
INTERNAL_COLLS = {HISTORY_COLL, PROFILE_COLL}
STATE = {"index_job": None}
_dense = {}          # device -> TextEmbedding
_sparse = None

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
        cols = []
        for c in cl.get_collections().collections:
            if c.name in INTERNAL_COLLS:
                continue
            info = cl.get_collection(c.name)
            v = info.config.params.vectors
            vecs = list(v.keys()) if isinstance(v, dict) else (["default"] if v else [])
            sv = info.config.params.sparse_vectors
            svecs = list(sv.keys()) if isinstance(sv, dict) else []
            cols.append({"name": c.name, "points": info.points_count, "vectors": vecs + [f"{s}(sparse)" for s in svecs]})
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

# ---------------- indeks profili (versiyon gibi kullanıcı alanları) ----------------
class ProfileReq(BaseModel):
    collection: str; version: str = ""

@app.get("/api/profile")
def profile_get(collection: str):
    return get_profile(collection)

@app.post("/api/profile")
def profile_set(r: ProfileReq):
    set_profile(r.collection, version=r.version)
    return {"ok": True}

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
            out.append({
                "name": c.name,
                "version": prof.get("version", ""),
                "language": latest.get("language") or prof.get("language", ""),
                "path": latest.get("path", ""),
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

# ---------------- arama (birden fazla koleksiyonda birlikte aranabilir) ----------------
class SearchReq(BaseModel):
    q: str; collections: list[str] = ["unidac"]; mode: str = "hybrid"; top_k: int = 8

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

@app.post("/api/search")
def search(r: SearchReq):
    t0 = time.time()
    dv = list(dense_model("gpu" if "CUDAExecutionProvider" in ort.get_available_providers() else "cpu")
              .embed([f"query: {r.q}"]))[0].tolist()
    sv = list(sparse_model().query_embed(r.q))[0]
    sq = models.SparseVector(indices=sv.indices.tolist(), values=sv.values.tolist())
    per_coll_limit = max(25, r.top_k * 3)
    by_coll, errors = {}, {}
    for c in r.collections:
        try:
            by_coll[c] = _search_one(c, dv, sq, r.mode, per_coll_limit)
        except Exception as e:
            # örn. seçilen koleksiyonda "dense"/"sparse" adlı vektör yok (eski/farklı şema) —
            # o koleksiyonu atla, diğerlerinde arama devam etsin.
            errors[c] = str(e)[:200]
    if not by_coll:
        return JSONResponse({"error": "Hiçbir seçili koleksiyonda arama yapılamadı: " + json.dumps(errors, ensure_ascii=False)}, status_code=400)

    if len(by_coll) == 1:
        # tek koleksiyon (ya seçilen tek buydu, ya da diğerleri hata verdi): Qdrant'ın kendi
        # (doğrudan karşılaştırılabilir) skoru korunur
        chosen = [(c, h) for c, pts in by_coll.items() for h in pts][:r.top_k]
    else:
        # birden fazla koleksiyon: skorlar aralarında karşılaştırılabilir değil (farklı
        # indeksler, farklı skor dağılımları) — bu yüzden RANK'e göre RRF ile birleştiriliyor
        K = 60
        scored = [(c, h, 1.0 / (K + rank + 1)) for c, pts in by_coll.items() for rank, h in enumerate(pts)]
        scored.sort(key=lambda t: t[2], reverse=True)
        chosen = [(c, h) for c, h, _ in scored[:r.top_k]]

    return {"ms": int((time.time() - t0) * 1000), "hits": [
        {"collection": c, "score": round(h.score, 3), "id": h.id,
         **{k: h.payload.get(k) for k in ("lib", "unit", "kind", "name", "line_start", "line_end")},
         "code": h.payload.get("code", "")[:1800], "tr": h.payload.get("tr")} for c, h in chosen]}

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
    path: str = ""                    # boşsa: kayıtlı kaynak veya mevcut chunk dosyası kullanılır
    lib: str = ""                     # boşsa: collection adı
    collection: str = "unidac"
    vectors: list[str] = ["dense", "sparse"]   # bu çalıştırmada hesaplanacak vektör türleri
    device: str = "gpu"                        # gpu | cpu (yalnız dense için)

def _run_index(r: IndexReq):
    st = STATE["index_job"]
    try:
        lib = r.lib or r.collection
        jsonl = ROOT / f"data/chunks-{r.collection}.jsonl"
        prev = get_history(r.collection).get(r.collection, [])
        src_path = r.path or (prev[0]["path"] if prev else "")
        if not src_path:
            raise RuntimeError("kaynak klasör yok — bir yol verin")

        # her seferinde yeniden chunk'la — chunker hızlıdır (~300 dosya/sn), asıl maliyetli
        # kısım embedding, ve hangi dosyaların gerçekten değiştiğini bilmek için önce
        # klasörün GÜNCEL halini görmemiz gerekir. Sadece yol artık diskte yoksa
        # (klasör taşınmış/silinmiş) elimizdeki son chunk dosyasına düşülür.
        if pathlib.Path(src_path).exists():
            st["phase"] = "chunking"
            p = subprocess.run([sys.executable, str(ROOT / "src/chunker.py"), src_path, lib, str(jsonl)],
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

        # mevcut noktaların hash + hangi vektör türlerine sahip oldukları + VEKTÖRLERİN
        # KENDİSİ (with_vectors=True) tek toplu scroll ile — değişmeyen chunk'larda eksik
        # vektör türü eklenirken diğer türü yeniden hesaplamak yerine olduğu gibi geri
        # yazabilelim (tek tek set_payload/update_vectors çağrısı YAPMIYORUZ; ölçüldü,
        # ~2 sn/çağrı — 25K nokta için saatler sürerdi. Bunun yerine her değişen/eksik
        # nokta için TEK bir tam upsert yapılıyor, ihtiyaç duyulmayan vektör türü buradan
        # olduğu gibi kopyalanıyor).
        # GERÇEK vektör varlığı Qdrant'ın kendi vektör deposundan okunuyor (with_vectors=True) —
        # kendi yazacağımız bir "has_dense/has_sparse" bayrağına GÜVENMİYORUZ, çünkü bu özellikten
        # önce oluşturulmuş koleksiyonlarda (örn. unidac) böyle bir alan hiç yazılmamış olurdu ve
        # yanlışlıkla "vektör yok" sanılırdı — doğrulandı.
        old = {}
        if exists:
            next_page = None
            while True:
                batch, next_page = cl.scroll(r.collection, limit=10000, offset=next_page,
                                              with_payload=["hash"], with_vectors=True)
                for p_ in batch:
                    old[p_.id] = {"hash": p_.payload.get("hash"), "vector": p_.vector or {}}
                if next_page is None:
                    break

        # kaynakta artık bulunmayan (silinmiş/yeniden adlandırılmış) eski noktalar
        stale_ids = [pid for pid in old if pid not in row_by_id]
        if stale_ids:
            cl.delete(r.collection, points_selector=models.PointIdsList(points=stale_ids))

        plan = []          # (row, pid, need_dense, need_sparse, before_dense, before_sparse)
        n_new = n_changed = n_unchanged = 0
        for pid, x in row_by_id.items():
            o = old.get(pid)
            is_new = o is None
            changed = is_new or o["hash"] != x["hash"]
            had_dense = (not is_new) and ("dense" in o["vector"])
            had_sparse = (not is_new) and ("sparse" in o["vector"])
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
        if not plan:
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
            pts = []
            for (x, pid, need_dense, need_sparse, before_dense, before_sparse), dv, sv in zip(b, dvs, svs):
                vec = {}
                if need_dense and dv is not None:
                    vec["dense"] = dv.tolist()
                elif before_dense:
                    vec["dense"] = old[pid]["vector"]["dense"]     # değişmedi — olduğu gibi yeniden yaz
                if need_sparse and sv is not None:
                    vec["sparse"] = models.SparseVector(indices=sv.indices.tolist(), values=sv.values.tolist())
                elif before_sparse:
                    vec["sparse"] = old[pid]["vector"]["sparse"]
                pts.append(models.PointStruct(
                    id=pid, vector=vec,
                    payload={k: x[k] for k in ("lib", "unit", "kind", "name", "line_start", "line_end", "hash")}
                             | {"code": x["code"][:4000]}))
            cl.upsert(r.collection, points=pts)   # her batch TEK çağrı — hem yeni hem değişen noktalar için
            st.update(done=i + len(b), rate=round((i + len(b)) / (time.time() - t0), 1))
        record_history(r.collection, src_path, r.vectors, len(rows), extra=hist_extra)
        st.update(phase="done", sec=round(time.time() - t0, 1))
    except Exception as e:
        st.update(phase="error", error=str(e)[:300])

@app.post("/api/index/start")
def index_start(r: IndexReq):
    if STATE["index_job"] and STATE["index_job"].get("phase") in ("starting", "chunking", "embedding"):
        return JSONResponse({"error": "zaten çalışan iş var"}, status_code=409)
    STATE["index_job"] = {"collection": r.collection, "mode": "+".join(r.vectors), "device": r.device,
                          "total": 0, "done": 0, "rate": 0, "phase": "starting"}
    threading.Thread(target=_run_index, args=(r,), daemon=True).start()
    return {"ok": True}

@app.get("/api/index/status")
def index_status():
    return STATE["index_job"] or {"phase": "idle"}

@app.get("/")
def index_page():
    return FileResponse(ROOT / "static" / "index.html")

# ---------------- RAG sohbet (chat) ----------------
class AskReq(BaseModel):
    q: str; collections: list[str] = ["unidac"]; mode: str = "hybrid"; model: str = "gemma4:12b"; lang: str = "tr"

@app.post("/api/ask")
def ask(r: AskReq):
    sr = search(SearchReq(q=r.q, collections=r.collections, mode=r.mode, top_k=6))
    if isinstance(sr, JSONResponse):
        return sr
    hits = sr["hits"]
    if not hits:
        return {"answer": "Bu soruyla eşleşen kod bulamadım." if r.lang == "tr" else "No matching code found.", "hits": []}
    ctx = "\n\n".join(f"[{i+1}] {h['name']} ({h['unit']} L{h['line_start']}-{h['line_end']}):\n{h['code'][:1100]}"
                      for i, h in enumerate(hits[:5]))
    if r.lang == "tr":
        prompt = ("Sen bir Delphi kod tabanı asistanisin. Kullanicinin sorusunu SADECE asagidaki kod parcalarina "
                  "dayanarak Turkce yanitla. Dayandigin parcalari [1] [2] gibi isaretle. Kod parcalari soruyu "
                  f"yanitlamaya yetmiyorsa bunu acikca soyle, uydurma.\n\nSORU: {r.q}\n\nKOD PARCALARI:\n{ctx}")
    else:
        prompt = ("You are a Delphi codebase assistant. Answer the user's question ONLY from the code snippets "
                  f"below, citing them as [1] [2]. If they are insufficient, say so plainly.\n\nQUESTION: {r.q}\n\nSNIPPETS:\n{ctx}")
    body = json.dumps({"model": r.model, "prompt": prompt, "stream": False,
                       "options": {"num_predict": 600}, "think": False}).encode()
    t0 = time.time()
    txt = json.loads(urllib.request.urlopen(
        urllib.request.Request(OLLAMA + "/api/generate", body, {"Content-Type": "application/json"}),
        timeout=600).read()).get("response", "").strip()
    return {"answer": txt, "sec": round(time.time() - t0, 1), "model": r.model, "ms_search": sr["ms"], "hits": hits}

@app.get("/settings")
def settings_page():
    return FileResponse(ROOT / "static" / "settings.html")
