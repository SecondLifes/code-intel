# 🙏 Acknowledgments

**CodeIntel** stands on the shoulders of the open-source projects, models,
and communities below. This page exists to credit them explicitly — not
just link to them once in a README aside.

## 📖 Open Source

| Project | What it's used for here | License |
|---|---|---|
| [Qdrant](https://github.com/qdrant/qdrant) | Vector database — hybrid dense+sparse search (`FusionQuery(Fusion.RRF)`), named vectors, payload indexes, the atomic staging+alias generation model | Apache-2.0 |
| [FastAPI](https://github.com/tiangolo/fastapi) + [Starlette](https://github.com/encode/starlette) + [Uvicorn](https://github.com/encode/uvicorn) | The entire web panel/API layer (`src/api/*`, SSE streaming for chat/deep-research) | MIT |
| [Tree-sitter](https://github.com/tree-sitter/tree-sitter) + [tree-sitter-language-pack](https://github.com/Goldziher/tree-sitter-language-pack) | Multi-language AST chunking (`src/chunker.py`) — Delphi/Pascal plus ~45 other languages via one generic engine | MIT |
| [FastEmbed](https://github.com/qdrant/fastembed) (+ `fastembed-gpu`) | Dense (`intfloat/multilingual-e5-large`) and sparse (`Qdrant/bm25`) embedding generation | Apache-2.0 |
| [intfloat/multilingual-e5-large](https://huggingface.co/intfloat/multilingual-e5-large) | Dense embedding model — 1024-dim multilingual (Turkish query / English code) semantic search | MIT |
| [jinaai/jina-reranker-v2-base-multilingual](https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual) | Cross-encoder reranker — optional precision pass over the top-N fused candidates | CC-BY-NC-4.0 (non-commercial; used here for a locally-run internal tool, not redistributed) |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) (`onnxruntime-gpu`) | Inference backend for the embedding/reranker models — CUDA execution provider for GPU acceleration | MIT |
| [Ollama](https://github.com/ollama/ollama) | Local LLM serving — chat (`/api/ask`), deep research (`/api/research/stream`), explanations, translation, the function-comparison table (`/api/compare`) | MIT |
| [Model Context Protocol (MCP) Python SDK](https://github.com/modelcontextprotocol/python-sdk) | `src/mcp_server.py` — 17 tools exposed to Claude Code/Codex/Gemini CLI over stdio and Streamable HTTP | MIT |
| [Pygments](https://github.com/pygments/pygments) | Syntax highlighting inside generated PDF/DOCX manuals | BSD-2-Clause |
| [highlight.js](https://github.com/highlightjs/highlight.js) | Self-hosted (no CDN) syntax highlighting in the search page, side panel, and generated manual | BSD-3-Clause |
| [SweetAlert2](https://github.com/sweetalert2/sweetalert2) | Self-hosted (no CDN) dialogs/toasts across the panel UI | MIT |
| [python-docx](https://github.com/python-openxml/python-docx) | DOCX manual export | MIT |
| [ReportLab](https://www.reportlab.com/opensource/) | PDF manual export | BSD-derived (ReportLab's own license) |
| [xxhash](https://github.com/ifduyue/python-xxhash) (XXH3-64) | Content-hash based incremental reindexing (skip unchanged chunks) | BSD-2-Clause |
| [watchdog](https://github.com/gorakhargosh/watchdog) | File-change detection in `remote-client/watch_client.py` (the optional remote sync client) | Apache-2.0 |

## 📚 References & Inspiration

- [Qdrant hybrid search / Reciprocal Rank Fusion documentation](https://qdrant.tech/documentation/) — the RRF fusion + named-vector design in `src/retrieval.py` follows Qdrant's own recommended hybrid-search pattern.
- [Model Context Protocol specification](https://modelcontextprotocol.io/) — tool/transport conventions for `src/mcp_server.py`'s stdio and Streamable HTTP modes.
- OWASP guidance on SSRF and stored-XSS — informed the 2026-07-25 security fixes (client-controlled outbound URL validation, HTML/JS-context-aware escaping) recorded in this repo's git history.

## 👥 Project Contributors

People who have contributed to this project.

- baspinar99@gmail.com
- emr.pov@gmail.com
- re.baspinar@gmail.com

---

*If this project uses something not credited here, please open an issue —
omissions are oversights, not deliberate.*
