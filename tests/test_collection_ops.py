"""Koleksiyon işlemleri round-trip testleri: rename, merge, export→import.

Hepsi atılabilir, minik (1-2 noktalı) fixture koleksiyonlarla çalışır —
gerçek indekslenmiş koleksiyonlara (Jedi/mORMot2/unidac) hiç dokunulmaz.
Qdrant gerektirir; yoksa atlanır (needs_qdrant, test_api.py ile aynı desen).
"""
import io
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.test_api import QDRANT_UP, needs_qdrant  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from src.panel import app
    with TestClient(app) as c:
        yield c


def _mk_fixture_collection(name: str, points: list[dict]):
    """(name, [{id, payload}]) — sparse-only, minimal şema, dense YOK (hızlı)."""
    import retrieval
    from qdrant_client import models
    cl = retrieval.cl
    if cl.collection_exists(name):
        cl.delete_collection(name)
    cl.create_collection(name, vectors_config={},
                         sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)})
    cl.upsert(name, points=[models.PointStruct(id=p["id"], vector={}, payload=p["payload"]) for p in points])


def _cleanup(*names: str):
    import retrieval
    for n in names:
        if retrieval.cl.collection_exists(n):
            retrieval.cl.delete_collection(n)


@needs_qdrant
def test_rename_round_trip_moves_points_profile_history(client):
    src, dst = "__test_rn_src", "__test_rn_dst"
    _cleanup(src, dst)
    try:
        _mk_fixture_collection(src, [{"id": 1, "payload": {"unit": "A.pas", "kind": "method", "name": "Foo"}}])
        client.post("/api/profile", json={"collection": src, "owner": "rntest-owner", "version": "9.9"})
        r = client.post("/api/collection/rename", json={"old_name": src, "new_name": dst})
        assert r.status_code == 200 and r.json()["points_copied"] == 1

        import retrieval
        assert not retrieval.cl.collection_exists(src)
        assert retrieval.cl.collection_exists(dst)
        pts, _ = retrieval.cl.scroll(dst, limit=10, with_payload=True)
        assert len(pts) == 1 and pts[0].payload["name"] == "Foo"

        prof = client.get("/api/profile", params={"collection": dst}).json()
        assert prof.get("owner") == "rntest-owner" and prof.get("version") == "9.9"
    finally:
        _cleanup(src, dst)


@needs_qdrant
def test_merge_keeps_sources_and_combines_points(client):
    a, b, target = "__test_mg_a", "__test_mg_b", "__test_mg_target"
    _cleanup(a, b, target)
    try:
        _mk_fixture_collection(a, [{"id": 101, "payload": {"unit": "A.pas", "kind": "method", "name": "AFunc"}}])
        _mk_fixture_collection(b, [{"id": 202, "payload": {"unit": "B.pas", "kind": "method", "name": "BFunc"}}])
        r = client.post("/api/collection/merge", json={"sources": [a, b], "target": target})
        assert r.status_code == 200 and r.json()["points_copied"] == 2

        import retrieval
        assert retrieval.cl.collection_exists(a) and retrieval.cl.collection_exists(b)   # kaynaklar SİLİNMEDİ
        pts, _ = retrieval.cl.scroll(target, limit=10, with_payload=True)
        names = {p.payload["name"] for p in pts}
        assert names == {"AFunc", "BFunc"}
    finally:
        _cleanup(a, b, target)


@needs_qdrant
def test_merge_reports_id_collisions_instead_of_silent_data_loss(client):
    a, b, target = "__test_mgc_a", "__test_mgc_b", "__test_mgc_target"
    _cleanup(a, b, target)
    try:
        # AYNI id -> gerçek çakışma senaryosu (dış analizde işaretlenen risk)
        _mk_fixture_collection(a, [{"id": 555, "payload": {"unit": "X.pas", "kind": "method", "name": "First"}}])
        _mk_fixture_collection(b, [{"id": 555, "payload": {"unit": "X.pas", "kind": "method", "name": "Second"}}])
        r = client.post("/api/collection/merge", json={"sources": [a, b], "target": target}).json()
        assert r["points_copied"] == 1
        assert r["collisions"].get(b) == 1   # ikinci kaynaktaki çakışan nokta raporlanmalı
        assert "collisions" in r["note"] or "çakışma" in r["note"]
    finally:
        _cleanup(a, b, target)


@needs_qdrant
def test_export_import_round_trip_preserves_points_and_profile(client):
    src, reimported = "__test_ei_src", "__test_ei_src"   # import ayni ada geri yazar (manifest'te kayitli)
    _cleanup(src)
    try:
        _mk_fixture_collection(src, [
            {"id": 1, "payload": {"unit": "A.pas", "kind": "method", "name": "Foo", "doc": "açıklama"}},
            {"id": 2, "payload": {"unit": "B.pas", "kind": "type", "name": "TBar"}},
        ])
        client.post("/api/profile", json={"collection": src, "owner": "eitest-owner"})

        exp = client.get("/api/collection/export", params={"collection": src})
        assert exp.status_code == 200
        gz_bytes = exp.content

        import retrieval
        retrieval.cl.delete_collection(src)   # ihraç edilen veriyle GERÇEKTEN geri yüklendiğini kanıtlamak için önce sil
        assert not retrieval.cl.collection_exists(src)

        files = {"file": ("test.jsonl.gz", io.BytesIO(gz_bytes), "application/gzip")}
        imp = client.post("/api/collection/import", files=files)
        assert imp.status_code == 200 and imp.json()["points"] == 2

        assert retrieval.cl.collection_exists(reimported)
        pts, _ = retrieval.cl.scroll(reimported, limit=10, with_payload=True)
        names = {p.payload["name"] for p in pts}
        assert names == {"Foo", "TBar"}
        assert client.get("/api/profile", params={"collection": reimported}).json().get("owner") == "eitest-owner"
    finally:
        _cleanup(src)


@needs_qdrant
def test_import_corrupt_file_leaves_existing_collection_untouched(client):
    """Atomiklik (Sıra 6) regresyon koruması — bozuk dosya var olan koleksiyona
    asla dokunmamalı (satır sayısı manifest'le uyuşmuyor -> validate-önce-yaz)."""
    name = "__test_corrupt_import"
    _cleanup(name)
    try:
        _mk_fixture_collection(name, [{"id": 1, "payload": {"unit": "A.pas", "kind": "method", "name": "Untouched"}}])
        exp = client.get("/api/collection/export", params={"collection": name})
        truncated = exp.content[: len(exp.content) // 2]   # dosyanın yarısı -> gzip/JSONL bozuk
        files = {"file": ("bad.jsonl.gz", io.BytesIO(truncated), "application/gzip")}
        imp = client.post("/api/collection/import", params={"overwrite": "true"}, files=files)
        assert imp.status_code == 400

        import retrieval
        assert retrieval.cl.collection_exists(name)
        pts, _ = retrieval.cl.scroll(name, limit=10, with_payload=True)
        assert len(pts) == 1 and pts[0].payload["name"] == "Untouched"
    finally:
        _cleanup(name)
