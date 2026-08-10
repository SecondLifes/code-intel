# Changelog

All notable changes to CodeIntel are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) ·
Versioning: [SemVer](https://semver.org/).

> **Introduced retroactively, and deliberately not backfilled.** This file
> starts from the current `1.0.0` state rather than reconstructing all 107
> commits — inventing a per-release history that was never recorded would
> produce a document that reads authoritative while being guesswork. The
> `1.0.0` entry describes what the software actually does today; entries
> from here on are written as changes land.
>
> **On version numbers, which currently disagree three ways:**
> `pyproject.toml` declares `1.0.0` (set 2026-07-24) and is treated here as
> authoritative — `settings.json` mirrors it. The repository also carries 90
> `v0.1.x` git tags from an auto-incrementing scheme that stopped on
> 2026-07-26 while development continued for another ~40 commits. Those tags
> are historical build markers, not releases, and are left untouched;
> whether to resume tagging (and from which number) is an open decision.

## [Unreleased]

### Added

- **AI-instruction layer** — `.agents/`, `.claude/`, `.cursor/`,
  `.gemini/`, `.github/`, `.kiro/`, `.specify/`, `AGENTS.md`, added via
  `rad-template-builder`'s Extraction Mode so this project participates in
  the workspace's shared-skill ecosystem. Content derived from the real
  codebase and confirmed before writing; no application file was touched
- Bundled skills: `python`, `rad-prompt-studio`, `rad-skill-finder`,
  `rad-web-scraping`, plus `fastapi`, six official `qdrant/skills`, and
  `python-mcp-server-generator`
- `.agents/rules/testing.md` — the real `tests/` vs `tests/manual/` split
  enforced by `pytest.ini`, regression-first test naming, and why
  `test_mcp_rest_parity` is a safety net rather than a manual chore

### Fixed

- Eleven false claims in the newly-written AI-instruction layer, each
  verified against the actual source: a fabricated `Depends(...)` DI
  convention (zero occurrences in `src/`), a "global mutable state" ban
  contradicting the deliberate shared `STATE` dict, "routes never call
  Qdrant directly" against 47 real direct calls, `sse-starlette` named as
  the streaming mechanism when it is never imported, an inverted
  sync-vs-async route-handler rule, two fabricated identifiers, and two
  dead paths

## [1.0.0] - 2026-07-24

Local-first hybrid code intelligence for Delphi/Pascal codebases and ~45
other languages.

### Added

- **Hybrid search** — dense (semantic) + sparse (BM25) retrieval fused by
  this project's own weighted RRF implementation in `src/retrieval.py`,
  with name-match boosting and optional cross-encoder reranking
- **RAG chat with citations** — `/api/ask` and a deep-research mode that
  pulls a symbol's full body plus callers/callees/type-hierarchy/unit
  dependencies into one context pack; SSE-streamed and truncation-aware
- **MCP server** — 17 tools over stdio and optional LAN-facing Streamable
  HTTP, each auto-generating its matching REST endpoint through the
  project's own `@tool` decorator
- **Multi-language chunking** — tree-sitter based, ~45 languages
  structurally with deep support (parent/child AST splitting, import
  extraction) for Delphi/Pascal, Python, C#, C/C++, Java, JS/TS, Go, Rust
- **Symbol graph** — inheritance, references, caller/callee edges in a
  dedicated collection rather than every point's payload
- **Atomic, resumable indexing** — a reindex builds into a staging
  collection and goes live by a single alias swap; the job queue survives
  a restart mid-index
- **Auto-generated manual** — per-collection HTML/PDF/DOCX with a
  collapsible class tree, self-hosted highlighting, AI-assisted TR/EN
  translation
- **Duplicate detection**, **git provenance and impact analysis**, and an
  owner/group registry with role-separated API keys, rate limiting and an
  audit log

### Notes

- `onnxruntime-gpu==1.22.0` is a hand-verified pin. Newer releases need
  CUDA-13 DLLs pip's `nvidia-cu12` packages do not provide, and the GPU
  then falls back to CPU silently. `fastembed` also depends on plain
  `onnxruntime`, so a bare `pip install -r requirements.txt` can overwrite
  the GPU build non-deterministically — `tools/install.ps1` re-applies the
  fix afterward
