"""Yardım/manual sistemi testleri: model üretimi (LLM'siz kısımlar), markdown->HTML,
çapraz-linkleme, HTML/PDF/DOCX render sözleşmesi, API uçları.

document_unit() Ollama gerektirdiği için gerçek build_manual() E2E'si burada
KOŞULMAZ (pahalı/yavaş, panel.py ile canlı doğrulandı) — bu dosya yalnızca
LLM'siz saf fonksiyonları (render_*, _cross_link, _md_to_html_fragment,
_chapter_key, _slug) ve API sözleşmesini test eder.
"""
import io
import json
import pathlib
import sys
import zipfile

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


def test_hljs_lang_maps_known_exceptions_and_passes_through_others():
    """Sıra 3/4 (kullanıcı, highlight.js seçildi): proje dil etiketleri ile
    vendored highlight.js dosya adları arasındaki BİLİNEN 3 istisna
    (static/vendor/highlightjs/languages içeriğine göre doğrulandı)."""
    assert manual._hljs_lang("pascal") == "delphi"
    assert manual._hljs_lang("objc") == "objectivec"
    assert manual._hljs_lang("vb") == "vbnet"
    assert manual._hljs_lang("python") == "python"   # eşleşenler olduğu gibi geçer
    assert manual._hljs_lang("zig") == ""   # bilinen-desteksiz -> boş (istemci hiç denemez)
    assert manual._hljs_lang("") == ""


def test_build_class_tree_nested_roots_external_and_unclassed_files():
    """Sıra B (kullanıcı, "Tree list Classlara göre yapılmalı iç içe"):
    - kalıtım zincirleri iç içe ağaç olmalı (TObject -> TBase -> TFoo)
    - ebeveyni bu bölümde tanımlı olmayan (TObject) düğüm "external" olmalı
      (kullanıcı kararı: gri/tıklanamaz kök)
    - hiç sınıfı olmayan dosyalar (Utils.pas) "Diğer/Global" grubuna düşmeli"""
    sections = [
        {"unit": "src/Base.pas", "slug": "base-pas", "title": "Base.pas"},
        {"unit": "src/Foo.pas", "slug": "foo-pas", "title": "Foo.pas"},
        {"unit": "src/Bar.pas", "slug": "bar-pas", "title": "Bar.pas"},
        {"unit": "src/Utils.pas", "slug": "utils-pas", "title": "Utils.pas"},
    ]
    chapter_types = [
        {"name": "TBase", "unit": "src/Base.pas"},
        {"name": "TFoo", "unit": "src/Foo.pas"},
        {"name": "TBar", "unit": "src/Bar.pas"},
    ]
    edges = [
        {"child_name": "tfoo", "child_display": "TFoo", "parent_name": "tbase", "parent_display": "TBase", "unit": "src/Foo.pas"},
        {"child_name": "tbase", "child_display": "TBase", "parent_name": "tobject", "parent_display": "TObject", "unit": "src/Base.pas"},
        # TBar hiç kenara sahip değil -> yalnız/izole kök
    ]
    tree = manual._build_class_tree(sections, chapter_types, edges)
    root_names = sorted(r["name"] for r in tree["roots"])
    assert root_names == ["TBar", "TObject"]

    tobj = next(r for r in tree["roots"] if r["name"] == "TObject")
    assert tobj["external"] is True and tobj["href"] is None
    assert [c["name"] for c in tobj["children"]] == ["TBase"]
    tbase = tobj["children"][0]
    assert tbase["external"] is False and tbase["href"] == "#base-pas"
    assert [c["name"] for c in tbase["children"]] == ["TFoo"]
    assert tbase["children"][0]["href"] == "#foo-pas"

    tbar = next(r for r in tree["roots"] if r["name"] == "TBar")
    assert tbar["external"] is False and tbar["href"] == "#bar-pas" and tbar["children"] == []

    assert tree["other_files"] == [{"title": "Utils.pas", "href": "#utils-pas"}]


