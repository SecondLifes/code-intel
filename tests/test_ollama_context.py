"""Ollama bağlam penceresi (num_ctx) sözleşmesi — regresyon testleri.

Saf testler: Ollama/Qdrant gerektirmez.

Kilitlenen gerçek hata (canlı doğrulandı, 2026-08-11): CodeIntel
get_context_pack() ile token_budget'a göre (6000-8000 token) özenle bir bağlam
paketi kuruyor, ama Ollama isteğinde `num_ctx` GÖNDERİLMİYORDU. Ollama'nın
varsayılanı 4096 token (resmî FAQ) ve fazlasını sessizce kırpıyor — hata da
uyarı da yok. `ollama ps` çıktısı 24.000 karakterlik bir bağlamda bile
"CONTEXT 4096" gösteriyordu; yani bağlam paketinin büyük kısmı modele hiç
ulaşmıyor, cevaplar eksik bağlamdan üretiliyordu.

Düzeltme sonrası aynı ölçüm: "CONTEXT 7241".
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from retrieval import CTX_MAX, CTX_MIN, fit_num_ctx


def test_small_prompt_keeps_ollama_default():
    """Küçük prompt'ta davranış değişmemeli — gereksiz yere KV cache büyütüp
    VRAM harcamanın anlamı yok."""
    assert fit_num_ctx("kısa soru", 600) == CTX_MIN


def test_deep_research_sized_prompt_grows_beyond_default():
    """ASIL HATA: ~24.000 karakterlik (derin arama boyutu) bir bağlam 4096'ya
    kırpılıyordu. Artık pencere prompt'u kapsayacak kadar büyümeli."""
    got = fit_num_ctx("x" * 24_000, 3000)
    assert got > CTX_MIN, "derin arama bağlamı hâlâ varsayılana kırpılıyor"
    assert got >= 24_000 / 4, "pencere prompt'un tamamını taşıyacak kadar büyük değil"


def test_window_leaves_room_for_the_answer():
    """Pencere yalnız prompt'u değil, üretilecek cevabı da kapsamalı — yoksa
    model cevabın ortasında bağlam sınırına çarpar."""
    prompt = "x" * 20_000
    assert fit_num_ctx(prompt, 3000) >= fit_num_ctx(prompt, 300) + 2000


def test_capped_so_kv_cache_cannot_exhaust_vram():
    """Üst sınır bilinçli: num_ctx büyüdükçe KV cache VRAM'i büyür. Bu makinede
    modeller zaten VRAM'i aşıp CPU'ya taşıyor (Ollama log'u: '49 layers
    (13 overflowing)') — sınırsız büyütmek durumu kötüleştirir."""
    assert fit_num_ctx("x" * 5_000_000, 3000) == CTX_MAX


def test_monotonic_in_prompt_size():
    """Daha büyük prompt asla daha küçük pencere üretmemeli."""
    sizes = [fit_num_ctx("x" * n, 600) for n in (1_000, 10_000, 50_000, 500_000)]
    assert sizes == sorted(sizes)
