# CodeIntel — Sıra 23-29 Kapanış Raporu (25 Temmuz 2026)

Önceki oturumda kalan TÜM açık maddeler ("yapılacakların tümünü yap" talimatı) bu oturumda bitirildi: test kapsamı genişlemesi, API-key rol ayrımı, chunker'da dev-metod bölmesi, kalıcı iş kaydı, atomik staging+alias indeks modeli, MCP HTTP transport, agentic edit. 7 commit, 43→66 test yeşil.

## Commit'ler
| Commit | İçerik |
|---|---|
| `f98e86e` | Sıra 23: merge/rename/export-import round-trip + SSE zarfı testleri |
| `c9f3f71` | Sıra 11a: API anahtarı kayıt defteri + rol ayrımı (okuma/yönetim) |
| `2132754` | Sıra 25: chunker'da dev metodlar için parent/child AST bölmesi |
| `6ead44a` | Sıra 26: kalıcı iş kaydı — panel restart sonrası indeksleme devam |
| `07c2ac8` | Sıra 27: atomik staging+alias indeks nesli modeli (opt-in) |
| `a10fc6a` | Sıra 11b: MCP'yi LAN'a opsiyonel HTTP transport ile açma |
| `e6808b5` | Sıra 11c: agentic edit — yalnız-göster diff önerisi (17. MCP tool) |

## Öne çıkanlar

**API anahtarları (Sıra 11a):** Tek "üstün" ortam-değişkeni anahtarının yerini rol ayrımlı (okuma/yönetim) bir kayıt defteri aldı — geriye dönük uyumlu (`CODEINTEL_API_KEY` hâlâ çalışır), Ayarlar'da üret/listele/iptal arayüzüyle. Ham anahtar yalnız üretildiği an gösterilir.

**Chunker'da dev-metod bölmesi (Sıra 25):** >400 satırlık metodlar eskiden yalnız ilk 400 satırla indeksleniyordu — 400. satırdan sonrası ARANAMAZDI. Artık gövde STATEMENT sınırlarında mantıksal parçalara bölünüp ayrı `method_part` chunk'ları olarak da indeksleniyor. Go'nun gövdeyi tek bir sarmalayıcı düğüme (`statement_list`) koyduğu — atlanmazsa bölmenin hiç gerçekleşmediği — canlı ayrıştırma testinde bulundu ve düzeltildi.

**Kalıcı iş kaydı (Sıra 26):** İndeksleme artık başlamadan önce `_index_jobs`'a bir checkpoint yazıyor; panel sert şekilde kesilirse (kill/çökme) açılışta bu kayıt bulunup aynı iş otomatik yeniden tetikleniyor. Model bilerek basit: "devam etmek" = "aynı isteği yeniden çalıştırmak" (indeksleme zaten hash bazlı diff'li, değişmeyen noktalar otomatik atlanır).

**Atomik staging+alias modeli (Sıra 27, en riskli madde):** Context7'den qdrant-client dokümanı + kurulu Qdrant'a karşı ampirik doğrulama ile temel varsayımlar kanıtlandı. Canlı doğrulamada gerçek bir hata bulundu: `delete_collection(alias)` sessizce hiçbir şey yapmıyor — düzeltilmeden bırakılsaydı bir kullanıcı "silindi" sanıp verinin hâlâ durduğunu fark etmezdi. Bilerek OPT-IN bırakıldı (`IndexReq.staged=True`) — mevcut 4 gerçek koleksiyon (Jedi/mORMot2/unidac/RESTRequest4Delphi) otomatik göçmedi, yalnız mekanizmanın kendisi atılabilir fixture'larla uçtan uca kanıtlandı.

**MCP HTTP transport (Sıra 11b):** Context7 dokümanı ile kurulu `mcp==1.28.1`'in gerçek kaynağı karşılaştırılınca kritik bir sapma bulundu: dokümanın işaret ettiği davranış ("yanlış host → 421 reddet") kurulu sürümde YANLIŞ — `transport_security` verilmezse koruma "geriye dönük uyumluluk için" SESSİZCE tamamen kapanıyor. Bu yüzden LAN'a açılırken `CODEINTEL_MCP_ALLOWED_HOSTS` ZORUNLU kılındı, eksikse süreç açık bir hatayla başlamayı reddediyor.

**Agentic edit (Sıra 11c):** 17. MCP tool — `propose_edit`, bir chunk + talimat alıp Ollama'dan unified diff üretir, hiçbir dosyaya yazmaz. Canlı doğrulamada gerçek Ollama (qwen3.6) `Calc.pas`'a doğru bir "sıfıra bölme kontrolü ekle" diff'i üretti; kaynak dosya çağrı öncesi/sonrası bayt bayt aynı kaldı.

## Genel durum
**66/66 test yeşil** (23 yeni test bu oturumda). Panel + Qdrant çalışır durumda test edildi. Gerçek 4 koleksiyon (Jedi 380.118, RESTRequest4Delphi 1.524, Synopse-mORMot2 112.304, unidac 57.086 nokta) hiç dokunulmadan, nokta sayıları aynı kaldı. Sıra 1-29 tamamen bitti — geriye yalnız Sıra 12 (veri-gated, yeni test verisi biriktikçe değerlendirilecek eval/kalite maddeleri) kaldı.
