# CodeIntel — Ek Özellik ve Genişletilebilirlik Analizi

**Tarih:** 24 Temmuz 2026  
**Kapsam:** Kaynak kod, REST/MCP yüzeyi, indeksleme hattı, arama/RAG, statik UI, testler, başlatma araçları ve canlı sistem durumu.

## 1. Yönetici özeti

CodeIntel bugün çalışan ve faydalı bir yerel Delphi kod zekâsı ürünüdür. En güçlü tarafı, aynı `retrieval.py` çekirdeğinin panel ve MCP tarafından ortak kullanılmasıdır. Tree-sitter tabanlı chunking, dense+sparse RRF, isim boost'u, çağrı ilişkileri, RAG ve koleksiyon yönetimi birlikte gerçek bir ürün omurgası oluşturuyor.

Yeni özellik eklemenin önündeki temel engel arama kalitesi değil, **özelliklerin tek bir uygulama dosyasında ve tek süreçte yoğunlaşmasıdır**. `panel.py` 1.193 satırda API, indeks işleri, Qdrant veri yönetimi, donanım keşfi, dosya sistemi erişimi, sohbet ve analitiği birlikte yürütüyor. UI tarafında da HTML/CSS/JavaScript aynı dosyalarda bulunuyor. Bu yapı birkaç ek özellik daha kaldırır; fakat sembol grafiği, Git geçmişi, kalıcı işler, çoklu kullanıcı veya eklenti sistemi gibi özelliklerde değişiklik maliyeti hızla büyür.

Önerilen ürün yönü:

1. Önce güvenilir indeks nesli, kalıcı iş kaydı ve provenance zemini.
2. Sonra gerçek Delphi sembol/referans grafiği ve ajan odaklı context pack.
3. Ardından Git-aware etki analizi, değerlendirme paneli ve kullanıcı geri bildirimi.
4. Çoklu kullanıcı/LAN/kurumsal kullanım ancak güvenlik sınırları tamamlandıktan sonra.

## 2. Doğrulanan mevcut durum

| Kontrol | Sonuç |
|---|---|
| Qdrant | Sağlıklı |
| Ollama | Sağlıklı |
| GPU | Kullanılabilir |
| Koleksiyonlar | Jedi, RESTRequest4Delphi, Synopse-mORMot2, unidac |
| Toplam indeks büyüklüğü | Yaklaşık 513 bin chunk |
| `pytest` | 6/6 geçti |
| Python derleme kontrolü | Geçti |
| UniDAC eval | Recall@8 %100, MRR 1.000 |
| Sıcak panel araması | 144 ms → 42 ms → 23 ms |

Eval sonucu olumlu fakat golden set yalnızca 10 soru, tek koleksiyon ve beklenen isim alt-dize eşleşmesine dayanıyor. Büyük Jedi ve mORMot2 koleksiyonları, çoklu koleksiyon sıralaması, filtreler, olumsuz sorgular ve RAG doğruluğu ölçülmüyor.

## 3. Mevcut mimari

```text
Delphi kaynakları
    ↓
chunker.py
    ↓ JSONL
panel.py indeks planı + embedding + call graph
    ↓
Qdrant
    ↓
retrieval.py
    ├── panel.py REST/RAG
    └── mcp_server.py MCP araçları
```

### Güçlü mimari kararlar

- Arama/açıklama/inceleme mantığının `retrieval.py` içinde ortaklaştırılması.
- Chunk kimliğinde satır numarasının kullanılmaması; satır kaymasında cache korunuyor.
- Dense ve sparse vektörlerin bağımsız, artımlı tamamlanabilmesi.
- Değişen içerik güvenle yazılmadan eski noktaların silinmemesi.
- MCP araçlarının ince adaptörler olarak kalması.
- Arama kalite değişikliklerinin Recall ve MRR ile ölçülmesi.
- Yerel çalışma ve Ollama kullanımı sayesinde kaynak kod gizliliğinin varsayılan olarak korunması.

