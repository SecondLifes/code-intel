# Code-Intel — Dış Mimari, Kod Kalitesi ve Ürün Analizi

**Analiz tarihi:** 23 Temmuz 2026  
**Kapsam:** Statik kod ve belge incelemesi; rakipler için güncel resmî dokümantasyon araştırması

## 1. İnceleme kapsamı ve erişilebilen dosyalar

Belirtilen yedi dosyanın tamamına erişildi:

| Dosya | Satır | Durum |
|---|---:|---|
| `src/chunker.py` | 71 | İncelendi |
| `src/panel.py` | 591 | İncelendi |
| `static/index.html` | 262 | İncelendi |
| `static/settings.html` | 361 | İncelendi |
| `DECISIONS.md` | 11 | İncelendi |
| `PANEL-PLAN.md` | 22 | İncelendi |
| `BOOTSTRAP-REPORT.md` | 26 | İncelendi |

`chunker.py` ve `panel.py`, Python derleme kontrolünden geçti. Bu statik analizdir; uçtan uca indeksleme, Qdrant ve Ollama testleri yeniden çalıştırılmadı.

## 2. Yönetici özeti

Code-Intel, prototip seviyesini aşmış, Delphi'ye özgü anlamlı teknik kararlar içeren bir sistemdir. Tree-sitter tabanlı bildirim/gövde ayrımı, XML dokümanlarının korunması, dense+sparse hibrit arama, değişmeyen vektörleri tekrar kullanma ve yerel LLM yaklaşımı güçlü temellerdir.

Bununla birlikte mevcut yapı henüz güvenilir bir üretim servisi değildir. En önemli sorunlar:

1. **İndeks güncellemesi atomik değil.** Eski noktalar yeni embedding'ler başarıyla yazılmadan siliniyor. İş yarıda kalırsa çalışan indeks eksik kalabilir.
2. **İş yönetimi süreç belleğine bağlı ve yarışa açık.** Yeniden başlatma, birden fazla Uvicorn worker'ı veya aynı anda gelen iki istek güvenli değil.
3. **Chunk kimliği yeterince benzersiz değil.** Yalnızca dosya adı ve ilk 160 karakter kullanılıyor; dizin bilgisi yok. Aynı adlı unit'ler sessizce birbirinin üzerine yazılabilir.
4. **Embedding/şema sürümü izlenmiyor.** Model veya chunk algoritması değiştiğinde sistem eski ve yeni vektörleri aynı koleksiyonda karıştırabilir.
5. **MCP ana hedefi henüz uygulanmamış.** Mevcut HTTP API iyi bir başlangıç olsa da `find_symbol`, `get_chunk`, referans/çağrı grafiği ve stabil provenance sözleşmesi yok.
6. **Güvenlik sınırı tanımlanmamış.** Kimlik doğrulama olmadan koleksiyon, model ve dosya sistemi yolu kullanıcı girdisi olarak kabul ediliyor. LAN'a açılması mevcut haliyle yüksek riskli.
7. **Arama kalitesi ölçülemiyor.** Golden-question eval, reranker, sonuç geri bildirimi ve indeks sürümüne bağlı kalite takibi bulunmuyor.
8. **Plan belgeleri uygulamadan sapmış.** Plan React/Vite/Tailwind, BM42 ve SSE söylüyor; mevcut sistem vanilla HTML, `Qdrant/bm25` ve polling kullanıyor.

En doğru sonraki adım, yeni özelliklerden önce **atomik indeks nesilleri + şema manifesti + eval tabanı** kurmak; hemen ardından salt-okunur MCP sunucusunu çıkarmaktır.

## 3. Mimari değerlendirme

### Güçlü yönler

#### Delphi'ye uygun semantik chunking

- **Bulgu:** Bildirim, implementasyon ve türler ayrı chunk türleri olarak çıkarılıyor; bildirim üzerindeki XML dokümanı chunk'a ekleniyor.
- **Kanıt:** `src/chunker.py:17-59`
- **Etkisi:** Genel amaçlı satır/paragraf bölmeye göre Delphi API keşfi ve Türkçe açıklama kalitesi artar.
- **Önerilen düzeltme:** Mevcut modeli koruyup unit, class, property ve call-site düğümleriyle genişletin.
- **Öncelik:** Düşük
- **Güven düzeyi:** Yüksek

#### Gerçek vektör varlığına dayalı artımlı güncelleme

- **Bulgu:** Sistem özel bayraklara güvenmek yerine mevcut vektörleri Qdrant'tan okuyup değişmeyenleri koruyor.
- **Kanıt:** `src/panel.py:451-500`
- **Etkisi:** Sparse ve dense indeksler ayrı zamanlarda tamamlanabiliyor; gereksiz embedding maliyeti azaltılıyor.
- **Önerilen düzeltme:** Diff motorunu bağımsız ve birim testli bir `IndexPlanner` bileşenine taşıyın.
- **Öncelik:** Orta
- **Güven düzeyi:** Yüksek

#### Hibrit arama

- **Bulgu:** Dense ve BM25 sparse sonuçları Qdrant içinde RRF ile birleştiriliyor.
- **Kanıt:** `src/panel.py:319-328`
- **Etkisi:** Türkçe doğal dil sorguları ile Delphi sembol/ad sorguları aynı yüzeyden destekleniyor.
- **Önerilen düzeltme:** Golden set üzerinde dense/sparse/hybrid karşılaştırması ve ikinci aşama reranker ekleyin.
- **Öncelik:** Orta
- **Güven düzeyi:** Yüksek

#### Yerel ve kaynak gösteren RAG

- **Bulgu:** Yanıt prompt'u yalnızca getirilen kod parçalarına dayanmayı ve `[1]`, `[2]` biçiminde kaynak göstermeyi emrediyor.
- **Kanıt:** `src/panel.py:560-587`
- **Etkisi:** Hassas Delphi kodlarının yerelde kalmasını ve kullanıcıya dayanak gösterilmesini sağlar.
- **Önerilen düzeltme:** Kaynak numaralarını kalıcı `repo/revision/path/line/chunk_id` provenance kaydına dönüştürün.
- **Öncelik:** Yüksek
- **Güven düzeyi:** Yüksek