def test_build_class_tree_cycle_is_safe():
    """Savunmacı: bozuk/döngülü kenar verisi (A<->B) sonsuz özyinelemeye
    girmemeli — çökmeden (muhtemelen boş) bir sonuç dönmeli."""
    sections = [{"unit": "A.pas", "slug": "a-pas", "title": "A.pas"}, {"unit": "B.pas", "slug": "b-pas", "title": "B.pas"}]
    chapter_types = [{"name": "A", "unit": "A.pas"}, {"name": "B", "unit": "B.pas"}]
    edges = [
        {"child_name": "a", "child_display": "A", "parent_name": "b", "parent_display": "B", "unit": "A.pas"},
        {"child_name": "b", "child_display": "B", "parent_name": "a", "parent_display": "A", "unit": "B.pas"},
    ]
    tree = manual._build_class_tree(sections, chapter_types, edges)
    assert isinstance(tree["roots"], list)


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


def test_md_to_html_fragment_applies_hljs_lang_class_to_code_fences():
    """Sıra 5 (kullanıcı): body_md içindeki kod örnekleri de highlight.js
    kullanmalı — hljs_lang verilirse fenced code blok class="language-X" alır."""
    html = manual._md_to_html_fragment("```\nTFoo = class(TBar)\nend;\n```", hljs_lang="delphi")
    assert '<pre><code class="language-delphi">' in html
    no_lang = manual._md_to_html_fragment("```\nplain\n```")
    assert '<pre><code>' in no_lang and 'class=' not in no_lang


def test_lang_switcher_active_class_does_not_collide_with_nav_active():
    """Canlı doğrulamada bulunan gerçek hata: dil rozeti class="active" kullanıyordu
    — nav a.active{color:var(--amber)!important} kuralı (bölüm vurgusu için) BUNU DA
    eşleyip !important ile eziyordu -> amber ÜSTÜNE amber (görünmez metin). Artık
    class="cur" (nav a.active seçicisiyle asla çakışmayacak bir ad)."""
    m = {**FAKE_MODEL, "translations": {"tr": {"label": "Türkçe", "sections": {}}}}
    html = manual.render_manual_html(m, "index", lang="tr")
    assert 'class="cur">Türkçe</a>' in html
    assert 'class="active">' not in html   # nav a.active ile ASLA aynı ad kullanılmamalı
    assert ".langsw a.cur" in html and "!important" in html.split(".langsw a.cur")[1].split("}")[0]


def test_render_html_index_and_chapter():
    idx = manual.render_manual_html(FAKE_MODEL, "index")
    assert "test-coll" in idx and "İçindekiler" in idx
    assert "<iframe" not in idx   # offline/self-contained — dış kaynak yok
    assert "http://" not in idx and "https://fonts" not in idx

    ch = manual.render_manual_html(FAKE_MODEL, "src")
    assert 'id="unita-pas"' in ch and 'id="unitb-pas"' in ch
    assert "[TBar]" not in ch and '<a href="/manual/test-coll/src.html#unitb-pas">TBar</a>' in ch   # cross-link uygulanmış

    # Sıra 7 (kullanıcı): Aç + Klasörde Aç + Tarayıcıda Göster — YALNIZ chunk_id'si olan bölümde (UnitA)
    assert "manualOpen('test-coll',123456,this)" in ch
    assert "manualOpenFolder('test-coll',123456,this)" in ch
    # FAKE_MODEL section lang="pascal" -> _hljs_lang eşlemesiyle "delphi" olarak geçmeli
    assert "manualShowInBrowser('test-coll',123456,'UnitA.pas',this,'delphi')" in ch

    # madde 2. tur, 2 (kullanıcı): "browserde aç" artık İÇE gömülü değil, sağ
    # panelde (index.html'deki #sidepanel deseniyle aynı) açılıyor
    assert 'id="sidepanel"' in ch and 'id="sp-body"' in ch and 'id="sp-resize"' in ch
    assert "ci-manual-spwidth" in ch
    assert 'class="sec-code"' not in ch   # eski, bölüm-içi gömülü render KALDIRILDI

    # madde 2. tur, 3/4/5 (kullanıcı): highlight.js self-hosted, her kod
    # gösteriminde (sağ panel) kullanılmalı — dinamik dil yükleyici + tema
    assert '/static/vendor/highlightjs/highlight.min.js' in ch
    assert "function manualHL(" in ch and "hljs.highlightElement" in ch
    assert ".hljs-keyword" in ch   # tema CSS'i

    # madde 2. tur, 5 (kullanıcı): body_md'deki kod örnekleri de (Public API vb.)
    # highlight.js kullanmalı — UnitA'nın gövdesinde bir ```kod bloğu``` var
    assert '<pre><code class="language-delphi">' in ch
    assert "querySelectorAll('main pre code" in ch   # sayfa yüklenince otomatik uygulanır

    # madde 2. tur (kullanıcı): manuel sayfasında da SweetAlert2 kullanılmalı — native
    # alert()/prompt() kalmamalı, self-hosted script dahil edilmeli (offline-first)
    assert '/static/vendor/sweetalert2.min.js' in ch
    assert "alert(" not in ch and "prompt(" not in ch
    assert "ciError(" in ch and "ciPrompt(" in ch

    # madde 2. tur, 3 (kullanıcı): sol menü index.html'deki sağ panel gibi
    # sürükle-daralt/genişlet olabilmeli, genişlik oturumlar arası hatırlanmalı
    assert 'id="manualnav"' in ch and 'id="navresize"' in ch
    assert "ci-manual-navw" in ch

    # madde 2. tur, 9 (kullanıcı): dil menüsünün ALTINA export menüsü — PDF/DOCX/ZIP
    assert 'class="exportmenu"' in ch
    assert "/api/manual/export?collection=test-coll&format=pdf" in ch
    assert "/api/manual/export?collection=test-coll&format=docx" in ch
    assert "/api/manual/export?collection=test-coll&format=zip" in ch
    assert ch.index('class="langsw"') < ch.index('class="exportmenu"')   # dil menüsünün ALTINDA

    # Sıra B (kullanıcı): class_tree'si OLMAYAN (eski) manuel — "Sınıflar"
    # sekmesi HİÇ görünmemeli, geriye uyumlu tek dosya listesi kalmalı
    assert 'class="navtabs"' not in ch and 'id="navview-classes"' not in ch


