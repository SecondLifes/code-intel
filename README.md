# 🧠 CodeIntel

<div align="center">

**A local-first, hybrid (semantic + keyword) code-intelligence tool for Delphi/Pascal codebases — and ~45 other languages — with a RAG chat panel and a 17-tool MCP server for AI coding agents.**

[![🇹🇷 Türkçe ](https://img.shields.io/badge/Turkish-Türkiye-red)](README.tr-TR.md)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-panel%20%2B%20API-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Qdrant](https://img.shields.io/badge/Qdrant-hybrid%20search-DC244C)](https://qdrant.tech/)
[![Ollama](https://img.shields.io/badge/Ollama-local%20LLM-000000)](https://ollama.com/)
[![MCP](https://img.shields.io/badge/MCP-17%20tools-purple)](https://modelcontextprotocol.io/)
[![Claude Code](https://img.shields.io/badge/Claude-Code-brown?logo=anthropic)](https://claude.ai)

*[🇹🇷 Türkçe](README.tr-TR.md) · [Contributing](CONTRIBUTING.md) · [Code of Conduct](CODE_OF_CONDUCT.md) · [Security](SECURITY.md) · [Acknowledgments](ACKNOWLEDGMENTS.md)*

![Overview](docs/images/hero.png)

</div>

## 📋 Index

- [Turkish-Türkçe](README.tr-TR.md)
- [What is this project?](#-what-is-this-project)
- [Why use it?](#-why-use-it)
- [Core Capabilities](#-core-capabilities)
- [Supported Languages](#-supported-languages)
- [MCP Tools (for AI Agents)](#-mcp-tools-for-ai-agents)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
- [Security Posture](#-security-posture)
- [Design & Philosophy](#-design--philosophy)
- [Acknowledgments](#-acknowledgments)
- [Contributing](#-contributing)

---

## 💡 What is this project?

**CodeIntel** is not an AI-behavior rules kit — it's a real, running application: a FastAPI backend + Qdrant vector database + Ollama local LLM, wired together into a code-search-and-understanding tool that grew out of indexing large Delphi libraries (UniDAC, ~25,000 chunks) and now generalizes to dozens of languages.

It answers questions a codebase search box normally can't:

- ✅ **Hybrid search** — dense (semantic) + sparse (BM25 keyword) fusion via Qdrant's RRF, with name-match boosting and an optional cross-encoder rerank pass
- ✅ **RAG chat with real citations** — "Cevapla" mode answers from the top-K matches; "Derin" (deep research) mode pulls the full body of the primary symbol plus its callers/callees/type-hierarchy/unit-dependencies into one context pack before answering
- ✅ **Agent-ready via MCP** — 17 tools (search, explain, relations, impact analysis, context packs...) served over stdio *and* LAN-exposed Streamable HTTP, so Claude Code/Codex CLI/Gemini CLI can query the same index the web panel uses
- ✅ **Self-documenting** — generates a full multi-chapter HTML/PDF/DOCX manual per collection, with AI-assisted TR/EN translation

> Say goodbye to `grep`-and-hope across a 25,000-chunk Delphi codebase, or asking an AI agent to "explain this" with zero context beyond the file you happened to have open.

---

## 🤔 Why use it?

| Without CodeIntel | With CodeIntel |
|---|---|
| `grep`/full-text search only, no semantic matching | Hybrid dense+sparse search, Turkish query ↔ English/Delphi code both work |
| An AI agent sees only the file you pasted | MCP tools give it the full call graph, type hierarchy, and unit dependencies on request |
| "Which of these 6 near-duplicate `Split` functions is safest?" — nobody knows without reading all 6 | The comparison table asks the LLM to score stability/performance for every candidate, side by side |
| Re-reading old commits to understand *why* code changed | `analyze_impact` correlates a diff range against affected chunks |
| Manually writing/maintaining developer docs | `document_unit`/the manual generator produce and cache them, refreshed on demand |

---

## 🌟 Core Capabilities

![Core Features](docs/images/core-features.png)

- **Hybrid RRF search** across multiple collections at once, with per-language filters, cross-encoder reranking, and a "why this ranked here" breakdown per result.
- **RAG chat** (`/api/ask`, `/api/ask/stream`) and **deep research** (`/api/research/stream`, token-budgeted context packs) — both SSE-streamed, both cached, both truncation-aware (surfaces Ollama's own `done_reason` instead of silently returning a cut-off answer).
- **Function comparison table** (`/api/compare`) — when a query surfaces several implementations doing the same job, one LLM call scores each for stability/performance with a one-line rationale.
- **Symbol graph** — inheritance, `find_references`, caller/callee edges, stored in its own internal collection (not embedded in every point's payload, so it scales independently of the code collection's size).
- **Git provenance + impact analysis** — correlate a commit range against the chunks it touched.
- **Auto-generated manual** — per-collection HTML/PDF/DOCX documentation, collapsible class-tree sidebar, self-hosted syntax highlighting (no CDN dependency), AI-assisted bilingual (TR/EN) translation.
- **Duplicate-code detection** — threshold-based similarity scan over already-indexed embeddings (no re-embedding needed).
- **Atomic, resumable indexing** — staging+alias generation model (reindex builds in a separate collection, only swapped in atomically once complete and verified), persistent job queue survives a restart mid-index.
- **Owner/Group registry, API keys with read/admin role separation, rate limiting, audit log** — the same panel supports single-operator local use and LAN-shared multi-key access.

---

## 🌐 Supported Languages

A generic Tree-sitter-based engine covers **~45 languages** structurally; **8 languages have deep support** (parent/child AST splitting for nested class methods, `uses`/import extraction, unit-head parsing): **Delphi/Pascal**, **Python**, **C#**, **C/C++**, **Java**, **JavaScript/TypeScript**, **Go**, **Rust**.

---

## 🤖 MCP Tools (for AI Agents)

`src/mcp_server.py` exposes 17 tools over stdio (default) and optionally LAN-facing Streamable HTTP — every tool also has a REST test endpoint under `/api/mcp/*` (parity enforced by `tests/test_api.py::test_mcp_rest_parity`), tried live from `static/api.html`.

| Tool | Purpose |
|---|---|
| `search_code` | Hybrid search with language/kind/unit filters |
| `find_similar` | Nearest neighbors of a given chunk |
| `read_unit` | Full content of a source file (unit) |
| `get_chunk` | A single chunk's full payload |
| `get_relations` | Caller/callee/same-file relations |
| `explain_chunk` | Fast or deep LLM explanation (cached) |
| `review_code` | LLM code review of a chunk |
| `propose_edit` | Show-only diff suggestion (never auto-applies) |
| `ask_domain_model` | Route a question to a domain-specific model (e.g. SQL) |
| `get_type_hierarchy` | Ancestors/descendants of a type |
| `find_references` | All references to a name across a collection |
| `analyze_impact` | Correlate a git diff range with affected chunks |
| `get_unit_deps` | `uses`/import dependency graph for a file |
| `get_context_pack` | Token-budgeted, multi-source context bundle for a task |
| `document_unit` | Generate/fetch cached documentation for a file |
| `list_domain_models` | List configured domain-specific models |
| `list_collections` | List indexed collections and their stats |

---

## 📂 Project Structure

```
code-intel/
│
├── src/
│   ├── retrieval.py          # Core search/RAG/explain logic — shared by panel AND mcp_server, never duplicated
│   ├── chunker.py            # Tree-sitter multi-language chunking
│   ├── manual.py             # Documentation generator (HTML/PDF/DOCX, i18n)
│   ├── mcp_server.py         # 17 MCP tools, stdio + Streamable HTTP
│   ├── panel.py              # FastAPI app entrypoint + security_guard middleware
│   ├── api/                  # Modular routers: search, index, admin, manual, mcp
│   └── services/             # Shared state, profiles, API keys, backups, indexing pipeline
│
├── static/
│   ├── index.html            # Search + chat panel
│   ├── settings.html         # Collection/index management
│   ├── api.html               # REST + MCP tool tester
│   └── viewer.html           # Standalone file viewer
│
├── tests/                    # pytest — most tests need a live Qdrant (@needs_qdrant, skip not fail)
├── tools/                    # start-system.ps1 / stop-system.ps1 / install-autostart.ps1
├── qdrant-bin/                # Qdrant binary (Windows)
├── mcp-config.json           # MCP server defaults (Qdrant/Ollama URLs, model names)
├── requirements.txt          # Pinned dependency versions (see the onnxruntime-gpu note inside)
└── pyproject.toml
```

> Not included in this copy: `data/` (Qdrant storage + chunk caches), `.venv/`, `backups/`, `logs/` — all regenerated locally, all `.gitignore`d.

---

## 🔧 Prerequisites

- **Python 3.12+**
- **Qdrant** (bundled binary under `qdrant-bin/`, or run your own)
- **Ollama** — for chat, deep research, explanations, translation, and the comparison table
- **PowerShell 7+ (`pwsh`)** — `tools/start-system.ps1`/`stop-system.ps1` are PowerShell scripts (Windows-first; the Python/FastAPI core itself is cross-platform)
- A CUDA-capable GPU is optional but strongly recommended for embedding throughput (see `requirements.txt`'s `onnxruntime-gpu` pinning note)

---

## ⚡ Quick Start

```bash
# 1. Install dependencies (pinned versions — see requirements.txt's onnxruntime-gpu note)
uv pip install -r requirements.txt --python .venv/Scripts/python.exe

# 2. Start Qdrant + Ollama + the panel (Windows)
pwsh tools/start-system.ps1 -NoBrowser
```

Then open `http://127.0.0.1:8500` — index a folder from Settings, then search/chat from the main page. To use it as an MCP server instead of (or alongside) the panel, point your AI CLI's MCP config at `src/mcp_server.py` (stdio) — see `mcp-config.json` for the defaults it reads (Qdrant/Ollama URLs, fast/deep model names).

```bash
pytest tests/ -q   # needs a live Qdrant (tools/start-system.ps1) for most tests; the rest skip cleanly
```

---

## 🔐 Security Posture

Binds to `127.0.0.1` by default; LAN exposure is opt-in via role-separated API keys (`read`/`admin`). See [SECURITY.md](SECURITY.md) for the full threat model, including two fixes worth knowing about if you're auditing this codebase: a client-controlled outbound-URL (SSRF) restriction added 2026-07-25, and an HTML/JS-context-aware escaping fix for the same date (plain `&<>`-only escaping is not sufficient inside an `onclick="fn('...')"` attribute — see `escJs()`/`_esc_js()`).

---

## 🎯 Design & Philosophy

![Design & Philosophy](docs/images/design-philosophy.png)

**Verify, don't assume.** Every fix recorded in this codebase's git history — the SSRF restriction, the escaping fix, the atomic-import redesign, the check-then-set race fix — was proven with a test that fails against the old code and passes against the new, not just reasoned about and left untested. The same discipline extends to search ranking (`tests/eval.py`'s golden-query benchmark) and to answers themselves (both chat modes report Ollama's own truncation signal rather than presenting a silently cut-off response as complete). The deliberate tradeoff: slower to ship a fix than "looks right on read," in exchange for a codebase where "the tests pass" actually means something.

---

## 🙏 Acknowledgments

See [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md) / [ACKNOWLEDGMENTS.tr-TR.md](ACKNOWLEDGMENTS.tr-TR.md) for the open-source projects and models this tool is built on.

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) / [CONTRIBUTING.tr-TR.md](CONTRIBUTING.tr-TR.md).

---

<div align="center">

Made with care by **Emrah BAŞPINAR** & **Recep Eymen BAŞPINAR**.

*[Contributing](CONTRIBUTING.md) · [Code of Conduct](CODE_OF_CONDUCT.md) · [Security](SECURITY.md) · [Acknowledgments](ACKNOWLEDGMENTS.md)*

</div>
