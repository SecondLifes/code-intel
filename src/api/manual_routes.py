"""Yardım/manual sistemi rotaları: üretim (arka plan iş), HTML görüntüleme,
PDF/DOCX dışa aktarma."""
import threading

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

try:
    from .. import manual
    from ..services.common import cl, INTERNAL_COLLS, STATE
except ImportError:
    import manual
    from services.common import cl, INTERNAL_COLLS, STATE

router = APIRouter()


class ManualBuildReq(BaseModel):
    collection: str
    scope: str = ""
    force: bool = False


def _run_manual_build(r: ManualBuildReq):
    job = STATE["manual_job"]
    try:
        result = manual.build_manual(r.collection, r.scope, r.force, st=job)
        if "error" in result:
            job.update(phase="error", error=result["error"])
        else:
            job.update(phase="done")
    except Exception as e:
        job.update(phase="error", error=str(e)[:300])


@router.post("/api/manual/build")
def manual_build(r: ManualBuildReq):
    if r.collection in INTERNAL_COLLS or not cl.collection_exists(r.collection):
        return JSONResponse({"error": f"koleksiyon yok: {r.collection}"}, status_code=404)
    if STATE.get("manual_job") and STATE["manual_job"].get("phase") == "building":
        return JSONResponse({"error": "zaten çalışan bir manual üretimi var"}, status_code=409)
    STATE["manual_job"] = {"phase": "starting", "collection": r.collection}
    threading.Thread(target=_run_manual_build, args=(r,), daemon=True).start()
    return {"ok": True}


@router.get("/api/manual/status")
def manual_status():
    return STATE.get("manual_job") or {"phase": "idle"}


@router.get("/api/manual/exists")
def manual_exists(collection: str):
    return {"exists": manual.load_manual(collection) is not None}


def _run_manual_build_all():
    """"Tümünü Oluştur": TÜM (iç olmayan) koleksiyonlar için tam kapsamlı
    (scope=boş) manual üretir — tek-koleksiyonluk düğmenin aksine kapsam
    daraltma sunmaz, tam koleksiyon işlenir. document_unit zaten önbellekli
    olduğundan bir koleksiyon ikinci kez üretilirse (kod değişmediyse) ucuzdur."""
    job = STATE["manual_all_job"]
    results = []
    try:
        names = [c.name for c in cl.get_collections().collections if c.name not in INTERNAL_COLLS]
        job.update(phase="running", total=len(names), done=0, results=[])
        for i, name in enumerate(names):
            job.update(current=name, done=i, results=results)
            r = manual.build_manual(name, "", False)
            results.append({"collection": name, "ok": "error" not in r,
                            "error": r.get("error", ""), "units": r.get("stats", {}).get("units", 0)})
        job.update(phase="done", done=len(names), results=results)
    except Exception as e:
        job.update(phase="error", error=str(e)[:300], results=results)


@router.post("/api/manual/build-all")
def manual_build_all():
    if STATE.get("manual_all_job") and STATE["manual_all_job"].get("phase") == "running":
        return JSONResponse({"error": "zaten çalışan bir toplu üretim var"}, status_code=409)
    STATE["manual_all_job"] = {"phase": "starting"}
    threading.Thread(target=_run_manual_build_all, daemon=True).start()
    return {"ok": True}


@router.get("/api/manual/build-all-status")
def manual_build_all_status():
    return STATE.get("manual_all_job") or {"phase": "idle"}


@router.get("/manual/{collection}")
@router.get("/manual/{collection}/{page}")
def manual_view(collection: str, page: str = "index"):
    model = manual.load_manual(collection)
    if model is None:
        return HTMLResponse("<h1>Manual henüz üretilmemiş</h1><p>Ayarlar sayfasından bu koleksiyon için "
                            "\"Manual Üret\" düğmesine basın.</p>", status_code=404)
    # nav/cross-link href'leri "{slug}.html" üretir (bkz. manual.render_manual_html) —
    # tarayıcı bunu TAM OLARAK bu path segmentiyle ister; ama render_manual_html
    # bölümü BARE slug'a göre eşliyor (uzantısız) — canlı doğrulamada yakalanan
    # gerçek hata: uzantı burada soyulmazsa HER bölüm sayfası 404 dönüyordu.
    page = page.removesuffix(".html")
    return HTMLResponse(manual.render_manual_html(model, page))


@router.get("/api/manual/export")
def manual_export(collection: str, format: str = "pdf"):
    model = manual.load_manual(collection)
    if model is None:
        return JSONResponse({"error": "bu koleksiyon için manual henüz üretilmemiş"}, status_code=404)
    if format == "docx":
        data = manual.render_manual_docx(model)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"
    elif format == "pdf":
        data = manual.render_manual_pdf(model)
        media = "application/pdf"
        ext = "pdf"
    else:
        return JSONResponse({"error": "format 'pdf' veya 'docx' olmalı"}, status_code=400)
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{collection}-manual.{ext}"'})
