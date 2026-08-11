"""Stabilite/Performans puanlarının sıralamaya etkisi — regresyon testleri.

Saf testler: Qdrant/Ollama gerektirmez (Qdrant istemcisi sahte bir nesneyle
değiştirilir, yalnızca eşleme/kırpma mantığı sınanır).

KULLANICI İSTEĞİ (madde 2): "Karşılaştırma tablosundaki puanlar arama
sıralamasını etkilesin."

KULLANICI KARARI (bu oturumda açıkça soruldu ve seçildi):
  - etki ZAYIF olsun, yalnızca eşitlik bozucu,
  - YALNIZCA puanlanan chunk'a uygulansın (aynı isimli diğerlerine değil).
Gerekçe: bu puanlar gerçek profiling DEĞİL, kod okumaya dayalı LLM tahminidir
(/api/compare prompt'u bunu modele de söylüyor). Güçlü bir çarpan, yanlış bir
tahminin alakalı sonucu aşağı itmesi demek olurdu. Aşağıdaki sınır testleri bu
kararı kilitler: bandı sessizce genişleten bir değişiklik testi düşürür.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import pytest

import retrieval
from retrieval import (CMP_SCORE_NEUTRAL, CMP_SCORE_WEIGHT, _cmp_multiplier,
                       _cmp_point_id, save_compare_scores)


class FakeQdrant:
    """upsert edilen noktaları yakalar — gerçek sunucu gerekmez."""

    def __init__(self):
        self.points = []
        self.created = []

    def collection_exists(self, name):
        return name in self.created

    def create_collection(self, name, **kw):
        self.created.append(name)

    def upsert(self, name, points):
        self.points.extend(points)


@pytest.fixture
def fake_cl(monkeypatch):
    fake = FakeQdrant()
    monkeypatch.setattr(retrieval, "cl", fake)
    monkeypatch.setattr(retrieval, "_cmp_cache_at", 0.0)
    return fake


HITS = [
    {"collection": "mORMot2", "id": 111, "name": "CompressMem", "unit": "core.pas"},
    {"collection": "mORMot2", "id": 222, "name": "Compress", "unit": "core.pas"},
]


# ---------------- çarpanın şekli (kullanıcı kararı) ----------------

def test_midpoint_score_has_no_effect_on_ranking():
    """Ölçeğin ortası puanlanmamış adayla EŞİT olmalı — yoksa tabloyu bir kez
    üretmek, puanı vasat çıkan her şeyi topluca aşağı/yukarı iterdi."""
    assert _cmp_multiplier(CMP_SCORE_NEUTRAL) == pytest.approx(1.0)


def test_effect_stays_a_weak_tiebreaker():
    """Kullanıcı kararı: etki zayıf. Band 1 ± CMP_SCORE_WEIGHT dışına çıkamaz."""
    for score in (1.0, 3.0, 5.5, 7.0, 10.0):
        m = _cmp_multiplier(score)
        assert 1.0 - CMP_SCORE_WEIGHT - 1e-9 <= m <= 1.0 + CMP_SCORE_WEIGHT + 1e-9, score
    assert CMP_SCORE_WEIGHT <= 0.2, "band tie-breaker olmaktan cikmis"


def test_higher_score_outranks_lower_for_otherwise_equal_candidates():
    base = 0.5
    assert base * _cmp_multiplier(9.0) > base * _cmp_multiplier(4.0)


def test_a_good_score_cannot_overturn_a_clearly_better_match():
    """ZAYIF olmanın asıl anlamı: yanlış bir LLM tahmini, füzyonun açıkça daha
    alakalı bulduğu sonucu tepeden indirememeli."""
    strong_but_unscored = 1.00
    weak_but_top_scored = 0.80 * _cmp_multiplier(10.0)
    assert strong_but_unscored > weak_but_top_scored


# ---------------- kalıcılaştırma eşlemesi ----------------

def test_scores_are_keyed_to_the_actual_hit_not_the_model_echo(fake_cl):
    """Model "name" alanına dosya/satır bilgisi karıştırabiliyor (canlı görüldü);
    koleksiyon/id her zaman asıl hit'ten alınmalı."""
    rows = [{"i": 1, "name": "Split (mORMot/SynCommons.pas L3193)", "stability": 8, "performance": 6}]
    assert save_compare_scores(rows, HITS, "q") == 1
    payload = fake_cl.points[0].payload
    assert (payload["collection"], payload["chunk_id"]) == ("mORMot2", 111)
    assert payload["combined"] == pytest.approx(7.0)


def test_rescoring_the_same_chunk_overwrites_instead_of_accumulating(fake_cl):
    """Deterministik nokta id'si: aynı chunk ikinci kez puanlanınca üzerine
    yazılmalı, yoksa çelişen kayıtlar birikir ve hangisinin geçerli olduğu
    belirsizleşirdi."""
    first = save_compare_scores([{"i": 1, "stability": 9, "performance": 9}], HITS)
    second = save_compare_scores([{"i": 1, "stability": 2, "performance": 2}], HITS)
    assert first == second == 1
    assert fake_cl.points[0].id == fake_cl.points[1].id == _cmp_point_id("mORMot2", 111)


def test_out_of_range_model_output_is_clamped(fake_cl):
    """Model 1-10 dışına çıkabiliyor; kırpılmazsa çarpan bandı delinir."""
    save_compare_scores([{"i": 1, "stability": 99, "performance": -5}], HITS)
    p = fake_cl.points[0].payload
    assert p["stability"] == 10.0 and p["performance"] == 1.0
    assert 1.0 - CMP_SCORE_WEIGHT <= _cmp_multiplier(p["combined"]) <= 1.0 + CMP_SCORE_WEIGHT


def test_bogus_row_index_is_skipped_not_crashed(fake_cl):
    """Model bazen var olmayan bir sıra numarası uyduruyor — tablo düşmemeli."""
    rows = [{"i": 99, "stability": 8, "performance": 8},
            {"i": "x", "stability": 8, "performance": 8},
            {"i": 2, "stability": 7, "performance": 7}]
    assert save_compare_scores(rows, HITS) == 1
    assert fake_cl.points[0].payload["chunk_id"] == 222


def test_saving_never_raises_when_qdrant_is_down(monkeypatch):
    """Puan saklamak bir iyileştirme — tabloyu düşürmemeli."""
    class Broken:
        def collection_exists(self, *a, **k):
            raise RuntimeError("qdrant yok")
    monkeypatch.setattr(retrieval, "cl", Broken())
    assert save_compare_scores([{"i": 1, "stability": 8, "performance": 8}], HITS) == 0
