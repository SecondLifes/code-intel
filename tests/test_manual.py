"""Yardım/manual sistemi testleri: model üretimi (LLM'siz kısımlar), markdown->HTML,
çapraz-linkleme, HTML/PDF/DOCX render sözleşmesi, API uçları.

document_unit() Ollama gerektirdiği için gerçek build_manual() E2E'si burada
KOŞULMAZ (pahalı/yavaş, panel.py ile canlı doğrulandı) — bu dosya yalnızca
LLM'siz saf fonksiyonları (render_*, _cross_link, _md_to_html_fragment,
_chapter_key, _slug) ve API sözleşmesini test eder.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
import manual  # noqa: E402

from tests.test_api import QDRANT_UP, needs_qdrant  # noqa: E402


FAKE_MODEL = {
    "collection": "test-coll", "scope": "", "title": "test-coll — Kullanım Kılavuzu",
    "owner": "acme", "group": "REST Library", "version": "1.0", "kaynak": "git", "url": "https://x",
    "generated_at": "2026-01-01T00:00:00Z",
    "stats": {"units": 2, "chapters": 1, "languages": {"pascal": 2}},
    "type_home": {"tfoo": "src.html#unita-pas", "tbar": "src.html#unitb-pas"},
    "chapters": [{
        "title": "src", "slug": "src",
        "sections": [
            {"title": "UnitA.pas", "slug": "unita-pas", "unit": "src/UnitA.pas", "lang": "pascal", "chunk_id": 123456,
             "body_md": "## Amaç\nBu birim TFoo sınıfını tanımlar ve TBar temel sınıfından türer.\n\n"
                        "```\nTFoo = class(TBar)\n```\n\n- Madde bir\n- Madde iki"},
            {"title": "UnitB.pas", "slug": "unitb-pas", "unit": "src/UnitB.pas", "lang": "pascal",
             "body_md": "## Amaç\nTemel sınıf TBar burada."},   # chunk_id YOK -> eski manual.json geriye uyum testi
        ],
    }],
}


def test_chapter_key_and_slug():
    assert manual._chapter_key("jvcl/tests/Foo.pas") == "jvcl"
    assert manual._chapter_key("Foo.pas") == "Genel"
    assert manual._slug("RESTRequest4D.Request.Client.pas") == "restrequest4d-request-client-pas"
    assert manual._slug("Ç ö ş İ") != ""   # Türkçe karakterler çökertmemeli


def test_topo_order_puts_foundations_first():
    """Sıra 6 (kullanıcı): sol menü dosya sırası bağımlılığa göre olmalı —
    kullanılan (temel) dosya, onu kullanandan ÖNCE gelmeli."""
    # C, B'yi kullanır; B, A'yı kullanır -> beklenen sıra: A, B, C
    order = manual._topo_order(["C.pas", "A.pas", "B.pas"], {"C.pas": {"B.pas"}, "B.pas": {"A.pas"}, "A.pas": set()})
    assert sorted(order, key=order.get) == ["A.pas", "B.pas", "C.pas"]

    # bağımsız dosyalar alfabetik sırada kalmalı
    order2 = manual._topo_order(["Z.pas", "M.pas", "A.pas"], {})
    assert sorted(order2, key=order2.get) == ["A.pas", "M.pas", "Z.pas"]

    # çevrim (A<->B) -> çökmemeli, ikisi de bir şekilde sıralanmalı
    order3 = manual._topo_order(["A.pas", "B.pas"], {"A.pas": {"B.pas"}, "B.pas": {"A.pas"}})
    assert set(order3) == {"A.pas", "B.pas"}


def test_cross_link_skips_code_and_self():
    linked = manual._cross_link(FAKE_MODEL["chapters"][0]["sections"][0]["body_md"],
                                 FAKE_MODEL["type_home"], self_href="src.html#unita-pas")
    assert "[TBar](src.html#unitb-pas)" in linked   # düz metinde link oluşmalı
    assert "TFoo = class(TBar)" in linked            # kod bloğu İÇİNDEKİ mention linklenmemeli
    assert "[TFoo]" not in linked                    # kendi sayfasına link verilmemeli


def test_md_to_html_fragment_basic():
    html = manual._md_to_html_fragment("## Başlık\nBir paragraf **kalın** metinle.\n\n- öğe1\n- öğe2")
    assert "<h2>Başlık</h2>" in html
    assert "<b>kalın</b>" in html
    assert "<ul><li>öğe1</li>" in html or ("<li>öğe1</li>" in html and "<ul>" in html)


def test_render_html_index_and_chapter():
    idx = manual.render_manual_html(FAKE_MODEL, "index")
    assert "test-coll" in idx and "İçindekiler" in idx
    assert "<iframe" not in idx   # offline/self-contained — dış kaynak yok
    assert "http://" not in idx and "https://fonts" not in idx

    ch = manual.render_manual_html(FAKE_MODEL, "src")
    assert 'id="unita-pas"' in ch and 'id="unitb-pas"' in ch
    assert "[TBar]" not in ch and '<a href="/manual/test-coll/src.html#unitb-pas">TBar</a>' in ch   # cross-link uygulanmış

    # Sıra 7 (kullanıcı): Aç + Tarayıcıda Göster — YALNIZ chunk_id'si olan bölümde (UnitA)
    assert "manualOpen('test-coll',123456,this)" in ch
    assert "manualShowInBrowser('test-coll',123456,'unita-pas',this)" in ch
    # chunk_id'si OLMAYAN eski-model bölümü (UnitB) için düğme HİÇ üretilmemeli — çökmemeli;
    # test fixture'ında tek chunk_id var, bu yüzden onclick çağrısı tam bir kez görünmeli
    # ("manualOpen(" kendisi ayrıca <script> içindeki fonksiyon TANIMINDA da geçiyor,
    # o yüzden tam çağrı imzasıyla (tırnaklı argümanlarla) sayıyoruz)
    assert ch.count("manualOpen('test-coll',") == 1

    missing = manual.render_manual_html(FAKE_MODEL, "hic-yok")
    assert "404" in missing


def test_render_html_links_are_absolute_not_relative():
    """Canlı doğrulamada bulunan gerçek hata: hrefler GÖRECELİ (`"src.html"`)
    üretiliyordu — sayfa `/manual/{collection}` adresinde (SONUNDA `/` YOK)
    sunulduğu için tarayıcı bunu son path segmentini DEĞİŞTİREREK çözüyordu
    (`/manual/src.html`, "RESTRequest4Delphi" tamamen kayboluyordu) — her
    link "Manual henüz üretilmemiş" gösteriyordu. Artık MUTLAK olmalı; bunu
    urljoin ile GERÇEK tarayıcı çözümlemesini simüle ederek kanıtlıyoruz."""
    from urllib.parse import urljoin
    import re as _re
    idx = manual.render_manual_html(FAKE_MODEL, "index")
    hrefs = _re.findall(r'href="([^"]+)"', idx)
    assert hrefs, "İndeks sayfasında hiç link bulunamadı"
    page_url_no_trailing_slash = "http://x/manual/test-coll"   # gerçek servis edilen URL — SONUNDA / YOK
    for href in hrefs:
        if href.startswith(("http://", "https://")):
            continue   # dış kaynak linki (ör. "Kaynak: <url>") — gezinme linki değil
        if href == "/manual/test-coll":
            continue   # koleksiyon KÖKÜNE (indekse) mutlak-yol linki — trailing slash sorunundan bağımsız güvenli
        resolved = urljoin(page_url_no_trailing_slash, href)
        assert resolved.startswith("http://x/manual/test-coll/"), \
            f"{href!r} göreceli çözüldü ve koleksiyon adını kaybetti: {resolved}"


def test_render_docx_produces_valid_zip():
    data = manual.render_manual_docx(FAKE_MODEL)
    assert data[:2] == b"PK"   # docx bir zip arşividir
    assert len(data) > 1000


def test_render_pdf_produces_valid_pdf():
    data = manual.render_manual_pdf(FAKE_MODEL)
    assert data[:5] == b"%PDF-"
    assert len(data) > 500


def test_load_manual_missing_returns_none():
    assert manual.load_manual("__kesinlikle_yok_boyle_bir_koleksiyon") is None


@needs_qdrant
def test_manual_chapter_route_strips_html_suffix():
    """Canlı doğrulamada bulunan İKİNCİ hata (ilki mutlak/göreceli href'ti):
    nav/cross-link href'leri "{slug}.html" formatında ("src.html") — ama
    /manual/{collection}/{page} rotası `page`'i AYNEN (uzantılı) render'a
    veriyordu, render ise BÖLÜM SLUG'INA (uzantısız "src") göre eşleştiriyordu
    — hiçbir eşleşme bulunamayıp her bölüm sayfası 404 dönüyordu. Gerçek bir
    model dosyası diske yazılıp HTTP üzerinden (route dahil) doğrulanıyor."""
    import json as _json
    from fastapi.testclient import TestClient
    from src.panel import app
    coll = "__test_manual_route"
    manual.MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = manual.MANUAL_DIR / f"{coll}.json"
    saved_model = {**FAKE_MODEL, "collection": coll}
    model_path.write_text(_json.dumps(saved_model, ensure_ascii=False), encoding="utf-8")
    try:
        with TestClient(app) as client:
            r = client.get(f"/manual/{coll}/src.html")
            assert r.status_code == 200 and "404" not in r.text[:20]
            assert 'id="unita-pas"' in r.text
    finally:
        model_path.unlink(missing_ok=True)


@needs_qdrant
def test_manual_api_endpoints_shape():
    from fastapi.testclient import TestClient
    from src.panel import app
    with TestClient(app) as client:
        assert client.get("/api/manual/exists", params={"collection": "__yok"}).json() == {"exists": False}
        assert client.get("/api/manual/status").json().get("phase") in ("idle", "starting", "building", "done", "error")
        bad = client.post("/api/manual/build", json={"collection": "__internal_test_yok"})
        assert bad.status_code == 404
        r = client.get("/manual/__kesinlikle_yok")
        assert r.status_code == 404 and "henüz üretilmemiş" in r.text
        exp = client.get("/api/manual/export", params={"collection": "__kesinlikle_yok", "format": "pdf"})
        assert exp.status_code == 404
        bad_fmt = client.get("/api/manual/export", params={"collection": "__kesinlikle_yok", "format": "xyz"})
        assert bad_fmt.status_code in (400, 404)   # önce manual-yok kontrolü de gelebilir, ikisi de kabul
