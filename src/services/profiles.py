"""Koleksiyon profilleri (_index_profiles), indeksleme tarihçesi (_index_history),
owner/group kayıt defterleri (_owners, _groups — Owner→Collection modeli)."""
import uuid
from datetime import datetime, timezone

from qdrant_client import models

try:
    from .common import cl, HISTORY_COLL, PROFILE_COLL, OWNER_COLL, GROUP_COLL
except ImportError:
    from services.common import cl, HISTORY_COLL, PROFILE_COLL, OWNER_COLL, GROUP_COLL

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
                {k: p.payload.get(k) for k in ("path", "vectors", "chunks", "date", "new", "changed", "unchanged", "deleted",
                                                 "language", "commit", "branch", "git_dirty", "status", "error")})
        if next_page is None:
            break
    for entries in out.values():
        entries.sort(key=lambda e: e["date"], reverse=True)
    return out

# ---------------- owner / group kayıt defterleri ----------------
# Owner→Collection modeli (GitHub'daki owner/repo, TMS gibi bir firmanın
# Vendor→Ürün modeliyle aynı şekle iniyor). Koleksiyon profilindeki owner/group
# alanları DÜZ METİN olarak kalıyor (şema değişmiyor) — bu kayıt defterleri
# yalnızca Ayarlar'daki açılır listeyi besleyen bir KAYNAK; foreign-key
# zorlaması yok, bir owner/group kaydı silinse bile onu zaten kullanmış
# koleksiyonların profili bozulmaz (yalnızca gelecekteki seçim listesinden düşer).
def _registry_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name.strip().lower()))

def _ensure_registry(coll: str):
    if not cl.collection_exists(coll):
        cl.create_collection(coll, vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT))

def _registry_list(coll: str) -> list[dict]:
    if not cl.collection_exists(coll):
        return []
    pts, _ = cl.scroll(coll, limit=500, with_payload=True)
    return sorted((p.payload for p in pts), key=lambda x: (x.get("name") or "").lower())

def _registry_upsert(coll: str, name: str, **fields) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("ad boş olamaz")
    _ensure_registry(coll)
    rid = _registry_id(name)
    existing = {}
    if cl.collection_exists(coll):
        pts = cl.retrieve(coll, ids=[rid], with_payload=True)
        existing = pts[0].payload if pts else {}
    payload = {**existing, "name": name, **{k: v for k, v in fields.items() if v is not None},
               "updated_at": datetime.now(timezone.utc).isoformat()}
    payload.setdefault("created_at", payload["updated_at"])
    cl.upsert(coll, points=[models.PointStruct(id=rid, vector=[0.0], payload=payload)])
    return payload

def _registry_delete(coll: str, name: str):
    if cl.collection_exists(coll):
        cl.delete(coll, points_selector=models.PointIdsList(points=[_registry_id(name)]))

def list_owners() -> list[dict]:
    return _registry_list(OWNER_COLL)

def upsert_owner(name: str, url: str | None = None, note: str | None = None) -> dict:
    return _registry_upsert(OWNER_COLL, name, url=url, note=note)

def delete_owner(name: str):
    _registry_delete(OWNER_COLL, name)

def list_groups() -> list[dict]:
    return _registry_list(GROUP_COLL)

def upsert_group(name: str, description: str | None = None) -> dict:
    return _registry_upsert(GROUP_COLL, name, description=description)

def delete_group(name: str):
    _registry_delete(GROUP_COLL, name)
