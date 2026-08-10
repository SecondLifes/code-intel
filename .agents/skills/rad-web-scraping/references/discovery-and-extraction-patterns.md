# Discovery & Extraction Patterns

Two phases: find the most stable way to access the data (Discovery), then
write an extractor that keeps working when the site changes (Extraction).
Skipping straight to DOM/CSS-selector parsing is the single biggest reason
scrapers break the next time a target redesigns its frontend.

## Phase 1 — Discovery (most to least stable)

Work down this list; stop at the first one that actually returns the data
you need. Each step down is more brittle than the last.

1. **A documented REST/GraphQL API.** Check for official API docs first —
   many sites that "need scraping" already expose one.
2. **An undocumented API found via network inspection.** Open the
   browser's Network tab, reload the page, and look for an XHR/fetch call
   returning JSON — most modern sites fetch their own content this way
   even without a public API. This is usually more stable than parsing
   the rendered HTML, since the JSON shape changes less often than CSS
   classes/markup structure.
3. **Server-rendered JSON embedded in the HTML** (a `<script>` tag with
   `window.__INITIAL_STATE__`, `__NEXT_DATA__`, or similar) — common in
   React/Next.js/Vue apps that server-render for SEO. Parse the JSON
   directly instead of the surrounding HTML.
4. **Platform-specific APIs** — WordPress (`/wp-json/`), Shopify
   (`/products.json`), and similar platforms expose predictable JSON
   endpoints once you know the platform underneath.
5. **Structured data markup** — JSON-LD (`<script type="application/ld+json">`)
   or `schema.org` microdata, when present, gives semantically labeled
   fields without any selector guessing.
6. **DOM parsing (last resort).** Only when none of the above exist.
   Prefer stable attributes (`data-testid`, `id`) over class names when
   selecting elements — class names churn with every styling change,
   `data-*` test hooks usually don't.

## Phase 2 — Extraction script patterns

### HTTP client escalation

Start cheap, escalate only when the cheaper option actually fails:

1. `httpx` (or `requests`) — works for the large majority of API/JSON
   targets from Phase 1.
2. `curl_cffi` — mimics real browser TLS fingerprints. **Scope is
   narrow and matches `SKILL.md`'s Golden Rules:** a site blocking your
   client based on its TLS/HTTP fingerprint is a bot-detection decision,
   and defeating it on a live third-party site is detection evasion —
   out of scope regardless of phrasing. Reach for `curl_cffi` only for
   client-compatibility issues in an environment you own or are
   explicitly authorized to test (your own service, a staging target, a
   documented pentest engagement) — never to get a blocked scraper back
   onto someone else's site.
3. Playwright (directly, or via crawl4AI/ScrapeGraphAI's built-in browser
   control — see `tool-selection.md`) — only when the data genuinely
   doesn't exist until JS runs.

### Pagination

Prefer an explicit `next` link/cursor/offset field from an API response
over inferring page count from the UI. When only page numbers are
available, loop until a page returns zero new items rather than a
hardcoded page limit — sites add/remove pages over time.

### Retry and backoff

Every request that can fail over a real network needs a bounded retry
with exponential backoff (e.g. `httpx` + `tenacity`, or crawl4AI/
ScrapeGraphAI's own built-in retry handling). Distinguish retryable
failures (timeouts, 429, 5xx) from ones that shouldn't retry (401, 403,
404 — retrying these just wastes time and looks more like abuse to the
target).

### Rate limiting

Throttle request rate deliberately (a fixed delay or a token-bucket
limiter) rather than firing requests as fast as the client can — this is
both good citizenship toward the target site and the single most common
reason a "working" scraper starts getting blocked under real load. Respect
any `Retry-After` header the server sends.

### Output formats

Match the format to the consumer: JSONL for streaming/large datasets
(one record per line, easy to resume), CSV for spreadsheet/BI consumption,
Parquet for large structured datasets headed into a data pipeline, or
directly into a database when the extraction is part of a larger service.
Don't default to a single format without checking what downstream actually
needs.