def test_render_html_shows_class_tree_tab_when_present():
    """Sıra B (kullanıcı): class_tree verisi VARSA sol menüde Dosyalar/Sınıflar
    sekmesi görünmeli; harici ebeveyn (TObject) tıklanamaz gri düğüm olmalı."""
    m = {**FAKE_MODEL, "chapters": [{
        **FAKE_MODEL["chapters"][0],
        "class_tree": {
            "roots": [{"name": "TObject", "href": None, "external": True, "children": [
                {"name": "TBar", "href": "#unitb-pas", "external": False, "children": [
                    {"name": "TFoo", "href": "#unita-pas", "external": False, "children": []},
                ]},
            ]}],
            "other_files": [],
        },
    }]}
    ch = manual.render_manual_html(m, "src")
    assert 'class="navtabs"' in ch and 'data-tab="classes"' in ch
    assert 'id="navview-files"' in ch and 'id="navview-classes"' in ch
    assert '<span class="ext" title=' in ch and '>TObject</span>' in ch   # harici -> tıklanamaz
    assert '<a href="/manual/test-coll/src.html#unitb-pas">TBar</a>' in ch   # kendi bölümü var -> link
    assert "function manualNavTab(" in ch

    # Sıra B/2. tur (kullanıcı): "Sınıf Ağacını Açılır Kapanır TreeList yap" —
    # çocuğu olan düğümler <details>/<summary>; yaprak (TFoo, çocuksuz) DEĞİL.
    assert "<details" in ch and "<summary>" in ch
    assert "<summary><a href=\"/manual/test-coll/src.html#unitb-pas\">TBar</a></summary>" in ch
    assert '<details open><summary><span class="ext"' in ch   # page="src"=ch.slug -> auto_open
    # yaprak TFoo <details> İÇİNDE DEĞİL, düz <a> kalmalı (çocuğu yok)
    assert '<li><a href="/manual/test-coll/src.html#unita-pas">TFoo</a></li>' in ch


