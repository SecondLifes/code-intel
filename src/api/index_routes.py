"""İndeksleme/analiz rotaları: /api/index, duplicates, symbols/rebuild, impact."""
import json
import threading

from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from .. import retrieval
    from ..services.common import cl, ROOT, INTERNAL_COLLS, STATE, STATE_LOCK
    from ..services.indexing_svc import IndexReq, DupScanReq, _run_index, _run_dup_scan, migrate_ids_v2, _run_git_update_all
except ImportError:
    import retrieval
    from services.common import cl, ROOT, INTERNAL_COLLS, STATE, STATE_LOCK
    from services.indexing_svc import IndexReq, DupScanReq, _run_index, _run_dup_scan, migrate_ids_v2, _run_git_update_all

router = APIRouter()

@router.post("/api/index/migrate-ids")
def migrate_ids(collection: str):
    """Chunker v2 repo-kimlikli ID'ye GPU'suz migrasyon (bkz. migrate_ids_v2).
    İdempotent — v2'ye geçmiş koleksiyonda moved=0 döner."""
    if collection in INTERNAL_COLLS or not cl.collection_exists(collection):
        return JSONResponse({"error": f"koleksiyon yok: {collection}"}, status_code=404)
    if STATE.get("index_job") and STATE["index_job"].get("phase") in ("starting", "chunking", "diffing", "embedding", "linking"):
        return JSONResponse({"error": "indeksleme sürerken migrasyon yapılamaz"}, status_code=409)
    return {"ok": True, **migrate_ids_v2(collection)}

@router.post("/api/index/start")
def index_start(r: IndexReq):
    # TÜM aktif fazlar sayılmalı — "diffing" ve "linking" eksikti ve o fazlardayken
    # ikinci bir iş başlatılıp STATE üzerine yazılabiliyordu (dış analizde bulunan,
    # kodda doğrulanan gerçek yarış durumu). STATE_LOCK: kontrol+atama ATOMIK
    # olmalı — kilitsizken iki eşzamanlı istek ikisi de kontrolü geçip iki ayrı
    # arka plan thread'i başlatabiliyordu (dış analiz, 4. tur).
    with STATE_LOCK:
        if STATE["index_job"] and STATE["index_job"].get("phase") in ("starting", "chunking", "diffing", "embedding", "linking"):
            return JSONResponse({"error": "zaten çalışan iş var"}, status_code=409)
        STATE["index_job"] = {"collection": r.collection, "mode": "+".join(r.vectors), "device": r.device,
                              "total": 0, "done": 0, "rate": 0, "phase": "starting"}
    threading.Thread(target=_run_index, args=(r,), daemon=True).start()
    return {"ok": True}

@router.get("/api/index/status")
def index_status():
    return STATE["index_job"] or {"phase": "idle"}

@router.post("/api/duplicates/start")
def duplicates_start(r: DupScanReq):
    if r.collection in INTERNAL_COLLS or not cl.collection_exists(r.collection):
        return JSONResponse({"error": f"koleksiyon yok: {r.collection}"}, status_code=404)
    with STATE_LOCK:
        # 4. tur — dış analiz: yalnız "scanning" kontrol ediliyordu, "starting"
        # (meta toplama bitene kadarki ilk faz, bkz. _run_dup_scan) SAYILMIYORDU
        # — bu, index_start'ta daha önce bulunup düzeltilen AYNI eksik-faz
        # deseniydi (dış analiz burada da yakaladı).
        if STATE.get("dup_job") and STATE["dup_job"].get("phase") in ("starting", "scanning"):
            return JSONResponse({"error": "zaten çalışan tarama var"}, status_code=409)
        STATE["dup_job"] = {"phase": "starting", "collection": r.collection}
    threading.Thread(target=_run_dup_scan, args=(r,), daemon=True).start()
    return {"ok": True}

@router.get("/api/duplicates/status")
def duplicates_status():
    return STATE.get("dup_job") or {"phase": "idle"}

@router.get("/api/duplicates/report")
def duplicates_report(collection: str):
    f = ROOT / f"data/dup-report-{collection}.json"
    if not f.exists():
        return JSONResponse({"error": "bu koleksiyon için rapor yok — önce tarama başlatın"}, status_code=404)
    return json.loads(f.read_text(encoding="utf-8"))

@router.get("/api/impact")
def impact(collection: str, base: str = "", head: str = "HEAD"):
    result = retrieval.analyze_impact(collection, base, head)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return result

# ---------------- Tümünü Güncelle (git pull + reindex, kaynak=git olan koleksiyonlar) ----------------
@router.post("/api/git-update-all")
def git_update_all():
    with STATE_LOCK:
        if STATE.get("git_update_job") and STATE["git_update_job"].get("phase") == "running":
            return JSONResponse({"error": "zaten çalışan bir güncelleme var"}, status_code=409)
        if STATE.get("index_job") and STATE["index_job"].get("phase") in ("starting", "chunking", "diffing", "embedding", "linking"):
            return JSONResponse({"error": "indeksleme sürerken toplu güncelleme başlatılamaz"}, status_code=409)
        STATE["git_update_job"] = {"phase": "starting"}
    threading.Thread(target=_run_git_update_all, daemon=True).start()
    return {"ok": True}

@router.get("/api/git-update-status")
def git_update_status():
    return STATE.get("git_update_job") or {"phase": "idle"}

# ---------------- sembol grafiği uçları ----------------
@router.post("/api/symbols/rebuild")
def symbols_rebuild(collection: str):
    """Var olan bir koleksiyon için sembol grafiğini (yeniden) kurar — normalde
    her indekslemede otomatik kurulur; bu uç eski koleksiyonların migrasyonu için."""
    if collection in INTERNAL_COLLS or not cl.collection_exists(collection):
        return JSONResponse({"error": f"koleksiyon yok: {collection}"}, status_code=404)
    return {"ok": True, **retrieval.build_symbol_graph(collection)}
