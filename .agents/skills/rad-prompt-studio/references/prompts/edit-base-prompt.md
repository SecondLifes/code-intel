# Edit Base Prompt

The standard prompt for applying an **approved** change to any `.md` file
or skill folder — a prompt, a rule, a `SKILL.md`, a whole
`references/*.md` set. This is the last step of Edit Mode (see
`SKILL.md`), reached only after `analysis-base-prompt.md` (and, when prior
analyses existed, `evaluation-base-prompt.md`) have already run and the
user has explicitly approved a specific change list. This file governs
*how* the edit itself is carried out and reported — it does not re-run
analysis or evaluation, and it never originates its own findings.

Load this after the five-lens identity (see `SKILL.md`) is already
adopted, and only once an approved change list exists.

## Golden rules

1. **No edit without a prior approved change list.** If you find yourself
   about to modify a file without a change list the user explicitly signed
   off on (from Edit Mode's approval step), stop — that's a process
   violation, not a shortcut. Go back and get approval first.
2. **Scope discipline.** Apply exactly the approved items — no
   opportunistic extra cleanup, no unrelated "while I'm in here" changes.
   If you notice something else worth fixing while editing, surface it as
   a new candidate for a *future* approval round, don't fold it in
   silently.
3. **Preserve intent, not just syntax.** An edit that technically resolves
   a finding but changes the file's meaning, tone, or scope in a way the
   finding didn't call for is a new defect, not a fix.
4. **Minimal diff.** Change only what the approved item requires. A
   one-line fix should produce a one-line diff, not a rewritten section.
5. **Verify after editing, not just before.** A `.md` file renders
   correctly and a skill folder's cross-references (paths, filenames
   mentioned in prose) still resolve — check both after the edit, not just
   assume the change was clean because it was small.
6. **Bidirectional propagation for shared system files.** Some files
   exist as deliberate copies on both sides of the kit ↔ workspace
   boundary: bundled `rad-*` skills under a kit's `.agents/skills/`.
   An approved edit to one side must reach the other side in the same
   run — both sides stay current, always:
   - **Editing inside a kit** (the working directory is a kit that is its
     own git repo): after applying the edit, locate the parent workspace —
     first at `../../` (marker: a `CLAUDE.md` charter there plus a
     matching canonical copy, `../../.claude/skills/<name>/`); if
     `../../` doesn't resolve (the kit is cloned somewhere else), read
     `root` from `%ProgramData%\rad\settings.json` and look
     there instead. If found either way, apply the identical change to
     the canonical copy too, and run the parent's
     `tools/sync-hardlinks.ps1` if the canonical file is hardlinked. If
     no parent exists by either route (a standalone clone on a machine
     without the hub), state that explicitly in the edit report's
     Verification field — never silently skip it.
   - **Editing at the workspace root**: if the edited file is a canonical
     `rad-*` skill, propagate to `blank-scaffold/` and to every
     `spec-kits/*` kit that actually bundles a copy — this is exactly
     `rad-template-builder`'s "Bundled `rad-*` skill drift" maintenance
     (see that skill), run as part of the same edit, not deferred to
     someday.
   - Kit-side copies live in separate git repos — commit the kit-side
     change in the kit's own repo (and note that the parent's submodule
     pointer needs bumping) rather than leaving the kit dirty.
