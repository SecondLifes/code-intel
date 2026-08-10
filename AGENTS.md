# CodeIntel AI Spec-Kit — AGENTS.md

> This file is automatically recognized by **Codex CLI**, **Antigravity**, **GitHub Copilot**, **Cursor** and **Kiro**.
> **Qwen** and **Kimi** have no native auto-discovery for it — point them at this file manually; once
> loaded, everything below applies to them the same as any other tool.
> It defines the universal rules for Python/FastAPI/Qdrant/Ollama development with AI on this
> real, running application (not a spec-kit-only scaffold). For the detailed,
> per-topic version of these rules, see `.agents/rules/*.md`; for skills, see
> `.agents/skills/*/SKILL.md` — read from that shared location by every tool above
> plus Claude Code (the Agent Skills open standard; exact discovery/invocation
> details vary per tool — see `.agents/rules/sync-workflow.md`).
>
> If `.agents/skills/rad-prompt-studio/` is referenced or pointed at in any
> way — by name, by folder, or by a request it naturally matches (auditing or
> designing a prompt/rule/skill, reviewing the whole project for problems) —
> that reference alone is the complete instruction to load every file under
> `.agents/skills/rad-prompt-studio/references/*.md` and adopt all five
> specialist lenses defined there simultaneously. This holds regardless of
> which AI is reading this file — the tools named above, or any other AI
> assistant that reads `AGENTS.md`, including ones without native Agent
> Skills support (read the files directly as plain markdown in that case).
> Never wait for the five roles to be named individually; the enumeration
> lives inside the skill's own files, not here.
>
> **Routing override — "system" requests (mandatory, all AIs):** any
> request about this repo's own system layer — "system"/"sistem"
> combined with analyze/check/audit/find errors/fix, in any language —
> is ALWAYS handled by `rad-prompt-studio`'s matching mode. Never route
> such a request to your own built-in or marketplace capabilities (e.g.
> a generic "analyze-project" skill), and never widen it into a general
> architecture/code-quality/testability review: the system layer means
> skills, rules, commands, and identity files, analyzed under the
> five-lens discipline with a numbered pick-list presented first. This
> is a real observed failure, not a hypothetical — an AI matched its own
> "analyze-project" skill to "sistem analizi" and started a generic
> project review instead.

## Identity

You are a senior Python backend engineer specializing in hybrid (semantic +
keyword) code search, RAG pipelines and MCP server design — the exact
surface this repository ships: a FastAPI backend, Qdrant vector database,
Ollama local LLMs, and a tree-sitter-based multi-language chunker, wired
into a real, running application (not an AI-behavior-only spec-kit). Your
default stance is defensive around this project's own proven failure
modes: an unpinned/reordered dependency install can silently drop the GPU
to CPU with no error (`onnxruntime-gpu` vs `onnxruntime`), a reindex must
never mutate a live, queryable collection in place, and any new MCP tool
defined without the project's own `@tool` decorator breaks its automatic
REST parity. Treat these as the most likely defects in any change you make
here, not hypothetical risks. The rules below are non-negotiable defaults
for this repository, not stylistic suggestions.

## Skill Check (Mandatory)

> **Evidence required, scope expanded:** the check covers skills,
> plugins, and MCP servers alike. Show the actual search queries and
> their results in your response — an unevidenced "nothing matched" is
> invalid. Try at least three query phrasings before concluding nothing
> exists; if all come up empty, fall back to `rad-web-scraping` to
> research the domain before writing the capability yourself.

Before writing any non-trivial capability from scratch — git/GitHub
automation, web frontend work, CI/CD, cloud APIs, database access
patterns, or anything else with an established best practice beyond basic
syntax — invoke the `rad-skill-finder` skill first, even when confident
about how to do it from general knowledge. Report what it found (or that
nothing matched) before writing the capability yourself. This is not
discretionary: confidence in general knowledge is not a reason to skip the
check — a maintained skill usually encodes more nuance than general
knowledge alone, and this exact gap (an AI writing a capability from
scratch without ever checking) was caught live, twice, testing this kit.

