"""API anahtarı kayıt defteri (_api_keys) — Sıra 11a. Rol ayrımı: "read" (arama/RAG/
analitik) | "admin" (koleksiyon CRUD, indeksleme, profil, owner/group, yedek...).

Ham anahtar HİÇBİR ZAMAN saklanmaz — yalnızca sha256 özeti. Nokta ID'si doğrudan
bu özet (hash) olduğu için doğrulama tek bir cl.retrieve(ids=[hash]) ile O(1)."""
import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from qdrant_client import models

try:
    from .common import cl, APIKEY_COLL
except ImportError:
    from services.common import cl, APIKEY_COLL

ROLES = {"read", "admin"}

def _hash(raw_key: str) -> str:
    """Qdrant nokta ID'si ya işaretsiz tamsayı ya da UUID olmalı — ham sha256 hex
    dizisi ikisi de değil. sha256'nın ilk 128 bitini deterministik bir UUID'ye
    çeviriyoruz (aynı ham anahtar -> aynı ID, çakışma direnci pratikte tam)."""
    return str(uuid.UUID(bytes=hashlib.sha256(raw_key.encode("utf-8")).digest()[:16]))

def _ensure():
    if not cl.collection_exists(APIKEY_COLL):
        cl.create_collection(APIKEY_COLL, vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT))

def generate_api_key(name: str, role: str) -> dict:
    """Yeni anahtar üretir. Ham değer YALNIZCA bu dönüşte görünür — sonrasında
    kurtarılamaz (bir daha gösterilmez), yalnız iptal edilip yenisi üretilebilir."""
    name = name.strip()
    if not name:
        raise ValueError("ad boş olamaz")
    if role not in ROLES:
        raise ValueError(f"geçersiz rol: {role} (beklenen: {ROLES})")
    _ensure()
    raw = "ci_" + secrets.token_urlsafe(32)
    kid = _hash(raw)
    now = datetime.now(timezone.utc).isoformat()
    payload = {"id": kid, "name": name, "role": role, "prefix": raw[:10] + "…",
               "created_at": now, "last_used_at": None}
    cl.upsert(APIKEY_COLL, points=[models.PointStruct(id=kid, vector=[0.0], payload=payload)])
    return {**payload, "key": raw}

def list_api_keys() -> list[dict]:
    if not cl.collection_exists(APIKEY_COLL):
        return []
    pts, _ = cl.scroll(APIKEY_COLL, limit=500, with_payload=True)
    return sorted((p.payload for p in pts), key=lambda x: x.get("created_at") or "", reverse=True)

def revoke_api_key(key_id: str):
    if cl.collection_exists(APIKEY_COLL):
        cl.delete(APIKEY_COLL, points_selector=models.PointIdsList(points=[key_id]))

def validate_api_key(raw_key: str | None) -> dict | None:
    """Geçerliyse {id, name, role, ...} döndürür (last_used_at'i best-effort günceller),
    değilse None. İç akışlar (middleware) bunu her istek için çağırır — hızlı olmalı."""
    if not raw_key or not cl.collection_exists(APIKEY_COLL):
        return None
    kid = _hash(raw_key)
    pts = cl.retrieve(APIKEY_COLL, ids=[kid], with_payload=True)
    if not pts:
        return None
    payload = pts[0].payload
    try:
        cl.set_payload(APIKEY_COLL, payload={"last_used_at": datetime.now(timezone.utc).isoformat()},
                        points=models.PointIdsList(points=[kid]))
    except Exception:
        pass   # kullanım zamanı güncellemesi isteği asla düşürmemeli
    return payload