## 4. Yeni özellik eklemeyi zorlaştıracak başlıca riskler

### P0 — Kalıcı ve atomik indeks nesli yok

İndeks güncellemesi aynı canlı koleksiyon üzerinde yapılıyor. İş yarıda kalırsa yeni ve eski veri karışabilir. `STATE["index_job"]` yalnızca bellekte tutulduğu için panel yeniden başladığında iş geçmişi, checkpoint ve hata bağlamı kaybolur.

Ek olarak `/api/index/start` çalışan iş kontrolünde `diffing` ve `linking` aşamalarını dışarıda bırakıyor. Bu aşamalarda ikinci bir manuel iş başlatılabilir ve global `STATE` üzerine yazılabilir.

**Öneri:** Her indeksleme için staging koleksiyonu + manifest + kalite kontrolü; başarıdan sonra Qdrant alias değişimi. Kalıcı `index_jobs` kaydı, iptal, yeniden deneme ve checkpoint eklenmeli.

### P0 — Kimlik ve merge modeli repository sınırını taşımıyor

Chunk kimliği `unit + kind + kod öneki` üzerinden üretiliyor; repository/library kimliği dahil değil. Panel ayrıca 64 bit hash'in yalnızca ilk 12 hex karakterini, yani 48 bitini Qdrant ID'sine çeviriyor.

Ayrı koleksiyonlarda bu çoğunlukla sorun değildir. Ancak merge sırasında iki kütüphanede aynı göreli yol ve imza varsa ID çakışır; mevcut kod ikinci noktayı sessizce atlar. Bu, birleşik koleksiyonda veri kaybına dönüşebilir.

**Öneri:** `repo_id + revision + relative_path + kind + qualified_symbol + normalized_signature` tabanlı tam 64 bit veya UUID kimliği. Merge öncesi collision raporu ve kaynak provenance zorunlu olmalı.

### P0 — “Tam kod” gerçekte tam değil

İndeksleme payload'a kodu `[:4000]` ile yazıyor. `get_chunk(full_code=True)` bu payload'ı döndürdüğü için adı “tam” olsa da uzun chunk'larda tam kaynak değildir. Chunker ayrıca 400 satırdan büyük düğümleri tamamen atıyor.

Bu durum context pack, refactoring yardımı, güvenilir code review ve etki analizi özelliklerini doğrudan sınırlar.

**Öneri:** Qdrant'ta arama özeti/chunk tutulmalı; tam kaynak güvenli bir source store veya kayıtlı repo kökünden okunmalı. Büyük metotlar parent/child AST chunk'larına bölünmeli ve `truncated` açıkça işaretlenmeli.

### P1 — `panel.py` çok fazla sorumluluk taşıyor

API routing, profil, import/export, indeks planı, embedding, çağrı grafiği, watcher, donanım taraması, RAG ve dosya görüntüleme aynı modülde. Yeni özellikler ortak global durum ve hata yönetimini daha kırılgan hale getirir.

**Önerilen ayrım:**

- `services/search_service.py`
- `services/index_service.py`
- `services/job_service.py`
- `services/collection_service.py`
- `services/rag_service.py`
- `repositories/qdrant_repository.py`
- `api/search_routes.py`, `api/index_routes.py`, `api/admin_routes.py`
- `config.py`

Bu bir mikroservis dönüşümü olmamalı; aynı süreçte modüler monolit yeterlidir.

### P1 — Çağrı grafiği büyük koleksiyonlarda pahalı

`_link_call_graph` koleksiyonun bütün noktalarını vektörleriyle belleğe alıyor ve ilişkisi değişmemiş noktalar dahil tamamını tekrar upsert ediyor. Jedi koleksiyonu yaklaşık 375 bin chunk olduğu için daha zengin grafik özellikleri bu yaklaşım üzerine eklenmemeli.

