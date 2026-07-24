"""Koleksiyon veri işlemleri: nokta kopyalama, akışlı export, rotasyonlu yedekleme."""
import json
import zlib
from datetime import datetime, timezone

from qdrant_client import models

try:
    from .common import (cl, INTERNAL_COLLS, STATE, BACKUP_DIR, BACKUP_KEEP, BACKUP_AUTO_MAX_POINTS)
    from .profiles import get_profile
except ImportError:
    from services.common import (cl, INTERNAL_COLLS, STATE, BACKUP_DIR, BACKUP_KEEP, BACKUP_AUTO_MAX_POINTS)
    from services.profiles import get_profile

def _copy_all_points(src: str, dst: str, skip_ids: set[int] | None = None) -> tuple[int, int]:
    """src koleksiyonundaki TÜM noktaları (vektör+payload) dst'ye kopyalar. Qdrant'ın
    kendi rename/copy API'si yok — bu yüzden scroll+upsert ile elle yapılıyor.
    skip_ids verilirse o id'ler atlanır (merge'de hedefte zaten var olan id'lerle
    çakışmayı önlemek için). (kopyalanan, atlanan) sayılarını döndürür — atlananlar
    merge'de ID ÇAKIŞMASI demektir ve sessizce yutulmamalı (dış analizde bulunan
    veri kaybı riski: iki kütüphanede aynı göreli yol+imza aynı 48-bit ID'yi üretir)."""
    n = skipped = 0
    next_page = None
    while True:
        batch, next_page = cl.scroll(src, limit=1000, offset=next_page, with_payload=True, with_vectors=True)
        if batch:
            pts = []
            for p in batch:
                if skip_ids and p.id in skip_ids:
                    skipped += 1
                    continue
                pts.append(models.PointStruct(id=p.id, vector=p.vector or {}, payload=p.payload))
            if pts:
                cl.upsert(dst, points=pts)
                n += len(pts)
        if next_page is None:
            break
    return n, skipped

def _vector_to_json(val):
    if hasattr(val, "indices"):   # models.SparseVector
        return {"_sparse": True, "indices": list(val.indices), "values": list(val.values)}
    return val

def _export_line_iter(collection: str, with_vectors: bool = True):
    """Export satırlarını ÜRETEÇ olarak verir — eski sürüm tüm satırları listede
    biriktirip sonra gzip'liyordu (375K'lık koleksiyonlarda GB'larca RAM; dış
    analizde işaret edilen bellek baskısı). İç koleksiyonların adsız (default)
    vektörü '_default' anahtarıyla taşınır."""
    info = cl.get_collection(collection)
    v, sv = info.config.params.vectors, info.config.params.sparse_vectors
    manifest = {
        "_manifest": True, "collection": collection,
        "dense_vectors": {k: {"size": vp.size, "distance": vp.distance.value} for k, vp in v.items()} if isinstance(v, dict) else {},
        "default_vector": ({"size": v.size, "distance": v.distance.value} if not isinstance(v, dict) and v else None),
        "sparse_vectors": list(sv.keys()) if isinstance(sv, dict) else [],
        "with_vectors": with_vectors,
        "points_count": info.points_count,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile": get_profile(collection),
    }
    yield json.dumps(manifest, ensure_ascii=False)
    next_page = None
    while True:
        batch, next_page = cl.scroll(collection, limit=1000, offset=next_page,
                                      with_payload=True, with_vectors=with_vectors)
        for p in batch:
            if not with_vectors:
                vec_out = {}
            elif isinstance(p.vector, dict):
                vec_out = {k: _vector_to_json(val) for k, val in (p.vector or {}).items()}
            else:
                vec_out = {"_default": p.vector}   # iç koleksiyonlar (size-1 adsız vektör)
            yield json.dumps({"id": p.id, "payload": p.payload, "vector": vec_out}, ensure_ascii=False)
        if next_page is None:
            break

def _gzip_iter(lines):
    """Satır üretecini akışlı gzip'e çevirir (bellekte tam kopya tutulmaz)."""
    co = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)   # 16+: gzip başlığı
    for line in lines:
        chunk = co.compress((line + "\n").encode("utf-8"))
        if chunk:
            yield chunk
    tail = co.flush()
    if tail:
        yield tail

def _run_backup(full_all: bool = False):
    """Tüm koleksiyonları backups\\ altına <ad>-<zaman>.jsonl.gz olarak yazar,
    koleksiyon başına en yeni BACKUP_KEEP kopya kalır. İç koleksiyonlar (profil,
    geçmiş, telemetri — küçük ve yeri doldurulamaz) HER ZAMAN dahil. Kullanıcı
    koleksiyonlarında otomatik modda BACKUP_AUTO_MAX_POINTS üstü atlanır
    (full_all=True — elle tetikleme — hepsini alır). Önce .tmp'ye yazılır,
    başarıyla bitince adlandırılır — yarım dosya asla yedek sanılmaz."""
    st = STATE.get("backup_job") or {}
    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        names = [c.name for c in cl.get_collections().collections]
        skipped = []
        st.update(phase="running", total=len(names), done=0)
        for i, name in enumerate(names):
            st.update(collection=name, done=i)
            if name not in INTERNAL_COLLS and not full_all:
                if cl.get_collection(name).points_count > BACKUP_AUTO_MAX_POINTS:
                    skipped.append(name)
                    continue
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            tmp = BACKUP_DIR / f".tmp-{name}.gz"
            final = BACKUP_DIR / f"{name}-{ts}.jsonl.gz"
            with open(tmp, "wb") as f:
                for chunk in _gzip_iter(_export_line_iter(name)):
                    f.write(chunk)
            tmp.rename(final)
            for old in sorted(BACKUP_DIR.glob(f"{name}-*.jsonl.gz"))[:-BACKUP_KEEP]:
                old.unlink()
        st.update(phase="done", done=len(names), skipped=skipped,
                  finished=datetime.now(timezone.utc).isoformat())
    except Exception as e:
        st.update(phase="error", error=str(e)[:300])