def test_render_html_class_tree_collapsed_for_non_active_chapter():
    """Şu an görüntülenmeyen bir bölümün ağacı varsayılan KAPALI (no "open") gelmeli."""
    m = {**FAKE_MODEL, "chapters": [{
        **FAKE_MODEL["chapters"][0],
        "class_tree": {
            "roots": [{"name": "TFoo", "href": "#unita-pas", "external": False, "children": [
                {"name": "TSub", "href": "#unitb-pas", "external": False, "children": []},
            ]}],
            "other_files": [],
        },
    }]}
    idx = manual.render_manual_html(m, "index")   # "index" != "src" -> auto_open olmamalı
    assert "<details><summary>" in idx   # "open" ÖZNİTELİĞİ YOK
    assert "<details open>" not in idx


def test_render_manual_zip_is_relative_and_navigable_without_server():
    """Sıra 8 (kullanıcı): statik HTML export, tek ZIP, hepsi göreli linkli —
    kullanıcının netleştirdiği kısıt: sunucu olmadan file://'dan gezinilebilmeli."""
    data = manual.render_manual_zip(FAKE_MODEL)
    assert isinstance(data, bytes) and len(data) > 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert "index.html" in names and "src.html" in names
        idx = zf.read("index.html").decode("utf-8")
        src = zf.read("src.html").decode("utf-8")
    # index.html src.html'e GÖRECELİ link vermeli (mutlak /manual/... veya http YOK) —
    # "Kaynak: git — https://x" metnindeki DIŞ referans hariç (gezinme linki değil, düz metin)
    assert 'href="src.html"' in idx
    import re as _re2
    nav_hrefs_idx = _re2.findall(r'href="([^"]+)"', idx)
    nav_hrefs_src = _re2.findall(r'href="([^"]+)"', src)
    for href in nav_hrefs_idx + nav_hrefs_src:
        assert not href.startswith(("http://", "https://", "/manual/", "/api/")), \
            f"statik pakette mutlak/harici gezinme linki olmamalı: {href!r}"
    assert "/manual/" not in src
    # dil seçici / "+ Dil ekle" statik pakette YOK (canlı Ollama çağrısı gerektirir)
    assert "manualAddLang" not in src and 'class="langsw"' not in src
    # Aç / Klasörde Aç YOK (bu makinenin dosya sistemine bağlı, taşınan zip'te anlamsız)
    assert "manualOpen(" not in src and "manualOpenFolder(" not in src
    # cross-link de göreli olmalı ("[TBar](src.html#unitb-pas)")
    assert 'href="src.html#unitb-pas"' in src
    # madde 2. tur, 2 (kullanıcı): statik pakette de "Kaynağı Göster" sağ panelde
    # açılır — ama fetch() YOK, kaynak <template> içine GÖMÜLÜ (offline çalışır)
    assert 'id="sidepanel"' in src and "manualShowSource(" in src
    assert "<template id=\"code-unita-pas\">" in src or "fetch(" not in src

    # madde 2. tur, 3/4/5 (kullanıcı): highlight.js statik pakette de çalışmalı —
    # ama /static/vendor/... (SUNUCU-bağımlı, mutlak) DEĞİL, ZIP'in İÇİNDE göreli
    # bir "highlightjs/" alt klasörü olarak (Sıra 8'in server-free kısıtına uyar)
    src_attrs = _re2.findall(r'src="([^"]+)"', idx) + _re2.findall(r'src="([^"]+)"', src)
    for s in src_attrs:
        assert not s.startswith(("http://", "https://", "/static/")), f"statik pakette mutlak script yolu olmamalı: {s!r}"
    assert 'src="highlightjs/highlight.min.js"' in src
    assert "highlightjs/languages/" in src   # manualHL'in dinamik yükleyicisi
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert "highlightjs/highlight.min.js" in names
        assert "highlightjs/languages/delphi.min.js" in names   # FAKE_MODEL lang="pascal" -> delphi
        assert "highlightjs/languages/python.min.js" not in names   # kullanılmayan dil paketlenmemeli


def test_render_html_missing_chapter_is_404():
    missing = manual.render_manual_html(FAKE_MODEL, "hic-yok")
    assert "404" in missing


