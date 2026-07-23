# Code-Intel — Dış Analiz Promptu (ChatGPT / Gemini için)

Bu dosyayı ChatGPT'ye veya Gemini'ye yapıştırın. Gerekirse aşağıda listelenen
dosyaları da ayrıca yapıştırın/yükleyin — model bu dosyaların içeriğini
göremiyorsa analiz yüzeysel kalır.

---

## Rol

Sen kıdemli bir yazılım mimarısın: vektör veritabanları (Qdrant), lokal LLM
dağıtımı (Ollama), hibrit arama (dense+sparse+RRF), FastAPI backend'leri ve
geliştirici araçları (dev tooling) konusunda derin deneyimin var. Bu projeyi
gerçek bir üretim sistemi olarak, göz kırpmadan, doğrudan eleştir.

## Görev

Aşağıda tanımlanan **Code-Intel** sistemini incele ve şunları üret:

1. **Mimari değerlendirme** — güçlü yönler, zayıf yönler, gizli riskler
   (özellikle: ölçeklenebilirlik, veri bütünlüğü, hata toleransı).
2. **Kod kalitesi bulguları** — varsa somut kod kokuları/anti-pattern'ler
   (dosya adı + satır aralığı vererek, tahmini değil).
3. **YENİLİK ÖNERİLERİ (öncelikli bölüm)** — bu sisteme eklenebilecek,
   henüz yapılmamış, gerçekten değer katacak özellikler. Her öneri için:
   - Ne eklenir, neden değerli
   - Kabaca nasıl uygulanır (hangi bileşen değişir)
   - Zorluk tahmini (kolay/orta/zor)
   Rakip/benzer araçlarda (örn. Sourcegraph Cody, Continue.dev, Cursor'ın
   codebase indexing'i, GitHub Copilot Workspace) olup burada eksik olan
   şeyleri özellikle ara.

## Sistem Açıklaması

**Amaç**: Delphi/Pascal kod tabanlarını (öncelik UniDAC kütüphanesi, ~25.000
kod parçası) tarayıp, hem anahtar kelime hem anlamsal (semantic) arama
yapılabilen, Türkçe açıklama üretebilen, bir sohbet arayüzü (RAG chat) sunan
ve MCP sunucusu üzerinden diğer AI ajanlarına (Claude, Codex, Gemini CLI gibi)
hizmet verebilecek bir kod-zekası sistemi.

**Yığın (stack)**:
- Python 3.12, FastAPI + uvicorn (`src/panel.py`, tek dosyalık backend)
- Ayrıştırma: `tree-sitter` + `tree-sitter-language-pack` (Pascal grameri
  hazır geliyor, özel yazılmadı) — `src/chunker.py`
- Hash: `xxhash` (XXH3-64, SIMD hızlandırmalı) — içerik değişikliği tespiti
- Vektör DB: Qdrant (Windows binary, yerel çalışıyor, `localhost:6333`)
  - Hibrit şema: named vectors `dense` (1024 boyut, multilingual-e5-large,
    `fastembed` ile) + `sparse` (BM25, yine `fastembed` ile) + Qdrant'ın
    native `FusionQuery(Fusion.RRF)` ile birleştirme
  - Ayrıca iki "iç" koleksiyon: `_index_history` (append-only log: her
    indeksleme çalıştırmasının yolu/tarihi/istatistikleri) ve
    `_index_profiles` (koleksiyon başına TEK nokta: kullanıcının elle
    girdiği versiyon/dil/klasör gibi alanlar)
- Çeviri/açıklama: Ollama (yerel), model seçimi donanım taramasıyla
  (CPU/RAM/GPU/VRAM, `nvidia-smi` + WMI) otomatik önerilebiliyor
- Arayüz: tek dosyalık vanilla JS/HTML/CSS (`static/index.html` sohbet,
  `static/settings.html` yönetim), build adımı yok, framework yok

**Şu anki özellikler**:
- Artımlı yeniden indeksleme: her çalıştırmada klasör yeniden taranır,
  içerik hash'i (XXH3) değişmeyen chunk'lar ATLANIR (yeniden embed
  edilmez), silinen dosyaların chunk'ları temizlenir
- Chunk türleri: `declProc` (interface bildirimleri, `/// <summary>`
  XML doc yorumları varsa çıkarılıp hem chunk metnine hem ayrı `doc`
  alanına ekleniyor), `defProc` (implementation gövdeleri), `declType`
  (tüm class/type bloğu)
- Çoklu koleksiyon arama: birden fazla indeks aynı anda seçilip
  aranabiliyor, sonuçlar RRF (rank-tabanlı) ile tek listede birleşiyor
- Kelime (sparse/BM25) ve Anlamsal (dense) indeksleme ayrı ayrı
  tetiklenebiliyor/yenilenebiliyor (biri hazır, diğeri sonra eklenebilir)
- Türkçe açıklama: hızlı (kısa, ucuz model) / derin (uzun, güçlü model)
  iki kademeli, sonuçlar Qdrant payload'ında kalıcı önbelleklenir

**Henüz YAPILMAYANLAR (bilinçli olarak ertelendi, öneri sunarken dikkate
alın — belki bunlardan bazıları asıl önerilmesi gereken şeylerdir)**:
- Çoklu dil desteği: şu an SADECE Pascal/Delphi gerçekten ayrıştırılıyor;
  diğer diller sadece dosya-uzantısı bazlı ETİKETLEME ile "Dil" alanında
  gösteriliyor, gerçek chunk'lanmıyor
- Claude/Gemini/OpenAI gibi bulut modelleri entegre değil (maliyet
  gerekçesiyle bilinçli olarak ertelendi) — sadece Ollama (yerel)
  kullanılıyor
- MCP sunucu katmanı henüz yazılmadı (planlanan ama bu oturumda
  başlanmadı) — hedef: bu arama/açıklama yeteneklerini Claude Code,
  Codex CLI, Gemini CLI gibi araçlara MCP tool olarak sunmak
- Değerlendirme/eval harness yok (golden-question benchmark'ı yok)
- Sadece tek makinede (yerel) çalışıyor; ikinci bir makineyle
  (kullanıcının Mac'i) paylaşımlı indeksleme/worker mimarisi tasarlandı
  ama uygulanmadı

## İncelenecek Dosyalar

Aşağıdaki dosyaları (küçükten büyüğe) modele ayrıca yapıştırın/yükleyin:

| Dosya | İçerik |
|---|---|
| `src/chunker.py` | Tree-sitter tabanlı ayrıştırma, doc-comment çıkarımı |
| `src/panel.py` | Tüm FastAPI backend'i (arama, indeksleme, geçmiş, profil, donanım) |
| `static/index.html` | Sohbet/arama arayüzü |
| `static/settings.html` | Yönetim paneli (indeksleme, model seçimi) |
| `DECISIONS.md` | Önceki mimari kararların kaydı (neden Qdrant, neden hibrit vs.) |
| `PANEL-PLAN.md` | Panel'in ilk tasarım planı |
| `BOOTSTRAP-REPORT.md` | İlk kurulum/test raporu (GPU hızlandırma, ilk indeksleme sonuçları) |

## Çıktı Formatı

Markdown, üç ana başlık (Mimari Değerlendirme / Kod Kalitesi / Yenilik
Önerileri). Yenilik önerilerini **etki sırasına göre** (en değerliden en
az değerliye) sıralayın, en az 5 tane somut öneri verin.

## Kontrol Listesi (kendi kendine sor)

- Her bulguya dosya adı + (mümkünse) satır numarası verdim mi?
- "Şunu ekleyin" derken sadece isim atmadım, gerçekten nasıl uygulanacağını
  yazdım mı?
- Zaten yapılmış bir şeyi (yukarıdaki "Şu anki özellikler" listesi) yeni
  öneri diye sunmadım mı?
- En az bir öneri, projenin asıl amacına (Delphi kod tabanını AI ajanlarına
  MCP üzerinden sunmak) doğrudan hizmet ediyor mu?