### Başlıca riskler

#### Kritik — İndeks güncellemesi atomik değil

- **Bulgu:** Kaynaktan silinen noktalar embedding ve upsert başlamadan önce canlı koleksiyondan kaldırılıyor.
- **Kanıt:** Silme `src/panel.py:473-476`; embedding/upsert `511-537`; geçmiş kaydı `538`.
- **Etkisi:** Model yükleme, GPU, Qdrant veya süreç hatasında indeks kısmen güncellenmiş halde kalır.
- **Önerilen düzeltme:** Her çalışma için staging koleksiyonu oluşturun; doğrulamadan sonra Qdrant alias'ını atomik değiştirin. Kısa vadede silmeleri başarılı upsert'lerden sonraya taşıyın.
- **Öncelik:** Kritik
- **Güven düzeyi:** Yüksek

#### Kritik — İş yaşam döngüsü yeniden başlatılabilir değil

- **Bulgu:** Tek iş durumu global sözlükte tutuluyor; arka plan işi daemon thread olarak çalışıyor.
- **Kanıt:** `src/panel.py:23`, `408-409`, `543-550`
- **Etkisi:** Süreç kapanınca iş ve ilerleme bilgisi kaybolur. Birden fazla worker ayrı `STATE` görür. Kontrol ve thread başlatma arasında atomik kilit yoktur.
- **Önerilen düzeltme:** Kalıcı `index_jobs` kaydı, lease/lock, heartbeat, checkpoint ve idempotency key kullanın.
- **Öncelik:** Kritik
- **Güven düzeyi:** Yüksek

#### Kritik — Chunk kimliği çakışabilir

- **Bulgu:** Kimlik `path.name`, tür ve içeriğin ilk 160 karakterinden türetiliyor; Qdrant ID'si için yalnızca ilk 12 hex karakter kullanılıyor.
- **Kanıt:** `src/chunker.py:48-58`, `src/panel.py:437-438`
- **Etkisi:** Farklı dizinlerde aynı isimli unit'ler ve aynı öneke sahip overload'lar aynı ID'yi üretebilir. `row_by_id` son kaydı tutarak önceki chunk'ı sessizce kaybedebilir.
- **Önerilen düzeltme:** `repo_id + relative_path + kind + qualified_symbol + normalized_signature` üzerinden tam 64 bit veya UUID kimliği üretin. Duplicate ID'de işi durdurun.
- **Öncelik:** Kritik
- **Güven düzeyi:** Yüksek

#### Yüksek — Şema ve embedding modeli geçişi yönetilmiyor

- **Bulgu:** Model adı ve 1024 boyutu kod içine sabitlenmiş; mevcut koleksiyonun uyumluluğu doğrulanmıyor.
- **Kanıt:** `src/panel.py:99-108`, `443-450`
- **Etkisi:** Model, tokenizer, prompt veya chunk algoritması değiştiğinde eski ve yeni embedding'ler aynı koleksiyonda karışabilir.
- **Önerilen düzeltme:** `schema_version`, `chunker_version`, `parser_version`, model adları, boyut ve prompt sürümünü içeren manifest ekleyin.
- **Öncelik:** Yüksek
- **Güven düzeyi:** Yüksek

#### Yüksek — Kod bağlamı kesiliyor veya atılıyor

- **Bulgu:** 400 satırdan büyük chunk'lar atılıyor; embedding 2.000, payload 4.000, arama yanıtı 1.800 ve RAG bağlamı 1.100 karakterle sınırlandırılıyor.
- **Kanıt:** `src/chunker.py:44`, `src/panel.py:516`, `534-535`, `361-364`, `572-573`
- **Etkisi:** Büyük Delphi prosedürlerinin kritik kontrol akışı görünmeyebilir.
- **Önerilen düzeltme:** Büyük metodları AST bloklarına bölün; parent/child ilişkisi, `truncated` alanı ve tam kaynak alma endpoint'i ekleyin.
- **Öncelik:** Yüksek
- **Güven düzeyi:** Yüksek

#### Kritik/Yüksek — LAN güvenlik sınırı yok

- **Bulgu:** Kimlik doğrulama/yetkilendirme yok; istemci koleksiyon, model ve yerel dosya yolu belirleyebiliyor.
- **Kanıt:** `src/panel.py:142-155`, `316-318`, `367-398`, `401-406`
- **Etkisi:** LAN'a açıldığında yetkisiz indeksleme, pahalı model çağrıları, Qdrant değişiklikleri ve klasör taraması mümkün olur.
- **Önerilen düzeltme:** Varsayılan localhost, API anahtarı veya OIDC, salt-okunur/yönetici rolleri, kaynak kök ve model allowlist'i, rate limit ve audit log.
- **Öncelik:** LAN için Kritik; yalnız localhost için Orta/Yüksek
- **Güven düzeyi:** Yüksek

#### Yüksek — Gözlemlenebilirlik yetersiz

- **Bulgu:** Bazı istisnalar sessizce yutuluyor; kalıcı hata geçmişi, metrik, trace veya eval kapısı yok.
- **Kanıt:** `src/panel.py:36-45`, `114-134`, `540-541`; `static/settings.html:218-229`
- **Etkisi:** Arama kalitesi gerilemesi veya altyapı kesintisi ancak kullanıcı şikâyetiyle fark edilebilir.
- **Önerilen düzeltme:** Yapılandırılmış log, iş/hata kaydı, OpenTelemetry, Prometheus ve indeks nesli başına eval kalite kapısı.
- **Öncelik:** Yüksek
- **Güven düzeyi:** Yüksek

#### Yüksek — MCP ürün sözleşmesi hazır değil

- **Bulgu:** Karar belgesi beş MCP aracını onaylıyor; çalışan kodda MCP katmanı ve bunların çoğuna karşılık gelen stabil servisler yok.
- **Kanıt:** `DECISIONS.md:8`; HTTP yüzeyi `src/panel.py:114-591`
- **Etkisi:** Claude Code, Codex veya Gemini CLI sistemi doğrudan araç olarak kullanamıyor.
- **Önerilen düzeltme:** `search_code`, `get_chunk`, `find_symbol`, `find_references`, `list_units`, ardından `get_context_pack` araçlarını çıkarın.
- **Öncelik:** Yüksek
- **Güven düzeyi:** Yüksek

