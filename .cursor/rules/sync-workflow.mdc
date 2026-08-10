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
| Rules (per-topic, glob-scoped) | `.agents/rules/*.md` | `.claude/rules/*.md` and `.cursor/rules/*.mdc` — **generated**, do not hand-edit. Note the extension: Cursor recognizes only `.mdc` under `.cursor/rules` and silently ignores `.md` there (cursor.com/docs/rules). |
| Slash commands | `.agents/commands/*.md` | `.claude/commands/*.md` — **generated**, do not hand-edit |
| Skills | `.agents/skills/*/SKILL.md` | content is never copied, but Claude Code needs an entry point: a **generated** junction/symlink per skill at `.claude/skills/<skill-name>` → `.agents/skills/<skill-name>`. Claude Code additionally gets a **generated** thin wrapper at `.claude/commands/<skill-name>.md` so the skill is also invocable as an explicit `/<skill-name>` command — see below. |
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

This copies the current source into `.claude/rules` (as `.md`) and
`.cursor/rules` (as `.mdc`), copies commands into `.claude/commands`,
generates one `.claude/commands/<skill-name>.md` wrapper per folder under
`.agents/skills/`, links each of those skill folders into `.claude/skills/`,
and removes any generated file, wrapper or link whose source was deleted. If a skill's folder name collides with a
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

**Why rules are copied, not symlinked:** this kit is distributed via
`git clone` into arbitrary projects. A symlink *committed to the repo*
requires Developer Mode/admin on Windows and `core.symlinks=true` in git to
survive a clone correctly; when that isn't the case the symlink degrades into
a plain text file containing the target path, and the tool silently finds zero
rules. Copies have no such failure mode.

**Why skills ARE linked, and why that's not a contradiction:** the paragraph
above is about links stored *in git*. The `.claude/skills/` entries are never
committed — `.gitignore` excludes them, and `tools/generate-ai-configs.ps1`
recreates them on the machine where it runs, after the clone. So the
degrades-on-clone failure simply cannot occur. On Windows the script creates
a **directory junction**, which needs neither elevation nor Developer Mode;
elsewhere, a symlink; and if the filesystem refuses both, it falls back to a
real copy and says so loudly.

**Why the link is needed at all:** Claude Code discovers skills only from
`.claude/skills/` (plus `~/.claude/skills`, plugins and enterprise paths).
`.agents/skills/` is **not** one of its discovery locations — verified against
`code.claude.com/docs/en/skills`. Linking keeps `.agents/skills/` the single
editable source while making every skill actually reachable; Claude Code
resolves the links and loads a skill reachable from several paths only once.

> **Corrected claim.** Earlier versions of this file, `AGENTS.md`,
> `docs/ai-ignore-strategy.md` and the generator script itself all asserted
> that `.agents/skills/` "is read as a fallback location natively by every
> supported tool as of 2026." That was never verified and is false for Claude
> Code. The consequence was not cosmetic: every skill in this kit was
> invisible to trigger matching, reachable only if the user happened to type
> the `/<skill-name>` wrapper by hand.

The `/<skill-name>` command wrapper is still generated, and is still
optional — it exists so a user who types the skill's name as a slash command
(instead of describing what they want) reaches it deterministically, from its
first step.
