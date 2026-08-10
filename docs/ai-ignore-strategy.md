# AI Ignore Strategy — CodeIntel

> Defines which files and folders should be **excluded** from AI context/indexing, and which must be **preserved**.

## Layered Approach

The strategy is applied in three complementary layers:

| Layer | File | Scope |
|-------|------|-------|
| **Universal** | `.gitignore` | All tools; prevents tracking of binaries, build artifacts and sensitive files |
| **IDE / Workspace** | `.vscode/settings.json` | `files.exclude` and `search.exclude` reduce noise in VS Code navigation and search |
| **Cursor-specific** | `.cursorignore` | Prevents Cursor AI from indexing heavy/irrelevant paths |
| **Instruction-based** | `AGENTS.md`, `.github/copilot-instructions.md` | Tells AI agents explicitly what context to use and what to skip |

## What to Exclude (all layers)

### Build Artifacts
- `__pycache__/`, `*.pyc`

### IDE / Tool Temporary Files
- `.pytest_cache/`, `.serena/`

### Output / Data Directories
- `data/`, `logs/`, `backups/`, `snapshots/`, `qdrant-bin/` (bundled Qdrant binary, not source)

### Dependencies and Package Caches
- `.venv/` (this project deliberately doesn't use one — see `CONTRIBUTING.md`'s "Antivirüs uyarıları" — but exclude it anyway if one ever appears locally)

### Sensitive / Credential Files
- `*.key`, `*.pfx`, `*.p12`, `.env`, `.env.*`

### Large / Noisy Files
- `*.log`, `*.dmp`, `*.bak`, `*.tmp`

## What to Preserve (NEVER exclude)

These files are essential for AI context and must always remain indexed and accessible:

| File / Path | Reason |
|-------------|--------|
| `AGENTS.md` | Universal rules for all AI agents (Codex CLI, Antigravity, Copilot, Cursor, Kiro) |
| `README.md` | Project overview and quick start |
| `src/**/*` | This project's actual generated deliverables (the default output location) |
| `tests/**/*.py` | Regression suite — test names document locked-in behavior |
| `docs/**/*.md` | Documentation |
| `.agents/rules/**/*.md` | **Single source of truth** for per-topic rules — generates `.claude/rules` and `.cursor/rules` |
| `.agents/commands/**/*.md` | Single source of truth for slash-commands — generates `.claude/commands` |
| `.agents/skills/**/SKILL.md` | Single source of truth for skills — content is never copied; Claude Code reaches it through generated links under `.claude/skills/` |
| `.github/copilot-instructions.md` | Copilot pre-prompt |
| `.claude/CLAUDE.md`, `.claude/rules/**/*.md` (generated), `.claude/commands/**/*.md` (generated) | Claude Code master prompt + generated rule/command copies |
| `.cursor/rules/**/*.md` (generated) | Cursor rules |
| `.gemini/rules/project-rules.md` | Gemini/Antigravity summary (hand-authored, same role as `AGENTS.md`) |
| `.kiro/steering/**/*.md` | Kiro steering docs |

> **Note:** `.claude/rules`, `.cursor/rules` and `.claude/commands` are **generated** from `.agents/rules` and `.agents/commands` by `tools/generate-ai-configs.ps1` — never hand-edit them directly, and never exclude `.agents/` itself from indexing. See `.agents/rules/sync-workflow.md` for the full architecture. A given AI session should only load the rule set matching the tool it runs as — see `AGENTS.md`'s "AI Context Policy" for the per-tool table.

## Tool-Specific Support Matrix

| AI Tool | Dedicated Ignore File | Behavior |
|---------|----------------------|----------|
| **Cursor** | `.cursorignore` | Explicit ignore for indexing and context |
| **Claude Code** | N/A | Uses rules/instructions; respects `.gitignore` and workspace excludes |
| **GitHub Copilot** | N/A | Follows `files.exclude`, `search.exclude`, `.gitignore` and instruction files |
| **Gemini / Antigravity** | N/A | Follows workspace structure and `.gitignore` |
| **Kiro** | N/A | Follows workspace structure and `.gitignore` |

## Maintenance Checklist

When adding new modules or subprojects:

- [ ] Verify build output folders are covered by `.gitignore`
- [ ] Verify `.cursorignore` includes any new heavy/binary paths
- [ ] Verify essential instruction files are NOT excluded
- [ ] Verify `.vscode/settings.json` excludes are up to date
