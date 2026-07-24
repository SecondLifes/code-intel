"""Koleksiyon profilleri (_index_profiles) ve indeksleme tarihçesi (_index_history)."""
import uuid
from datetime import datetime, timezone

from qdrant_client import models

try:
    from .common import cl, HISTORY_COLL, PROFILE_COLL
except ImportError:
    from services.common import cl, HISTORY_COLL, PROFILE_COLL

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