## 4. Kod kalitesi bulguları

| Önem | Yer | Kanıt | Risk | Çözüm | Efor |
|---|---|---|---|---|---|
| Kritik | `panel.py:473-539` | Canlı silme embedding'den önce | Eksik indeks | Staging nesli + alias | Büyük |
| Kritik | `chunker.py:48-58`, `panel.py:437-438` | Dizin içermeyen ve 48 bite indirilen ID | Sessiz chunk kaybı | Relative path + qualified symbol + UUID | Orta |
| Kritik | `panel.py:543-550` | İş kontrolü ve thread başlatma kilitsiz | İki eşzamanlı iş | Kalıcı lease/lock | Orta |
| Yüksek | `panel.py:412-432` | Koleksiyon adı dosya yoluna doğrulanmadan ekleniyor | Path traversal/yazma girişimi | Regex ve `resolve()` sınır kontrolü | Küçük |
| Yüksek | `panel.py:367-398` | Cache anahtarı yalnız `tr`/`tr_deep` | Model değişse de eski açıklama | Model+prompt+hash cache anahtarı | Küçük |
| Yüksek | `panel.py:99-108`, `443-450` | Model/şema sabit, uyumluluk kontrolü yok | Karışık embedding uzayı | Manifest ve migration | Orta |
| Yüksek | `panel.py:1-591` | API, Qdrant, indexing, RAG, donanım ve UI servisi tek dosyada | Test/bakım maliyeti | `api`, `indexing`, `retrieval`, `llm`, `storage`, `jobs` ayrımı | Büyük |
| Yüksek | `panel.py:316-318`, `401-406` | `top_k`, mode, device, koleksiyon ve vektör türleri sınırsız | Kaynak tüketimi/geçersiz durum | Pydantic `Literal` ve sınırlar | Küçük |
| Yüksek | `chunker.py:64` | Yalnız `*.pas` taranıyor | `.dpr`, `.dpk`, `.inc` dışarıda | Uzantı/parsing stratejisi | Orta |
| Orta | `panel.py:349-364` | Koleksiyonlar arası fused rank yapılıp eski skor döndürülüyor | Yanıltıcı skor | `raw_score`, `rank`, `fused_score` | Küçük |
| Orta | `panel.py:462-469` | Tüm vektörler belleğe alınıyor | Büyük koleksiyonda RAM/ağ maliyeti | Hedefli çekme ve ayrı hash manifesti | Orta |
| Orta | `panel.py:437` | JSONL dosyası `with` olmadan ve bütünüyle okunuyor | Kaynak/bellek sorunu | `with open` ve streaming | Küçük |
| Orta | `panel.py:371-398` | Nokta yokluğu/Ollama hatası modellenmiyor | Kontrolsüz 500 ve boş cache | 404/502 modelleri | Küçük |
| Orta | `index.html:182-183`, `settings.html:221-223` | Sunucu değerleri inline handler içine giriyor; tırnak kaçışı yok | Koşullu DOM injection | DOM API + `addEventListener` | Orta |
| Orta | `PANEL-PLAN.md:3-12` | React/BM42/SSE planı; vanilla/BM25/polling uygulaması | Belge sapması | Karar ve durum güncellemesi | Küçük |
| Düşük | `panel.py:197-209` | GET endpoint'i sunucuda klasör diyaloğu açıyor | Uzak/otomatik isteğin yan etkisi | Yerel adaptör veya admin POST | Küçük |

Endpoint'ler `async def` değildir; bu yüzden “async endpoint içinde doğrudan bloklayan işlem” hatası yoktur. Ancak 600 saniyelik senkron Ollama çağrıları thread kapasitesini tüketebilir.

## 5. Yenilik önerileri

### 1. Golden-question eval ve kalite kapısı

- **Çözdüğü problem:** Arama değişikliklerinin iyileşme mi gerileme mi olduğu bilinmiyor.
- **Kullanıcı değeri:** Tekrarlanabilir Delphi arama kalitesi.
- **Önerilen kullanıcı deneyimi:** Soru/beklenen symbol yönetimi ve nesiller arası karşılaştırma.
- **Teknik tasarım:** Recall@k, MRR, nDCG, groundedness ve latency runner'ı.
- **Değişecek bileşenler:** Yeni `eval` modülü, API/UI, CI.
- **Yeni veri modeli veya Qdrant alanları:** `_eval_sets`, `_eval_runs`, `generation_id`.
- **Bağımlılıklar:** Stabil chunk ID/provenance.
- **Riskler:** Dar ve önyargılı golden set.
- **Zorluk:** Orta
- **Tahmini uygulama büyüklüğü:** M
- **Beklenen etki:** Çok yüksek
- **Önerilen sıra:** 1
- **Başarı ölçütü:** En az 100 gerçek soruda baseline ve sürüm karşılaştırması.

### 2. Delphi Code-Intel MCP sunucusu

- **Çözdüğü problem:** Ajanlar Code-Intel bağlamını araç olarak alamıyor.
- **Kullanıcı değeri:** Codex, Claude Code, Gemini CLI ve Continue doğrudan Delphi kodunu araştırır.
- **Önerilen kullanıcı deneyimi:** Tek komutla stdio; isteğe bağlı kimlik doğrulamalı Streamable HTTP.
- **Teknik tasarım:** `search_code`, `get_chunk`, `find_symbol`, `find_references`, `list_units`, `get_index_status`.
- **Değişecek bileşenler:** Arama servis katmanı ve yeni MCP sunucusu.
- **Yeni veri modeli veya Qdrant alanları:** `repo_id`, `revision`, `relative_path`, `symbol_id`, `generation_id`.
- **Bağımlılıklar:** Stabil kimlik, manifest, erişim politikası.
- **Riskler:** Büyük araç yanıtları ve istemci farkları.
- **Zorluk:** Orta
- **Tahmini uygulama büyüklüğü:** M
- **Beklenen etki:** Çok yüksek
- **Önerilen sıra:** 2
- **Başarı ölçütü:** Üç farklı ajan istemcisinde kaynaklı Delphi cevabı.

