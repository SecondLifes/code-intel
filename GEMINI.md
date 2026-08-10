# CodeIntel AI Spec-Kit — Gemini CLI / Antigravity Context

Gemini CLI builds its context from a hierarchy of `GEMINI.md` files — the
global `~/.gemini/GEMINI.md`, then every `GEMINI.md` from the working
directory up to the project root. It does **not** read
`.gemini/rules/project-rules.md` on its own; that file is this kit's
hand-authored Gemini summary, and this file is what actually puts it in
front of the model.

Nothing is duplicated here. The import below pulls in the real content, so
`.gemini/rules/project-rules.md` stays the single place it is edited.

@./.gemini/rules/project-rules.md

## Also binding

The universal, tool-independent rules live in `AGENTS.md`, and the
per-topic rules in `.agents/rules/*.md`. Read them when the task they
govern comes up — they are as binding here as they are for any other tool
this kit supports.

> **Why this file exists:** this kit shipped a
> `.gemini/rules/project-rules.md` and an AI-tool table naming it as
> Gemini's source, but no `GEMINI.md` anywhere and no `context.fileName`
> override in a `.gemini/settings.json` — so Gemini CLI loaded none of it.
> Verified against `geminicli.com/docs/cli/gemini-md`. The alternative fix
> is a `.gemini/settings.json` with
> `{"context": {"fileName": ["GEMINI.md", "AGENTS.md"]}}`; this file was
> chosen instead because it works with no configuration at all.
