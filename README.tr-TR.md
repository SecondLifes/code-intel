
# 🧠 CodeIntel

<div align="center">

**Delphi/Pascal kod tabanları — ve ~45 diğer dil — için yerel-öncelikli, hibrit (anlamsal + kelime) bir kod-zekâsı aracı; RAG sohbet paneli ve AI kod ajanları için 17 araçlı bir MCP sunucusuyla birlikte.**

[![🇹🇷 Türkçe ](https://img.shields.io/badge/Turkish-Türkiye-red)](README.tr-TR.md)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-panel%20%2B%20API-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Qdrant](https://img.shields.io/badge/Qdrant-hybrid%20search-DC244C)](https://qdrant.tech/)
[![Ollama](https://img.shields.io/badge/Ollama-local%20LLM-000000)](https://ollama.com/)
[![MCP](https://img.shields.io/badge/MCP-17%20araç-purple)](https://modelcontextprotocol.io/)
[![Claude Code](https://img.shields.io/badge/Claude-Code-brown?logo=anthropic)](https://claude.ai)

*[🇬🇧 English](README.md) · [Katkıda Bulunma](CONTRIBUTING.tr-TR.md) · [Davranış Kuralları](CODE_OF_CONDUCT.md) · [Güvenlik](SECURITY.tr-TR.md) · [Teşekkürler](ACKNOWLEDGMENTS.tr-TR.md)*

![Overview](docs/images/hero.png)

</div>

## 📋 İçindekiler

- [English-](README.md)İngilizce
- [Bu proje nedir?](#-bu-proje-nedir)
- [Neden kullanılır?](#-neden-kullanılır)
- [Temel Yetenekler](#-temel-yetenekler)
- [Desteklenen Diller](#-desteklenen-diller)
- [MCP Araçları (AI Ajanları İçin)](#-mcp-araçları-ai-ajanları-i̇çin)
- [Proje Yapısı](#-proje-yapısı)
- [Ön Koşullar](#-ön-koşullar)
- [Hızlı Başlangıç](#-hızlı-başlangıç)
- [Uzak GPU Devretme (opsiyonel)](#-uzak-gpu-devretme-opsiyonel)
- [Güvenlik Duruşu](#-güvenlik-duruşu)
- [Tasarım ve Felsefe](#-tasarım-ve-felsefe)
- [Teşekkürler](#-teşekkürler)
- [Katkıda Bulunma](#-katkıda-bulunma)

---

## 💡 Bu proje nedir?

**CodeIntel** bir AI-davranış kuralları kiti değil — gerçek, çalışan bir uygulama: bir FastAPI backend + Qdrant vektör veritabanı + Ollama yerel LLM'i, büyük Delphi kütüphanelerini (UniDAC, ~25.000 chunk) indeksleme ihtiyacından doğup artık onlarca dile genelleşen bir kod-arama-ve-anlama aracına dönüştürecek şekilde bir araya getirilmiş.

Normal bir kod tabanı arama kutusunun cevaplayamayacağı soruları cevaplıyor:

- ✅ **Hibrit arama** — Qdrant'ın RRF'i üzerinden dense (anlamsal) + sparse (BM25 kelime) füzyonu, isim-eşleşme boost'u ve isteğe bağlı cross-encoder rerank geçişiyle
- ✅ **Gerçek atıflı RAG sohbet** — "Cevapla" modu üst-K eşleşmelerden yanıt verir; "Derin" (derin araştırma) modu, yanıtlamadan önce ana sembolün tam gövdesini + çağıranlarını/çağırdıklarını/tip-hiyerarşisini/unit-bağımlılıklarını TEK bir bağlam paketinde toplar
- ✅ **MCP üzerinden ajana hazır** — 17 araç (arama, açıklama, ilişkiler, etki analizi, bağlam paketleri...) hem stdio hem LAN'a açık Streamable HTTP üzerinden sunulur, böylece Claude Code/Codex CLI/Gemini CLI web panelinin kullandığı AYNI indeksi sorgulayabilir
- ✅ **Kendi kendini belgeler** — koleksiyon başına, AI destekli TR/EN çeviriyle, çok bölümlü tam bir HTML/PDF/DOCX manual üretir

> 25.000 chunk'lık bir Delphi kod tabanında `grep`-ve-umut etmeye, ya da bir AI ajanına elinizdeki dosya dışında hiçbir bağlam olmadan "bunu açıkla" demeye veda edin.

---

## 🤔 Neden kullanılır?

| CodeIntel Olmadan | CodeIntel İle |
|---|---|
| Yalnız `grep`/tam metin arama, anlamsal eşleşme yok | Hibrit dense+sparse arama, hem Türkçe sorgu hem İngilizce/Delphi kodu çalışır |
| Bir AI ajanı yalnız yapıştırdığınız dosyayı görür | MCP araçları istek üzerine tam çağrı grafiğini, tip hiyerarşisini, unit bağımlılıklarını verir |
| "Bu 6 neredeyse-aynı `Split` fonksiyonundan hangisi daha güvenli?" — 6'sını da okumadan kimse bilemez | Karşılaştırma tablosu, LLM'den her adayı yan yana stabilite/performans açısından puanlamasını ister |
| Kodun *neden* değiştiğini anlamak için eski commit'leri tekrar okuma | `analyze_impact` bir diff aralığını etkilenen chunk'larla ilişkilendirir |
| Geliştirici dokümanlarını elle yazma/güncel tutma | `document_unit`/manual üretici bunları üretip önbelleğe alır, istek üzerine yenilenir |

---

## 🌟 Temel Yetenekler

![Core Features](docs/images/core-features.png)

- **Hibrit RRF arama** — aynı anda birden fazla koleksiyonda, dil bazlı filtrelerle, cross-encoder rerank ile ve her sonuç için "neden burada sıralandı" dökümüyle.
- **RAG sohbet** (`/api/ask`, `/api/ask/stream`) ve **derin araştırma** (`/api/research/stream`, token bütçeli bağlam paketleri) — ikisi de SSE akışlı, ikisi de önbellekli, ikisi de kesilme-farkında (Ollama'nın kendi `done_reason` sinyalini, sessizce kesik bir cevap sunmak yerine kullanıcıya gösterir).
- **Fonksiyon karşılaştırma tablosu** (`/api/compare`) — bir sorgu aynı işi yapan birden fazla implementasyon ortaya çıkardığında, tek bir LLM çağrısı her birini stabilite/performans açısından tek cümlelik gerekçeyle puanlar.
- **Sembol grafiği** — kalıtım, `find_references`, çağıran/çağrılan kenarları, kendi iç koleksiyonunda saklanır (her noktanın payload'ına gömülü değil, böylece kod koleksiyonunun boyutundan bağımsız ölçeklenir).
- **Git provenance + etki analizi** — bir commit aralığını dokunduğu chunk'larla ilişkilendirir.
- **Otomatik üretilen manual** — koleksiyon başına HTML/PDF/DOCX dokümantasyon, açılır/kapanır sınıf-ağacı kenar çubuğu, kendi barındırılan syntax highlighting (CDN bağımlılığı yok), AI destekli iki dilli (TR/EN) çeviri.
- **Kopya-kod tespiti** — zaten indekslenmiş embedding'ler üzerinde eşik-tabanlı benzerlik taraması (yeniden embed gerekmez).
- **Atomik, devam ettirilebilir indeksleme** — staging+alias nesil modeli (yeniden indeksleme ayrı bir koleksiyonda inşa edilir, ancak tamamlanıp doğrulandığında atomik olarak devreye alınır), kalıcı iş kuyruğu bir yeniden başlatmayı indeks-ortasında bile atlatır.
- **Owner/Group kayıt defteri, okuma/yönetim rol ayrımlı API anahtarları, hız sınırlama, audit log** — aynı panel hem tek-operatörlü yerel kullanımı hem LAN-paylaşımlı çoklu-anahtar erişimini destekler.

---

## 🌐 Desteklenen Diller

Jenerik bir Tree-sitter tabanlı motor yapısal olarak **~45 dili** kapsıyor; **8 dilin derin desteği var** (iç içe sınıf metotları için ebeveyn/çocuk AST bölmesi, `uses`/import çıkarımı, unit-head ayrıştırma): **Delphi/Pascal**, **Python**, **C#**, **C/C++**, **Java**, **JavaScript/TypeScript**, **Go**, **Rust**.

---

## 🤖 MCP Araçları (AI Ajanları İçin)

`src/mcp_server.py`, stdio (varsayılan) ve isteğe bağlı LAN'a açık Streamable HTTP üzerinden 17 araç sunar — her aracın `/api/mcp/*` altında bir REST test ucu da vardır (uyum `tests/test_api.py::test_mcp_rest_parity` ile zorunlu kılınır), `static/api.html`'den canlı denenebilir.

| Araç | Amaç |
|---|---|
| `search_code` | Dil/tür/unit filtreleriyle hibrit arama |
| `find_similar` | Verilen bir chunk'ın en yakın komşuları |
| `read_unit` | Bir kaynak dosyanın (unit) tam içeriği |
| `get_chunk` | Tek bir chunk'ın tam payload'ı |
| `get_relations` | Çağıran/çağrılan/aynı-dosya ilişkileri |
| `explain_chunk` | Hızlı veya derin LLM açıklaması (önbellekli) |
| `review_code` | Bir chunk'ın LLM kod incelemesi |
| `propose_edit` | Yalnız-göster diff önerisi (asla otomatik uygulanmaz) |
| `ask_domain_model` | Bir soruyu alana özel bir modele yönlendirir (örn. SQL) |
| `get_type_hierarchy` | Bir tipin ataları/alt sınıfları |
| `find_references` | Bir koleksiyonda bir isme tüm referanslar |
| `analyze_impact` | Bir git diff aralığını etkilenen chunk'larla ilişkilendirir |
| `get_unit_deps` | Bir dosya için `uses`/import bağımlılık grafiği |
| `get_context_pack` | Bir görev için token-bütçeli, çok kaynaklı bağlam paketi |
| `document_unit` | Bir dosya için dokümantasyon üretir/getirir (önbellekli) |
| `list_domain_models` | Yapılandırılmış alana-özel modelleri listeler |
| `list_collections` | İndekslenmiş koleksiyonları ve istatistiklerini listeler |

---

## 📂 Proje Yapısı

```
code-intel/
│
├── src/
│   ├── retrieval.py          # Çekirdek arama/RAG/açıklama mantığı — hem panel HEM mcp_server tarafından ortak kullanılır, asla kopyalanmaz
│   ├── chunker.py            # Tree-sitter çok dilli parçalama
│   ├── manual.py             # Dokümantasyon üretici (HTML/PDF/DOCX, i18n)
│   ├── mcp_server.py         # 17 MCP aracı, stdio + Streamable HTTP
│   ├── panel.py              # FastAPI uygulama girişi + security_guard middleware
│   ├── api/                  # Modüler router'lar: search, index, admin, manual, mcp
│   └── services/             # Ortak durum, profiller, API anahtarları, yedekler, indeksleme hattı
│
├── static/
│   ├── index.html            # Arama + sohbet paneli
│   ├── settings.html         # Koleksiyon/indeks yönetimi
│   ├── api.html               # REST + MCP araç test sayfası
│   └── viewer.html           # Bağımsız dosya görüntüleyici
│
├── tests/                    # pytest — testlerin çoğu canlı bir Qdrant gerektirir (@needs_qdrant, başarısız değil atlanır)
├── tools/                    # install.ps1 / start-system.ps1 / stop-system.ps1 / uninstall.ps1 / install-autostart.ps1
├── qdrant-bin/                # Qdrant ikili dosyası (Windows)
├── mcp-config.json           # MCP sunucusu varsayılanları (Qdrant/Ollama URL'leri, model adları)
├── requirements.txt          # Pinlenmiş bağımlılık sürümleri (içindeki onnxruntime-gpu notuna bakın)
└── pyproject.toml
```

> Bu kopyada YOK: `data/` (Qdrant depolama + chunk önbellekleri), `backups/`, `logs/` — hepsi yerelde yeniden üretilir, hepsi `.gitignore`'lu. `.venv/` de yok, ve bu kasıtlı — aşağıdaki Hızlı Başlangıç'a bakın.

---

## 🔧 Ön Koşullar

- **Python 3.12 veya 3.13** — daha yenisi DEĞİL. Pinlenmiş bağımlılıkların (`numpy`, `onnxruntime-gpu`, `grpcio`, `lxml`, `mmh3`...) 3.14+ için henüz hazır Windows wheel'i yok, çok yeni bir yorumlayıcı kurulumda derleyici hatasıyla patlar. `tools/install.ps1` bunu sizin için kontrol eder. Tam açıklama için CONTRIBUTING.tr-TR.md "Desteklenen Python sürümleri"ne bakın.
- **Qdrant** (`qdrant-bin/` altında paketlenmiş ikili, ya da kendi kurulumunuz)
- **Ollama** — sohbet, derin araştırma, açıklamalar, çeviri ve karşılaştırma tablosu için. Bu makinede yerel, ya da ağınızdaki uzak bir sunucu — `tools/install.ps1` hangisini istediğinizi sorar. (Aşağıdaki GPU/CPU seçiminden BAĞIMSIZDIR — embedding/reranking, Ollama nerede çalışırsa çalışsın her zaman yerelde çalışır.)
- **PowerShell 7+ (`pwsh`)** — `tools/*.ps1` PowerShell script'leridir (Windows-öncelikli; Python/FastAPI çekirdeğinin kendisi platform-bağımsızdır)
- CUDA destekli bir GPU isteğe bağlıdır ama embedding verimi için şiddetle önerilir (bkz. `requirements.txt`'nin `onnxruntime-gpu` pinleme notu). GPU'nuz yok mu? `tools/install.ps1` GPU-mu-CPU-mu diye de sorar, CPU seçerseniz NVIDIA CUDA paketlerini boşuna indirmek yerine tamamen atlar.

---

## ⚡ Hızlı Başlangıç

```bash
# 1. Kur (Python sürümünüzü kontrol eder, yerel-mi-uzak-mı Ollama sorar, sonra
#    `pip install -r requirements.txt`'i kasıtlı olarak sistemde kurulu
#    Python'unuza karşı çalıştırır — proje-lokal .venv/uv DEĞİL, neden için
#    CONTRIBUTING.tr-TR.md "Antivirüs uyarıları"na bakın)
pwsh tools/install.ps1

# 2. Qdrant + Ollama + paneli başlat (Windows)
pwsh tools/start-system.ps1 -NoBrowser
```

Ardından `http://127.0.0.1:8500`'ü açın — Ayarlar'dan bir klasör indeksleyin, sonra ana sayfadan arayın/sohbet edin. Panel yerine (veya panelle birlikte) bir MCP sunucusu olarak kullanmak için AI CLI'nızın MCP yapılandırmasını `src/mcp_server.py`'a (stdio) yönlendirin — okuduğu varsayılanlar (Qdrant/Ollama URL'leri, hızlı/derin model adları) için `mcp-config.json`'a bakın.

Diğer yaşam döngüsü script'leri: `pwsh tools/stop-system.ps1` (panel + Qdrant'ı durdur), `pwsh tools/install-autostart.ps1` (Windows oturum açılışında çalıştır), `pwsh tools/uninstall.ps1` (servisleri durdur, autostart görevini kaldır; daha derin temizlik için `-RemovePackages`/`-RemoveData` — her birinin neye dokunup neye dokunmadığı için script'in kendi başlığına bakın).

```bash
pytest tests/ -q   # testlerin çoğu için canlı bir Qdrant gerekir (tools/start-system.ps1); geri kalanı sorunsuzca atlanır
```

---

## 🖧 Uzak GPU Devretme (opsiyonel)

GPU'suz bir makinede mi çalışıyorsunuz? `remote-client/`, ayrı dağıtılan opsiyonel bir senkron istemcisi: yerel bir klasörü izler, değişen dosyaları HTTP ile GPU'lu bir CodeIntel sunucusuna gönderir (`POST /api/remote-mirror/{client_id}/...`, admin-anahtarı gerektirir, path-traversal'a karşı sıkı doğrulanır — bkz. `src/api/remote_routes.py`). Sunucu bunları istemciye özel bir ayna klasöre yazar; o klasör bir koleksiyonun `path`i olarak `auto_refresh: true` ile kayıtlıysa, **mevcut** watcher/artımlı-yeniden-indeksleme hattı otomatik devreye girer — yeni indeksleme mantığı yok, sadece dosyaları başka bir yerden sunucunun diskine güvenle getirmenin bir yolu. Hiç kullanmazsanız sunucuda sıfır etki. Bkz. [remote-client/README.md](remote-client/README.md).

---

## 🔐 Güvenlik Duruşu

Varsayılan olarak `127.0.0.1`'e bağlanır; LAN'a açılma rol-ayrımlı API anahtarları (`read`/`admin`) ile isteğe bağlıdır. Tam tehdit modeli için [SECURITY.tr-TR.md](SECURITY.tr-TR.md)'e bakın — bu kod tabanını denetliyorsanız bilmeye değer iki düzeltme dahil: 2026-07-25'te eklenen istemci-kontrollü giden-URL (SSRF) kısıtlaması ve aynı tarihli HTML/JS-bağlamına-duyarlı kaçış düzeltmesi (salt `&<>` kaçışı bir `onclick="fn('...')"` özniteliği İÇİNDE yeterli DEĞİLDİR — bkz. `escJs()`/`_esc_js()`).

---

## 🎯 Tasarım ve Felsefe

![Design & Philosophy](docs/images/design-philosophy.png)

**Doğrula, varsayma.** Bu kod tabanının git geçmişinde kayıtlı her düzeltme — SSRF kısıtlaması, kaçış düzeltmesi, atomik-import yeniden tasarımı, check-then-set yarış düzeltmesi — sadece muhakeme edilip test edilmeden bırakılmadı, eski kodda BAŞARISIZ olan yeni kodda GEÇEN bir testle kanıtlandı. Aynı disiplin arama sıralamasına (`tests/eval.py`'nin altın-sorgu ölçütü) ve cevapların kendisine de uzanır (her iki sohbet modu da, sessizce kesilmiş bir cevabı eksiksizmiş gibi sunmak yerine Ollama'nın kendi kesilme sinyalini bildirir). Bilinçli ödünleşim: bir düzeltmeyi "okuyunca doğru görünüyor" demekten daha yavaş yayınlamak, karşılığında "testler geçti" ifadesinin gerçekten bir anlam taşıdığı bir kod tabanı.

---

## 🙏 Teşekkürler

Bu aracın üzerine inşa edildiği açık kaynak projeler ve modeller için bkz. [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) / [ACKNOWLEDGMENTS.tr-TR.md](ACKNOWLEDGMENTS.tr-TR.md).

---

## 🤝 Katkıda Bulunma

Bkz. [CONTRIBUTING.md](CONTRIBUTING.md) / [CONTRIBUTING.tr-TR.md](CONTRIBUTING.tr-TR.md).

---

<div align="center">

**Emrah BAŞPINAR** ve **Recep Eymen BAŞPINAR** tarafından özenle yapıldı.

*[Katkıda Bulunma](CONTRIBUTING.tr-TR.md) · [Davranış Kuralları](CODE_OF_CONDUCT.md) · [Güvenlik](SECURITY.tr-TR.md) · [Teşekkürler](ACKNOWLEDGMENTS.tr-TR.md)*

</div>
