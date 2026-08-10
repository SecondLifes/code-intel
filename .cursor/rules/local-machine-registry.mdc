# The `.rad` Hub — Single Machine-Wide Root, One JSON File, Live Reference

One root, `%ProgramData%\rad` (Windows) / `/usr/local/share/rad`. Outside
every repo, never committed, never published. Holds a single
`settings.json`, `skills\` (the categorized link farm), and a handful of
convenience links (`rad.ps1`, `workspace`, `tools`, `rules`, `prompts`,
`analysis`, `spec-kits\`) — every one of them a **live link**, never a
copy, into the registered workspace's own files. Nothing under the hub
root is a primary source; the workspace is.

**One JSON file, not two.** An earlier design split machine-wide facts
(which workspace, which kits) and personal settings into
`registry.json` + `settings.json`. There was no real reason for the
split — `settings.json` alone now holds both.

**Live reference, not publish-and-copy.** `rules\`, `prompts\` and
`analysis\` under the hub root are not populated by copying files — they
are single links straight into the workspace's own `share\rules\`,
`share\prompts\` and `share\analysis\`. Reading through the hub link and
reading the workspace's `share\` folder directly are the same files. If
the workspace's real path is ever unreachable, the correct response is
"workspace unreachable, cannot resolve" — never a guess and never a
silently stale fallback copy from some earlier "publish" step, because
there is no publish step anymore.

Built and maintained by `tools/rad.ps1` in the AI-Spec-Kits-Maker
workspace. Idempotent, needs no elevation.

**A missing hub root is never fatal.** It means cross-kit references and
shared rules are unavailable on this machine — say so plainly and point at
`pwsh tools/rad.ps1 -Action Install`; never guess the content that would
have been there.

## `settings.json` — the shared source of truth

```json
{
  "schema_version": 3,
  "updated": "2026-07-31 08:16",
  "updated_by": "user@MACHINE",
  "root": "E:\\...\\AI-Spec-Kits-Maker",
  "last_bootstrap": { "date": "...", "machine": "..." },
  "kits": {
    "erp-muhasebe-temel": {
      "path": "E:\\...\\spec-kits\\erp-muhasebe-temel",
      "registered_at": "...", "registered_by": "...", "machine": "..."
    }
  }
}
```

- **`root`** — the registered workspace's own path. Every other shared
  path (`rules`, `prompts`, `analysis`, `skills`) is **derived** from this
  one fact (`root\share\rules`, `root\share\prompts`, `root\share\
  analysis`, `root\.claude\skills` or `root\.agents\skills`) — there is no
  separate `shared` block duplicating them, because a duplicate is just
  another thing that can drift.
- **`kits`** — one entry per registered kit, keyed by its registry name
  (never the literal folder name of the workspace or the kits folder —
  those can be renamed; the registry key must not silently go stale when
  they are).
- Any other top-level key is personal/opaque machine state (see "Stack
  keys" below) — coexists with `root`/`kits` in the same file without
  conflict.

**This file is authoritative; the convenience links under the hub root are
not.** Resolve every path through it. A link that is missing or broken is
a cosmetic problem, never a reason to report a kit as unavailable — check
`settings.json` before concluding anything.

Writes are serialized by a lock file and committed by temp-file rename, so
concurrent registrations cannot corrupt or silently overwrite each other.
Never hand-edit `settings.json`; run the scripts.

## Shared rules — read them, they are not optional

`root\share\rules\` holds rules that apply to **every** kit on this
machine (commit/versioning discipline, cross-kit reference resolution,
and whatever else the workspace keeps there). Read them at the start of
any task they govern — they are as binding as this kit's own
`.agents/rules/`, and they are deliberately **not** copied into the kit,
so an edit in the workspace takes effect everywhere immediately, with no
publish or re-install step required.

## Referencing another kit

This kit declares what it borrows in its own root `settings.json` (this
kit's own file, at its own repo root — a different file from the hub's
`%ProgramData%\rad\settings.json`, same name, different job):

```json
"references": [
  { "kit": "erp-muhasebe-temel",
    "reason": "Shared PostgreSQL schema and accounting vocabulary",
    "paths": [".agents/rules/db-schema.md"] }
]
```

Resolve `kit` → the hub's `settings.json` → `kits.<name>.path`, then read
the listed paths under it. Full procedure, failure handling and the
copy-vs-reference decision table: the workspace's
`share\rules\cross-kit-reference.md`.

**Never hardcode another kit's filesystem path** in this kit's files. The
name goes in this kit's own `settings.json`; the path lives only in the
hub's `settings.json`.

## Registering this kit

This kit carries no registration logic of its own — it only knows how to
find and call the workspace's own script, through the hub root's symlink:

```batch
tools\register.bat                    :: register under this folder's own name
tools\register.bat -Name my-kit       :: register under an explicit name
tools\register.bat -Unregister        :: remove the entry
```

`register.bat` checks for `%ProgramData%\rad\rad.ps1` first — if the hub
isn't installed on this machine, it says so plainly (`Hub kurulu değil.`)
and stops; it never tries to register anywhere else.

Re-run it after moving or re-cloning the kit — a registration pointing at
a path that no longer exists is reported as `STALE REGISTRATION` by
`rad.ps1 -Action Verify`.

## Stack keys in the hub's `settings.json`

```json
"delphi": {
  "installs": ["37", "14"],
  "sources": { "global": ["c:\\01\\git\\opensource"], "TMS": "c:\\01\\TMS" }
}
```

`installs` is an **opaque list** — never interpret the values as product
versions unless the user defines them in that conversation. `sources`
registers directories holding actually-installed library/vendor source:
when a library topic comes up, search these and **read the real installed
source** before reaching for the web, citing the file path read. Missing
file or missing key means skip silently — it is optional infrastructure.

Never store secrets in the hub root — paths and opaque markers only.

## `analysis\` — a single machine's work product, not a permanent archive

`root\share\analysis\{repo}\{target}\{ai_name}_v{n}.md` holds analysis
reports (reachable through the hub's `analysis\` link too — same files).
Filenames carry no per-user segment, so on a machine with more than one
user, two people running the same analysis at the same time can collide on
the same filename — accepted as out of scope for this tool, since the hub
targets a single-developer machine. The retention rule in
`analysis-output.md` (a resolved finding's report gets deleted once the
fix lands, git history becomes the permanent record) already keeps this
folder from growing into something that would need backing up. Because it
lives inside the workspace's own folder tree now, the workspace's
`.gitignore` excludes it — it is real, useful, work-in-progress data, but
never meant to be committed.

## Disciplines (AI-binding)

1. **Never `rm -rf` anything under the hub root.** Removing links is
   `rad.ps1 -Action Clean`'s job (it deletes reparse points without
   recursing). A recursive delete pushed through a link destroys real
   repo files.
2. **No destructive git through a link.** A git command run inside
   `.rad\spec-kits\<kit>` operates on the real repo — there is no sandbox
   copy. Know which repo you are really in.
3. **Repair = rebuild — but only for links, not for `settings.json`
   itself.** Broken or suspect links are never fixed by hand:
   `-Action Install` (idempotent), or `Clean` then `Install`. Every link
   under the hub root resolves back to a git-tracked repo or the
   workspace's own `share\` folder, so losing the links alone costs
   nothing. `settings.json` itself is different: `-Action Install` only
   ever sets `root`/`last_bootstrap` and preserves whatever `kits` and
   personal keys already exist — it does **not** rediscover or
   re-register kits on its own. If `settings.json` is deleted (not just
   the links), every kit's registration is gone until each one re-runs
   its own `tools\register.bat`, and any personal top-level keys (stack
   install paths, etc.) are gone for good unless you'd written them down
   elsewhere. Treat `settings.json` itself, not the links around it, as
   the one thing in the hub root actually worth being careful with.
4. **`-Action Push` is user-invoked.** AIs commit; the user publishes.
