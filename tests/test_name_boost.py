"""İsim-eşleşme boost'u — orantılılık regresyon testleri.

Saf testler: Qdrant/Ollama gerektirmez.

KİLİTLENEN GERÇEK HATA (kullanıcı bildirimi, 2026-08-11): boost iki kademeliydi —
sorgunun TÜM kelimeleri isimde geçiyorsa 3.0, HERHANGİ biri geçiyorsa düz 1.5.
İkinci kademe hiçbir şeyi ayırt etmiyordu:

    "UUID oluşturma" sorgusunda adında "uuid" geçen HER aday, ismi ne kadar
    alakalı olursa olsun aynı 1.5 çarpanını alıyordu.

Yani boost, tam eşleşme dışındaki her durumda sıralamaya bilgi KATMIYOR, sadece
"en az bir kelimesi tutan" adayları topluca yukarı itiyordu. Artık çarpan
eşleşmenin gücüyle orantılı (kapsam × kesinlik düzelticisi).

Ölçülmüş etki (golden set, 60 soru, hibrit, k=8): GENEL MRR 0.560 -> 0.581,
nDCG@8 0.594 -> 0.618; en zayıf koleksiyon mORMot2 MRR 0.436 -> 0.505.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from retrieval import NAME_BOOST_MAX, _name_boost, _tokenize


def boost(query: str, name: str) -> float:
    return _name_boost(_tokenize(query), _tokenize(name))


def test_partial_matches_do_not_all_get_the_same_multiplier():
    """ASIL HATA: adında "uuid" geçen her şey aynı düz 1.5'i alıyordu.

    Üç aday da sorgudan yalnız "uuid"i tutuyor ama isimlerinin ne kadarı
    sorguyla ilgili farklı — çarpanları da farklı olmalı."""
    q = "uuid oluşturma"
    scores = {n: boost(q, n) for n in ("TUuid", "UuidToText", "TSynUuidGeneratorHelper")}
    assert len(set(scores.values())) == 3, f"boost hala ayirt etmiyor: {scores}"
    # Kısa ve odaklı isim, sorgu-dışı kelimelerle dolu isimden yukarıda olmalı
    assert scores["TUuid"] > scores["UuidToText"] > scores["TSynUuidGeneratorHelper"]


def test_more_of_the_query_matched_means_a_bigger_boost():
    """Kapsam baskın terim: sorgunun 2/2'sini tutan, 1/2'sini tutandan yüksek."""
    assert boost("uuid oluşturma", "UuidOluşturma") > boost("uuid oluşturma", "UuidToText")


def test_exact_name_match_still_gets_the_maximum():
    """Eski davranışın DOĞRU olan tarafı korunmalı: birebir eşleşme tavanı alır."""
    assert boost("split string", "SplitString") == NAME_BOOST_MAX


def test_exact_match_outranks_a_name_that_merely_contains_the_query():
    """Eskiden ikisi de 3.0 alıyordu (q ⊆ n yeterliydi) — birebir isim,
    fazladan kelimelerle şişmiş isimden önce gelmeli."""
    assert boost("split string", "SplitString") > boost("split string", "TStringHelperSplitStringEx")


def test_no_shared_word_means_no_boost():
    assert boost("uuid oluşturma", "CompressMem") == 1.0


def test_boost_never_exceeds_the_ceiling():
    """Çarpan füzyon skoruyla çarpıldığı için üst sınır gerçekten bağlayıcı."""
    for q, n in (("split string", "SplitString"), ("uuid", "TUuid"),
                 ("a", "A"), ("parse block seq", "ParseBlockSeq")):
        assert 1.0 <= boost(q, n) <= NAME_BOOST_MAX


def test_empty_sides_are_neutral():
    assert _name_boost(set(), {"split"}) == 1.0
    assert _name_boost({"split"}, set()) == 1.0
