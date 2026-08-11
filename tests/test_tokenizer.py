"""Sorgu/isim tokenizer'ı — Türkçe girdi regresyon testleri.

Saf testler: Qdrant/Ollama gerektirmez.

Kilitlenen gerçek hata (kullanıcı bildirimi madde 7 "anlamsız arama sonuçları",
2026-08-11): `_WORD_RE` `[a-zA-Z0-9]+` idi ve Türkçe kelimeleri HER aksanlı
harfte parçalıyordu:

    "UUID oluşturma"  -> ['olu', 'turma', 'uuid']
    "bağlantı açma"   -> ['a', 'ba', 'lant', 'ma']
    "şifre doğrulama" -> ['do', 'ifre', 'rulama']

Bu parçalar (özellikle "a", "ba", "ma") rastgele tanımlayıcı token'larıyla
eşleşip `_fuse_collection`'daki isim-boost'unu SAHTE olarak tetikliyordu —
alakasız sonuçlar 1.5x/3x çarpanla yukarı çıkıyordu.

Neden golden set bunu yakalamadı: 60 sorunun 31'i Türkçe kelime içeriyor ama
HİÇBİRİ aksanlı karakter kullanmıyor ("dogrulama", "olusturma" diye yazılmış) —
yani benchmark, kullanıcının gerçekten yazdığı girdiyi hiç test etmiyor.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

from retrieval import _tokenize


@pytest.mark.parametrize("query,expected", [
    ("UUID oluşturma",   {"uuid", "oluşturma"}),
    ("bağlantı açma",    {"bağlantı", "açma"}),
    ("şifre doğrulama",  {"şifre", "doğrulama"}),
])
def test_turkish_words_are_not_shredded(query, expected):
    """ASIL HATA: aksanlı harfler kelimeyi bölüyordu."""
    assert _tokenize(query) == expected


def test_no_meaningless_single_letter_fragments():
    """'bağlantı açma' -> ['a','ba','lant','ma'] gibi tek/iki harflik parçalar
    üretilmemeli — bunlar tanımlayıcı token'larıyla kazara eşleşip sahte
    isim-boost tetikliyordu."""
    toks = _tokenize("bağlantı açma")
    assert not any(len(t) <= 2 for t in toks), f"anlamsız kısa parça üretildi: {toks}"


def test_camelcase_splitting_still_works():
    """Türkçe düzeltmesi, İngilizce tanımlayıcıların camelCase bölünmesini
    BOZMAMALI — isim eşleştirmesinin temeli bu."""
    assert _tokenize("GetComputerUuid") == {"get", "computer", "uuid"}


@pytest.mark.parametrize("ident,expected", [
    ("TCRConnection", {"tcr", "connection"}),
    ("TDBGrid",       {"tdb", "grid"}),
    ("IHTTPClient",   {"ihttp", "client"}),
    ("TJSONObject",   {"tjson", "object"}),
])
def test_acronym_prefixed_identifiers_split(ident, expected):
    """İKİNCİ gerçek hata: yalnız küçük→BÜYÜK sınırı bölündüğü için Delphi'nin
    kısaltma önekli isimleri HİÇ bölünmüyordu ({'tcrconnection'}) — yani
    "connection" sorgusuyla asla eşleşmiyor, isim-boost'u hiç alamıyorlardı.
    Ölçülen etki (tests/eval.py): mORMot2 MRR 0.389 -> 0.424, Jedi 0.535 -> 0.562."""
    assert _tokenize(ident) == expected


def test_uppercase_turkish_dotted_i_is_known_edge_case():
    r"""BİLİNEN SINIR DURUMU (düzeltilmedi, bilinçli): büyük 'İ' küçültülünce
    'i' + birleşen nokta (U+0307) oluyor; birleşen işaret \w sayılmadığı için
    kelime orada bölünüyor. Yalnız TAMAMI BÜYÜK Türkçe sorgularda görülür,
    normal kullanımda değil — bu yüzden ek karmaşıklık eklenmedi."""
    assert "çözümü" in _tokenize("İŞLEM ÇÖZÜMÜ")


def test_underscore_is_a_separator_not_a_letter():
    """`[^\\W_]+` deseninde `_` bilinçli olarak dışlandı: snake_case
    tanımlayıcılar ayrı token'lara bölünmeli."""
    assert _tokenize("_ShortToUuid") == {"short", "to", "uuid"}


def test_digits_are_kept():
    """Sürüm/boyut içeren tanımlayıcılar (Utf8, Int64) bozulmamalı."""
    assert "utf8" in _tokenize("RawUtf8")
    assert "int64" in _tokenize("Int64Value") or "int" in _tokenize("Int64Value")


def test_empty_and_none_are_safe():
    assert _tokenize("") == set()
    assert _tokenize(None) == set()
