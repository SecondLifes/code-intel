# Code-Intel — Mimari, Kod Kalitesi ve Ürün Yeniliği Analizi

## Rolün

Sen; yazılım mimarisi, geliştirici araçları, kod arama sistemleri ve yerel yapay zekâ çözümleri konusunda deneyimli kıdemli bir yazılım mimarısın.

Uzmanlık alanların:

- Qdrant ve vektör veritabanları
- Dense + sparse hibrit arama ve RRF
- RAG tabanlı kod asistanları
- Ollama ve yerel LLM dağıtımı
- FastAPI servisleri
- Tree-sitter tabanlı kaynak kodu ayrıştırma
- MCP sunucuları
- Sourcegraph Cody, Continue, Cursor ve GitHub Copilot gibi kod zekâsı araçları

Code-Intel projesini gerçek bir üretim sistemi olarak değerlendir. Nezaket amacıyla sorunları yumuşatma; fakat her eleştiriyi somut teknik kanıtla destekle.

## Temel kurallar

1. Yalnızca sağlanan dosyalarda görebildiğin kod hakkında kesin konuş.
2. Kodla ilgili her bulguda dosya adı ve mümkünse kesin satır aralığı ver.
3. Dosyada görmediğin davranışları olmuş gibi varsayma.
4. Kanıtlanamayan noktaları açıkça “varsayım” veya “doğrulanması gerekiyor” şeklinde işaretle.
5. Genel geçer, yüzeysel tavsiyeler verme.
6. Zaten uygulanmış bir özelliği yeni öneri olarak sunma.
7. Bir önerinin neden gerekli olduğunu, hangi mevcut sorunu çözdüğünü ve nasıl uygulanacağını birlikte açıkla.
8. Rakip ürünler hakkında güncel internet erişimin varsa yalnızca resmî ve güncel kaynakları araştır. Araştırma tarihini ve kaynak bağlantılarını belirt.
9. İncelemen için gerekli bir dosya eksikse bunu açıkça bildir. Eksik dosyayı görmeden o bölüm hakkında kod bulgusu üretme.

## Projenin amacı

Code-Intel, öncelikle Delphi/Pascal kod tabanlarını tarayan bir kod zekâsı sistemidir.

Başlıca hedefleri:

- Yaklaşık 25.000 kod parçası içeren UniDAC gibi büyük Delphi kütüphanelerini indekslemek
- Anahtar kelime ve anlamsal arama sunmak
- Kod parçaları için Türkçe açıklamalar üretmek
- RAG tabanlı bir sohbet arayüzü sağlamak
- Arama ve açıklama yeteneklerini MCP üzerinden Claude Code, Codex, Gemini CLI ve benzeri AI ajanlarına sunmak

## Mevcut teknik yapı

- Python 3.12
- FastAPI ve Uvicorn
- Tree-sitter ve `tree-sitter-language-pack`
- XXH3-64 içerik hash’i
- Qdrant
- `multilingual-e5-large` tabanlı 1024 boyutlu dense vektörler
- FastEmbed tabanlı BM25 sparse vektörler
- Qdrant `FusionQuery(Fusion.RRF)` ile hibrit arama
- Ollama üzerinden yerel LLM kullanımı
- Vanilla HTML, CSS ve JavaScript arayüzü
- Build adımı veya frontend framework’ü bulunmuyor

Backend’in büyük bölümü `src/panel.py` dosyasında yer alıyor.

## Qdrant veri modeli

Ana kod koleksiyonlarına ek olarak iki sistem koleksiyonu bulunuyor:

- `_index_history`: Her indeksleme çalışmasının yolunu, zamanını ve istatistiklerini tutan append-only kayıt
- `_index_profiles`: Koleksiyon başına tek nokta kullanarak sürüm, dil ve klasör gibi kullanıcı tarafından girilen bilgileri tutan profil

Kod koleksiyonlarında named vector yapısı kullanılıyor:

- `dense`: Anlamsal arama
- `sparse`: BM25 tabanlı sözcüksel arama

## Uygulanmış özellikler

Aşağıdakileri yeni özellik olarak önerme:

- Artımlı yeniden indeksleme
- XXH3 ile değişmeyen chunk’ları atlama
- Silinmiş dosyalara ait chunk’ları temizleme
- `declProc`, `defProc` ve `declType` chunk türleri
- XML `/// <summary>` açıklamalarını çıkarma
- Çoklu koleksiyon araması
- Koleksiyonlar arası RRF birleştirmesi
- Sparse ve dense indekslerin ayrı ayrı oluşturulabilmesi
- Hızlı ve derin olmak üzere iki seviyeli Türkçe açıklama
- Açıklamaların Qdrant payload’ında önbelleklenmesi
- Donanım taramasıyla uygun Ollama modeli önerilmesi

## Bilinen eksikler

Aşağıdakiler henüz uygulanmadı:

- Pascal dışındaki diller için gerçek parser ve chunking desteği
- Claude, Gemini veya OpenAI gibi bulut modelleri
- MCP sunucu katmanı
- Golden-question benchmark veya başka bir eval sistemi
- Çok makineli worker ve paylaşımlı indeksleme mimarisi

Bu maddeleri önerebilirsin; ancak yalnızca isimlerini tekrar etmekle yetinme. Proje bağlamında sağlayacakları değeri, mimari tasarımlarını ve uygulanma sıralarını açıkla.

## İncelenecek dosyalar

- `src/chunker.py`
- `src/panel.py`
- `static/index.html`
- `static/settings.html`
- `DECISIONS.md`
- `PANEL-PLAN.md`
- `BOOTSTRAP-REPORT.md`

Önce hangi dosyalara gerçekten erişebildiğini listele. İçeriği sağlanmamış dosyalar için analiz yapma.

# Görevler

## 1. Mimari değerlendirme

Sistemi aşağıdaki açılardan değerlendir:

- Bileşenlerin sorumluluk ayrımı
- Ölçeklenebilirlik
- Veri bütünlüğü
- Hata toleransı ve yeniden başlatılabilirlik
- Eşzamanlı indeksleme ve yarış koşulları
- Qdrant koleksiyon ve payload tasarımı
- Şema ve embedding modeli geçişleri
- İndeks sürümleme
- Silme ve güncelleme tutarlılığı
- Arama kalitesi
- Ollama bağımlılığı ve model yaşam döngüsü
- Güvenlik
- Gözlemlenebilirlik
- Test edilebilirlik
- Bakım maliyeti
- MCP entegrasyonuna hazır olma durumu

Her bulguyu şu formatta ver:

- **Bulgu**
- **Kanıt:** dosya ve satır aralığı
- **Etkisi**
- **Önerilen düzeltme**
- **Öncelik:** Kritik / Yüksek / Orta / Düşük
- **Güven düzeyi:** Yüksek / Orta / Düşük

Önce güçlü yönleri, ardından riskleri açıkla.

## 2. Kod kalitesi analizi

Somut olarak görülebilen problemleri tespit et:

- Aşırı büyümüş dosya veya fonksiyonlar
- Sorumlulukların birbirine karışması
- Tekrarlanan kod
- Hata yönetimi sorunları
- Kaynakların kapatılmaması
- Bloklayan işlemlerin async endpoint içinde çalıştırılması
- Yarış koşulları
- Global değişken ve paylaşılan durum
- Kontrolsüz subprocess kullanımı
- Path traversal veya komut enjeksiyonu
- Eksik giriş doğrulaması
- Sessizce yutulan hatalar
- Sabitlenmiş model veya şema varsayımları
- Verimsiz Qdrant sorguları
- Frontend durum yönetimi ve XSS riskleri
- Test edilmesi zor tasarım kararları

Her bulgu için:

| Alan | Açıklama |
|---|---|
| Önem | Kritik / Yüksek / Orta / Düşük |
| Yer | Dosya ve kesin satır aralığı |
| Kanıt | İlgili kodun kısa açıklaması |
| Risk | Gerçek kullanımda oluşabilecek sonuç |
| Çözüm | Uygulanabilir düzeltme |
| Efor | Küçük / Orta / Büyük |

Kanıt bulunmayan kategorilerde problem uydurma.

