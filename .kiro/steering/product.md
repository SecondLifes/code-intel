# Product — CodeIntel Spec-Kit

## Purpose

This spec-kit provides the rules, conventions and standards for developing this **Python/FastAPI/Qdrant/Ollama** application with the help of AI assistants. CodeIntel itself is not an AI-behavior-only scaffold — it is a real, running local-first hybrid (semantic + keyword) code-intelligence tool for Delphi/Pascal and ~45 other languages, with a RAG chat panel and a 17-tool MCP server for AI coding agents. This kit ensures that all AI-assisted changes to it follow:

- **PEP 8** (naming/casing rules)
- **SOLID Principles**, adapted to this codebase's real two-layer split (routes/services, not a Domain/Application/Infrastructure split)
- **Clean Code** (short methods, descriptive names, guard clauses)
- This project's own proven safety disciplines: dependency-pin discipline (`onnxruntime-gpu`), atomic reindex, MCP/REST tool parity

## Target Audience

- Contributors extending CodeIntel's search, RAG, or MCP-tool surface with AI assistance
- Anyone maintaining the indexing/chunking pipeline who needs the real gotchas (GPU fallback, reindex atomicity) surfaced up front, not rediscovered

## References

- `AGENTS.md` in the project root contains the complete reference of all rules
- `README.md` documents the application itself (features, MCP tools, quick start)
- `DECISIONS.md` records the project's Phase-0 architecture decisions
