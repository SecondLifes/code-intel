"""Derin araştırma (research_stream) kaynak kartı sözleşmesi — regresyon testleri.

Hepsi SAF: Qdrant/Ollama gerektirmez, her ortamda çalışır (bkz.
.agents/rules/testing.md'nin iki katmanlı ayrımı — dış servis isteyen testler
tests/manual/'a ait).

Kilitlenen gerçek hata (kullanıcı bildirimi + ekran görüntüsü, 2026-08-11):
"Tarayıcıda Göster" çoğu sonuçta ilgili fonksiyona konumlanmıyor, kod genişletme
düğmesi çalışmıyordu. Kök neden UI değil, bu eşlemeydi: kaynak kartları satır
aralığını "L0-0" (related section'lar) veya "L143-143" (primary; line_end
yanlışlıkla line_start'tan kopyalanmış) olarak alıyordu.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.api.search_routes import _bare_name, section_to_hit


def test_line_end_is_not_copied_from_line_start():
    """ASIL HATA: line_end, line_start'tan okunuyordu — çok satırlı her fonksiyon
    UI'da tek satırlıkmış gibi görünüyordu (ekran görüntüsünde 'L143-143')."""
    hit = section_to_hit({"kind": "primary", "title": "X", "text": "kod",
                          "line_start": 6517, "line_end": 6521})
    assert hit["line_start"] == 6517
    assert hit["line_end"] == 6521, "line_end line_start'tan kopyalanmamalı"


def test_related_section_line_range_survives():
    """İKİNCİ YARISI: related section'lar satır alanlarını taşımayınca 0'a düşüp
    UI'da 'L0-0' oluyordu; retrieval.py artık taşıyor, buradan da geçmeli."""
    hit = section_to_hit({"kind": "related", "title": "Y", "text": "kod",
                          "line_start": 3918, "line_end": 3935})
    assert (hit["line_start"], hit["line_end"]) == (3918, 3935)


def test_missing_line_fields_degrade_to_zero_not_crash():
    """Satır alanı gerçekten yoksa 0'a düşmek DOĞRU davranış (UI 'L0-0' gösterir),
    ama KeyError ile 500'e düşmek değil — bu ayrımı kilitler."""
    hit = section_to_hit({"kind": "related", "title": "Z", "text": "kod"})
    assert hit["line_start"] == 0 and hit["line_end"] == 0


def test_line_zero_is_treated_as_missing_not_valid():
    """`or 0` kullanımı bilinçli: 0 geçerli bir satır numarası değil (dosyalar
    1'den başlar), o yüzden 0 ve None aynı şekilde ele alınmalı."""
    hit = section_to_hit({"kind": "related", "title": "Z", "text": "kod",
                          "line_start": 0, "line_end": None})
    assert hit["line_start"] == 0 and hit["line_end"] == 0


def test_unit_suffix_stripped_from_display_name():
    """Kaynak kartındaki isimden ' (unit.pas)' soyulmalı — unit zaten meta
    satırında ayrıca gösteriliyor."""
    s = {"kind": "primary", "title": "ObjectUuidToText (src/core/mormot.core.os.pas)",
         "unit": "src/core/mormot.core.os.pas", "text": "kod"}
    assert section_to_hit(s)["name"] == "ObjectUuidToText"


def test_unit_suffix_only_stripped_when_it_actually_matches():
    """Başka bir parantezli son ek yanlışlıkla kesilmemeli."""
    s = {"kind": "primary", "title": "Split (overloaded)", "unit": "a/b.pas", "text": "kod"}
    assert _bare_name(s) == "Split (overloaded)"


def test_code_is_truncated_to_ui_budget():
    """Kaynak kartı gövdesi 1200 karakterle sınırlı — SSE meta olayı şişmesin."""
    s = {"kind": "related", "title": "big", "text": "x" * 5000}
    assert len(section_to_hit(s)["code"]) == 1200
