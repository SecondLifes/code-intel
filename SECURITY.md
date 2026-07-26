# Security Policy

## Supported Versions

CodeIntel is a locally-run tool (single FastAPI process + Qdrant + Ollama) without a formal release train yet. We currently support and provide fixes for:

| Version | Supported          |
| ------- | ------------------ |
| Latest (`main`) | :white_check_mark: |
| Older tags | :x: |

## Threat Model (read this before reporting)

CodeIntel binds to `127.0.0.1` by default and treats localhost as fully trusted. It can optionally be exposed to a LAN (Settings → API Keys, role-separated `read`/`admin` keys) for MCP access from another machine — this is the only mode where the items below matter to someone other than the operator running it:

- **Admin-prefixed endpoints** (`/api/collection/*`, `/api/index/start`, `/api/duplicates/start`, `/api/backup/run`, `/api/symbols/rebuild`, `/api/profile`, `/api/owners`, `/api/groups`, `/api/apikeys`, `/api/git-update-all`, `/api/index/migrate-ids`, `/api/manual/build`, `/api/manual/translate`) require `role=admin` or `localhost` from a non-local caller.
- **Chat endpoints** (`/api/ask`, `/api/ask/stream`, `/api/research/stream`, `/api/compare`) accept an optional `ollama_url` override, honored **only** for `localhost` or `role=admin` callers — a `read`-role remote key cannot redirect the server's outbound LLM calls (fixed 2026-07-25 after an external security review found this was previously unrestricted — see `git log --grep=SSRF`).
- Rate limiting (300 req/10s per client) and an admin write-audit log (`logs/admin-audit.log`) apply to all non-local traffic.

Known accepted limitations for a single-operator local tool (not currently treated as vulnerabilities on their own): no TLS on the LAN listener, no CSRF tokens (same-origin API-key model instead), collection import trusts the uploader's gzip/JSONL content once decompressed within logged size limits.

## Reporting a Vulnerability

If you find a security vulnerability — an endpoint that bypasses the role/localhost check above, a path traversal, an injection (SQL/command/prompt), a stored-XSS in the search/settings/manual UI, or a way to make the server issue an unintended outbound request (SSRF) — please report it via **[FILL IN: repo URL]/issues** using the `security` label, or privately at **baspinar99@gmail.com or emr.pov@gmail.com** if the issue shouldn't be public yet.

Please include:

* A description of the vulnerability.
* A proof of concept or steps to reproduce.
* Potential impact.

We will acknowledge your report within 48 hours and provide a timeline for a fix if applicable.
