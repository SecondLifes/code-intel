# Constitution — CodeIntel Spec-Kit

> Fundamental principles that govern all development in this project.

## Language and Platform

This project uses **Python ≥3.12** with **FastAPI, the MCP SDK, Qdrant client and Ollama** and data access via the **Qdrant client** (no relational database/ORM). All generated code MUST follow **PEP 8**.

## Non-Negotiable Principles

### 1. SOLID Always (adapted to this codebase's two-layer split)

- **SRP:** Routes parse requests and call a service; services hold business logic — never mixed in one file.
- **OCP:** New language support is a new `Chunker` class in the extension registry, not a branch inside an existing one.
- **LSP:** Every per-language chunker returns the same chunk record shape.
- **ISP:** Shared helpers (`services/common.py`) stay small; feature-specific helpers live in their own `*_svc.py`.
- **DIP:** Route handlers receive Qdrant/Ollama clients via FastAPI `Depends(...)`, never inline instantiation.

### 2. Clean Code Always

- Extract by responsibility, not a fixed line-count ceiling
- Self-describing names in `snake_case`/`PascalCase`/`UPPER_SNAKE_CASE`
- Guard clauses instead of nesting
- Named constants (no magic numbers — e.g. `HUGE_LINES = 400`)
- Python docstrings (`"""..."""`) for public APIs; comments/docstrings in Turkish, identifiers in English

### 3. Structure (No Domain/Application/Infrastructure Split)

```
src/api/*_routes.py → src/services/*_svc.py → chunker.py / retrieval.py / Qdrant / Ollama
```

**Routes never call Qdrant/Ollama directly** — always through a service.

### 4. Naming Conventions

- `*_routes.py` suffix for FastAPI routers, `*_svc.py` suffix for service modules
- `snake_case` functions/variables/modules, `PascalCase` classes, `UPPER_SNAKE_CASE` constants

### 5. Absolute Prohibitions

- ❌ Mutating a live Qdrant collection mid-reindex (always stage + atomic alias swap)
- ❌ Global mutable state
- ❌ Business logic in a route handler
- ❌ Generic/broad exception catch without handling
- ❌ A new MCP tool defined with raw `mcp.tool()` instead of this project's `@tool` decorator (breaks the automatic REST parity `test_api.py::test_mcp_rest_parity` verifies)
- ❌ Bumping `onnxruntime-gpu==1.22.0`, or re-running `pip install -r requirements.txt`, without re-verifying GPU activation afterward

## Development Process

1. **Specify** — Define requirements and acceptance criteria
2. **Plan** — Design the route/service split before implementing
3. **Implement** — Clean code following SOLID and this project's conventions
4. **Test** — `pytest` for unit testing (`tests/manual/` only for real-service verification)
5. **Review** — Check adherence to the rules of this constitution