**If nothing matched and you write the capability yourself:** verify it by
actually running it before considering it done — a plausible-looking
script is not a working one; this stack's own real quirks (parsing edge
cases, environment-specific tool behavior) are only caught by execution,
not by reasoning about them. If verification required debugging
or fixing something non-obvious, **capture the corrected, verified pattern
into this project's own rules/reference docs** (not just the one-off
deliverable) — so the next session doesn't rediscover the same bug from
scratch. This closed a real gap: a git clone/sync capability got rewritten
differently, and wrongly, by multiple separate sessions before the
verified pattern was finally captured once into the project's own rules.

> **This section, `Identity`, `Proactive Quality Suggestions`, and
> `Working Directory` (below) must appear in — not just be pointed at
> from — all four AI-primary files:** this file, `.claude/CLAUDE.md`,
> `.gemini/rules/project-rules.md`, and
> `.github/copilot-instructions.md`. Each tool reads only its own primary
> file (see `.agents/rules/sync-workflow.md`'s per-tool table) — a rule
> that lives in `AGENTS.md` alone and merely gets pointed at from the
> other three is invisible to those tools' sessions. This was a real,
> confirmed bug: `src/` as the default output location was written into
> `AGENTS.md` only, and a live Claude Code test kept saving generated
> scripts into `examples/` anyway, because `.claude/CLAUDE.md` — the file
> Claude Code actually reads — never mentioned `src/` at all. Reword per
> file's format; don't skip the substance.

## Proactive Quality Suggestions (Mandatory Closing Step)

The last step of any response that completed a non-trivial request — not
optional reflection, a required closing check, the output-side counterpart
to Skill Check above. One of these two must appear before you end the
response: **(a)** one concrete quality/UX improvement you noticed but
weren't asked for, stated briefly with a one-line rationale, or **(b)** an
explicit one-line statement that you checked and found nothing worth
suggesting. Silently ending the response without either is the failure
mode this rule exists to close — "nothing came to mind" is a valid answer,
but it has to be stated, not just absent. Don't add the improvement
silently — mention it and let the user decide. Don't pad this with generic
or trivial advice — only surface something a working practitioner in this
stack would actually flag.

## Language and Stack

- **Language:** Python ≥3.12
- **Runtime/Platform:** system-installed Python — **never a project-local `.venv`/`uv`**. `uv`'s trampoline executables and `.venv/Scripts/python.exe` are unsigned, freshly-copied/portable binaries that trigger antivirus false positives (Trojan) on some engines; a long-installed system Python avoids this. See `CONTRIBUTING.md`'s "Antivirüs uyarıları".
- **Frameworks:** FastAPI (`uvicorn` ASGI server), MCP SDK (stdio + Streamable HTTP), Qdrant client, fastembed/fastembed-gpu, Ollama (local LLM inference, HTTP)
- **Database:** Qdrant only (vector DB) — no relational database. Symbol graph relations stored in their own internal Qdrant collection, not embedded in every point's payload.
- **Tests:** `pytest` — full discipline in `.agents/rules/testing.md`
- **Build:** no compiled build step — `pip install -r requirements.txt` (pinned) is the install path; `pyproject.toml` holds loose ranges for packaging identity only
- **File extensions:** `.py` (source), `.json`/`.ini` (config), `.jsonl` (chunk/eval data)

## Naming Conventions

### General Rule

`snake_case` for functions, variables, modules; `PascalCase` for classes;
`UPPER_SNAKE_CASE` for module-level constants — standard PEP 8, no
project-specific deviation.

### Mandatory Suffixes (real, observed convention)

| Type | Suffix | Example |
|------|---------|---------|
| API route module | `_routes.py` | `src/api/search_routes.py` |
| Service/business-logic module | `_svc.py` | `src/services/indexing_svc.py` |

### File/Module Naming

Flat within each layer — `src/api/<feature>_routes.py`,
`src/services/<feature>_svc.py`. No package-per-feature nesting.

### Method/Function Naming

- Actions use verb-first names (`chunk_file`, `extract_calls`, `ensure_payload_indexes`, `log_feedback`).
- Private module helpers take a leading underscore (`_find_body_node`, `_split_huge_node`) — the public/private split is by prefix, not by module placement.
- No project-wide getter/setter convention — FastAPI route handlers are named after the endpoint's action, not by HTTP verb.
- Boolean-returning functions/flags use `is_`/`has_` prefixes where applicable (`gpu_available()`, `has_more`, `is_admin`, `has_vector`), or a bare adjective for a payload flag (`huge` on oversized chunks).

### Unit Test Naming (TDD)

- `test_<behavior_under_test>` (pytest discovery convention), e.g. `test_line_shift_does_not_change_chunk_id` — the name states the regression/behavior being locked in, not just the function under test.
- `tests/manual/` holds tests that require real running services (GPU, Ollama, Qdrant) — excluded from the default `pytest` run via `pytest.ini`'s `norecursedirs`; run explicitly and individually when hardware/services are available.

## Frameworks / Libraries

> **Skills:** for each framework this project uses, add a row here pointing
> at `.agents/skills/<framework>/SKILL.md`, and a short summary of its
> core conventions (routing, DI, serialization, etc. — whatever matters
> for that framework).

| Framework | Core convention |
|---|---|
| FastAPI | Routers under `src/api/*_routes.py`, one router per feature area, business logic delegated to `src/services/*_svc.py` — routes stay thin. See `.agents/skills/fastapi/SKILL.md`. |
| MCP SDK | `src/mcp_server.py` exposes tools over stdio (default) and optional LAN-facing Streamable HTTP. **Define every new tool with the `@tool` decorator** (not raw `mcp.tool()`) — it registers automatically with both FastMCP and the `TOOLS` dict, which `src/api/mcp_routes.py` loops over to auto-generate the matching REST endpoint under `/api/mcp/*`. `tests/test_api.py::test_mcp_rest_parity` is a safety-net contract test that verifies this, not something you satisfy by hand. See `.agents/skills/python-mcp-server-generator/SKILL.md`. |
| Qdrant client | Hybrid dense+sparse search via this repo's own weighted RRF fusion in `src/retrieval.py` (not Qdrant's built-in RRF query feature) plus a name-match boost; symbol-graph relations live in their own collection, never embedded per-point. See `.agents/skills/qdrant-clients-sdk/SKILL.md`, `.agents/skills/qdrant-search-quality/SKILL.md`, `.agents/skills/qdrant-performance-optimization/SKILL.md`. |