### 3. Sembol, referans, inheritance ve çağrı grafiği

- **Çözdüğü problem:** “Kim çağırıyor?” ve “hangi sınıf override ediyor?” soruları güvenilir yanıtlanamıyor.
- **Kullanıcı değeri:** Bakım, refactoring ve onboarding hızlanır.
- **Önerilen kullanıcı deneyimi:** Definition, references, callers/callees, ancestors/descendants.
- **Teknik tasarım:** Delphi scope, `uses`, inheritance, qualified call ve `inherited` çözümlemesi.
- **Değişecek bileşenler:** Chunker, graph builder, search, MCP.
- **Yeni veri modeli veya Qdrant alanları:** `symbol_id`, `qualified_name`, `container_id`, edge kayıtları.
- **Bağımlılıklar:** IFDEF/include stratejisi.
- **Riskler:** Overload ve koşullu derleme çözümlemesi.
- **Zorluk:** Zor
- **Tahmini uygulama büyüklüğü:** XL
- **Beklenen etki:** Çok yüksek
- **Önerilen sıra:** 3
- **Başarı ölçütü:** Etiketli sette definition/reference precision ve recall ≥ %90.

### 4. Atomik indeks nesilleri ve provenance

- **Çözdüğü problem:** Yarım indeks, eski cache ve kaynağı belirsiz cevaplar.
- **Kullanıcı değeri:** Her cevabın revision/generation bilgisi ve rollback.
- **Önerilen kullanıcı deneyimi:** Güncellik göstergesi ve önceki nesle dönüş.
- **Teknik tasarım:** Immutable generation, staging, doğrulama, alias swap, retention.
- **Değişecek bileşenler:** Worker, history/profile, search response.
- **Yeni veri modeli veya Qdrant alanları:** `git_commit`, `generation_id`, parser/model manifesti.
- **Bağımlılıklar:** Git olmayan kaynaklar için snapshot kimliği.
- **Riskler:** Geçici iki kat disk.
- **Zorluk:** Orta
- **Tahmini uygulama büyüklüğü:** L
- **Beklenen etki:** Çok yüksek
- **Önerilen sıra:** 4
- **Başarı ölçütü:** Kesilen işte canlı alias'ın değişmemesi.

### 5. Repo-map ve ajan odaklı context pack

- **Çözdüğü problem:** RAG en yakın chunk'ları buluyor fakat repository yapısı ve ilişkiler kayboluyor.
- **Kullanıcı değeri:** Ajanlar daha az araç çağrısıyla doğru bağlamı alır.
- **Önerilen kullanıcı deneyimi:** `get_context_pack(task, token_budget)`.
- **Teknik tasarım:** Repo özeti, unit özetleri, graph, hybrid retrieval, rerank ve token budgeting.
- **Değişecek bileşenler:** Summary pipeline, retrieval, MCP.
- **Yeni veri modeli veya Qdrant alanları:** `summary_level`, `parent_id`, `dependencies`, `token_count`.
- **Bağımlılıklar:** Temel sembol/uses grafiği.
- **Riskler:** Bağlam şişmesi ve eski özetler.
- **Zorluk:** Zor
- **Tahmini uygulama büyüklüğü:** L
- **Beklenen etki:** Yüksek
- **Önerilen sıra:** 5
- **Başarı ölçütü:** Gerekli dosyanın context pack'e giriş oranı.

### 6. Reranker ve kullanıcı geri bildirimi

- **Çözdüğü problem:** RRF sonrası kalite katmanı ve öğrenme döngüsü yok.
- **Kullanıcı değeri:** Kısa sembol ve Türkçe davranış sorgularında daha iyi ilk sonuçlar.
- **Önerilen kullanıcı deneyimi:** İlgili/ilgisiz ve doğru chunk geri bildirimi.
- **Teknik tasarım:** İlk 30-50 sonucu cross-encoder ile rerank; feedback'i eval adayına dönüştürme.
- **Değişecek bileşenler:** Search, UI, eval.
- **Yeni veri modeli veya Qdrant alanları:** `_search_feedback`, query, rank, click, relevance.
- **Bağımlılıklar:** Eval ve provenance.
- **Riskler:** Az veri ve popülerlik yanlılığı.
- **Zorluk:** Orta
- **Tahmini uygulama büyüklüğü:** M
- **Beklenen etki:** Yüksek
- **Önerilen sıra:** 6
- **Başarı ölçütü:** MRR/precision@5 ve ilk sonuç fayda oranında artış.

### 7. Git-aware arama ve değişiklik etkisi

- **Çözdüğü problem:** Kodun neden değiştiği ve bir değişikliğin nereleri etkilediği bilinmiyor.
- **Kullanıcı değeri:** Regresyon analizi ve legacy bakım.
- **Önerilen kullanıcı deneyimi:** “Bu metodu değiştirirsem ne etkilenir?”, blame ve ilgili commitler.
- **Teknik tasarım:** Git log/blame ingest; call graph ve birlikte değişen dosya analizi.
- **Değişecek bileşenler:** Git ingester, graph, MCP/UI.
- **Yeni veri modeli veya Qdrant alanları:** `last_commit`, `authors`, `change_frequency`, `cochange_files`.
- **Bağımlılıklar:** Sembol grafiği ve repo kimliği.
- **Riskler:** Kişisel veri ve büyük geçmiş maliyeti.
- **Zorluk:** Zor
- **Tahmini uygulama büyüklüğü:** L
- **Beklenen etki:** Yüksek
- **Önerilen sıra:** 7
- **Başarı ölçütü:** Geçmiş regresyonlarda etkilenen dosyaların top-k başarısı.

### 8. Otomatik mimari ve API dokümantasyonu

