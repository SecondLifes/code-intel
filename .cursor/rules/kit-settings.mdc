# Kit Settings (`settings.json`) — Rules

Every kit ships a `settings.json` at its own root (next to `AGENTS.md`,
`README.md`) — **committed to git**, unlike `analysis/` (gitignored,
local-only). Think of it like a `package.json`'s `version` field: it is
this repo's own source of truth for its own operational state, not a
shared cross-kit file like the workspace root's `template-vars.json`
(which holds identity/legal values substituted once at kit-creation
time and never touched again).

## Current schema

```json
{
  "$comment": "Per-kit operational settings — committed to git. Extend with new top-level keys as needs arise; document each addition here and in this file's own $comment.",
  "versioning": {
    "scheme": "semver",
    "current_version": "0.1.0"
  }
}
```

- **`versioning.current_version`** — this kit's current released version.
  This is the value the fix-publication workflow reads before tagging
  and writes back after bumping — see
  `.agents/skills/rad-prompt-studio/references/prompts/edit-base-prompt.md`'s
  Golden Rule 7. The annotated git tag (`vMAJOR.MINOR.PATCH`) must always
  match this value; if they ever disagree, `settings.json` is correct
  and the tag needs to catch up (or vice versa if a tag was created
  without updating this file — audit which one is stale from the actual
  git tag list and the CHANGELOG, don't guess).
- **`versioning.scheme`** — currently always `"semver"`. Present so a
  future non-semver kit isn't forced into the wrong assumption silently.

## Extensibility

This file is deliberately small today and expected to grow — new
top-level keys get added here as real needs arise (the workspace owner
described this explicitly: "ileride çok genişletilebilir"). When adding a
new key:

1. Document it in this rule file (schema + meaning) before or alongside
   introducing it in code/workflow.
2. Keep it kit-local operational state — identity/legal/contributor data
   still belongs in the workspace root's `template-vars.json`, not here.
3. Never store secrets (API keys, tokens, credentials) in this file — it
   is committed and public once the kit is published.

## Where it's read/written

- **`rad-template-builder`** seeds a new kit's `settings.json` from
  `blank-scaffold`'s default (or, in Derivation Mode, resets
  `current_version` to a fresh baseline rather than inheriting the base
  kit's version — a derived kit starts its own version history).
- **The fix-publication workflow** (edit-base-prompt Golden Rule 7) reads
  `current_version`, computes the bump (PATCH for fixes, MINOR for added
  capabilities, MAJOR for breaking changes), writes the new value back,
  commits it, and only then creates the matching git tag.
- **Any kit-local tooling** (a future `update.bat` successor, CI, etc.)
  may read this file instead of re-deriving the version from git tags.
