"""Uzak istemci dosya senkronu: bir istemci makinesindeki değişen dosyaları
(oluştur/güncelle/sil/taşı) sunucudaki bir "ayna" (mirror) klasöre yazar.

Bilinçli tasarım: burada YENİ bir indeksleme/chunking/embedding kodu YOK.
Ayna klasör (data/remote_mirrors/<client_id>/...), normal bir koleksiyon
profilinin `path`i olarak POST /api/profile ile kaydedilip auto_refresh=true
yapılırsa, indexing_svc.py'deki MEVCUT _watch_loop mtime değişikliğini görüp
otomatik artımlı yeniden-indeksleme (chunk→diff→embed→upsert, sadece değişen
chunk'lar) zaten tetikliyor. Bu dosyanın tek işi, gelen içeriği güvenle
diske yazmak/silmek/taşımak — indeksleme mekanizması hiç değişmedi.

GÜVENLİK (security-sensitive — bkz. CONTRIBUTING.md): relative_path/client_id
path-traversal'a karşı sıkı doğrulanır. `_safe_path()` şunları REDDEDER:
  - `client_id` alfanümerik/tire/alt-çizgi dışında bir şey içeriyorsa
  - relative_path'te ':' geçiyorsa (sürücü harfi — C:\\... — veya benzeri)
  - relative_path '/' ile başlıyorsa (mutlak/UNC-benzeri)
  - herhangi bir yol bileşeni '..' ise
  - normalize edilmiş nihai yol, ayna kökünün DIŞINA çözülüyorsa
Bu uç zaten ADMIN_PREFIXES üzerinden (panel.py) role=admin bir API anahtarı
ya da localhost gerektiriyor — path-traversal koruması buna ek bir katman,
tek başına yetkilendirme değil.
"""
import base64
import pathlib

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

try:
    from ..services.common import REMOTE_MIRROR_DIR
except ImportError:
    from services.common import REMOTE_MIRROR_DIR

router = APIRouter()


class RemoteFileReq(BaseModel):
    relative_path: str
    content_b64: str


class RemoteDeleteReq(BaseModel):
    relative_path: str


class RemoteMoveReq(BaseModel):
    old_relative_path: str
    new_relative_path: str


def _mirror_root(client_id: str) -> pathlib.Path:
    return REMOTE_MIRROR_DIR / client_id


def _valid_client_id(client_id: str) -> bool:
    return bool(client_id) and all(c.isalnum() or c in "_-" for c in client_id) and len(client_id) <= 64


def _safe_path(client_id: str, relative_path: str) -> pathlib.Path | None:
    """relative_path'i client_id'nin ayna kökü İÇİNE güvenle çözer.
    Traversal/mutlak yol/sürücü harfi denemesinde None döner (çağıran 400 üretir)."""
    if not _valid_client_id(client_id):
        return None
    if not relative_path or not relative_path.strip():
        return None
    if ":" in relative_path:              # sürücü harfi (C:) vb. — reddet
        return None
    norm = relative_path.replace("\\", "/")
    if norm.startswith("/"):              # mutlak/UNC-benzeri — reddet
        return None
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    root = _mirror_root(client_id).resolve()
    target = root.joinpath(*parts).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


@router.post("/api/remote-mirror/{client_id}/file")
def remote_file_upsert(client_id: str, r: RemoteFileReq):
    target = _safe_path(client_id, r.relative_path)
    if target is None:
        return JSONResponse({"error": "geçersiz client_id veya relative_path (path traversal reddedildi)"}, status_code=400)
    try:
        content = base64.b64decode(r.content_b64, validate=True)
    except Exception:
        return JSONResponse({"error": "content_b64 geçerli base64 değil"}, status_code=400)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return {"ok": True, "path": target.relative_to(_mirror_root(client_id).resolve()).as_posix()}


@router.post("/api/remote-mirror/{client_id}/delete")
def remote_file_delete(client_id: str, r: RemoteDeleteReq):
    target = _safe_path(client_id, r.relative_path)
    if target is None:
        return JSONResponse({"error": "geçersiz client_id veya relative_path (path traversal reddedildi)"}, status_code=400)
    if target.exists() and target.is_file():
        target.unlink()
    return {"ok": True}


@router.post("/api/remote-mirror/{client_id}/move")
def remote_file_move(client_id: str, r: RemoteMoveReq):
    src = _safe_path(client_id, r.old_relative_path)
    dst = _safe_path(client_id, r.new_relative_path)
    if src is None or dst is None:
        return JSONResponse({"error": "geçersiz client_id veya relative_path (path traversal reddedildi)"}, status_code=400)
    if not src.exists():
        return JSONResponse({"error": "kaynak dosya yok"}, status_code=404)
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dst)
    return {"ok": True}
