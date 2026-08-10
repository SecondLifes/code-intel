# PROMPT PATTERNS — DESIGN-MODE REFERENCE

> v1 — Named prompt structures for building a new prompt from requirements.
> Load on demand. This file is not part of the five-lens identity.

## WHEN TO LOAD

Read this file only in **Design** mode (see WORK MODES in
`prompt-engineer-analyst.md`) — creating a new prompt from requirements.
Analysis, Correction, Optimization, Compression, Refactoring, and Full
Review do not need it.

## SELECTION RULE — read before the catalog

These are structures in common use. They are a menu, not a default, and
none of them is required for a prompt to be good.

- Start with no named structure. Reach for one only when a specific
  requirement calls for it: an expertise frame the model must adopt, a
  reasoning order that must be enforced, an audience the output must be
  pitched to, or a validation step that must not be skipped.
- State which pattern was chosen and why in the Design output's summary
  section. Never apply one silently.
- A prompt that needs no named pattern is a valid result, not a gap.
- Add each section only for a distinct behavioral requirement. Structure
  added to look thorough costs tokens and control without buying either.

This follows the Artifact style rule in `prompt-engineer-analyst.md`:
structural convention is a stylistic assumption to verify against the
target model, never an automatic default. The CORE PRINCIPLE still
governs — the simplest prompt that reliably produces the intended
behavior.

## CATALOG

### RTF — Role, Task, Format
- **Shape:** expert identity → specific action → required output shape.
- **Use when:** the task depends on a particular expertise frame, and the
  output shape is fixed and stateable up front.
- **Avoid when:** the role adds nothing the task statement doesn't already
  imply. A decorative role line is the most common form of wasted prompt.

### Chain of Thought — enforced reasoning order
- **Shape:** problem → named sequential steps → conclusion.
- **Use when:** a wrong intermediate step invalidates the result
  (debugging, derivation, tracing, diagnosis) and the order genuinely
  matters.
- **Avoid when:** the target is a reasoning model that already reasons
  internally — imposing an external step list can constrain rather than
  help. Request the conclusion, the checks, and a concise justification
  instead; never require disclosure of hidden chain-of-thought (see
  MODEL ADAPTATION).

### RISEN — Role, Instructions, Steps, End goal, Narrowing
- **Shape:** RTF plus an explicit end-state and explicit scope limits.
- **Use when:** the work is multi-phase and the main failure risk is scope
  drift or an unstated definition of "done."
- **Avoid when:** scope is already obvious. The Narrowing section is the
  reason to choose this over RTF; without real constraints to state, it
  is RTF with extra headings.

### RODES — Role, Objective, Details, Examples, Sense check
- **Shape:** RISEN's framing plus concrete input details and a closing
  validation criterion.
- **Use when:** the output is a design or proposal that can look complete
  while being wrong, so it needs a stated correctness test.
- **Avoid when:** you cannot name a real sense-check criterion. An empty
  validation step teaches the model that validation is ceremonial.

### Chain of Density — iterative compression
- **Shape:** successive passes, each shorter, each preserving what the
  previous pass established as essential.
- **Use when:** summarizing or compressing, and information loss per pass
  needs to be visible and controllable.
- **Avoid when:** one summary at a stated length would do. The iteration
  is the cost and the point; pay it only when the compression ratio
  matters.

### RACE — Role, Audience, Context, Expectation
- **Shape:** communicator identity → who is being addressed → situation →
  what the audience must know or do.
- **Use when:** the same content must be pitched differently by audience
  (executive vs. engineer), and getting the register wrong is the main
  failure mode.
- **Avoid when:** there is no distinct audience, or the audience is the
  requester. Then it collapses into RTF.

## TASK SHAPE → STARTING STRUCTURE

A starting point for selection, not a lookup table. Verify the choice
against the actual requirement before committing to it.

| Task shape | Start from | What earns the choice |
|---|---|---|
| Needs a specific expertise frame | RTF | The role changes the answer |
| Order of reasoning is load-bearing | Chain of Thought | A wrong step invalidates the result |
| Multi-phase with drift risk | RISEN | There are real constraints to state |
| Design/proposal needing validation | RODES | A concrete sense-check exists |
| Compression with controlled loss | Chain of Density | The ratio matters |
| Same content, different audiences | RACE | Register is the failure mode |
| None of the above | No named pattern | Simplicity is the correct answer |

## COMBINING PATTERNS

Combine only when the task genuinely spans two dimensions that no single
pattern covers — most commonly a framing pattern plus a reasoning
pattern (e.g. RODES for structure and validation, Chain of Thought for
an enforced analysis order).

Rules:
- Two patterns is the practical ceiling. Beyond that, section count grows
  faster than control does.
- Merge overlapping sections rather than repeating them. RODES's Role and
  RTF's Role are the same section, not two.
- State the combination and its justification in the design summary, the
  same as a single pattern.

## PRE-DELIVERY CHECKS

Applied in addition to the REVISION RULES delivery checks in
`prompt-engineer-analyst.md`, not instead of them:

- **Self-containment** — everything the prompt depends on is either stated
  in it or explicitly named as a required input. A prompt that silently
  inherits context from the conversation that produced it breaks the
  moment it is used anywhere else.
- **Every section earns its place** — each one carries a behavioral
  requirement that would be lost if removed. If a section can be deleted
  without changing expected behavior, delete it.
- **Structural weight matches task complexity** — a simple task gets a
  short, lightly-structured prompt.

## WHAT THIS FILE IS NOT

Not a claim that structured prompts outperform unstructured ones in
general — that depends on the target model and the task, and is a
prediction to verify, not a settled result. These patterns are named,
reusable shapes for recurring requirements. Choosing none of them is a
supported outcome.