**Öneri:** Sembol ve ilişki verisini ayrı bir graph/index koleksiyonunda tutmak; yalnız değişen unit'leri yeniden çözmek; ters referansları ayrı kayıtlar olarak güncellemek.

### P1 — Import/export büyük koleksiyonlarda bellek baskısı yaratır

Export bütün JSONL satırlarını listede biriktirip daha sonra gzip yapıyor. Import ise dosyanın tamamını okuyor, tamamını açıyor ve `splitlines()` ile yeniden çoğaltıyor. 375 bin+ chunk'lı koleksiyonlarda bellek tüketimi hızla büyür.

Overwrite import mevcut koleksiyonu tüm satırlar doğrulanmadan önce siliyor. Bozuk bir dosya yarıda hata verirse eski koleksiyon kaybolmuş, yenisi eksik kalmış olabilir.

**Öneri:** Streaming gzip/JSONL, manifest ve checksum doğrulaması, staging koleksiyonu, başarıdan sonra alias/rename.

### P1 — Yapılandırma tek kaynak değil

`mcp-config.json` içinde Qdrant ve Ollama URL'leri var; fakat `retrieval.py` sabit `127.0.0.1` adreslerini kullanıyor. Bu URL ayarları fiilen etkisiz. Model seçimi de panel localStorage, MCP config ve kod varsayılanları arasında dağılmış durumda.

**Öneri:** Pydantic tabanlı tek `Settings` nesnesi; env > config file > default önceliği. Panel ve MCP aynı ayarı kullanmalı.

### P1 — Güvenlik sınırı yerel kullanımın ötesinde yeterli değil

- API anahtarı yalnız ortam değişkeni ayarlıysa çalışıyor; boşsa bütün yönetim uçları açık.
- `/api/view-file` kullanıcıdan mutlak dosya yolu alıyor.
- HTML viewer `srcdoc` iframe'ini sandbox olmadan çalıştırıyor; görüntülenen HTML aynı origin üzerinden panel API'lerine erişebilir.
- Import overwrite, delete, rename, dosya açma ve klasör seçme aynı API yüzeyinde.
- Rate limit, rol ayrımı, CSRF koruması ve yönetim audit log'u yok.

Varsayılan `127.0.0.1` bind riski azaltıyor; LAN veya çoklu kullanıcı özelliği eklenmeden önce çözülmeli.

**Öneri:** `viewer` için sandbox, izinli kaynak kökleri, read/admin rol ayrımı, yönetim uçlarında zorunlu auth, rate limit ve audit log.

### P2 — MCP/REST/UI araç tanımları elle çoğaltılıyor

Yeni bir MCP aracı eklemek için en az `mcp_server.py`, `panel.py`, `api.html` kartı ve JavaScript `TOOLS` kaydı değiştirilmek zorunda. Sözleşme kayması riski var.

**Öneri:** Tek tool registry/schema kaynağından MCP kaydı, REST test adapter'ı ve test UI formu üretmek. En azından contract testleriyle isim/parametre eşitliği doğrulanmalı.

### P2 — Test kapsamı ürün yüzeyine göre dar

Otomatik testlerin tamamı chunker regresyonları. Arama füzyonu, dedup, profil, merge collision, import/export, indeks planı, API auth, SSE ve MCP sözleşmeleri için izole otomatik test yok.

**Öneri:** Qdrant local/in-memory test doubles ile servis testleri; küçük fixture koleksiyonuyla API integration testleri; MCP tool contract snapshot'ları.

## 5. En değerli ek özellik adayları