## 3. Yenilik ve ürün geliştirme önerileri

Bu bölüm analizin en önemli kısmıdır.

En az 8 somut öneri üret ve etki sırasına göre sırala. Öneriler yalnızca teknik borç temizliği değil, Code-Intel’i daha güçlü bir kod zekâsı ürünü hâline getirecek yetenekler olmalı.

Şu alanları özellikle araştır:

- MCP üzerinden ajanlara sunulabilecek yüksek değerli araçlar
- Sembol, referans ve çağrı grafiği
- Kod ilişkileri ve bağımlılık analizi
- Repo-level context oluşturma
- Değişiklik etkisi analizi
- Git geçmişi ve blame bilgisinin aramaya katılması
- Mimari ve API dokümantasyonunun otomatik çıkarılması
- Arama kalitesi değerlendirmesi
- Kullanıcı geri bildirimlerinden öğrenme
- Güven ve kaynak gösterimi
- İndeks güncelliği ve provenance
- Çoklu repository desteği
- IDE ve CLI entegrasyonu
- Güvenli bulut modeli fallback’i
- Çok makineli indeksleme
- Sourcegraph Cody, Continue, Cursor ve GitHub Copilot ekosisteminde bulunan fakat Code-Intel’de olmayan yetenekler

Her öneriyi şu şablonla açıkla:

### Öneri adı

- **Çözdüğü problem**
- **Kullanıcı değeri**
- **Önerilen kullanıcı deneyimi**
- **Teknik tasarım**
- **Değişecek bileşenler**
- **Yeni veri modeli veya Qdrant alanları**
- **Bağımlılıklar**
- **Riskler**
- **Zorluk:** Kolay / Orta / Zor
- **Tahmini uygulama büyüklüğü:** S / M / L / XL
- **Beklenen etki:** Düşük / Orta / Yüksek / Çok yüksek
- **Önerilen sıra**
- **Başarı ölçütü**

En az bir öneri, Delphi kod tabanını AI ajanlarına MCP üzerinden sunma ana hedefine doğrudan hizmet etmeli.

## 4. Rakip ve yetenek boşluğu analizi

Code-Intel’i aşağıdakilerle karşılaştır:

- Sourcegraph Cody
- Continue
- Cursor codebase indexing
- GitHub Copilot’ın codebase/agent yetenekleri

Güncel ve doğrulanabilir bilgiye erişebiliyorsan şu tabloyu oluştur:

| Yetenek | Code-Intel | Cody | Continue | Cursor | GitHub Copilot | Code-Intel için önem |
|---|---:|---:|---:|---:|---:|---|

Rakipte bulunduğunu doğrulayamadığın bir özelliği kesin bilgi gibi yazma. Resmî kaynak bağlantısı ver veya “doğrulanamadı” olarak işaretle.

## 5. Öncelikli yol haritası

Önerileri şu dönemlere ayır:

- **İlk 2 hafta:** Temel güvenilirlik ve ölçüm
- **İlk 1–2 ay:** MCP ve yüksek değerli kod zekâsı özellikleri
- **3–6 ay:** Ölçekleme, çoklu dil ve ileri seviye analiz

Her dönem için:

- Yapılacak işler
- İşlerin bağımlılık sırası
- Beklenen çıktı
- Kabul kriterleri
- Ertelenmesi gereken işler

Son olarak, yalnızca üç maddelik bir “hemen şimdi yapılacaklar” listesi ver.

# Zorunlu çıktı düzeni

1. **İnceleme kapsamı ve erişilebilen dosyalar**
2. **Yönetici özeti**
3. **Mimari değerlendirme**
4. **Kod kalitesi bulguları**
5. **Yenilik önerileri**
6. **Rakip ve yetenek boşluğu analizi**
7. **Öncelikli yol haritası**
8. **Hemen şimdi yapılacak üç iş**
9. **Belirsizlikler ve görülmesi gereken ek dosyalar**

Yanıtı Türkçe ve Markdown olarak hazırla. Bulguları önem ve etki sırasına göre sırala. Kesinlik ile varsayımı birbirinden açıkça ayır.