- **Çözdüğü problem:** Repository-level bilgi ve unit ilişkileri kalıcı değil.
- **Kullanıcı değeri:** Yeni geliştirici ve ajanlar legacy kütüphaneyi hızlı anlar.
- **Önerilen kullanıcı deneyimi:** Unit kataloğu, public API, sınıf hiyerarşisi ve diyagramlar.
- **Teknik tasarım:** AST/graph'tan deterministik iskelet; LLM yalnız açıklama katmanında.
- **Değişecek bileşenler:** Graph, docs generator, UI/MCP resources.
- **Yeni veri modeli veya Qdrant alanları:** `doc_type`, `source_symbol_ids`, `generation_id`, `confidence`.
- **Bağımlılıklar:** Graph ve provenance.
- **Riskler:** Mimari niyetin yanlış yorumlanması.
- **Zorluk:** Orta
- **Tahmini uygulama büyüklüğü:** L
- **Beklenen etki:** Yüksek
- **Önerilen sıra:** 8
- **Başarı ölçütü:** Üretilen iddiaların kaynak sembollere bağlanma oranı %100.

### 9. Çoklu repository çalışma alanları

- **Çözdüğü problem:** Çoklu koleksiyon var ancak repository/revision/bağımlılık semantiği yok.
- **Kullanıcı değeri:** Uygulama, UniDAC ve ortak framework kontrollü tek bağlamda aranır.
- **Önerilen kullanıcı deneyimi:** İsimlendirilmiş workspace, repo ve revision seçimi.
- **Teknik tasarım:** `workspace -> repositories -> generations` modeli.
- **Değişecek bileşenler:** Profil, search, UI, MCP.
- **Yeni veri modeli veya Qdrant alanları:** `workspace_id`, `repo_id`, `revision`, `dependency_role`.
- **Bağımlılıklar:** Atomik nesiller ve provenance.
- **Riskler:** Benzer sembollerin yanlış repodan gelmesi.
- **Zorluk:** Orta
- **Tahmini uygulama büyüklüğü:** M
- **Beklenen etki:** Yüksek
- **Önerilen sıra:** 9
- **Başarı ölçütü:** Cross-repo sorularda doğru repo/symbol top-5 oranı.

### 10. Güvenli model yönlendirme ve dağıtık worker

- **Çözdüğü problem:** Ollama tek hata noktası ve uzun işler tek makineye bağlı.
- **Kullanıcı değeri:** Yerel gizlilik korunurken kontrollü kapasite artışı.
- **Önerilen kullanıcı deneyimi:** “Yalnız yerel”, “redakte ederek bulut”, “yalnız açık kaynak” politikaları.
- **Teknik tasarım:** Provider adapter, DLP/redaction, queue, lease, retry ve dead-letter queue.
- **Değişecek bileşenler:** LLM service, jobs, settings.
- **Yeni veri modeli veya Qdrant alanları:** `provider`, `model_digest`, `data_policy`, `attempt`, `lease_owner`.
- **Bağımlılıklar:** Kalıcı iş sistemi ve auth.
- **Riskler:** Kod sızıntısı, maliyet ve model farkı.
- **Zorluk:** Zor
- **Tahmini uygulama büyüklüğü:** L
- **Beklenen etki:** Orta/Yüksek
- **Önerilen sıra:** 10
- **Başarı ölçütü:** Worker kaybında devam; yerel politikada sıfır dış model isteği.

## 6. Rakip ve yetenek boşluğu analizi

Araştırmada yalnızca resmî ürün belgeleri kullanıldı:

