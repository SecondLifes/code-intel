"""API smoke + sözleşme testleri — Sıra 1 (birleşik yol haritası).

İki katman:
1. SMOKE: FastAPI TestClient ile gerçek uçlara istek — canlı Qdrant gerektirir
   (yoksa testler SKIP edilir, CI'da kırmızıya boyamaz). Amaç: panel.py
   modülerleşmesi (Sıra 2) sırasında davranışın korunduğunu kanıtlamak.
2. SÖZLEŞME: MCP tool'ları ile /api/mcp/* REST test uçlarının PARİTESİ —
   tool tanımları elle çoğaltıldığı için (bilinen borç #23) kayma burada yakalanır.

Çalıştır: .venv/Scripts/python.exe -m pytest tests/test_api.py -q
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def _qdrant_up() -> bool:
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:6333/collections", timeout=3)
        return True
    except Exception:
        return False


QDRANT_UP = _qdrant_up()
needs_qdrant = pytest.mark.skipif(not QDRANT_UP, reason="Qdrant ayakta değil — smoke testler atlandı")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from src.panel import app
    # TestClient startup event'lerini tetikler (payload index migrasyonu vs.) — sorun değil, idempotent
    with TestClient(app) as c:
        yield c


# ---------------- 1) SMOKE ----------------
@needs_qdrant
def test_health(client):
    d = client.get("/api/health").json()
    assert d["qdrant"] is True
    assert isinstance(d["collections"], list) and d["collections"]
    assert all("_" != c["name"][0] for c in d["collections"])   # iç koleksiyonlar sızmamalı


@needs_qdrant
def test_search_basic_and_filters(client):
    d = client.post("/api/search", json={"q": "split string", "collections": ["unidac"], "top_k": 5}).json()
    assert d["total"] > 0 and d["hits"]
    h = d["hits"][0]
    for key in ("collection", "score", "id", "unit", "name", "kind", "code", "why"):
        assert key in h
    # kind filtresi gerçekten filtrelemeli
    d2 = client.post("/api/search", json={"q": "split string", "collections": ["unidac"],
                                           "top_k": 5, "kind": "method"}).json()
    assert d2["hits"] and all(h["kind"] == "method" for h in d2["hits"])
    # decl/impl dedup: aynı (unit, bare-isim) çifti hem decl hem method olarak dönmemeli
    d3 = client.post("/api/search", json={"q": "split string", "collections": ["unidac"], "top_k": 20}).json()
    seen = {}
    for h in d3["hits"]:
        key = (h["unit"], (h["name"] or "").split(".")[-1].lower())
        assert not (key in seen and {seen[key], h["kind"]} == {"decl", "method"}), f"dedup ihlali: {key}"
        seen[key] = h["kind"]


@needs_qdrant
def test_search_pagination_total_stable(client):
    a = client.post("/api/search", json={"q": "connection", "collections": ["unidac"], "top_k": 5, "offset": 0}).json()
    b = client.post("/api/search", json={"q": "connection", "collections": ["unidac"], "top_k": 5, "offset": 5}).json()
    assert a["total"] == b["total"]   # sayfalar arası total tutarlılığı (gerçek eski bug)
    assert [h["id"] for h in a["hits"]] != [h["id"] for h in b["hits"]]


@needs_qdrant
def test_relations_and_chunk(client):
    hit = client.post("/api/search", json={"q": "split string", "collections": ["unidac"],
                                            "top_k": 1, "kind": "method"}).json()["hits"][0]
    r = client.post("/api/relations", json={"collection": "unidac", "id": hit["id"]}).json()
    for key in ("calls", "called_by", "same_unit"):
        assert key in r
    c = client.post("/api/mcp/get_chunk", json={"collection": "unidac", "id": hit["id"]}).json()
    assert "truncated" in c and "source" in c and c["code"]


@needs_qdrant
def test_feedback_and_analytics(client):
    ok = client.post("/api/feedback", json={"collection": "unidac", "id": 1, "q": "__apitest",
                                             "verdict": "up", "name": "T"}).json()
    assert ok.get("ok") is True
    bad = client.post("/api/feedback", json={"collection": "unidac", "id": 1, "q": "x", "verdict": "hmm"})
    assert bad.status_code == 400
    a = client.get("/api/analytics").json()
    for key in ("searches", "zero_queries", "top_queries", "feedback"):
        assert key in a


@needs_qdrant
def test_symbol_endpoints(client):
    h = client.post("/api/mcp/get_type_hierarchy",
                    json={"collection": "unidac", "type_name": "TCRConnection"}).json()
    assert "descendants" in h and isinstance(h["descendants"], list)
    r = client.post("/api/mcp/find_references", json={"collection": "unidac", "name": "SplitString"}).json()
    assert r["definitions"], "SplitString tanımı bulunmalıydı"


@needs_qdrant
def test_impact_requires_git(client):
    # unidac'ın kaynak yolu git deposu değil (veya yok) — zarif hata bekleriz, 500 değil
    r = client.get("/api/impact", params={"collection": "unidac"})
    assert r.status_code in (200, 400)
    assert "error" in r.json() or "changed_units" in r.json()


@needs_qdrant
def test_internal_collections_protected(client):
    r = client.delete("/api/collection", params={"collection": "_index_profiles"})
    assert r.status_code == 400


# ---------------- 2) SÖZLEŞME: MCP <-> REST paritesi ----------------
def test_mcp_rest_parity():
    """Her MCP tool'unun /api/mcp/<ad> REST test ucu olmalı (ve tersi) — tool
    tanımları 4 yerde elle çoğaltıldığı için kaymayı burada yakalarız."""
    import asyncio
    from src import mcp_server, panel
    tools = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    rest = {route.path.removeprefix("/api/mcp/") for route in panel.app.routes
            if route.path.startswith("/api/mcp/")}
    missing_rest = tools - rest
    missing_tool = rest - tools
    assert not missing_rest, f"REST test ucu olmayan MCP tool'ları: {missing_rest}"
    assert not missing_tool, f"MCP karşılığı olmayan REST uçları: {missing_tool}"
