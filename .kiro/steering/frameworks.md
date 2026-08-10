# Frameworks — CodeIntel Spec-Kit

## Supported Frameworks

### FastAPI

- **When to use:** every HTTP-facing feature — web panel, REST API, SSE streaming endpoints.
- **Style:** routers under `src/api/*_routes.py`, one per feature area; business logic delegated to `src/services/*_svc.py`.
- **Features used:** `APIRouter` per feature area, `pydantic` v2 models for request/response validation, and `StreamingResponse` with `media_type="text/event-stream"` for SSE (hand-written `event:`/`data:` frames — **not** `sse-starlette`, which is only a transitive dependency of `mcp` and never imported here). Shared Qdrant/Ollama access comes from `src/services/common.py`'s module-level singletons, not FastAPI `Depends(...)` — which this project does not use at all.
- **Installation:** `pip install -r requirements.txt` (already pinned).
- **Skills:** `.agents/skills/fastapi/SKILL.md`

### MCP SDK

- **When to use:** exposing a capability to AI coding agents (Claude Code, Codex CLI, Gemini CLI) via `src/mcp_server.py`.
- **Style:** define every tool with the `@tool` decorator (not raw `mcp.tool()`) — it registers with FastMCP and auto-generates the matching `/api/mcp/*` REST endpoint; `tests/test_api.py::test_mcp_rest_parity` verifies this, it isn't satisfied by hand.
- **Features:** stdio transport (default) and optional LAN-facing Streamable HTTP.
- **Skills:** `.agents/skills/python-mcp-server-generator/SKILL.md`

### Qdrant Database

- **When to use:** all persistent storage — vectors, payload metadata, and the symbol graph (its own internal collection).
- **Access:** `qdrant-client` (Python), configured via `mcp-config.json`'s `qdrant_url`.
- **Features:** hybrid dense+sparse search with RRF fusion, staged+atomic-alias-swap reindexing.
- **Critical rules:** never mutate a live collection mid-reindex; never bump `onnxruntime-gpu==1.22.0` without re-verifying GPU activation.
- **Skills:** `.agents/skills/qdrant-clients-sdk/SKILL.md`, `.agents/skills/qdrant-search-quality/SKILL.md`, `.agents/skills/qdrant-performance-optimization/SKILL.md`, `.agents/skills/qdrant-deployment-options/SKILL.md`, `.agents/skills/qdrant-scaling/SKILL.md`, `.agents/skills/qdrant-monitoring/SKILL.md`

## Framework Decision

```
Need an HTTP endpoint? → FastAPI router under src/api/
Need to expose a capability to an AI agent? → MCP tool in src/mcp_server.py, defined with the `@tool` decorator (auto-generates its REST parity endpoint)
Need persistence/search? → Qdrant, through a service in src/services/
Need local LLM inference? → Ollama HTTP call, through a service
```

## Transversal Golden Rule (Resource Management and Errors)

Regardless of the feature being built:
1. **Never mutate a live Qdrant collection in place** — stage into a separate collection, swap via alias only once verified.
2. **Transparent and specific errors:** do not silently swallow generic errors. Catch specific exception types at the boundary that actually raises them, and surface truncated/cut-off LLM output (`done_reason`) instead of hiding it.

## General Rules for All Frameworks

- PEP 8 and SOLID (adapted to this codebase's two-layer split) apply regardless of framework.
- This project's `*_routes.py`/`*_svc.py` naming convention always applies.
- Unit tests (`pytest`, default suite) are mandatory for new behavior; `tests/manual/` is for real-service verification only.
- Routes stay thin; services hold logic — applies to every new feature.
