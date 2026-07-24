"""Güvenlik sınırı testleri (Sıra 4): path traversal, iframe sandbox, audit log."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.test_api import QDRANT_UP, needs_qdrant  # noqa: E402  (aynı canlılık kontrolü)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from src.panel import app
    with TestClient(app) as c:
        yield c


@needs_qdrant
def test_view_file_traversal_blocked(client):
    # izinli kökler dışındaki mutlak yol 403 olmalı — içeriği olan gerçek bir sistem dosyası
    r = client.get("/api/view-file", params={"path": "C:\\Windows\\win.ini"})
    # win.ini .ini uzantılı -> önce uzantı kontrolüne takılır; traversal'ı .txt ile test et
    r2 = client.get("/api/view-file", params={"path": "C:\\Windows\\System32\\drivers\\etc\\hosts.txt"})
    assert r.status_code == 400            # desteklenmeyen uzantı
    assert r2.status_code in (403, 404)    # kök dışı: 403 (varsa) / yol yoksa da asla 200 değil
    r3 = client.get("/api/view-file", params={"path": str(ROOT.parent / "herhangi.txt")})
    assert r3.status_code == 403           # proje kökünün BİR ÜSTÜ — kök dışı, kesin 403


@needs_qdrant
def test_view_file_project_root_allowed(client):
    target = next(ROOT.glob("*.md"), None)
    assert target is not None
    r = client.get("/api/view-file", params={"path": str(target)})
    assert r.status_code == 200 and r.json()["content"]


def test_viewer_iframe_sandboxed():
    html = (ROOT / "static" / "viewer.html").read_text(encoding="utf-8")
    assert "<iframe sandbox" in html, "viewer iframe'i sandbox'sız — görüntülenen HTML panel API'lerine erişebilir"


@needs_qdrant
def test_admin_write_is_audited(client, tmp_path):
    audit = ROOT / "logs" / "admin-audit.log"
    before = audit.stat().st_size if audit.exists() else 0
    client.post("/api/profile", json={"collection": "unidac"})   # zararsız no-op admin yazması
    assert audit.exists() and audit.stat().st_size > before
    last = audit.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "/api/profile" in last and "POST" in last
