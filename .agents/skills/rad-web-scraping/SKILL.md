---
name: rad-web-scraping
description: General-purpose web scraping / structured data extraction skill — how to discover the most stable data source on a target site (API over DOM), which library to reach for (crawl4AI, ScrapeGraphAI, or plain HTTP), and how to write extraction scripts that survive site redesigns (retries, rate limiting, pagination). Use whenever a task needs data pulled from a website, or LLM/RAG-ready content extracted from arbitrary pages.
---

# Web Scraping / Structured Data Extraction

## When to Use

- Pulling structured data (prices, listings, articles, tables) from a website for a script, pipeline, or dataset.
- Turning arbitrary web pages into clean Markdown/text for an LLM, RAG index, or agent to consume.
- Deciding between a plain HTTP request, a scraping library, and full browser automation for a given target.
- Reviewing or debugging an existing scraper that's fragile or getting blocked.

## Usage

| You say | What happens |
|---|---|
| `"Pull the prices from this site"` / `"Bu siteden ilan verilerini çek"` | Discovery-priority check first (API → embedded JSON → sitemap/feed → DOM as last resort, full order in `references/discovery-and-extraction-patterns.md`), then `references/tool-selection.md`'s decision tree picks the library. |
| `"Turn these pages into clean Markdown for my RAG index"` | Recommends `crawl4AI` (LLM/RAG-ready output) per `references/tool-selection.md`. |
| `"My scraper keeps getting blocked / breaks randomly"` | Reviews against the retry/backoff/rate-limit baseline in `references/discovery-and-extraction-patterns.md` — a scraper missing these isn't hardened, it's incomplete. |
| `"Bypass this CAPTCHA / get around their bot detection"` | Refused — out of scope regardless of phrasing; reasonable retries/rate-limiting are fine, detection evasion is not. |
| A scraping request with no target site/URL named (`"Scrape it"`, `"veriyi çek"`) | Asks what site/data is meant before picking any tool — never guesses a target, and an empty request is never treated as "nothing to do." |

## Golden Rules

- **Discover before you parse.** A REST/GraphQL API, a JSON blob embedded in the page's HTML, or a sitemap/feed is more stable than any CSS selector — always look for one before writing DOM-parsing code. Full priority order: `references/discovery-and-extraction-patterns.md`.
- **Plain HTTP before a browser.** Reach for `httpx`/`requests` first; only escalate to Playwright/browser automation when the target genuinely requires JS execution or session state a plain client can't replicate. A headless browser is slower, heavier, and more fragile than it looks.
- **Pick the tool for the job, not the first one you remember** — `references/tool-selection.md` has a verified decision tree (crawl4AI vs ScrapeGraphAI vs raw HTTP vs Playwright) with install commands, license, and when each wins.
- **Retry, back off, and rate-limit by default.** A scraper with no retry/backoff either gets blocked or silently drops data the first time the network hiccups — this isn't optional hardening, it's baseline correctness for anything hitting a live site repeatedly.
- **Scope and ethics — non-negotiable.** Only scrape data you're legitimately allowed to access; respect `robots.txt` and a site's terms of service. Never write code whose purpose is bypassing CAPTCHAs, defeating bot-detection, or evading paywalls/access controls — that's out of scope for this skill regardless of what's requested, matching this environment's own prohibition on bot-detection bypass. Reasonable technical robustness (retries, realistic headers, rate limiting) is fine; detection *evasion* is not.

Full details, code patterns, and the verified tool comparison are in the reference files below.

## references/

- `tool-selection.md` — decision tree for choosing a scraping approach: `crawl4AI` (LLM-ready Markdown, RAG/agent pipelines), `ScrapeGraphAI` (graph-based extraction pipelines, native MCP server exposure), plain `httpx`/`BeautifulSoup` (simple structured pages), Playwright (JS-heavy/session-gated sites) — with install commands, license, and verified quality signals for each.
- `discovery-and-extraction-patterns.md` — the discovery-priority methodology (API → embedded JSON → platform-specific endpoints → structured markup → DOM parsing as last resort) and extraction script patterns (HTTP client escalation, pagination, retry/backoff, rate limiting, output formats).
