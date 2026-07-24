"""Arama/RAG rotaları: /api/search, explain, relations, reveal, ask(+stream), feedback, analytics."""
import json
import os
import pathlib
import subprocess
import time
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

try:
    from .. import retrieval
    from ..services.common import cl, OLLAMA, SEARCH_LOG_COLL
    from ..services.profiles import get_profile
except ImportError:
    import retrieval
    from services.common import cl, OLLAMA, SEARCH_LOG_COLL
    from services.profiles import get_profile

router = APIRouter()

# ---------------- arama (birden fazla koleksiyonda birlikte aranabilir) ----------------
# Çekirdek hibrit RRF arama mantığı retrieval.py'de — panel.py VE mcp_server.py ortak kullanır.
class SearchReq(BaseModel):
    q: str; collections: list[str] = ["unidac"]; mode: str = "hybrid"; top_k: int = 8; offset: int = 0
    kind: str = ""      # "" | method | decl | type
    unit: str = ""      # dosya yolu alt-dizesi filtresi (örn. "Providers/")
    rerank: bool = False

@router.post("/api/search")
def search(r: SearchReq):
    result = retrieval.search(r.q, r.collections, r.mode, r.top_k, r.offset,
                              kind=r.kind, unit=r.unit, rerank=r.rerank)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return result

# ---------------- açıklama (cache'li) ----------------
class ExplainReq(BaseModel):
    collection: str; id: int; depth: str = "fast"; model: str = ""

@router.post("/api/explain")
def explain(r: ExplainReq):
    result = retrieval.explain_chunk(r.collection, r.id, r.depth, r.model)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return result

# ---------------- ilişkiler (çağıran/çağırdığı/aynı dosya) ----------------
class RelationsReq(BaseModel):
    collection: str; id: int

@router.post("/api/relations")
def relations(r: RelationsReq):
    result = retrieval.get_relations(r.collection, r.id)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return result

# ---------------- dosyayı/klasörü aç (yalnızca kaynak yolu bu makinede varsa) ----------------
class RevealReq(BaseModel):
    collection: str; id: int; mode: str = "file"   # "file" | "folder" | "browser"

@router.post("/api/reveal")
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

# ---------------- yanıt önbelleği ----------------
# Aynı soru + koleksiyon seti + model için LLM'i yeniden çalıştırmamak (30-60 sn
# tasarruf). YALNIZCA geçmişsiz (ilk tur) sorular önbelleklenir — çok turlu
# yanıtlar konuşma bağlamına bağlıdır, önbellekten dönmesi yanlış olur. 7 günden
# eski kayıtlar bayat sayılır (indeks bu arada değişmiş olabilir).
import uuid as _uuid
ANSWER_TTL_SEC = 7 * 24 * 3600

def _ans_key(r) -> str:
    return str(_uuid.uuid5(_uuid.NAMESPACE_DNS,
        f"ans|{r.model}|{r.lang}|{r.mode}|{','.join(sorted(r.collections))}|{r.q.strip().lower()}"))

def _ans_get(r) -> dict | None:
    if r.history:
        return None
    try:
        if not cl.collection_exists(retrieval.ANSWER_COLL):
            return None
        pts = cl.retrieve(retrieval.ANSWER_COLL, ids=[_ans_key(r)], with_payload=True)
        if not pts:
            return None
        pl = pts[0].payload
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(pl["date"])).total_seconds()
        return pl if age < ANSWER_TTL_SEC else None
    except Exception:
        return None

def _ans_put(r, answer: str, hits: list, total: int):
    if r.history or not answer:
        return
    try:
        if not cl.collection_exists(retrieval.ANSWER_COLL):
            from qdrant_client import models as _m
            cl.create_collection(retrieval.ANSWER_COLL,
                vectors_config=_m.VectorParams(size=1, distance=_m.Distance.DOT))
        from qdrant_client import models as _m
        cl.upsert(retrieval.ANSWER_COLL, points=[_m.PointStruct(id=_ans_key(r), vector=[0.0],
            payload={"answer": answer, "hits": hits[:6], "total": total, "model": r.model,
                     "date": datetime.now(timezone.utc).isoformat()})])
    except Exception:
        pass

@router.post("/api/ask")
def ask(r: AskReq):
    cached = _ans_get(r)
    if cached:
        return {"answer": cached["answer"], "cached": True, "model": cached.get("model"),
                "total": cached.get("total"), "hits": cached.get("hits", [])}
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
    _ans_put(r, txt, hits, sr.get("total", len(hits)))
    return {"answer": txt, "sec": round(time.time() - t0, 1), "model": r.model, "ms_search": sr["ms"],
            "total": sr.get("total", len(hits)), "hits": hits}