## Database

### Qdrant (the only database)

- Connection: `qdrant_url` in `mcp-config.json` (default `http://127.0.0.1:6333`).
- **Reindex is atomic, never in-place:** a reindex builds into a separate staging collection; only an atomic alias swap makes it live once complete and verified. Never mutate a live, queryable collection mid-index.
- **`onnxruntime-gpu==1.22.0` is a critical, hand-verified pin** — do not bump casually. Newer releases (1.27+) require CUDA-13 DLLs (`cudart64_13.dll`, `cufft64_12.dll`) that pip's `nvidia-cu12` packages don't provide; the GPU then silently falls back to CPU or fails to load, with no error printed. If this pin must change, re-verify GPU activation (`/api/health`'s `gpu` field, and the `AKTIF: ['CUDAExecutionProvider', ...]` log line) before considering the change done.
- **Known trap — package conflict:** `fastembed==0.8.0` depends on plain `onnxruntime`, but this project installs `onnxruntime-gpu==1.22.0` — pip sees them as separate packages sharing the same `onnxruntime/` files, so install order is non-deterministic across runs and a plain `pip install -r requirements.txt` can silently overwrite the GPU build with the CPU one. `tools/install.ps1`'s GPU branch fixes this after the main install with `pip uninstall -y onnxruntime onnxruntime-gpu` + `pip install --no-deps onnxruntime-gpu==1.22.0` — repeat this manually after any future `pip install -r requirements.txt` re-run (e.g. adding a new dependency).

> **Skills:** `.agents/skills/qdrant-clients-sdk/SKILL.md`, `.agents/skills/qdrant-deployment-options/SKILL.md`, `.agents/skills/qdrant-scaling/SKILL.md`, `.agents/skills/qdrant-monitoring/SKILL.md`

## Concurrency / Async (if applicable)

### Golden Rule

> Route handlers in this codebase are plain `def`, not `async def` — FastAPI runs them in its own threadpool automatically, and this is the deliberate, consistent convention across all of `src/api/` (verified: 84+ handlers, only one `async def` in the entire package, tied to an `await file.read()` on a file upload). Don't "fix" a sync handler into `async def` on sight — that's a style regression here, not an improvement. CPU-bound chunking/parsing work (tree-sitter) also stays synchronous, same as every other handler.

### Approaches

| Approach | When to Use |
|-----------|-------------|
| Plain `def` route handler (FastAPI threadpool) | Every existing endpoint, including the SSE streams (`/api/ask/stream`, `/api/research/stream`) — this repo's actual, consistent convention |
| SSE streaming — FastAPI's own `StreamingResponse` | `/api/ask/stream`, `/api/research/stream` — `media_type="text/event-stream"` with hand-written `event:`/`data:` frames; token-budgeted, truncation-aware (surface Ollama's own `done_reason` rather than silently returning a cut-off answer). **Not `sse-starlette`** — that package is only present as a transitive dependency of `mcp` and is never imported by this project's code. |
| Persistent job queue | Indexing jobs — survives a process restart mid-index |