- [Sourcegraph Cody Context](https://sourcegraph.com/docs/cody/core-concepts/context)
- [Sourcegraph Agentic Context](https://sourcegraph.com/docs/cody/capabilities/agentic-context-fetching)
- [Continue Codebase Awareness](https://docs.continue.dev/guides/codebase-documentation-awareness)
- [Continue Agent Tools](https://docs.continue.dev/ide-extensions/agent/how-it-works)
- [Continue Reranking](https://docs.continue.dev/customize/model-roles/reranking)
- [Cursor Working with Context](https://docs.cursor.com/en/guides/working-with-context)
- [Cursor Agent Tools](https://docs.cursor.com/en/agent/tools)
- [Cursor Installation and Indexing](https://docs.cursor.com/get-started/installation)
- [GitHub Copilot: Explore a codebase](https://docs.github.com/en/copilot/tutorials/explore-a-codebase)
- [GitHub Copilot Spaces](https://docs.github.com/en/copilot/concepts/context/spaces)
- [GitHub Copilot MCP and cloud agent](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/mcp-and-cloud-agent)

Gösterim: ✅ doğrulandı, ◐ kısmi/dolaylı, ❌ yok, ? resmî kaynakta yeterince doğrulanmadı.

| Yetenek | Code-Intel | Cody | Continue | Cursor | GitHub Copilot | Code-Intel için önem |
|---|---:|---:|---:|---:|---:|---|
| Doğal dil codebase soru-cevap | ✅ | ✅ | ✅ | ✅ | ✅ | Temel; mevcut |
| Dense + keyword retrieval | ✅ | ✅ | ◐ | ✅ | Semantic indeks ✅, ayrıntı ? | Mevcut avantaj |
| İkinci aşama reranker | ❌ | ? | ✅ | ◐ | ? | Yüksek |
| Sembol/definition context | ◐ | ✅ | ✅ | ✅ | ◐ | Çok yüksek |
| Referans ve code graph | ❌ | ✅ | ? | ? | ? | Çok yüksek |
| Çoklu repository context | ◐ | ✅ | ◐ | ◐ | ✅ | Yüksek |
| Git/değişiklik bağlamı | ❌ | ◐ | ✅ | ✅ | ✅ | Yüksek |
| Agent edit/terminal | ❌ | ✅ | ✅ | ✅ | ✅ | MCP ile bağlanmalı |
| MCP istemci desteği | ❌ | ✅ | ✅ | ✅ | ✅ | Orta |
| Kendi Delphi zekâsını MCP ile sunma | ❌ | Uygulanabilir | Uygulanabilir | Uygulanabilir | Uygulanabilir | Çok yüksek |
| Kalıcı proje kuralları | ❌ | ◐ | ✅ | ✅ | ✅ | Orta/Yüksek |
| Tam provenance/revision | Kısmi | ✅ | ◐ | ◐ | ✅ | Çok yüksek |
| Takım/paylaşılan indeks | ◐ | ✅ | ◐ | ✅ | ✅ | Orta |
| Arama kalite eval sistemi | ❌ | ? | ? | ? | ? | Stratejik avantaj |
| Tam yerel çalışma | ✅ | ◐ | Yapılandırmaya bağlı | Hayır | Hayır | Güçlü farklılaştırıcı |

Code-Intel'in Cursor veya Copilot gibi genel amaçlı bir kod düzenleme ajanına dönüşmesi gerekmiyor. En güçlü konumlandırma, **Delphi'ye özgü yüksek doğruluklu kod grafiği ve provenance sağlayan yerel MCP intelligence layer** olmaktır.

### Rakiplerdeki en iyi yaklaşımlar ve neden iyi oldukları

Buradaki “en iyi” ifadesi tek bir genel kazanan anlamına gelmez. Her ürünün en güçlü olduğu farklı bir alan vardır. Code-Intel açısından değerli olan, bu yaklaşımların uygun parçalarını Delphi ve yerel çalışma hedefiyle birleştirmektir.

#### 1. Sourcegraph Cody — Kod grafiği ve çoklu repository bağlamında en güçlü yaklaşım

**Öne çıkan yetenekler**

- Keyword search, Sourcegraph Search ve Code Graph birlikte kullanılıyor.
- Kod yalnızca metin benzerliğiyle değil; bileşenlerin birbirine nasıl bağlandığı ve nerelerde kullanıldığı üzerinden de bağlama alınıyor.
- VS Code, JetBrains, Visual Studio ve web istemcilerinde çoklu repository bağlamı destekleniyor.
- Dosya ve semboller doğrudan bağlam olarak seçilebiliyor.

**Neden iyi**

Vektör benzerliği “aynı anlama gelen kodu” bulabilir; fakat “bu fonksiyonu kim çağırıyor?”, “bu tip nerede uygulanıyor?” veya “bu değişiklik hangi bileşenlere yayılır?” soruları için yeterli değildir. Cody'nin Code Graph yaklaşımı semantik aramayı yapısal ilişkilerle tamamlar. Büyük ve birbiriyle ilişkili repository'lerde doğru bağlamı bulma olasılığı bu nedenle yükselir.

**Code-Intel için alınması gereken ders**

Code-Intel, Cody'nin genel amaçlı kod grafiğini Delphi'ye özgü biçimde uygulamalıdır:

- `uses` bağımlılıkları
- class inheritance ve interface implementation
- declaration/definition ilişkisi
- callers/callees
- override ve `inherited` çağrıları
- property getter/setter bağlantıları
- çoklu repository/revision bağlamı

Bu özellik, Code-Intel'i yalnızca “Delphi için vektör arama” olmaktan çıkarıp gerçek bir Delphi code intelligence motoruna dönüştürür.

**Resmî bağlantılar**

- [Cody Context — keyword search, Sourcegraph Search, Code Graph ve çoklu repository](https://sourcegraph.com/docs/cody/core-concepts/context)
- [Sourcegraph Code Navigation](https://sourcegraph.com/docs/code-navigation)
- [Cody Agentic Context Fetching](https://sourcegraph.com/docs/cody/capabilities/agentic-context-fetching)

#### 2. Continue — Özelleştirilebilir, yerel ve MCP tabanlı mimaride en iyi örnek

**Öne çıkan yetenekler**

- Agent; dosya okuma, pattern arama, code search ve Git geçmişi araçlarıyla bağlam topluyor.
- `.continue/rules` aracılığıyla proje ve dizin seviyesinde bilgi verilebiliyor.
- Özel MCP sunucuları ve özel Code RAG sistemleri bağlanabiliyor.
- Vector search sonrasında özel bir reranker rolü kullanılabiliyor.
- Yerel model, self-hosted model ve özel sağlayıcı seçimi yapılabiliyor.

**Neden iyi**

Continue tek bir kapalı retrieval veya model yaklaşımına bağlı değildir. Model, embedding, reranker, kurallar ve araçlar ayrı roller olarak değiştirilebilir. Bu, özellikle kaynak kodunun dışarı çıkarılamadığı kurumsal veya legacy projelerde önemlidir. Codebase bilgisinin doğrudan agent araçlarıyla toplanması, eski “tek seferde birkaç vektör sonucu getir” yaklaşımından daha esnek bir araştırma döngüsü sağlar.

Continue ayrıca retrieval ile reranking'i ayırır. İlk aşama yüksek recall ile adayları toplarken ikinci aşama kullanıcı sorusuna gerçekten yararlı olan parçaları seçer. Bu yaklaşım Code-Intel'in mevcut RRF sonuçlarını iyileştirmek için doğrudan uygulanabilir.

**Code-Intel için alınması gereken ders**

- Qdrant retrieval katmanını panelden bağımsız bir servis haline getirin.
- Dense, sparse ve reranker modellerini manifest üzerinden değiştirilebilir yapın.
- Code-Intel'i Continue'a özel bir MCP sunucusu olarak bağlayın.
- Yerel Ollama ve yerel reranker seçeneklerini birinci sınıf destekleyin.
- Repository mimarisi ve Delphi kurallarını ajanlara sağlayan proje kuralı/context-pack üretin.

**Resmî bağlantılar**

- [Continue Codebase and Documentation Awareness](https://docs.continue.dev/guides/codebase-documentation-awareness)
- [Continue Agent Mode Tools](https://docs.continue.dev/ide-extensions/agent/how-it-works)
- [Continue Rerank Role](https://docs.continue.dev/customize/model-roles/reranking)
- [Continue CLI](https://docs.continue.dev/cli/quickstart)

#### 3. Cursor — Ajan kullanıcı deneyimi ve büyük indeks güncelliğinde en güçlü yaklaşım

**Öne çıkan yetenekler**

- Agent; codebase search, grep, dosya okuma, düzenleme, terminal ve MCP araçlarını aynı döngüde kullanıyor.
- Ask, Agent ve Manual gibi risk/yetki düzeyleri farklı çalışma modları bulunuyor.
- Ajan değişiklikleri diff olarak inceletiliyor ve checkpoint'lerle geri alınabiliyor.
- Codebase değişiklikleri Merkle tree ile karşılaştırılıyor; değişmeyen chunk embedding'leri tekrar kullanılıyor.
- Benzer takım indeksleri güvenli şekilde yeniden kullanılarak büyük repository'lerde ilk sorguya ulaşma süresi azaltılıyor.
- Cursor'un yayımladığı ölçüme göre semantic search, kendi değerlendirmelerinde yanıt doğruluğunu ortalama %12,5 artırmış.

**Neden iyi**

Cursor'un başarısı yalnızca embedding modelinden gelmiyor. Arama, dosya okuma, düzenleme, terminal, kullanıcı onayı ve geri alma tek bir akışta birleştiriliyor. Kullanıcı, ajanı çalışırken yönlendirebiliyor ve yapılan değişikliği diff/checkpoint üzerinden denetleyebiliyor.

İndeks tarafındaki Merkle tree ve içerik bazlı embedding cache yaklaşımı da önemlidir. Bu tasarım, repository'nin tamamını her değişiklikte taramak veya yeniden embedding yapmak yerine yalnızca değişen dalları işler. Takım indekslerinin erişim kanıtlarıyla yeniden kullanılması ise büyük repository onboarding süresini ciddi biçimde azaltır.

**Code-Intel için alınması gereken ders**

- XXH3 tabanlı chunk diff yaklaşımını repo-relative Merkle manifestine yükseltin.
- İndeks güncelliğini dosya, klasör ve generation seviyesinde görünür yapın.
- MCP araçlarını `read-only search`, `analysis` ve ileride `write/execute` olarak ayrı yetki gruplarına ayırın.
- Ajanın ilk sonuçla yetinmeyip `search -> get_chunk -> references -> related unit` döngüsü kurabilmesini sağlayın.
- Dağıtık kullanımda aynı repository snapshot'ının embedding'lerini güvenli şekilde yeniden kullanın.

**Resmî bağlantılar**

- [Cursor Agent Tools](https://docs.cursor.com/en/agent/tools)
- [Cursor Agent Modes](https://docs.cursor.com/agent)
- [Cursor Codebase Indexing](https://docs.cursor.com/get-started/installation)
- [Cursor: Securely Indexing Large Codebases — Merkle tree, cache ve takım indeksleri](https://cursor.com/blog/secure-codebase-indexing)
- [Cursor CLI ve MCP](https://docs.cursor.com/en/cli/using)

#### 4. GitHub Copilot — Geliştirme yaşam döngüsü, ekip bağlamı ve yönetişimde en güçlü yaklaşım

**Öne çıkan yetenekler**

- Copilot Spaces; repository, kod, pull request, issue, serbest metin, görsel ve dosyaları ortak bir bağlamda topluyor.
- GitHub kaynakları değiştikçe Space bağlamı otomatik güncelleniyor.
- Space ekip içinde paylaşılabiliyor ve kullanıcı yalnızca erişim yetkisi olan kaynakları görebiliyor.
- Cloud agent yerel ve uzak MCP araçlarını kullanabiliyor.
- Varsayılan GitHub MCP bağlantısı geçerli repository için sınırlı, salt-okunur token kullanıyor.
- MCP yapılandırması repository ve custom-agent seviyesinde yönetilebiliyor.

**Neden iyi**

GitHub Copilot kodu izole bir dosya kümesi olarak değil; issue, pull request, repository kuralları, review ve ekip bilgisinden oluşan bir geliştirme yaşam döngüsünün parçası olarak ele alıyor. Copilot Spaces'ın en güçlü yanı, belirli bir görev veya alan için kalıcı ve paylaşılabilir bir “çalışma bağlamı” oluşturmasıdır. Kaynakların otomatik güncellenmesi, manuel hazırlanmış bağlamın hızla eskimesini engeller.

Salt-okunur ve repository ile sınırlandırılmış varsayılan MCP token yaklaşımı da güvenlik açısından iyi bir örnektir. Araçlara erişim “sunucu kurulduysa her şeyi yapabilir” şeklinde değil; repository, araç ve yetki seviyesinde sınırlandırılır.

**Code-Intel için alınması gereken ders**

- “Workspace” modelini yalnız repository listesi olarak değil; kod, mimari notlar, benchmark soruları, kararlar ve ilgili issue/PR bağlamını kapsayan paylaşılabilir bir paket olarak tasarlayın.
- MCP sunucusunu varsayılan salt-okunur yapın.
- Araç allowlist'i ve repository-scoped token/rol modeli uygulayın.
- Her context pack'i indeks generation'ı ile otomatik güncelleyin.
- İleride GitHub/GitLab issue ve PR bilgisini Delphi symbol graph ile ilişkilendirin.

**Resmî bağlantılar**

- [GitHub Copilot Spaces](https://docs.github.com/en/copilot/concepts/context/spaces)
- [GitHub Copilot Repository Indexing](https://docs.github.com/en/copilot/concepts/context/repository-indexing)
- [MCP and GitHub Copilot Cloud Agent](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/mcp-and-cloud-agent)
- [GitHub Copilot Repository Custom Instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions-in-your-ide/add-repository-instructions-in-your-ide)

### En iyi özelliklerin Code-Intel için önerilen birleşimi

| Kaynak ürün | Alınacak en iyi yaklaşım | Code-Intel'deki karşılığı | Öncelik |
|---|---|---|---:|
| Sourcegraph Cody | Code Graph + çoklu repo bağlamı | Delphi symbol/reference/call graph | 1 |
| Continue | Modüler model rolleri + reranker + özel MCP/RAG | Yerel ve değiştirilebilir retrieval pipeline | 2 |
| Cursor | Merkle güncelliği + agent tool loop + checkpoint mantığı | Güvenilir artımlı indeks ve ajan context araçları | 3 |
| GitHub Copilot | Paylaşılabilir, güncel Space + repository-scoped MCP güvenliği | Code-Intel workspace ve salt-okunur MCP politikası | 4 |

Önerilen hedef mimari şu birleşimdir:

1. **Sourcegraph gibi yapısal:** Delphi sembol ve ilişki grafiği.
2. **Continue gibi açık ve değiştirilebilir:** Yerel model, reranker, kurallar ve MCP.
3. **Cursor gibi güncel ve ajan dostu:** Hızlı incremental indeks, tam kaynak araçları ve çok adımlı araştırma.
4. **GitHub gibi yönetilebilir:** Paylaşılabilir workspace, provenance ve en az yetki prensibi.

## 7. Öncelikli yol haritası

### İlk 2 hafta — Temel güvenilirlik ve ölçüm

**Yapılacak işler**

1. Chunk ID'yi repo-relative path ve qualified symbol ile düzeltme.
2. Koleksiyon/model/path/top-k doğrulaması; localhost ve temel API anahtarı.
3. Silmeleri indeks sonuna taşıma; başarısız iş kaydı ve kalıcı job ID.
4. Şema/embedding manifesti.
5. 50-100 soruluk golden set ve dense/sparse/hybrid baseline.
6. Plan belgelerini uygulamayla eşitleme.

**Bağımlılık sırası:** Kimlik → manifest → güvenli indeks → eval → belge.

**Beklenen çıktı:** Yarım işte bozulmayan, model/şeması bilinen ve kalite metriği bulunan tek makineli sürüm.

**Kabul kriterleri**

- Duplicate ID işi durdurur.
- Kesilen iş canlı indeksi bozmaz.
- Manifest API'den görülebilir.
- Recall@5/10, MRR ve latency raporu üretilir.
- Geçersiz girdiler 4xx döndürür.

**Ertelenecekler:** Çoklu dil, bulut LLM, büyük UI yenilemesi, çok makineli worker.

### İlk 1-2 ay — MCP ve yüksek değerli kod zekâsı

**Yapılacak işler**

1. `panel.py` servis ayrımı.
2. Salt-okunur MCP sunucusu.
3. Tam chunk alma ve provenance.
4. Delphi sembol tablosu, `uses` bağımlılıkları ve temel referans çözümleme.
5. Reranker ve feedback.
6. Repo-map/context-pack.
7. CLI/IDE kurulum örnekleri.

**Bağımlılık sırası:** Servis ayrımı → provenance → MCP → sembol indeksi → context pack → reranker.

**Beklenen çıktı:** Ajanların Delphi kod tabanını güvenilir araçlarla araştırabildiği ilk ürün sürümü.

**Kabul kriterleri**

- MCP araçları üç istemcide contract testinden geçer.
- Arama sonucu `get_chunk` ile tam kaynağa bağlanır.
- Her sonuç repo, revision, path, satır ve generation içerir.
- Definition/reference doğruluğu ölçülür.

**Ertelenecekler:** Yazma yetkili MCP araçları, kendi kod yazma ajanı, karmaşık graph UI.

### 3-6 ay — Ölçekleme, çoklu dil ve ileri analiz

**Yapılacak işler**

1. Call/inheritance graph ve değişiklik etkisi.
2. Git/blame/co-change ingest.
3. Çoklu repository workspace.
4. `.dpr`, `.dpk`, `.inc` ve IFDEF/include; ardından ikinci dil.
5. Kalıcı dağıtık worker.
6. Güvenli bulut fallback.
7. Otomatik mimari/API dokümantasyonu.
8. Tam atomik generation/alias ve retention.

**Bağımlılık sırası:** Delphi graph → Git/impact → workspace → worker → çoklu dil/bulut.

**Beklenen çıktı:** Büyük Delphi ekosistemlerinde çalışan, repository-level bağlam sunan ve yatay ölçeklenebilen platform.

**Kabul kriterleri**

- Worker kaybında işler devam eder.
- Cross-repo benchmark ölçülür.
- Koşullu derleme kaynaklı parser kaybı raporlanır.
- Etki analizi geçmiş regresyonlarda doğrulanır.
- Yasaklı kaynaklar buluta gönderilmez.

**Ertelenecekler:** Cursor/Copilot ile genel amaçlı IDE özelliklerinde birebir rekabet.

## 8. Hemen şimdi yapılacak üç iş

1. **Chunk ID'yi düzeltin:** `repo_id + relative_path + kind + qualified_signature` kullanın ve duplicate ID'de indekslemeyi durdurun.
2. **İndeksi güvenli hale getirin:** Silmeleri sona taşıyın, kalıcı job/manifest yazın ve staging collection + alias modeline geçin.
3. **Golden set + MCP çekirdeğini başlatın:** 50-100 gerçek Delphi sorusuyla baseline alın; aynı retrieval servisini `search_code` ve `get_chunk` MCP araçlarının temeli yapın.

## 9. Belirsizlikler ve görülmesi gereken ek dosyalar

Aşağıdaki konular incelenen yedi dosyadan kesin olarak değerlendirilemedi:

- `test_parse.py`, `test_corpus.py`, `test_e2e.py`
- `pyproject.toml`, lock veya requirements dosyaları
- Qdrant konfigürasyonu, snapshot/backup ve authentication
- Gerçek Uvicorn host, worker ve reverse-proxy dağıtımı
- Firewall/LAN erişim kuralları
- Parser hata örnekleri ve IFDEF ön-işleyici tasarımı
- Gerçek Qdrant payload ve koleksiyon şemaları
- Model digest ve lisans kayıtları
- CI/CD, benchmark korpusu, load ve güvenlik testleri
- Gizli dosyaları dışlayan indeksleme politikası
- Listede olmayan MCP tasarım veya implementasyon dosyaları

Güvenlik değerlendirmesindeki en yüksek riskler özellikle servis LAN'a veya başka makinelere açıldığında geçerlidir. Yalnızca `127.0.0.1` üzerinde tek kullanıcıyla çalıştırmak saldırı yüzeyini azaltır; veri bütünlüğü ve yeniden başlatılabilirlik sorunlarını ortadan kaldırmaz.