def test_cross_link_query_string_comes_before_fragment_not_after():
    """Kullanıcı bulgusu: Türkçe görüntülerken bir çapraz-referansa (class/tip
    adı) tıklayınca İngilizce (baz) sayfaya gidiyordu. Kök neden: type_home
    değerleri zaten "{slug}.html#{section}" biçiminde (FRAGMENT dahil); qs
    ("?lang=tr") SONA eklenince "...html#section?lang=tr" çıkıyordu — bu
    GEÇERSİZ bir URL'dir ("?query" HER ZAMAN "#fragment"tan ÖNCE gelmeli),
    tarayıcı "?lang=tr" kısmını fragment'ın PARÇASI sayıp query'yi tamamen
    kaybediyordu. Doğrusu: "...html?lang=tr#section"."""
    m = {**FAKE_MODEL, "translations": {"tr": {"label": "Türkçe", "sections": {
        "src|unita-pas": "## Amaç\nBu birim TFoo sınıfını tanımlar ve TBar temel sınıfından türer.\n\n```\nTFoo = class(TBar)\n```",
    }}}}
    ch = manual.render_manual_html(m, "src", lang="tr")
    # doğru sıra: ".html?lang=tr#slug" — YANLIŞ sıra (".html#slug?lang=tr") ASLA görünmemeli
    assert '<a href="/manual/test-coll/src.html?lang=tr#unitb-pas">TBar</a>' in ch
    assert "src.html#unitb-pas?lang=tr" not in ch
    assert "?lang=tr#" in ch   # query HER ZAMAN fragment'tan önce


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
        if href == "#":
            continue   # yalnız-fragment (ör. "+ Dil ekle") — mevcut sayfaya işaret eder, JS ile ele alınır
        if href == "/manual/test-coll":
            continue   # koleksiyon KÖKÜNE (indekse) mutlak-yol linki — trailing slash sorunundan bağımsız güvenli
        if href.startswith("/api/"):
            continue   # Sıra 9: export menüsü — kök-mutlak API ucu, /manual/{collection} altında DEĞİL (kasıtlı)
        resolved = urljoin(page_url_no_trailing_slash, href)
        assert resolved.startswith("http://x/manual/test-coll/"), \
            f"{href!r} göreceli çözüldü ve koleksiyon adını kaybetti: {resolved}"


def test_pygments_lex_colors_keywords_and_falls_back_gracefully():
    """Sıra 3. tur (kullanıcı): "PDF/DOCX'te de syntax highlighting kullanılacak"
    — pygments taklit EDİLMEDEN gerçek tokenize sonucu doğrulanır (kütüphane
    zaten hafif/hızlı, Ollama gibi yavaş/kararsız değil)."""
    parts = manual._pygments_lex("TFoo = class(TBar)\nend;", "pascal")
    colored = [(c, t) for c, t in parts if c]
    assert any(c == "C58A37" and "class" in t for c, t in colored)   # keyword -> amber-d
    # dil boşsa ya da pygments tanımıyorsa TEK renksiz parçaya sessizce düşer
    assert manual._pygments_lex("foo bar", "") == [(None, "foo bar")]
    assert manual._pygments_lex("foo bar", "__kesinlikle-yok-boyle-bir-dil__") == [(None, "foo bar")]


def test_render_docx_produces_valid_zip():
    data = manual.render_manual_docx(FAKE_MODEL)
    assert data[:2] == b"PK"   # docx bir zip arşividir
    assert len(data) > 1000


def test_render_docx_code_block_has_pygments_colored_runs():
    """Sıra 3. tur: DOCX'teki kod bloğunda GERÇEKTEN renkli run'lar var mı —
    üretilen .docx (bir zip) açılıp document.xml içinde amber-d rengi aranır."""
    data = manual.render_manual_docx(FAKE_MODEL)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert 'w:val="C58A37"' in xml   # UnitA'nın body_md'sindeki ```class``` bloğu


def test_render_pdf_produces_valid_pdf():
    data = manual.render_manual_pdf(FAKE_MODEL)
    assert data[:5] == b"%PDF-"
    assert len(data) > 500


def test_load_manual_missing_returns_none():
    assert manual.load_manual("__kesinlikle_yok_boyle_bir_koleksiyon") is None