7. **Fix publication workflow (git repos with a GitHub remote).** The AI
   applying the fixes owns the whole publication trail itself — helper
   scripts like a kit's `update.bat` are manual conveniences for humans,
   never part of this flow. Per **accepted finding**, in this order:
   1. **GitHub issue first** — `gh issue create` on the target's own
      repo: title = the finding's one-line summary, body = the evidence
      (file:line citations, which analyses found it, cross-confirmation
      notes). The returned number `#N` is the finding's public ID.
   2. **One commit per finding** — message `Fix <summary> (#N)`, body
      carrying the why. Trivially-related findings in the same file may
      share one commit listing every issue ref. Never one giant
      commit for the whole run.
   3. **`CHANGELOG.md`** — every fix adds a line under the release-in-
      progress's `### Fixed` (Keep a Changelog format; create the file
      if the repo lacks one). Committed as its own final `chore:` commit.
   4. **Version tag** — after all fixes: if the kit has a `settings.json`
      (see `.agents/rules/kit-settings.md`), read
      `versioning.current_version`, compute the bump (PATCH for fixes,
      MINOR if features/capabilities were added, MAJOR for breaking
      changes), write the new value back and commit it, then create the
      matching annotated `vMAJOR.MINOR.PATCH` tag locally — tag and
      `settings.json` must always agree. If the kit predates
      `settings.json`, fall back to deriving the next version from the
      latest existing tag instead of blocking on the missing file.
   5. **Never push** — commits, tags, and the moment issues get linked
      to commits all go live when the *user* pushes; issue creation via
      `gh` is the one step that touches GitHub directly, and it only
      happens for findings the user already approved fixing.
   6. **Retention** — once a target's fixes are committed, delete its
      report files per `analysis-output.md`'s Retention rule; git
      history + issues + CHANGELOG are the permanent record.
   If the repo has no GitHub remote or `gh` isn't authenticated, skip
   the issue step, note that in each commit body, and continue —
   the workflow degrades gracefully, it never blocks the fix.

## Mandatory report header

```
# Edit — `{target_name}` v{n}
**Editor:** {ai_name} ({model}, if known) · **Run:** v{n} · **Date:** {ISO date}
**Target:** `{path}`
**Approved from:** `analysis/result/{target_name}/{ai_name}_v{n}.md`
  {and, if applicable} `analysis/result/{target_name}/evaluation_{ai_name}_v{n}.md`
**Approved items:** {list the exact finding IDs/titles the user signed off on}
```

### Mandatory short Turkish summary (ELI10 — same rule as `analysis-base-prompt.md`'s)

```
## Kısa Özet (Türkçe — bilgilendirme amaçlı, değerlendirilmez)

{2-4 cümlelik sade özet: ne değiştirildi, hangi onaylı maddeler uygulandı,
doğrulama nasıl yapıldı.}
```

## Standard edit entry format

One entry per approved item applied:

```
### [{ORIGINAL-CATEGORY-ID}] Short finding title (as approved)

- Source finding: `analysis/result/{target_name}/{ai_name}_v{n}.md#{finding-id}`
  {or the evaluation file, if the item came from there}
- Change applied: precise description of what was edited — file, section,
  before → after in one line, or a short diff excerpt
- Verification: how it was confirmed the file/folder is still valid after
  the change (re-opened and read; cross-references checked; rendered/
  syntax-checked) — never "should be fine," state what was actually done
- Deviation from approval: NONE | {if the actual edit differs from what was
  approved in any way, state exactly how and why — this must never happen
  silently}
```

## Process

1. **Confirm the approval list is current.** If time has passed or the
   target changed since approval, re-verify the finding still applies
   before editing — don't apply a stale approval to a file that has since
   moved on.
2. **Apply items one at a time**, in the order listed, writing the Edit
   report entry for each immediately after applying it — not batched at
   the end from memory.
3. **Re-open the edited file/folder** after all approved items are applied
   and confirm: the change is present, nothing outside the approved scope
   changed, and any cross-references (other files' mentions of this
   target's paths, filenames, or section headers) still resolve.
4. **Flag any approved item that could not be applied as approved** —
   because the file changed underneath, the approval was ambiguous, or
   applying it as literally stated would break something the finding
   didn't anticipate. Don't silently apply a different version of it;
   stop and ask.

## Output

Write the edit report to
`analysis/result/{target_name}/edit_{ai_name}_v{n}.md` — see
`.agents/rules/analysis-output.md` for the full naming convention this
extends. The actual file/folder edit itself lands at its real path in the
workspace, per normal editing — this report is the audit trail of what
changed and why, not a copy of the changed content.
