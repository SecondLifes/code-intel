# project:review

`project:review`

Please review the current diffs (`git diff` and `git diff --cached`) against this project's coding standards from `.claude/CLAUDE.md` and the appropriate rules within `.claude/rules/` (generated from the canonical `.agents/rules/`). Structure the review around this checklist: correctness, security, performance, SOLID, resource/memory management, naming, tests, and confirm at minimum that:
- Naming conventions (`snake_case`/`PascalCase`/`UPPER_SNAKE_CASE`, `*_routes.py`/`*_svc.py` suffixes) are respected.
- Routes stay thin — no business logic leaked into a `*_routes.py` handler instead of its matching `*_svc.py`.
- No new MCP tool uses raw `mcp.tool()` instead of this project's `@tool` decorator (which auto-generates the REST parity `test_api.py::test_mcp_rest_parity` verifies).
- No reindex/collection-mutation change bypasses the stage-then-atomic-alias-swap pattern.
- Resource/memory leaks are unlikely with the new changes.
- Qdrant/FastAPI/Ollama-specific constraints are respected — dependency pin discipline, and route handlers left as plain `def` (this repo's consistent convention; don't convert to `async def` without a real, measured reason).
