---
name: python
description: General-purpose Python engineering skill — profiling/performance optimization, pytest-based testing (fixtures, mocking, async, property-based), and design principles (SRP, composition over inheritance, dependency injection). Use whenever writing, reviewing, testing, or optimizing Python code, including ad-hoc scripts written to accomplish a task in this workspace.
---

# Python

Consolidated from three separately-sourced skills (`wshobson/agents`:
`python-performance-optimization`, `python-testing-patterns`,
`python-design-patterns` — reviewed for correctness, no issues found)
into one, per this workspace's "one skill per topic" policy.

## When to Use

- Writing an ad-hoc Python script to accomplish a task (data processing, file manipulation, automation, validation)
- Identifying and fixing performance bottlenecks (CPU, memory, I/O)
- Writing or reviewing tests (unit, integration, async, property-based)
- Designing a new component/service or refactoring a tangled one
- Deciding between inheritance and composition, or whether to add an abstraction

## Usage

| You say | What happens |
|---|---|
| `"Write a script to parse these CSVs"` / ad-hoc helper script request | Applies the Golden Rules directly (simplicity first, single responsibility) — no reference file needed for a small script. |
| `"This function is slow, why?"` / `"Bu kodu optimize et"` | Loads `references/performance.md` — profiles with `cProfile`/`py-spy` first, then applies the matching optimization pattern. |
| `"Write tests for this"` / `"Şunun için pytest yaz"` | Loads `references/testing.md` — fixtures, mocking, async tests, property-based testing as the case requires. |
| `"Refactor this class"` / `"Composition mi inheritance mi kullanmalıyım?"` | Loads `references/design-patterns.md` — SRP, composition-over-inheritance, Rule of Three, dependency injection. |

## Golden Rules

- **Profile before optimizing.** Measure with `cProfile`/`py-spy` first — don't guess at bottlenecks.
- **Simplicity first (KISS).** Choose the simplest solution that works; complexity must be justified by concrete requirements.
- **Single Responsibility.** Each function/class has one reason to change — separate HTTP parsing, business logic, and data access.
- **Compose, don't inherit** for flexibility and testability; **inject dependencies** through constructors.
- **Rule of Three** — don't abstract until you have three real instances of the duplication; a wrong abstraction is worse than repetition.
- **Test in isolation.** Fakes/mocks for external dependencies; never hit a real database in unit tests.
- **Use built-ins and generators** for large datasets; prefer `dict`/`set` lookups over list scans.

Full details, code, and worked examples for each area are in the reference files below — read the one that matches the task at hand rather than guessing.

## references/

- `performance.md` — profiling tools (cProfile, line_profiler, memory_profiler, py-spy), optimization patterns (comprehensions, generators, caching, `__slots__`, multiprocessing, async I/O), database/memory optimization, benchmarking, common pitfalls.
- `testing.md` — pytest fundamentals, fixtures/conftest, mocking, monkeypatching, async tests, property-based testing (Hypothesis), database testing, CI/CD integration, coverage configuration.
- `design-patterns.md` — KISS, SRP, separation of concerns, composition over inheritance, Rule of Three, dependency injection, common anti-patterns, troubleshooting guide.
