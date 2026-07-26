# Contributing to CodeIntel

First off, thank you for considering contributing! It's people like you who make this tool better for everyone using it.

By participating in this project, you agree to abide by its [Code of Conduct](CODE_OF_CONDUCT.md).

## How Can I Contribute?

### Reporting Bugs

* Check the [issue tracker]([FILL IN: repo URL]/issues) to see if the bug has already been reported.
* If not, open a new issue. Clearly describe the problem and include steps to reproduce it — for search-quality issues, include the exact query and collection; for indexing issues, include the language/file pattern.

### Suggesting Enhancements

* Open an issue with the tag `enhancement`.
* Explain the use case — CodeIntel is used both as a web panel (`static/*.html`) and as an MCP server (`src/mcp_server.py`) for AI coding agents; say which surface(s) the enhancement targets.

### Pull Requests

1. Fork the repository.
2. Create a new branch for your feature or bugfix.
3. Implement your changes, following the codebase's existing conventions (see below).
4. Run the test suite (`pytest tests/ -q`) — it needs a running Qdrant instance for most tests (`tools/start-system.ps1` starts Qdrant + Ollama + the panel); tests are skipped, not failed, when Qdrant is unreachable.
5. If you touched `src/api/search_routes.py`, `src/retrieval.py`, or anything security-sensitive (auth, outbound URLs, HTML rendering), also run `tests/test_security.py`.
6. Submit a Pull Request targeting the `main` branch.

## Project Structure (where things live)

CodeIntel is a modular FastAPI monolith, not a plugin/rules framework — there is no `.agents/rules/` regeneration step here, just Python and static HTML/JS:

| Area | Where |
|---|---|
| Core search/RAG logic (hybrid RRF, chunk retrieval, explanations, context packs) | `src/retrieval.py` — shared by both the panel and the MCP server, never duplicated |
| Multi-language chunking (Tree-sitter) | `src/chunker.py` |
| Web panel routes | `src/api/{search,index,admin,manual,mcp}_routes.py`, mounted from `src/panel.py` |
| Shared services (state, profiles, API keys, backups, indexing pipeline) | `src/services/*.py` |
| MCP server (17 tools, stdio + Streamable HTTP) | `src/mcp_server.py` |
| Documentation/manual generator | `src/manual.py` |
| Frontend (no build step, no framework) | `static/index.html` (search), `static/settings.html` (collection/index management), `static/api.html` (REST + MCP tool tester), `static/viewer.html` |
| Tests | `tests/test_api.py` (API + security regression), `tests/test_chunker.py`, `tests/test_collection_ops.py`, `tests/test_generations.py`, `tests/test_manual.py`, `tests/test_security.py`, `tests/eval.py` (retrieval-quality benchmark) |

## Adding a New MCP Tool

MCP tools are registered in exactly one place (`src/mcp_server.py`'s `TOOLS` registry) and exposed two ways — a native MCP tool and a REST test endpoint under `/api/mcp/*`. `tests/test_api.py::test_mcp_rest_parity` enforces that every tool has both; a tool without its REST counterpart (or vice versa) fails CI. Add the tool once, then add its REST route in `src/api/mcp_routes.py`.

## Adding Support for a New Language

`src/chunker.py`'s generic Tree-sitter engine already covers ~45 languages structurally; 8 languages (including Pascal/Delphi) have deeper support (parent/child AST splitting for nested class methods, `uses`/import extraction). Adding a new language usually means: verify `tree-sitter-language-pack` ships a grammar for it, add its file-extension mapping, and — if you want deep support — add its node-type mapping alongside the existing ones in `src/chunker.py`. Add a fixture-based test in `tests/test_chunker.py` before claiming support.

## Technical Standards

* **Security-sensitive changes** (anything touching `ollama_url`/outbound HTTP, HTML rendering via `esc()`/`escJs()` in the frontend or `_esc()`/`_esc_js()` in `src/manual.py`, the `STATE_LOCK` check-then-set pattern, or the staging+alias generation model in `src/services/generations.py`) need a regression test proving the fix, not just a read-through — see the git history around 2026-07-25 for the pattern (SSRF, stored-XSS, import atomicity, check-then-set race) each fixed with a test that fails against the old code and passes against the new.
* **Backend routes returning errors** use `JSONResponse({"error": "..."}, status_code=...)`, not raised exceptions that become opaque 500s.
* **New Qdrant-backed features** should follow the existing internal-collection naming convention (`_` prefix, e.g. `_search_log`, `_answer_cache`) and be added to `INTERNAL_COLLS` in `src/services/common.py` so they're excluded from user-facing collection listings.

### Testing

* `pytest tests/ -q` — most tests are marked `@needs_qdrant` and skip cleanly without a live Qdrant; a handful of pure-function tests (escaping, URL sanitization) run with no dependencies at all.
* `tests/eval.py` is a retrieval-quality benchmark (Recall@k, MRR, p50/p95 latency) against a golden query set — run it after any change to ranking/fusion logic in `src/retrieval.py`.

## Communication

* Use the [issue tracker]([FILL IN: repo URL]/issues) for bugs, questions, and proposals.
* Respect all contributors and maintainers — see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
