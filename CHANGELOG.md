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

### Fixed

- **Searching while an answer was still streaming crashed the panel with
  `TypeError: Cannot set properties of null (setting 'innerHTML')`.** `run()`
  only disabled the Go button, but three other paths call it directly — the
  Enter key, suggestion chips (`pick()`) and `jumpTo()`. A second search reset
  `#out`, destroying `#ans`/`#anssrc`/`#cmpwrap` while the previous stream was
  still writing into them; the stale loop then wrote to `null`, and that
  TypeError landed in the old `run()`'s `catch`, painting a red error box over
  the *new* search's results. Searches now carry a sequence number (stale runs
  write nothing) and the previous request is genuinely aborted, which also ends
  the abandoned generation instead of leaving the GPU busy for the rest of a
  ~220 s deep answer — the cause of the "screen freezes, then results appear"
  behaviour. `compareFunctions()` had the identical hazard and is guarded the
  same way. Regression test: `tests/test_panel_overlap.py`, which runs the real
  `run()`/`runAskStream()` extracted from `index.html` against a fake DOM and
  was verified to reproduce the crash on the pre-fix version.
- **Claude Code could not discover any of this kit's skills.** It looks only
  under `.claude/skills/`; `.agents/skills/` is not one of its discovery
  locations, so every skill here was unreachable by trigger matching and only
  worked if the user typed the generated `/<skill-name>` wrapper by hand.
  `tools/generate-ai-configs.ps1` now creates one junction (Windows, no
  elevation needed) / symlink per skill under `.claude/skills/`, pointing back
  at `.agents/skills/`. The links are gitignored and regenerated after a clone,
  so the "symlink degrades on clone" hazard that keeps rules as copies does not
  apply. Verified against `code.claude.com/docs/en/skills`.
- **Cursor ignored every rule in this kit.** `.cursor/rules/` held `.md` files;
  Cursor recognizes only `.mdc` there and silently skips anything else. The
  frontmatter was already correct — only the extension was wrong. The generator
  now writes `.mdc` and sweeps the old `.md` copies instead of leaving both.
  Verified against `cursor.com/docs/rules`.
- **Gemini CLI read nothing.** The AI-tool table pointed it at
  `.gemini/rules/project-rules.md`, but Gemini CLI builds context from the
  `GEMINI.md` hierarchy. Added a root `GEMINI.md` that imports that file rather
  than duplicating it. Verified against `geminicli.com/docs/cli/gemini-md`.
- **`.claude/settings.json` used invented keys.** `allowCommands`/`denyPaths`
  are not Claude Code settings, so the advertised `.env`/`.key` protection and
  the pre-approved generator command never existed. Rewritten to the real
  `permissions.allow`/`permissions.deny` schema.
- Corrected the false claim, repeated across this kit's rules, `AGENTS.md`,
  `docs/ai-ignore-strategy.md`, the READMEs and the generator itself, that
  `.agents/skills/` "is read as a fallback location natively by every supported
  tool." It is not, and that assumption is what left the skills unreachable.
- Fixed the mutually broken links between `prompt-engineer-analyst.md` and
  `design/prompt-patterns.md` in the bundled `rad-prompt-studio`.

### Added

- `.agents/rules/analysis-output.md` — the input-resolution and output-naming
  rule the three bundled `rad-prompt-studio` master prompts reference but which
  was not present in this kit, leaving them unable to resolve a report path.
- `tools/verify-kit.ps1` and `.github/workflows/verify.yml` — a mechanical
  consistency gate (generator drift, Cursor extension, skill-link presence,
  `SKILL.md` frontmatter, `[FILL IN` residue, README image links, `LICENSE`),
  runnable locally as `pwsh tools/verify-kit.ps1` and in CI from one script.


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
