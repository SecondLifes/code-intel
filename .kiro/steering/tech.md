# Technical Stack — CodeIntel

## Language and Runtime

- **Language:** Python ≥3.12
- **Runtime:** system-installed Python — **never** a project-local `.venv`/`uv` (unsigned/portable trampoline executables trigger AV false positives; see `CONTRIBUTING.md`'s "Antivirüs uyarıları")
- **Build System:** none compiled — `pip install -r requirements.txt` (pinned) is the install path
- **Native IDE:** none required — any editor/IDE with Python support

## Main Frameworks

| Framework | Usage |
|-----------|-----|
| FastAPI + uvicorn | Web panel + REST API (`src/panel.py`, `src/api/*_routes.py`) |
| MCP SDK | 17-tool MCP server, stdio + optional Streamable HTTP (`src/mcp_server.py`) |
| Qdrant client + fastembed(-gpu) | Hybrid dense+sparse vector search |
| Ollama (HTTP) | Local LLM inference for RAG chat/deep research |
| tree-sitter + tree-sitter-language-pack | Multi-language source chunking (`src/chunker.py`) |

## Supported Databases

- **Qdrant** (vector DB) — the only database. No relational database.

### Qdrant — Critical Rules

- **Driver:** `qdrant-client` (Python)
- Reindex is staged into a separate collection, swapped in via alias only once verified — never mutate a live collection in place.
- `onnxruntime-gpu==1.22.0` is a hand-verified critical pin — bumping it without re-verifying GPU activation risks a silent CPU fallback with no error printed.
- **Skills:** `.agents/skills/qdrant-clients-sdk/SKILL.md`, `.agents/skills/qdrant-performance-optimization/SKILL.md`

## Concurrency / Async — Critical Rules

- **Rule of Thumb:** I/O-bound route handlers (Qdrant queries, Ollama calls) are `async def`; CPU-bound chunking/parsing stays synchronous.
- SSE streaming endpoints (`/api/ask/stream`, `/api/research/stream`) are token-budgeted and truncation-aware — surface `done_reason` rather than silently returning a cut-off answer.
- **Skills:** `.agents/skills/fastapi/SKILL.md`

## External Dependencies

- Pinned exactly in `requirements.txt` (historically a `uv pip freeze` output, now applied to system Python) — `pyproject.toml` only holds loose ranges for packaging identity. Prefer `requirements.txt` for a clean install.

## Code Standards

### File Types

| Extension | Description |
|----------|-----------|
| `.py` | Source code |
| `.json` | Config (`mcp-config.json`), eval data |
| `.ini` | `pytest.ini` |
| `.jsonl` | Chunk/eval datasets |

### Naming Suffixes

```
src/api/<feature>_routes.py    ← FastAPI router
src/services/<feature>_svc.py  ← business logic
```

## Testing and Quality (TDD)

- **Test framework:** `pytest`
- **Infrastructure Isolation:** `tests/` (default `pytest` run) contains no real external-service calls; `tests/manual/` (excluded via `pytest.ini`'s `norecursedirs`) holds tests that genuinely need a running GPU/Ollama/Qdrant — run those explicitly.
- **Regression-first naming:** a test name states the behavior/regression being locked in (`test_line_shift_does_not_change_chunk_id`), not just the function under test.
- **MCP/REST parity:** any new MCP tool needs a passing `tests/test_api.py::test_mcp_rest_parity` entry.