| Sıra | Özellik | Kullanıcı değeri | Mimari etki | Tahmini efor | Ön koşul |
|---:|---|---|---|---|---|
| 1 | Gerçek symbol/reference graph | Çok yüksek | Yüksek | L | Sembol veri modeli |
| 2 | Agent context pack | Çok yüksek | Orta | M | Provenance + graph |
| 3 | Git-aware değişiklik etkisi | Çok yüksek | Yüksek | L | Repo/revision kimliği |
| 4 | Eval yönetimi ve kalite kapısı | Yüksek | Orta | M | Nesil manifesti |
| 5 | Arama geri bildirimi | Yüksek | Düşük/Orta | S-M | Telemetri şeması |
| 6 | Kaydedilmiş aramalar/çalışma alanları | Orta/Yüksek | Orta | M | Kullanıcı/oturum modeli |
| 7 | Otomatik dokümantasyon ve diyagram | Orta/Yüksek | Orta | M-L | Graph + context pack |
| 8 | Duplicate/benzer kod analizi | Orta | Düşük/Orta | S-M | `find_similar` mevcut |
| 9 | Çoklu kullanıcı ve paylaşım | Orta | Çok yüksek | L | Güvenlik ve kalıcı işler |
| 10 | Çoklu dil parser eklentileri | Değişken | Yüksek | L | Parser abstraction |

## 6. Özelliklerin ayrıntılı değerlendirmesi

### 6.1 Gerçek Delphi symbol/reference graph

Mevcut çağrı grafiği regex ve bare-name eşleşmesine dayanıyor. Ürünü rakiplerinden ayıracak sonraki büyük sıçrama; unit, class, interface, inheritance, implementation, property accessor, uses ve mümkün olduğunca qualified call ilişkilerini modellemektir.

Önerilen kullanıcı özellikleri:

- “Tanıma git”
- “Tüm referansları bul”
- “Çağıranlar / çağrılanlar”
- “Üst sınıflar / alt sınıflar”
- “Interface implementasyonları”
- “Bu değişiklik hangi unit ve public API'leri etkiler?”

Bu grafik Qdrant payload'ına büyük listeler halinde gömülmemeli; ayrı sembol ve edge kayıtları kullanılmalı.

### 6.2 Agent context pack

Yeni MCP aracı önerisi:

```text
get_context_pack(
  task,
  collections,
  token_budget,
  include_tests=true,
  include_relations=true
)
```

Araç yalnız benzer chunk'ları değil; ana sembol, tanımı, çağıran/çağrılanlar, aynı unit, ilgili tipler ve mümkünse testleri token bütçesi içinde seçmelidir. Bu, CodeIntel'i arama aracından ajanlar için gerçek kod bağlam motoruna dönüştürür.

### 6.3 Git-aware arama ve değişiklik etkisi

Her indeks nesline `repo_id`, `commit_sha`, branch ve indexed_at eklenmeli. Sonrasında:

- değişen semboller,
- ilgili commitler,
- blame,
- iki revision arasında semantik arama,
- “bu diff hangi çağıranları etkiler?”,
- eski/yeni API karşılaştırması

sunulabilir.

Kaynak kod Git deposu değilse özellik graceful fallback yapmalıdır.

### 6.4 Eval stüdyosu ve kalite kapısı

Mevcut eval iyi bir başlangıçtır fakat ürün özelliğine dönüştürülmeli:

- koleksiyon bazlı golden set,
- olumlu ve olumsuz sorgular,
- Recall@k, MRR, nDCG,
- dense/sparse/hybrid/rerank karşılaştırması,
- p50/p95 latency,
- nesiller arası regresyon,
- RAG kaynak doğruluğu ve “bağlam yetersiz” başarısı.

Yeni indeks nesli kalite eşiğini geçmeden canlı alias'a alınmamalıdır.

### 6.5 Kullanıcı geri bildirimi ve arama açıklanabilirliği

Her sonuç için:

- ilgili / ilgisiz,
- doğru sembol buydu,
- sonuç neden geldi: dense rank, sparse rank, isim boost'u, koleksiyon önceliği,
- sorguyu golden sete ekle

özellikleri eklenebilir. Bu veriler doğrudan otomatik ranking modeline verilmeden önce manuel eval genişletmek için kullanılmalıdır.