def test_model_for_lang_pure():
    """Sıra 5 (kullanıcı): i18n — model_for_lang saf fonksiyon: çeviri yoksa/baz
    dilse model AYNEN döner (mutasyon YOK); çeviri varsa yalnız body_md değişir,
    yapı (slug/chunk_id/lang rozeti) AYNEN kalır; çevrilmemiş bir bölüm baz dile
    SESSİZCE düşer (hiç boş görünmez)."""
    base = manual.model_for_lang(FAKE_MODEL, "")
    assert base is FAKE_MODEL   # dönüşüm yok -> aynı nesne (gereksiz kopya değil)
    assert manual.model_for_lang(FAKE_MODEL, "en") is FAKE_MODEL   # "en" zaten baz dil (FAKE_MODEL'de lang alanı yok -> varsayılan "en")

    m = {**FAKE_MODEL, "translations": {"tr": {"label": "Türkçe", "sections": {
        "src|unita-pas": "## Amaç (TR)\nÇevrilmiş metin."}}}}
    tr = manual.model_for_lang(m, "tr")
    assert tr is not m   # KOPYA — özgün asla mutasyona uğramaz
    sec_a = tr["chapters"][0]["sections"][0]
    sec_b = tr["chapters"][0]["sections"][1]
    assert sec_a["body_md"] == "## Amaç (TR)\nÇevrilmiş metin."
    assert sec_b["body_md"] == FAKE_MODEL["chapters"][0]["sections"][1]["body_md"]   # çevrilmemiş -> baz dile düşer
    assert sec_a["slug"] == "unita-pas" and sec_a["chunk_id"] == 123456   # yapı korunur
    assert FAKE_MODEL["chapters"][0]["sections"][0]["body_md"].startswith("## Amaç\n")   # özgün DEĞİŞMEDİ


def test_translate_manual_saves_and_caches_per_section(tmp_path, monkeypatch):
    """translate_manual: chunk_id'siz saf model diske yazılıp AI çağrısı
    monkeypatch'lenir (gerçek Ollama gerektirmez — canlı Ollama doğrulaması
    ayrıca panel ile elle yapıldı). force=False iken zaten çevrilmiş bölüm
    TEKRAR çevrilmemeli (önbellek section-bazlı)."""
    monkeypatch.setattr(manual, "MANUAL_DIR", tmp_path)
    coll = "__test_translate_pure"
    manual._save_manual(coll, json.loads(json.dumps(FAKE_MODEL)))   # derin kopya, diske yaz

    calls = []
    def fake_generate(model, prompt, num_predict=1400):
        calls.append(prompt)
        return f"[ÇEVİRİ #{len(calls)}]"
    monkeypatch.setattr(manual.retrieval, "ollama_generate", fake_generate)

    r = manual.translate_manual(coll, "tr", "Türkçe")
    assert r == {"ok": True, "lang": "tr", "label": "Türkçe", "sections": 2}
    assert len(calls) == 2   # FAKE_MODEL'de 2 section var
    saved = manual.load_manual(coll)
    assert saved["translations"]["tr"]["label"] == "Türkçe"
    assert set(saved["translations"]["tr"]["sections"]) == {"src|unita-pas", "src|unitb-pas"}
    # özgün İngilizce body_md HİÇ değişmedi (çeviri ayrı alanda)
    assert saved["chapters"][0]["sections"][0]["body_md"] == FAKE_MODEL["chapters"][0]["sections"][0]["body_md"]

    # ikinci çağrı (force=False) -> zaten çevrilmiş, YENİ AI çağrısı olmamalı
    r2 = manual.translate_manual(coll, "tr", "Türkçe")
    assert r2["sections"] == 2 and len(calls) == 2   # calls sayısı ARTMADI

    # aynı dile (baz) çeviri istemek hata vermeli
    assert "error" in manual.translate_manual(coll, "en", "English")
    # üretilmemiş koleksiyon hata vermeli
    assert "error" in manual.translate_manual("__hic_yok", "tr")


def test_list_manual_languages(tmp_path, monkeypatch):
    monkeypatch.setattr(manual, "MANUAL_DIR", tmp_path)
    coll = "__test_langs"
    assert manual.list_manual_languages(coll) == []   # üretilmemiş -> boş liste
    m = json.loads(json.dumps(FAKE_MODEL))
    m["translations"] = {"tr": {"label": "Türkçe", "sections": {}}}
    manual._save_manual(coll, m)
    langs = manual.list_manual_languages(coll)
    assert {"code": "en", "label": "English", "base": True} in langs
    assert {"code": "tr", "label": "Türkçe", "base": False} in langs


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
