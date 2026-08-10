# Analysis/Evaluation/Edit Output Convention

The shared input-resolution and output-naming rule for the bundled
`rad-prompt-studio` skill's three master prompts
(`analysis-base-prompt.md`, `evaluation-base-prompt.md`,
`edit-base-prompt.md`). None of those three files restate this — they all
point here. Without this file present, none of them can resolve where a
report goes or what it is named.

## Where input comes from

1. **A specific path is named in the request** (a file or a folder) →
   analyze/evaluate/edit that path directly, in place. Nothing gets copied
   anywhere first.
2. **No path named, request is "review this project/repo" or
   equivalent** → bulk traversal mode (`analysis-base-prompt.md`'s
   "Determining the target" section). The map is this repo's own
   `AGENTS.md` + `docs/proje-haritasi.md`, not a staged folder.
3. **Request is "system analizi"/"system analysis" or equivalent** →
   System Analysis mode (`analysis-base-prompt.md`'s own section). In a
   kit, the system layer is `.agents/skills/`, `.agents/rules/`,
   `.agents/commands/` and the four AI-primary identity files
   (`AGENTS.md`, `.claude/CLAUDE.md`, `.github/copilot-instructions.md`,
   `.gemini/rules/project-rules.md`) — **never** the kit's own subject-matter
   code under `src/` or `examples/`. Drop everything on the exclusion list
   (any `*.tr-TR.md` file, and any bundled third-party skill this kit did
   not author), then present the rest as a numbered pick-list and wait for
   the user to choose before analyzing anything.
4. **No path named and no bulk-review/system-analysis phrasing either** →
   scan `src/` for `.md` files and skill-shaped folders (a folder
   containing its own `SKILL.md`). Present every match as a numbered
   pick-list and ask the user which one(s) to analyze — never a bare
   open-ended "what would you like me to analyze?" when there's something
   concrete to offer. Only fall back to the bare open-ended question if
   that scan comes back empty. Never guess, and never treat "nothing
   specified" as "nothing to do."

**"Tümü"/"all" replied to any pick-list (rule 3's, rule 4's, or
Evaluation mode's own) means every item in that specific list — never an
implicit switch to rule 2's bulk traversal mode.** A pick-list "all" and
"review this whole repo" are two different instructions; conflating them
was an observed real failure (an AI that, after presenting a pick-list,
treated "all" as license to traverse everything else too).

**Evaluation mode's own target resolution** (explicit target vs. a
pick-list scanned from the existing report folders) is specified in
`evaluation-base-prompt.md`'s own "Determining the target" section, not
repeated here — same numbered-pick-list and "'all' means this list only"
discipline as the analysis modes above.

## Where output goes

Reports are **work product, not repo content** — they are never committed
with the kit. Default location, for every mode, is the machine-wide `.rad`
hub's `analysis` link (`%ProgramData%\rad\analysis`, which points at the
registered workspace's own `share\analysis\` folder — see
`local-machine-registry.md`):

```
%ProgramData%\rad\analysis\{repo_name}\{target_name}\{ai_name}_v{n}.md
```

- `{repo_name}` — this kit's own folder name.
- `{target_name}` — the target's own file/folder/skill name, exactly as it
  appears on disk (`system` for a system-analysis write-up covering the
  whole system layer).
- `{ai_name}` — the acting AI's own identity, lowercase (`claude`, `codex`,
  `gemini`, `copilot`, ...).
- `{n}` — version number, starting at `v1`. Re-running the same mode
  against the same target later increments it (`v2`, `v3`, ...) instead of
  overwriting — every past run stays on record.

**Fallback:** if `%ProgramData%\rad\` does not exist on this machine (the
hub isn't installed — the workspace's own `pwsh tools/rad.ps1 -Action
Install` creates it), write to this repo's own `analysis/result/` folder
instead, using the same `{target_name}\{ai_name}_v{n}.md` shape, and say
so in the report header. `analysis/` is already gitignored by this kit.

Mode-specific filename prefixes, all under that same
`{repo_name}\{target_name}\` folder:

| Mode | Filename |
|---|---|
| Analysis | `{ai_name}_v{n}.md` |
| Analysis — reconciling multiple prior analyses (explicit opt-in) | `synthesis_{ai_name}_v{n}.md` |
| Evaluation (standalone request, or Edit mode's automatic pre-check) | `evaluation_{ai_name}_v{n}.md` |
| Edit (the applied-change report) | `edit_{ai_name}_v{n}.md` |

**Manual override.** The user may give an explicit output folder path
instead of the default — when they do, that path wins outright; don't
also write a copy to the default location.

## One file per target per run

Never write one combined file covering multiple targets, and never
overwrite a prior run's file — increment `{n}` instead. Each mode's own
master prompt owns everything about the file's *content*; this rule only
owns *where it lands and what it's named*.

## Retention — corrected analyses get deleted, not kept forever

Once a target's findings have actually been corrected (an `edit_*.md` has
been written for it), delete every analysis/evaluation/edit report file
under that target's folder. The fix now lives in the actual file;
`git log`/`git diff` plus the CHANGELOG is the permanent record of what
changed and why — a duplicate archive of the resolved analysis is not kept
alongside it.

Unresolved analyses — no edit applied yet, or explicitly deferred pending
a user decision — are **not** deleted by this rule; it only fires once a
target's findings have actually been corrected. The versioning rule above
(`{n}` incrementing, never overwriting) still governs multiple runs
*before* that point.
