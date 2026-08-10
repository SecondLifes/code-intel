# Testing — Rules

`pytest` is the only test framework. Everything below is the real,
observed discipline of this repository, verified against `pytest.ini` and
the actual suite — not generic advice.

## The two-tier split (non-negotiable)

```
tests/            ← default `pytest` run — NO real external services
tests/manual/     ← needs a real GPU / Ollama / Qdrant — EXCLUDED from the default run
```

`pytest.ini` enforces this:

```ini
[pytest]
testpaths = tests
norecursedirs = tests/manual .venv .git __pycache__
```

- A test that needs a running Qdrant, a loaded Ollama model, or actual GPU
  hardware belongs in `tests/manual/` — putting it in `tests/` breaks the
  default run for everyone who doesn't have that hardware up.
- Conversely, a test that needs nothing external belongs in `tests/`, where
  it actually runs. Don't park a self-contained test in `tests/manual/`
  where nobody executes it.
- `tests/manual/` is run explicitly and individually when the hardware and
  services are available — it is never expected to pass in a bare checkout.

## Naming — the name states the locked-in behavior

`test_<behavior_under_test>`, not `test_<function_name>`. The name should
say what regression it prevents:

```python
# Good — the real convention (tests/test_chunker.py)
def test_line_shift_does_not_change_chunk_id(tmp_path):
    """KRİTİK regresyon: bir chunk'ın ÜSTÜNE satır eklemek, içeriği aynı kalan
    chunk'ların ID'sini DEĞİŞTİRMEMELİ (satır no ID'ye katılmıyor olmalı)."""

# Weak — names the function, not the behavior
def test_chunk_file():
```

Docstrings in tests follow the codebase-wide convention: **Turkish**, and
they state *why the test exists* (which bug it locks out), not what the
code does.

## Self-contained fixtures, no external files

Tests build their own inputs — `tmp_path` plus inline source snippets
defined as module-level constants in the test file itself (see
`tests/test_chunker.py`'s `OVERLOADED_CLASS`). A test in `tests/` must not
depend on a path outside the repo, a network call, a pre-existing Qdrant
collection, or a model download.

## Contract tests are safety nets, not chores

`tests/test_api.py::test_mcp_rest_parity` verifies that every MCP tool has
its matching `/api/mcp/*` REST endpoint. **This parity is structural, not
manual** — the `@tool` decorator in `src/mcp_server.py` registers with both
FastMCP and the `TOOLS` dict, and `src/api/mcp_routes.py` loops over that
dict to generate the endpoints. The test exists to catch someone bypassing
`@tool` (e.g. using raw `mcp.tool()`), not to be satisfied by hand.

Treat any other contract test the same way: it encodes an invariant the
architecture already guarantees, so a failure means the architecture was
bypassed — fix the bypass, don't patch the test.

## When a fix requires a test

Every bug fixed in the chunker, retrieval, or an API contract gets a
regression test in `tests/` **named after the bug's symptom**. This is how
`test_chunker.py` grew: each test is a bug that once shipped. A fix with no
test is an invitation for the same bug to return silently.

## Running

```bash
pytest                       # default suite (tests/, excludes tests/manual/)
pytest tests/manual/test_gpu.py -v   # a single manual test, hardware present
```

No coverage threshold is enforced. Don't add one without agreeing on it
first — an arbitrary gate on a suite this shaped produces busywork, not
safety.