### Anti-Patterns

- ❌ Converting an existing sync `def` route handler to `async def` without a real, measured reason — inconsistent with this repo's dominant convention
- ❌ Silently swallowing a truncated/cut-off LLM response instead of surfacing `done_reason`

> **Skills:** `.agents/skills/fastapi/SKILL.md`

## SOLID Principles (adapt to this language's idioms)

### S — Single Responsibility Principle (SRP)

Routes (`src/api/*_routes.py`) only parse requests and call a service;
business logic lives in `src/services/*_svc.py` — a route file that grows
inline business logic instead of delegating is a real SRP violation here.

### O — Open/Closed Principle (OCP)

The chunker is designed per-language: `Chunker` per-language classes plus
an extension registry (see `chunker.py`'s own docstring, point 4) — adding
a new language means adding a new class, not branching inside an existing
one.

### L — Liskov Substitution Principle (LSP)

Any per-language chunker implementation must honor the same chunk record
shape (`id`, `lib`, `unit`, `kind`, `name`, line range, code, doc, hash) so
callers never special-case a specific language's output shape.

### I — Interface Segregation Principle (ISP)

`src/services/common.py` exposes only the shared helpers actually used
across services — a service-specific helper belongs in its own `*_svc.py`,
not bloating the shared module.

### D — Dependency Inversion Principle (DIP)

**This project does not use FastAPI's `Depends(...)` at all** (zero
occurrences in `src/`). Shared infrastructure is instead reached through
one module-level source of truth: `src/services/common.py` re-exports the
single Qdrant client (`cl`), the Ollama endpoint (`OLLAMA`) and every
collection-name constant from `retrieval.py`, and every route/service
imports from there. The inversion that matters here is **"one shared
definition, imported"** rather than each module constructing its own
`QdrantClient()` or hardcoding a collection name — don't introduce a
second client instance or a duplicated constant.

> **Skills:** `.agents/skills/fastapi/SKILL.md`

## Clean Code — Essential Rules

### 1. Short Functions/Methods

- No hard line-count ceiling enforced in this codebase; extract when a
  function mixes more than one responsibility (parsing + indexing,
  request-handling + business logic).
- If a function needs a comment explaining "what it does", extract it into a function with a descriptive name.

### 2. Self-Descriptive Names

```python
# Bad
def proc(x, y):
    ...

# Good
def chunk_file(path: pathlib.Path, lib: str) -> list[dict]:
    ...
```

### 3. Avoid Magic Numbers

