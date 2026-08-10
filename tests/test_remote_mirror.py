"""Uzak istemci dosya senkronu (src/api/remote_routes.py) testleri.

İki katman:
1. SAF FONKSİYON: _safe_path()'in path-traversal'ı (mutlak yol, '..', sürücü
   harfi, geçersiz client_id) gerçekten reddettiğini kanıtlar — Qdrant
   gerekmez, her zaman çalışır. Bu, CONTRIBUTING.md'nin security-sensitive
   değişiklikler için istediği regresyon testi (okuma değil, kanıt).
2. UÇ-UCA: TestClient ile gerçek HTTP istekleri. remote_routes.py Qdrant'a
   hiç dokunmadığı için @needs_qdrant GEREKMEZ — panel.py'nin startup
   event'i Qdrant'a erişemese bile idempotent/try-except'li olduğundan
   TestClient(app) her ortamda güvenle oluşturulabilir.
"""
import base64
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.api import remote_routes


# ---------------- 1) SAF FONKSİYON: path-traversal ----------------

@pytest.fixture
def mirror_root(tmp_path, monkeypatch):
    monkeypatch.setattr(remote_routes, "REMOTE_MIRROR_DIR", tmp_path)
    return tmp_path


def test_safe_path_accepts_normal_relative_path(mirror_root):
    p = remote_routes._safe_path("client1", "src/foo.pas")
    assert p == (mirror_root / "client1" / "src" / "foo.pas").resolve()


def test_safe_path_accepts_backslash_separators(mirror_root):
    # istemci Windows'ta '\\' gonderebilir - normalize edilip kabul edilmeli
    p = remote_routes._safe_path("client1", "src\\foo.pas")
    assert p == (mirror_root / "client1" / "src" / "foo.pas").resolve()


def test_safe_path_rejects_dotdot_traversal(mirror_root):
    assert remote_routes._safe_path("client1", "../../evil.txt") is None
    assert remote_routes._safe_path("client1", "src/../../evil.txt") is None
    assert remote_routes._safe_path("client1", "..") is None


def test_safe_path_rejects_absolute_path(mirror_root):
    assert remote_routes._safe_path("client1", "/etc/passwd") is None
    assert remote_routes._safe_path("client1", "\\windows\\system32\\evil.dll") is None


def test_safe_path_rejects_drive_letter(mirror_root):
    assert remote_routes._safe_path("client1", "C:\\Windows\\evil.dll") is None
    assert remote_routes._safe_path("client1", "C:/Windows/evil.dll") is None


def test_safe_path_rejects_invalid_client_id(mirror_root):
    assert remote_routes._safe_path("../escape", "foo.txt") is None
    assert remote_routes._safe_path("client/1", "foo.txt") is None
    assert remote_routes._safe_path("", "foo.txt") is None
    assert remote_routes._safe_path("a" * 65, "foo.txt") is None   # cok uzun


def test_safe_path_rejects_empty_or_dot_relative_path(mirror_root):
    assert remote_routes._safe_path("client1", "") is None
    assert remote_routes._safe_path("client1", "   ") is None
    assert remote_routes._safe_path("client1", ".") is None


def test_safe_path_never_escapes_root_even_after_resolve(mirror_root):
    # dolayli bir traversal denemesi - cok sayida ust-dizin bilesenini normal
    # bir dosya adiyla karistirarak resolve() sonrasi kacip kacmadigini dogrular
    p = remote_routes._safe_path("client1", "a/b/c/../../../../../etc/passwd")
    assert p is None


# ---------------- 2) UÇ-UCA: HTTP ----------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(remote_routes, "REMOTE_MIRROR_DIR", tmp_path)
    from fastapi.testclient import TestClient
    from src.panel import app
    with TestClient(app) as c:
        yield c


