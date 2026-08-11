"""Panel eş zamanlılığı: akış sürerken başlatılan İKİNCİ arama regresyonları.

KİLİTLENEN HATA (kullanıcı ekran görüntüsü, 2026-08-11):
    "TypeError: Cannot set properties of null (setting 'innerHTML')"
    "...ekran bir süre kilitleniyor sonra sonuçlar geliyor"

run() yalnız $('go') düğmesini kilitliyordu, ama run() üç ayrı yoldan daha
çağrılabiliyor: Enter tuşu (input onkeydown), öneri çipleri (pick()) ve
jumpTo(). Akış sürerken ikinci bir arama $('out')'u sıfırlayınca #ans/#anssrc/
#cmpwrap DOM'dan siliniyor, hâlâ dönen ESKİ akış döngüsü null'a innerHTML
yazıp patlıyordu — ve o TypeError eski run()'ın catch'inde err() ile kırmızı
kutuya dönüşüp YENİ aramanın sonucunun üzerine basılıyordu.

Testler `tests/panel_overlap_harness.mjs`'yi çalıştırır: harness index.html'den
run()/runAskStream()'i GERÇEKTEN çıkarıp sahte bir DOM üzerinde koşturur, string
araması yapmaz. Düzeltme öncesi sürüme karşı koşulup hatayı yakaladığı
doğrulandı (`node tests/panel_overlap_harness.mjs <eski_index.html>`).

Node yoksa atlanır: bu depo pytest tabanlıdır ve node beyan edilmiş bir bağımlılık
değildir — çıplak bir checkout'ta varsayılan koşu yeşil kalmalı.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

HARNESS = pathlib.Path(__file__).parent / "panel_overlap_harness.mjs"
pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node yok — panel JS davranış testi atlanıyor")


@pytest.fixture(scope="module")
def result() -> dict:
    proc = subprocess.run(["node", str(HARNESS)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"harness çöktü:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_overlapping_search_does_not_set_innerhtml_on_null(result):
    """Akış yarıdayken ikinci arama başlarsa eski döngü null'a yazmamalı."""
    assert result["crashed"] is None, (
        f"eski akış silinmiş DOM'a yazdı: {result['crashed']} — {result['out_html']}")


def test_stale_stream_error_does_not_overwrite_new_search_output(result):
    """Bayat akışın hatası YENİ aramanın çıktısını ezmemeli.

    Kullanıcının gördüğü sıra tam olarak buydu: önce kırmızı hata kutusu, sonra
    (yeni aramanın) sonuçları. #out yalnız en son aramaya ait olmalı."""
    assert result["out_belongs_to_second"], f"#out bayat hata kutusu ile ezilmiş: {result['out_html']}"


def test_new_search_aborts_the_previous_in_flight_stream(result):
    """Yeni arama öncekini GERÇEKTEN iptal etmeli.

    Yalnız DOM yazımını engellemek yetmez: sunucudaki üretim sürüyor (derin
    modda ~220 sn GPU meşgul) — "ekran bir süre kilitleniyor" hissinin sebebi
    buydu. AbortController olmadan bu sayı 0 kalır."""
    assert result["aborted"] >= 1, "önceki istek iptal edilmedi (AbortController yok/bağlı değil)"
