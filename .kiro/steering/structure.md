# Structure and Conventions — CodeIntel

## Structure (Two-Layer, No Domain/Application/Infrastructure Split)

```
src/
├── api/            ← FastAPI routers, one per feature area (*_routes.py) — thin, delegate to services
├── services/        ← Business logic (*_svc.py) + shared helpers (common.py)
├── chunker.py        ← Per-language parsing/chunking (tree-sitter based)
├── retrieval.py       ← Hybrid search / RRF fusion
├── manual.py          ← Auto-generated manual (HTML/PDF/DOCX) build
├── mcp_server.py       ← 17-tool MCP server (stdio + Streamable HTTP)
└── panel.py            ← Web panel entry point
tests/
├── test_*.py           ← Default pytest suite (no real external services)
└── manual/             ← Requires real GPU/Ollama/Qdrant — excluded from default run
```

This project intentionally has no Domain/Application/Infrastructure/
Presentation split — that layering doesn't fit a FastAPI service this
size. The real dependency direction is flat and one-way instead:

## Dependency Rule

```
src/api/*_routes.py → src/services/*_svc.py → chunker.py / retrieval.py / Qdrant client / Ollama client
```

- **Routes** never call Qdrant/Ollama directly — always through a service.
- **Services** hold all business logic and orchestration.
- **`chunker.py`/`retrieval.py`** are called by services, not by routes.

## File/Module Naming

### Standard
```
src/api/<feature>_routes.py
src/services/<feature>_svc.py
```

### Examples

| Layer | Standard | Example |
|--------|--------|---------|
| API route | `<feature>_routes.py` | `src/api/search_routes.py` |
| Service | `<feature>_svc.py` | `src/services/indexing_svc.py` |
| Shared service helper | `common.py` | `src/services/common.py` |

## File/Module Sections

```
module docstring (what/why, real gotchas fixed — see chunker.py for the depth expected)
imports
module-level constants
private (_-prefixed) helpers
public functions/classes
```