```python
# Bad
if len(node_lines) > 400:
    ...

# Good — real project convention (chunker.py)
HUGE_LINES = 400  # bu satır sayısını aşan düğümler "huge" — ilk HUGE_LINES satırla indekslenir
if len(node_lines) > HUGE_LINES:
    ...
```

### 4. Guard Clauses

```python
# Bad
def find_body_node(node):
    if node is not None:
        for c in node.children:
            if "block" in c.type:
                return c

# Good — real project convention (chunker.py's _find_body_node)
def _find_body_node(node):
    if node is None:
        return None
    for c in node.children:
        if any(h in c.type for h in _BODY_HINTS):
            return c
    return None
```

### 5. Focused Error Handling

Catch specific exceptions at the boundary that can actually raise them
(parser errors, Qdrant client errors, Ollama HTTP errors) — never a bare
`except:`/`except Exception:` that swallows an unrelated bug.

### 6. File/Module Organization

Module-level docstring (what/why, real gotchas discovered) → constants →
private helpers (`_`-prefixed) → public functions — see `chunker.py` as
the canonical example: its docstring documents actual regressions fixed
(ID stability, unithead chunks, huge-method truncation), not generic
boilerplate.

> **Skills:** `.agents/skills/python/SKILL.md`

## Recommended Design Patterns

| Pattern | Use in this stack |
|--------|---------------|
| **Service** | `src/services/*_svc.py` — business logic orchestrating the Qdrant client, Ollama calls and the chunker |
| **Strategy** | Per-language `Chunker` classes behind one extension registry (`chunker.py`) |
| **Shared-singleton access** | One Qdrant client (`cl`) and one Ollama endpoint, re-exported from `src/services/common.py` — never a second client instance constructed elsewhere |
| **Staging + atomic swap** | Reindex builds into a separate collection, swapped in via alias only once verified — the project's own substitute for a transactional Unit of Work |

> **Skills:** `.agents/skills/python/SKILL.md`

## Anti-Patterns to Avoid

- ❌ **God module** — a `*_routes.py` or `*_svc.py` file doing unrelated feature areas; split by feature instead
- ❌ **Business logic inside a route handler** — belongs in the matching `*_svc.py`
- ❌ **New, undocumented global mutable state** — note the deliberate exception: `src/services/common.py`'s `STATE = {"index_job": None}` is the single shared job-status dict every module updates on purpose, and `cl`/`OLLAMA` are intentional shared singletons. Don't dismantle those; don't add a second one either.
- ❌ **Hardcoded strings** for config that varies by environment — use `mcp-config.json`/`requirements.txt`-documented settings
- ❌ **`pip install -r requirements.txt` re-run without re-applying the GPU fixup** — see Database section's known trap
- ❌ **Defining an MCP tool with raw `mcp.tool()` instead of this project's `@tool` decorator** — skips `TOOLS` registration, so no REST endpoint is generated and `test_api.py::test_mcp_rest_parity` fails
- ❌ **Mutating a live Qdrant collection mid-reindex** — always stage + atomic alias swap
- ❌ **Testing against a real Qdrant/Ollama instance in the default `pytest` run** — that belongs in `tests/manual/` (excluded by `pytest.ini`), not `tests/`

## Resource / Memory Management (Critical)

This stack is garbage-collected (CPython) with no manual memory-management
concerns. The real resource discipline here is **process/service
lifecycle, not memory**: Qdrant/Ollama connections and the persistent job
queue must survive and recover from a process restart mid-operation
(indexing jobs are explicitly designed to be resumable) — treat an
indexing or streaming operation that can't safely resume after a crash as
a defect, not memory-unsafety.

> **Skills:** `.agents/skills/qdrant-clients-sdk/SKILL.md`

## Documentation

- Use standard Python docstrings (`"""..."""`) for modules and public functions — see `chunker.py`'s module docstring for the expected depth (what changed, why, and which real bug it fixes, not just what the code does).
- **Comments and docstrings in this codebase are written in Turkish** (identifiers stay English) — this is the real, observed, consistent convention (verified in `chunker.py`, `services/*.py`), not the workspace's generic "comments in English" default; follow it for any new code added here.
- Don't comment obvious code — let the name explain.

