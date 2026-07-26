# CodeIntel'e Katkıda Bulunma

Öncelikle katkıda bulunmayı düşündüğünüz için teşekkürler! Bu aracı kullanan herkes için daha iyi hale getiren sizin gibi insanlar.

Bu projeye katılarak [Davranış Kuralları](CODE_OF_CONDUCT.md)'na uymayı kabul etmiş olursunuz.

## Nasıl Katkıda Bulunabilirim?

### Hata Bildirme

* Hatanın daha önce bildirilip bildirilmediğini görmek için [issue takipçisini]([FILL IN: repo URL]/issues) kontrol edin.
* Bildirilmemişse yeni bir issue açın. Sorunu net şekilde tanımlayın ve tekrar üretme adımlarını ekleyin — arama kalitesi sorunları için tam sorguyu ve koleksiyonu, indeksleme sorunları için dil/dosya desenini ekleyin.

### İyileştirme Önerme

* `enhancement` etiketiyle bir issue açın.
* Kullanım senaryosunu açıklayın — CodeIntel hem bir web paneli (`static/*.html`) hem de AI kod ajanları için bir MCP sunucusu (`src/mcp_server.py`) olarak kullanılıyor; iyileştirmenin hangi yüzey(ler)i hedeflediğini belirtin.

### Pull Request'ler

1. Depoyu fork'layın.
2. Özelliğiniz veya hata düzeltmeniz için yeni bir dal (branch) oluşturun.
3. Kod tabanının mevcut kurallarını izleyerek değişikliklerinizi uygulayın (aşağıya bakın).
4. Test paketini çalıştırın (`pytest tests/ -q`) — testlerin çoğu çalışan bir Qdrant örneği gerektirir (`tools/start-system.ps1` Qdrant + Ollama + paneli başlatır); Qdrant'a ulaşılamadığında testler BAŞARISIZ değil ATLANIR.
5. `src/api/search_routes.py`, `src/retrieval.py` veya güvenlikle ilgili herhangi bir şeye (kimlik doğrulama, giden URL'ler, HTML render) dokunduysanız `tests/test_security.py`'yi de çalıştırın.
6. `main` dalını hedefleyen bir Pull Request gönderin.

## Proje Yapısı (neyin nerede olduğu)

CodeIntel modüler bir FastAPI monolitidir, bir eklenti/kural çerçevesi değil — burada `.agents/rules/` yeniden üretme adımı yok, yalnız Python ve statik HTML/JS var:

| Alan | Nerede |
|---|---|
| Çekirdek arama/RAG mantığı (hibrit RRF, chunk getirme, açıklamalar, bağlam paketleri) | `src/retrieval.py` — hem panel hem MCP sunucusu tarafından ortak kullanılır, asla kopyalanmaz |
| Çok dilli parçalama (Tree-sitter) | `src/chunker.py` |
| Web paneli rotaları | `src/api/{search,index,admin,manual,mcp}_routes.py`, `src/panel.py`'den monte edilir |
| Ortak servisler (durum, profiller, API anahtarları, yedekler, indeksleme hattı) | `src/services/*.py` |
| MCP sunucusu (17 araç, stdio + Streamable HTTP) | `src/mcp_server.py` |
| Dokümantasyon/manual üretici | `src/manual.py` |
| Frontend (build adımsız, framework'süz) | `static/index.html` (arama), `static/settings.html` (koleksiyon/indeks yönetimi), `static/api.html` (REST + MCP araç test sayfası), `static/viewer.html` |
| Testler | `tests/test_api.py` (API + güvenlik regresyonu), `tests/test_chunker.py`, `tests/test_collection_ops.py`, `tests/test_generations.py`, `tests/test_manual.py`, `tests/test_security.py`, `tests/eval.py` (arama kalitesi ölçütü) |

## Yeni Bir MCP Aracı Ekleme

MCP araçları TEK bir yerde kayıtlıdır (`src/mcp_server.py`'nin `TOOLS` kayıt defteri) ve iki şekilde sunulur — yerel bir MCP aracı ve `/api/mcp/*` altında bir REST test ucu. `tests/test_api.py::test_mcp_rest_parity` her aracın ikisine de sahip olduğunu zorunlu kılar; REST karşılığı olmayan (veya tersi) bir araç CI'da başarısız olur. Aracı bir kez ekleyin, sonra REST rotasını `src/api/mcp_routes.py`'ye ekleyin.

## Yeni Bir Dil Desteği Ekleme

`src/chunker.py`'nin jenerik Tree-sitter motoru zaten yapısal olarak ~45 dili kapsıyor; 8 dilin (Delphi/Pascal dahil) daha derin desteği var (iç içe sınıf metotları için ebeveyn/çocuk AST bölmesi, `uses`/import çıkarımı). Yeni bir dil eklemek genelde şunu gerektirir: `tree-sitter-language-pack`'in o dil için bir gramer sunduğunu doğrulayın, dosya-uzantısı eşlemesini ekleyin, ve — derin destek isterseniz — `src/chunker.py`'deki mevcutlarla birlikte node-tipi eşlemesini ekleyin. Desteği iddia etmeden önce `tests/test_chunker.py`'ye fixture tabanlı bir test ekleyin.

## Teknik Standartlar

* **Güvenlikle ilgili değişiklikler** (`ollama_url`/giden HTTP'ye, frontend'de `esc()`/`escJs()` veya `src/manual.py`'de `_esc()`/`_esc_js()` ile HTML render'a, `STATE_LOCK` check-then-set desenine, veya `src/services/generations.py`'deki staging+alias nesil modeline dokunan her şey) sadece okuma değil, düzeltmeyi KANITLAYAN bir regresyon testi gerektirir — desen için 2026-07-25 civarındaki git geçmişine bakın (SSRF, saklı-XSS, import atomikliği, check-then-set yarışı) — her biri eski kodda BAŞARISIZ olan, yeni kodda GEÇEN bir testle düzeltildi.
* **Hata döndüren backend rotaları** `JSONResponse({"error": "..."}, status_code=...)` kullanır, opak 500'lere dönüşen fırlatılmış istisnalar değil.
* **Yeni Qdrant-destekli özellikler** mevcut iç-koleksiyon isimlendirme kuralını (`_` öneki, örn. `_search_log`, `_answer_cache`) izlemeli ve kullanıcıya görünen koleksiyon listelerinden hariç tutulmaları için `src/services/common.py`'deki `INTERNAL_COLLS`'a eklenmelidir.

### Test Etme

* `pytest tests/ -q` — testlerin çoğu `@needs_qdrant` ile işaretli ve canlı bir Qdrant olmadan sorunsuzca atlanır; birkaç saf-fonksiyon testi (kaçış, URL doğrulama) hiçbir bağımlılık olmadan çalışır.
* `tests/eval.py`, altın sorgu setine karşı bir arama-kalitesi ölçütüdür (Recall@k, MRR, p50/p95 gecikme) — `src/retrieval.py`'deki sıralama/füzyon mantığında herhangi bir değişiklikten sonra çalıştırın.

## İletişim

* Hata, soru ve öneriler için [issue takipçisini]([FILL IN: repo URL]/issues) kullanın.
* Tüm katkıcılara ve bakımcılara saygı gösterin — bkz. [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
