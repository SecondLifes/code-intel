# 🙏 Teşekkürler

**CodeIntel**, aşağıdaki açık kaynak projelerin, modellerin ve toplulukların
omuzlarında duruyor. Bu sayfa onlara açıkça teşekkür etmek için var — README'de
bir kez link vermekle yetinmek yerine.

## 📖 Açık Kaynak

| Proje | Burada Ne İçin Kullanılıyor | Lisans |
|---|---|---|
| [Qdrant](https://github.com/qdrant/qdrant) | Vektör veritabanı — hibrit dense+sparse arama (`FusionQuery(Fusion.RRF)`), adlandırılmış vektörler, payload indeksleri, atomik staging+alias nesil modeli | Apache-2.0 |
| [FastAPI](https://github.com/tiangolo/fastapi) + [Starlette](https://github.com/encode/starlette) + [Uvicorn](https://github.com/encode/uvicorn) | Tüm web paneli/API katmanı (`src/api/*`), sohbet/derin araştırma için SSE akışı | MIT |
| [Tree-sitter](https://github.com/tree-sitter/tree-sitter) + [tree-sitter-language-pack](https://github.com/Goldziher/tree-sitter-language-pack) | Çok dilli AST parçalama (`src/chunker.py`) — Delphi/Pascal artı tek bir jenerik motorla ~45 diğer dil | MIT |
| [FastEmbed](https://github.com/qdrant/fastembed) (+ `fastembed-gpu`) | Dense (`intfloat/multilingual-e5-large`) ve sparse (`Qdrant/bm25`) embedding üretimi | Apache-2.0 |
| [intfloat/multilingual-e5-large](https://huggingface.co/intfloat/multilingual-e5-large) | Dense embedding modeli — 1024 boyutlu çok dilli (Türkçe sorgu / İngilizce kod) anlamsal arama | MIT |
| [jinaai/jina-reranker-v2-base-multilingual](https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual) | Cross-encoder reranker — füzyonlanmış üst-N adaylar üzerinde isteğe bağlı hassasiyet geçişi | CC-BY-NC-4.0 (ticari olmayan; burada yalnız yerel çalışan iç bir araçta kullanılıyor, yeniden dağıtılmıyor) |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) (`onnxruntime-gpu`) | Embedding/reranker modelleri için çıkarım motoru — GPU hızlandırma için CUDA execution provider | MIT |
| [Ollama](https://github.com/ollama/ollama) | Yerel LLM sunumu — sohbet (`/api/ask`), derin araştırma (`/api/research/stream`), açıklamalar, çeviri, fonksiyon karşılaştırma tablosu (`/api/compare`) | MIT |
| [Model Context Protocol (MCP) Python SDK](https://github.com/modelcontextprotocol/python-sdk) | `src/mcp_server.py` — stdio ve Streamable HTTP üzerinden Claude Code/Codex/Gemini CLI'a sunulan 17 araç | MIT |
| [Pygments](https://github.com/pygments/pygments) | Üretilen PDF/DOCX manuallerde syntax highlighting | BSD-2-Clause |
| [highlight.js](https://github.com/highlightjs/highlight.js) | Kendi barındırılan (CDN'siz) syntax highlighting — arama sayfası, yan panel, üretilen manual | BSD-3-Clause |
| [SweetAlert2](https://github.com/sweetalert2/sweetalert2) | Kendi barındırılan (CDN'siz) diyalog/toast bileşenleri — panel genelinde | MIT |
| [python-docx](https://github.com/python-openxml/python-docx) | DOCX manual export | MIT |
| [ReportLab](https://www.reportlab.com/opensource/) | PDF manual export | BSD-türevi (ReportLab'in kendi lisansı) |
| [xxhash](https://github.com/ifduyue/python-xxhash) (XXH3-64) | İçerik-hash tabanlı artımlı yeniden indeksleme (değişmeyen chunk'ları atlama) | BSD-2-Clause |
| [watchdog](https://github.com/gorakhargosh/watchdog) | `auto_refresh` açık koleksiyonlar için otomatik kaynak-klasör izleyicisi | Apache-2.0 |

## 📚 Referanslar ve İlham

- [Qdrant hibrit arama / Reciprocal Rank Fusion dokümantasyonu](https://qdrant.tech/documentation/) — `src/retrieval.py`'deki RRF füzyonu + adlandırılmış-vektör tasarımı, Qdrant'ın kendi önerdiği hibrit-arama desenini izliyor.
- [Model Context Protocol spesifikasyonu](https://modelcontextprotocol.io/) — `src/mcp_server.py`'nin stdio ve Streamable HTTP modları için araç/transport kuralları.
- SSRF ve saklı-XSS üzerine OWASP rehberliği — bu deponun git geçmişinde kayıtlı 2026-07-25 güvenlik düzeltmelerine (istemci-kontrollü giden URL doğrulaması, HTML/JS bağlamına duyarlı kaçış) yön verdi.

## 👥 Proje Katkıcıları

Bu projeye katkıda bulunan kişiler.

- baspinar99@gmail.com
- emr.pov@gmail.com
- re.baspinar@gmail.com

---

*Bu proje burada teşekkür edilmeyen bir şey kullanıyorsa lütfen bir issue açın —
eksikler kasıtlı değil, gözden kaçmadır.*
