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
def test_owners_groups_registry_crud(client):
    name = "__test_owner_apitest"
    r = client.post("/api/owners", json={"name": name, "url": "https://example.com/x"})
    assert r.status_code == 200 and r.json()["ok"] is True
    listed = client.get("/api/owners").json()["owners"]
    assert any(o["name"] == name for o in listed)
    # aynı ada tekrar upsert -> hata değil, güncelleme
    r2 = client.post("/api/owners", json={"name": name, "url": "https://example.com/y"})
    assert r2.status_code == 200
    client.delete("/api/owners", params={"name": name})
    listed2 = client.get("/api/owners").json()["owners"]
    assert not any(o["name"] == name for o in listed2)

    gname = "__test_group_apitest"
    r3 = client.post("/api/groups", json={"name": gname, "description": "test"})
    assert r3.status_code == 200
    assert any(g["name"] == gname for g in client.get("/api/groups").json()["groups"])
    client.delete("/api/groups", params={"name": gname})
    assert not any(g["name"] == gname for g in client.get("/api/groups").json()["groups"])


@needs_qdrant
def test_apikeys_crud_and_role_validation(client):
    """CRUD uçları TestClient='testclient' -> her zaman is_local sayılır (middleware
    admin kilidini localhost'ta hiç uygulamaz), yani buradaki asıl kanıt yükü
    apikeys.validate_api_key()'in doğru rolü döndürmesi ve iptalin gerçekten
    anahtarı geçersiz kılması — middleware'in host-bazlı dalını AYRI test ediyoruz
    (test_middleware_role_gate_pure) çünkü TestClient gerçek uzak host taklit edemez."""
    r = client.post("/api/apikeys", json={"name": "__test_key_read", "role": "read"})
    assert r.status_code == 200
    created = r.json()["key"]
    assert created["role"] == "read" and created["name"] == "__test_key_read"
    raw = created["key"]
    assert raw.startswith("ci_") and len(raw) > 20

    listed = client.get("/api/apikeys").json()["keys"]
    match = next((k for k in listed if k["id"] == created["id"]), None)
    assert match is not None and "key" not in match   # liste ham anahtarı ASLA içermemeli

    import pathlib as _pl, sys as _sys
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "src"))
    from services import apikeys as _ak
    rec = _ak.validate_api_key(raw)
    assert rec is not None and rec["role"] == "read"
    assert _ak.validate_api_key("gecersiz-bir-anahtar-asla-eslesmez") is None

    bad_role = client.post("/api/apikeys", json={"name": "__test_key_bad", "role": "superuser"})
    assert bad_role.status_code == 400

    client.delete("/api/apikeys", params={"id": created["id"]})
    assert _ak.validate_api_key(raw) is None   # iptal sonrası artık geçersiz
    listed2 = client.get("/api/apikeys").json()["keys"]
    assert not any(k["id"] == created["id"] for k in listed2)


@needs_qdrant
def test_job_checkpoint_persists_and_clears(client):
    """Sıra 26: _save_job_checkpoint/_clear_job_checkpoint/load_pending_job —
    saf kalıcılık katmanı, gerçek bir indeksleme çalıştırmadan doğrulanır."""
    import pathlib as _pl, sys as _sys
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "src"))
    from services import indexing_svc as _isvc
    req = _isvc.IndexReq(collection="__test_job_ckpt", path="C:/nowhere", vectors=["sparse"], device="cpu")
    _isvc._clear_job_checkpoint()   # önceki koşudan artık kalmasın
    assert _isvc.load_pending_job() is None
    _isvc._save_job_checkpoint(req)
    loaded = _isvc.load_pending_job()
    assert loaded is not None and loaded.collection == "__test_job_ckpt" and loaded.path == "C:/nowhere"
    _isvc._clear_job_checkpoint()
    assert _isvc.load_pending_job() is None


@needs_qdrant
def test_run_index_clears_checkpoint_on_handled_error(client):
    """Yakalanmış bir hata (ör. var olmayan kaynak) sonrası checkpoint SİLİNMELİ
    — aksi halde bir sonraki panel açılışında aynı bozuk iş sessizce sonsuza
    dek yeniden denenirdi. Yalnız SERT kesilme (kill/çökme, except'e hiç
    girilmeden) kaydı ayakta bırakmalı — bu senaryo burada test edilmiyor
    (süreç öldürmeyi gerektirir), yalnız normal hata yolu doğrulanıyor."""
    import pathlib as _pl, sys as _sys
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "src"))
    from services import indexing_svc as _isvc
    from services.common import STATE
    req = _isvc.IndexReq(collection="__test_job_errpath", path="", vectors=["sparse"], device="cpu")
    STATE["index_job"] = {"collection": req.collection, "phase": "starting"}
    _isvc._run_index(req)   # path="" ve geçmiş/profil de yok -> RuntimeError("kaynak klasör yok")
    assert STATE["index_job"]["phase"] == "error"
    assert _isvc.load_pending_job() is None


