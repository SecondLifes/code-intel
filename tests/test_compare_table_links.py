"""Stabilite/Performans tablosundan fonksiyona atlama — regresyon testleri.

KULLANICI İSTEĞİ (madde 1): "Tablodan dosya/fonksiyon adına tıklayınca ilgili
fonksiyona gitsin; ayrıca oradan doğrudan 'Tarayıcıda Göster' yapılabilsin."

Kilitlenen asıl bağ: atlama ancak tablonun ürettiği hedef, kaynak kartının
GERÇEK DOM id'siyle aynı şemayı kullanırsa çalışır —
    srcCard()          -> <div class="src" id="s{hit.id}">
    cmpJump()          -> $('s'+hit.id)
Bu iki yer birbirinden habersiz değişirse atlama SESSİZCE bozulur: tıklama
hiçbir şey yapmaz, hata da vermez. Harness ikisini de index.html'den çıkarıp
gerçekten çalıştırır ve id'leri karşılaştırır.

Node yoksa atlanır (bkz. tests/test_panel_overlap.py'deki aynı gerekçe).
"""
import json
import pathlib
import shutil
import subprocess

import pytest

HARNESS = pathlib.Path(__file__).parent / "compare_table_harness.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node yok — panel JS davranış testi atlanıyor")


@pytest.fixture(scope="module")
def result() -> dict:
    proc = subprocess.run(["node", str(HARNESS)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"harness çöktü:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_table_jump_target_matches_the_real_source_card_id(result):
    """Tablonun atlama hedefi ile srcCard'ın ürettiği id AYNI olmalı."""
    assert result["jump_target_matches_card_id"], (
        f"atlama hedefi kart id'siyle uyusmuyor: {result['target_from_table']} != {result['card_id']}")


def test_both_the_function_name_and_the_file_name_are_clickable(result):
    """Kullanıcı "dosya/fonksiyon adına" dedi — ikisi de tıklanabilir olmalı,
    yani 2 satır için 4 atlama kancası."""
    assert result["jump_hooks"] == 4, f"beklenen 4 atlama kancasi, bulunan {result['jump_hooks']}"


def test_every_row_offers_show_in_browser_directly(result):
    """"Oradan doğrudan Tarayıcıda Göster" — her satırda bir düğme, ve satır
    numaraları CMP_HITS'e 1 tabanlı doğru eşlenmeli."""
    assert result["browser_buttons"] == [1, 2], result["browser_buttons"]


def test_row_indexes_stay_1_based_and_in_range(result):
    """i, CMP_HITS'e 1 tabanlı indeks — 0 tabanlıya kayması sessizce yanlış
    fonksiyona götürürdü."""
    assert result["jump_indexes_are_1_based_and_in_range"]
    assert result["rows_rendered"] == 2