@router.post("/api/ask/stream")
def ask_stream(r: AskReq):
    """SSE akışlı RAG sohbet — /api/ask ile aynı arama+prompt yolu, ama Ollama
    yanıtı token token akıtılır: önce `meta` olayı (kaynak hit'ler + arama süresi),
    sonra `data:` satırlarında {"t": parça}, en sonda `done` olayı. Panel arayüzü
    bunu kullanır; eski bloklayan /api/ask REST istemcileri için aynen durur.
    Önbellekli yanıtlar tek parça halinde anında akar (cached=true)."""
    cached = _ans_get(r)
    if cached:
        def gen_cached():
            meta = {"hits": cached.get("hits", []), "ms_search": 0,
                    "total": cached.get("total"), "model": cached.get("model"), "cached": True}
            yield f"event: meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'t': cached['answer']}, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {\"sec\": 0, \"cached\": true}\n\n"
        return StreamingResponse(gen_cached(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})
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
        full = []   # akan yanıt biriktirilir — sonda önbelleğe yazmak için
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
                        full.append(tok)
                        yield f"data: {json.dumps({'t': tok}, ensure_ascii=False)}\n\n"
                    if d.get("done"):
                        break
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)[:200]}, ensure_ascii=False)}\n\n"
            return
        _ans_put(r, "".join(full).strip(), hits, sr.get("total", len(hits)))
        yield f"event: done\ndata: {json.dumps({'sec': round(time.time() - t0, 1)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ---------------- derin araştırma modu (Sıra 8) ----------------
# Tek atımlık RAG'in üstü: get_context_pack ile ana sembolün TAM kodu + çağrı/tip/
# unit bağlamı toplanır, derin modelle sentezlenir; adımlar SSE ile UI'da görünür.
class ResearchReq(BaseModel):
    q: str; collections: list[str] = ["unidac"]; model: str = ""; lang: str = "tr"
    token_budget: int = 6000

@router.post("/api/research/stream")
def research_stream(r: ResearchReq):
    mdl = r.model or retrieval._CFG.get("deep_model", "qwen3.6")

    def gen():
        yield f"event: step\ndata: {json.dumps({'step': 'arama + bağlam paketi hazırlanıyor'}, ensure_ascii=False)}\n\n"
        pack = retrieval.get_context_pack(r.q, r.collections, r.token_budget)
        if "error" in pack:
            yield f"event: error\ndata: {json.dumps(pack, ensure_ascii=False)}\n\n"
            return
        secs = pack.get("sections", [])
        meta_hits = [{"collection": s.get("collection"), "id": s.get("id"), "name": s.get("title"),
                       "unit": s.get("unit", ""), "kind": s["kind"], "line_start": s.get("line_start", 0),
                       "line_end": s.get("line_start", 0), "score": s.get("score", ""),
                       "code": s["text"][:1200], "why": {}}
                      for s in secs if s["kind"] in ("primary", "related")]
        yield ("event: meta\ndata: " + json.dumps({
            "hits": meta_hits, "total": len(secs), "model": mdl,
            "pack": {"sections": len(secs), "used_tokens_est": pack.get("used_tokens_est"),
                      "omitted": len(pack.get("omitted", []))}}, ensure_ascii=False) + "\n\n")
        if not secs:
            yield f"data: {json.dumps({'t': 'Bu soruyla eşleşen kod bulamadım.'}, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"
            return
        ctx = "\n\n".join(f"[S{i+1} — {s['kind']}: {s['title']}]\n{s['text']}" for i, s in enumerate(secs))
        if r.lang == "tr":
            prompt = ("Sen kidemli bir Delphi mimarisin. Asagidaki soruyu YALNIZCA verilen baglam "
                      "bolumlerine dayanarak derinlemesine yanitla: mimari akisi, ilgili siniflar/"
                      "cagri iliskileri ve dikkat edilmesi gerekenleri acikla. Dayandigin bolumleri "
                      "[S1] [S2] gibi isaretle; baglam yetmiyorsa hangi ek bilginin gerektigini soyle, "
                      f"uydurma.\n\nSORU: {r.q}\n\nBAGLAM:\n{ctx}")
        else:
            prompt = ("You are a senior Delphi architect. Answer ONLY from the context sections below, "
                      "covering architecture flow, related types/call relations and caveats; cite as "
                      f"[S1] [S2]. If context is insufficient, say what else is needed.\n\nQUESTION: {r.q}\n\nCONTEXT:\n{ctx}")
        yield f"event: step\ndata: {json.dumps({'step': f'{mdl} ile sentezleniyor'}, ensure_ascii=False)}\n\n"
        body = json.dumps({"model": mdl, "prompt": prompt, "stream": True,
                           "options": {"num_predict": 900}, "think": False}).encode()
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

@router.post("/api/feedback")
def feedback(r: FeedbackReq):
    result = retrieval.log_feedback(r.collection, r.id, r.q, r.verdict, r.name)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return result

# ---------------- arama analitiği (telemetri panosu) ----------------
@router.get("/api/analytics")
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