def test_upsert_writes_file(client, tmp_path):
    content = b"begin\n  writeln('merhaba');\nend."
    b64 = base64.b64encode(content).decode()
    r = client.post("/api/remote-mirror/testclient1/file",
                     json={"relative_path": "src/unit1.pas", "content_b64": b64})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    written = tmp_path / "testclient1" / "src" / "unit1.pas"
    assert written.exists()
    assert written.read_bytes() == content


def test_upsert_overwrites_existing_file(client, tmp_path):
    b64_1 = base64.b64encode(b"eski").decode()
    b64_2 = base64.b64encode(b"yeni").decode()
    client.post("/api/remote-mirror/testclient1/file",
                json={"relative_path": "a.pas", "content_b64": b64_1})
    r = client.post("/api/remote-mirror/testclient1/file",
                     json={"relative_path": "a.pas", "content_b64": b64_2})
    assert r.status_code == 200
    assert (tmp_path / "testclient1" / "a.pas").read_bytes() == b"yeni"


def test_upsert_rejects_traversal(client):
    b64 = base64.b64encode(b"evil").decode()
    r = client.post("/api/remote-mirror/testclient1/file",
                     json={"relative_path": "../../evil.txt", "content_b64": b64})
    assert r.status_code == 400
    assert "error" in r.json()


def test_upsert_rejects_bad_base64(client):
    r = client.post("/api/remote-mirror/testclient1/file",
                     json={"relative_path": "a.txt", "content_b64": "not-valid-base64!!!"})
    assert r.status_code == 400


def test_upsert_rejects_invalid_client_id(client):
    # tek bir URL path segmenti icinde kalan, ama _valid_client_id icin
    # gecersiz karakterler (nokta) tasiyan bir client_id - '..'/'/' iceren
    # degerler zaten Starlette routing katmaninda farkli davranabildigi icin
    # (yol segmenti belirsizligi) burada test edilmiyor; asil traversal
    # korumasi relative_path testlerinde (test_upsert_rejects_traversal vb.)
    # zaten kanitlaniyor.
    b64 = base64.b64encode(b"x").decode()
    r = client.post("/api/remote-mirror/client.name/file",
                     json={"relative_path": "a.txt", "content_b64": b64})
    assert r.status_code == 400


def test_delete_removes_file(client, tmp_path):
    target = tmp_path / "testclient1" / "a.pas"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x")
    r = client.post("/api/remote-mirror/testclient1/delete", json={"relative_path": "a.pas"})
    assert r.status_code == 200
    assert not target.exists()


def test_delete_nonexistent_file_is_noop_ok(client):
    r = client.post("/api/remote-mirror/testclient1/delete", json={"relative_path": "never-existed.pas"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_delete_rejects_traversal(client, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("dokunulmamali")
    r = client.post("/api/remote-mirror/testclient1/delete", json={"relative_path": "../outside.txt"})
    assert r.status_code == 400
    assert outside.exists()   # sunucu disina sizip silinmemis olmali


def test_move_relocates_file(client, tmp_path):
    src = tmp_path / "testclient1" / "old.pas"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("içerik")
    r = client.post("/api/remote-mirror/testclient1/move",
                     json={"old_relative_path": "old.pas", "new_relative_path": "renamed/new.pas"})
    assert r.status_code == 200, r.text
    assert not src.exists()
    dst = tmp_path / "testclient1" / "renamed" / "new.pas"
    assert dst.exists()
    assert dst.read_text() == "içerik"


def test_move_rejects_traversal_on_either_side(client, tmp_path):
    src = tmp_path / "testclient1" / "old.pas"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("x")
    r = client.post("/api/remote-mirror/testclient1/move",
                     json={"old_relative_path": "old.pas", "new_relative_path": "../../escape.pas"})
    assert r.status_code == 400
    assert src.exists()   # kaynak dokunulmadan kalmalı


def test_move_missing_source_returns_404(client):
    r = client.post("/api/remote-mirror/testclient1/move",
                     json={"old_relative_path": "nope.pas", "new_relative_path": "new.pas"})
    assert r.status_code == 404