### 6.6 Duplicate ve benzer implementasyon analizi

`find_similar` zaten temel altyapıyı sağlıyor. Düşük maliyetli ürünleştirme:

- unit veya koleksiyon genelinde benzerlik taraması,
- eşik üstü çiftleri kümeleme,
- aynı kütüphane/farklı kütüphane ayrımı,
- kopya kod raporu,
- “muhtemel ortak yardımcı metoda çıkarılabilir” işareti.

Bu özellik kısa vadede en hızlı teslim edilebilecek yüksek görünürlüklü iyileştirmedir.

### 6.7 Kaydedilmiş çalışma alanları

Koleksiyon seçimi, filtreler, grup modu ve model tercihleri bugün tarayıcı localStorage'ında tutuluyor. “Workspace” nesnesi eklenirse ekip veya farklı görevler için aranacak koleksiyonlar, öncelikler, sahip/grup filtreleri ve model politikaları kaydedilebilir.

Tek kullanıcıda Qdrant profile koleksiyonu yeterli olabilir. Çoklu kullanıcı planlanıyorsa ayrı uygulama veritabanı gerekir.

## 7. Önerilen uygulama sırası

### Aşama 0 — Genişlemeye hazırlık

1. `panel.py` içinden servisleri ayır.
2. Tek `Settings` nesnesi oluştur.
3. Kalıcı job modeli ve tekil job lock ekle.
4. Index manifest/provenance şemasını tanımla.
5. Tam kaynak erişimi ve büyük chunk stratejisini düzelt.
6. API/MCP contract testleri ekle.

### Aşama 1 — Hızlı ürün kazanımları

1. Arama sonucu geri bildirimi.
2. Ranking açıklaması/debug görünümü.
3. Duplicate/benzer kod raporu.
4. Eval paneli ve koleksiyon bazlı golden set.

### Aşama 2 — Ayırt edici kod zekâsı

1. Symbol/reference graph.
2. Inheritance ve implementation ilişkileri.
3. `get_context_pack`.
4. Otomatik unit/API dokümantasyonu.

### Aşama 3 — Repository zekâsı

1. Git revision provenance.
2. Diff ve etki analizi.
3. Revision karşılaştırmalı arama.
4. Kaydedilmiş workspace'ler.

### Aşama 4 — Paylaşım ve ölçek

1. Rol tabanlı auth.
2. Güvenli LAN/HTTP MCP.
3. Kalıcı kuyruk ve dağıtık worker.
4. Streaming import/export ve backup/restore.

## 8. Şimdilik ertelenmesi gerekenler

- Otonom kod değiştiren agent: mevcut ürünün güvenilir read-only zekâsı daha değerlidir.
- Genel amaçlı çoklu dil desteği: Delphi uzmanlığı seyrelir; önce parser abstraction kurulmalı.
- Mikroservislere bölme: mevcut ölçek için gereksiz işletim maliyeti.
- Öğrenen özel reranker: geri bildirim verisi ve daha geniş eval olmadan overfit riski yüksek.
- Çoklu kullanıcı SaaS: güvenlik, tenant izolasyonu ve kalıcı iş modeli kurulmadan erken.

## 9. Net karar

Bir sonraki büyük özellik olarak doğrudan “daha fazla sohbet” veya “daha büyük model” eklemek yerine **Delphi sembol grafiği + context pack** yönüne gidilmelidir. Ancak bunu mevcut `_link_call_graph` fonksiyonunu büyüterek yapmak doğru değildir.

İlk teknik paket şu olmalıdır:

1. provenance/manifest,
2. tam kaynak erişimi,
3. ayrı sembol-edge veri modeli,
4. kalıcı indeks işi,
5. genişletilmiş eval.

Bu temel kurulduktan sonra `find_references`, `get_context_pack`, Git etki analizi ve otomatik dokümantasyon birbirini besleyen, düşük tekrar maliyetli özelliklere dönüşür.

