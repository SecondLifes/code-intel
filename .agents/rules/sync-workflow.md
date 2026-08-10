---
description: "How this repo's multi-tool AI config is organized and kept in sync — read this before editing any rule, command or skill."
alwaysApply: true
---

# AI Config Source of Truth & Sync Workflow

This repo supports five AI coding tools (Claude Code, Cursor, Codex CLI, GitHub
Copilot, Gemini/Antigravity CLI). To avoid maintaining near-duplicate copies by
hand, most content has a single canonical source under `.agents/`.

## Where content actually lives

| Content | Canonical source | Generated / native copies |
|---|---|---|
| Rules (per-topic, glob-scoped) | `.agents/rules/*.md` | `.claude/rules/*.md`, `.cursor/rules/*.md` — **generated**, do not hand-edit |
| Slash commands | `.agents/commands/*.md` | `.claude/commands/*.md` — **generated**, do not hand-edit |
| Skills | `.agents/skills/*/SKILL.md` | content needs no copy — every supported tool reads `.agents/skills/` natively (Agent Skills open standard, agentskills.io). Claude Code additionally gets a **generated** thin wrapper at `.claude/commands/<skill-name>.md` so the skill is also invocable as an explicit `/<skill-name>` command — see below. |
| Root universal summary | `AGENTS.md` | none — hand-authored, references `.agents/rules` for detail |
| Gemini/Antigravity summary | `.gemini/rules/project-rules.md` | none — hand-authored, same role as `AGENTS.md` but Gemini-specific |
| Copilot pre-prompt | `.github/copilot-instructions.md` | none — hand-authored, references `AGENTS.md` |
| Kiro steering docs | `.kiro/steering/*.md` | none — different concept (living project context, not per-topic rules), intentionally out of this sync scheme |

## Mandatory workflow

**Whenever you add, edit or delete a file under `.agents/rules/` or
`.agents/commands/`, OR add/remove a skill folder under `.agents/skills/`,
immediately run the generator before finishing your turn:**

```powershell
pwsh tools/generate-ai-configs.ps1
```

This copies the current source into `.claude/rules`, `.cursor/rules` and
`.claude/commands`, generates one `.claude/commands/<skill-name>.md` wrapper
per folder under `.agents/skills/`, and removes any generated file whose
source (or skill) was deleted. If a skill's folder name collides with a
hand-authored file under `.agents/commands/`, the script skips generating a
wrapper for it and prints a warning — hand-authored commands always win.
Never hand-edit files inside `.claude/rules/`, `.cursor/rules/` or
`.claude/commands/` directly — they will be silently overwritten on the next
run and any change made only there will be lost.

**Whenever you add, remove or rename a file under `.agents/rules/`,
`.agents/commands/` or `.agents/skills/`, also update
`docs/proje-haritasi.md` in the same turn** — add/remove/rename the
corresponding row and write a short Turkish description of what it does. The
generator script cannot do this part for you (it doesn't know what a new
rule/skill/command actually does); it only *warns* at the end of its run if
something in `.agents/` isn't mentioned anywhere in `docs/proje-haritasi.md`
yet. Treat that warning as a checklist item, not something to silence by
adding the filename without a real description.

**Why not symlinks:** this kit is distributed via `git clone` into arbitrary
projects. Directory symlinks require Developer Mode/admin on Windows and
`core.symlinks=true` in git to survive a clone correctly; when that isn't the
case the symlink degrades into a plain text file containing the target path,
and the tool silently finds zero rules. A generated-copy script has no such
failure mode.

**Why skills are different:** skill *content* doesn't need this treatment
because `.agents/skills/` is read as a fallback location natively by every
supported tool as of 2026 — the SKILL.md itself is never copied. The one
thing that IS generated per skill is the optional `/<skill-name>` command
wrapper, and only for Claude Code — natural-language trigger matching still
works everywhere without it; the wrapper exists purely so a user who types
the skill's name as a slash command (instead of describing what they want)
still reaches it, deterministically, from its first step.