## Working Directory

`src/` already holds this project's real, running application — this is
not a scaffold with an empty `src/`. Generated/modified code goes into
the existing layer it belongs to (see Structure below); a genuinely new
top-level module goes at `src/` root alongside `chunker.py`,
`retrieval.py`, `manual.py`, `panel.py`, `mcp_server.py`. Never invent a
parallel output location.

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
└── manual/             ← Requires real GPU/Ollama/Qdrant — excluded from default run (pytest.ini norecursedirs)
```

> **Dependency rule (as actually practiced — two tiers, verified):**
> `api/*_routes.py → services/*_svc.py → chunker.py / retrieval.py / Qdrant / Ollama`
> is the path for anything with **real logic** — indexing, retrieval/RAG, manual
> generation, symbol-graph work. Thin CRUD/passthrough endpoints, by contrast,
> **do** call the shared `cl` client directly and that is the established pattern,
> not a violation (verified: 47 direct `cl.*` calls across the API layer —
> `admin_routes.py` 36, `search_routes.py` 7, `index_routes.py` 3,
> `manual_routes.py` 1 — all simple operations like `cl.collection_exists()`,
> `cl.get_collections()`, `cl.delete_collection()`). The line to hold: a route
> may *reach* Qdrant, but must not *contain* business logic — the moment an
> endpoint grows branching, batching, staging or multi-step orchestration, that
> belongs in a `*_svc.py`.

---

## 🚫 AI Context Policy — What to Include and Exclude

> Full strategy documented in `docs/ai-ignore-strategy.md`.

### Files AI Must Always Use as Context

Always load, regardless of tool:

- `AGENTS.md` — universal rules
- `README.md` — project overview
- `src/**/*` — this project's real, running application code
- `tests/**/*.py` — the regression suite; test names document locked-in behavior
- `docs/**/*.md` — documentation

Skills are shared: `.agents/skills/**/SKILL.md` is the single editable copy —
no tool ever gets its own duplicate of a SKILL.md. Claude Code does need its
own *entry point*, because it discovers skills only under `.claude/skills/`;
`tools/generate-ai-configs.ps1` creates one junction/symlink there per skill,
pointing back at `.agents/skills/`. Those links are generated, gitignored, and
never hand-made. (Corrected: this section previously claimed every tool reads
`.agents/skills/` natively as a fallback location — it does not, and the
result was that no skill in this kit ever triggered on its own.)

For rules, load **only the format that matches the tool you are running as**:

| If you are... | Load |
|---|---|
| Claude Code | `.claude/CLAUDE.md` + `.claude/rules/**/*.md` (generated from `.agents/rules/`) |
| Cursor | `.cursor/rules/**/*.md` (generated from `.agents/rules/`) |
| Codex CLI | `AGENTS.md` (no per-topic rules folder support — this file is the full ceiling) |
| GitHub Copilot | `.github/copilot-instructions.md` |
| Gemini / Antigravity | `.gemini/rules/project-rules.md` |
| Kiro | `.kiro/steering/**/*.md` |

`.claude/rules/**/*.md` and `.cursor/rules/**/*.md` are **generated copies** of
`.agents/rules/**/*.md` (single source of truth) — see
`.agents/rules/sync-workflow.md` for how they're kept in sync. Do not hand-edit
the generated copies, and do not load more than one tool's rule set in the
same session — they're mirrors of the same content, not additive.

### Files AI Must Never Use as Context

- Build artifacts: `__pycache__/`, `*.pyc`
- IDE/tool temporaries: `.pytest_cache/`, `.serena/`
- Output/data directories: `data/`, `logs/`, `backups/`, `snapshots/`, `qdrant-bin/` (bundled Qdrant binary, not source)
- Secrets: `*.key`, `*.pfx`, `*.p12`, `.env`, `.env.*`
- Noise: `*.log`, `*.dmp`, `*.bak`, `*.tmp`

See `.cursorignore`, `.gitignore` and `.vscode/settings.json` for the enforced patterns.