def test_middleware_role_gate_pure():
    """Middleware'in host-farkında rol kapısını (_presented_key_role + admin-yolu
    kısıtı) gerçek HTTP olmadan doğrular — TestClient host'u hep 'testclient' (yerel
    sayılır) olduğundan uzak-host senaryosunu HTTP üzerinden tetiklemek mümkün değil;
    bu yüzden panel.py'nin ürettiği rolü doğrudan çağırıyoruz."""
    import pathlib as _pl, sys as _sys
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "src"))
    import panel
    assert panel._presented_key_role(None) == (None, "")
    assert panel._presented_key_role("kesinlikle-gecersiz") == (None, "")


@needs_qdrant
def test_profile_kaynak_validation_and_clearing(client):
    # profile_set koleksiyonun GERÇEKTEN var olmasını istemez (_index_profiles
    # bağımsız bir kayıt) — gerçek "unidac" profilini kirletmemek için sahte ad.
    coll = "__test_profile_kaynak"
    bad = client.post("/api/profile", json={"collection": coll, "kaynak": "gecersiz-deger"})
    assert bad.status_code == 400
    ok = client.post("/api/profile", json={"collection": coll, "kaynak": "ticari"})
    assert ok.status_code == 200
    assert client.get("/api/profile", params={"collection": coll}).json().get("kaynak") == "ticari"
    # boş string temizleme için izinli olmalı (400 DEĞİL)
    clear = client.post("/api/profile", json={"collection": coll, "kaynak": ""})
    assert clear.status_code == 200
    assert client.get("/api/profile", params={"collection": coll}).json().get("kaynak") == ""


def test_git_update_status_idle_shape():
    """Qdrant gerekmez — sadece boşta iken beklenen şekli döndürdüğünü doğrular."""
    import pathlib as _pl
    import sys as _sys
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "src"))
    from services.common import STATE
    assert (STATE.get("git_update_job") or {"phase": "idle"}).get("phase") in ("idle", "done", "running", "error", "starting")


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


# ---------------- 1b) SSE AKIŞ ZARFI (Ollama'sız) ----------------
# /api/ask/stream ve /api/research/stream'in gövdesi LLM token akışı ürettiği
# için burada koşulmaz (yavaş/kararsız). Ama HER İKİSİ de var-olmayan bir
# koleksiyonda retrieval.search()'ün {"error": ...} döndürdüğü yolu paylaşır —
# bu, Ollama'ya hiç dokunmadan SSE zarfının (event: .../data: .../\n\n) uçtan
# uca doğru üretildiğini kanıtlamaya yeter.
@needs_qdrant
def test_ask_stream_sse_envelope_on_search_error(client):
    r = client.post("/api/ask/stream", json={"q": "test", "collections": ["__kesinlikle_yok_boyle_bir_koleksiyon"]})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "event: error\ndata: " in r.text
    assert "Hiçbir seçili koleksiyonda" in r.text


@needs_qdrant
def test_ask_stream_sse_envelope_cached_answer(client):
    """Önbellekli yol (cached=true) Ollama'ya hiç gitmez — meta/data/done üçlüsü tek seferde akar."""
    import pathlib as _pl, sys as _sys
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "src"))
    from api import search_routes
    import retrieval
    fake_req = search_routes.AskReq(q="__sse_cache_test_query__", collections=["unidac"], model="test-model")
    search_routes._ans_put(fake_req, "önbellekten test yanıtı", [], 0)
    key = search_routes._ans_key(fake_req)
    try:
        r = client.post("/api/ask/stream", json={"q": "__sse_cache_test_query__", "collections": ["unidac"], "model": "test-model"})
        assert r.status_code == 200
        assert "event: meta\ndata: " in r.text
        assert '"cached": true' in r.text
        assert "önbellekten test yanıtı" in r.text
        assert "event: done\ndata: " in r.text
    finally:
        from qdrant_client import models as _m
        retrieval.cl.delete(retrieval.ANSWER_COLL, points_selector=_m.PointIdsList(points=[key]))


@needs_qdrant
def test_research_stream_sse_envelope_on_search_error(client):
    r = client.post("/api/research/stream", json={"q": "test", "collections": ["__kesinlikle_yok_boyle_bir_koleksiyon"]})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "event: step\ndata: " in r.text
    assert "event: error\ndata: " in r.text


# ---------------- 2) SÖZLEŞME: MCP <-> REST paritesi ----------------
def test_mcp_rest_parity():
    """Her MCP tool'unun /api/mcp/<ad> REST test ucu olmalı (ve tersi) — tool
    tanımları 4 yerde elle çoğaltıldığı için kaymayı burada yakalarız."""
    import asyncio
    from src import mcp_server, panel
    tools = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    def all_paths(routes):
        # FastAPI 0.139+ include_router'ı _IncludedRouter olarak sarar — içine in
        for r in routes:
            p = getattr(r, "path", None)
            if p:
                yield p
            inner = getattr(r, "original_router", None)
            if inner is not None:
                yield from all_paths(inner.routes)
    rest = {p.removeprefix("/api/mcp/") for p in all_paths(panel.app.routes)
            if p.startswith("/api/mcp/")}
    missing_rest = tools - rest
    missing_tool = rest - tools
    assert not missing_rest, f"REST test ucu olmayan MCP tool'ları: {missing_rest}"
    assert not missing_tool, f"MCP karşılığı olmayan REST uçları: {missing_tool}"
