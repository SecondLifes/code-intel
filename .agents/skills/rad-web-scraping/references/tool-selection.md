# Tool Selection

Verified directly (license, stars, maintenance, install method — see
Honesty note at the bottom) before being recommended here. Don't default
to the first library that comes to mind; pick based on the actual shape
of the task.

## Decision tree

1. **Is a plain HTTP request enough?** (the target returns usable JSON/HTML
   without needing JS execution) → use `httpx` + `BeautifulSoup`/`lxml`
   directly. No extra dependency, fastest, least fragile. Most APIs and a
   surprising number of "dynamic-looking" sites qualify — check the
   Network tab for an XHR/fetch call returning JSON before assuming you
   need a browser.

2. **Do you need the result as clean Markdown/text for an LLM, RAG index,
   or agent to consume** (not just structured fields)? → **`crawl4AI`**
   (`unclecode/crawl4AI`).
   - Apache 2.0, 73k+ GitHub stars, actively maintained (v0.9.2 as of
     July 2026).
   - Purpose-built for turning arbitrary pages into "LLM-ready Markdown"
     — structured markdown generation with citation references,
     LLM-driven extraction across providers, intelligent chunking,
     full browser control (proxies, sessions, JS execution) when needed.
   - Install: `pip install -U crawl4ai && crawl4ai-setup` (also ships a
     Docker image for deployment).
   - Default choice for anything RAG/agent-facing — it's the strongest
     verified match for that specific shape of task.

3. **Do you need a graph-based, multi-step extraction pipeline, or native
   MCP server exposure** (an agent calling scraping as a tool over MCP
   rather than a library import)? → **`ScrapeGraphAI`**
   (`ScrapeGraphAI/Scrapegraph-ai`).
   - MIT, 28.5k+ GitHub stars, actively maintained (2,889+ commits,
     latest release v2.1.5 as of July 2026).
   - Uses an LLM plus a graph-logic pipeline to scrape websites *and*
     local documents (XML, HTML, JSON, Markdown) with the same
     interface. Integrates with LangChain, LlamaIndex, Crew.ai.
   - Exposed as an MCP server via Smithery AI — pick this over crawl4AI
     specifically when the consumer needs to call scraping as an MCP
     tool rather than a Python import.
   - Install: `pip install scrapegraphai && playwright install`.

4. **Does the target require real browser behavior** (JS-rendered content
   neither of the above handles well, complex session/cookie state,
   multi-step interaction before data appears) → Playwright directly, via
   crawl4AI's or ScrapeGraphAI's own browser-control features first
   (both wrap Playwright already) before reaching for raw Playwright —
   less code, same capability.

## Evaluated and rejected

Found during evaluation, not recommended:

- **`ScrapingBee/ai-web-scraper`** — hosted/paid API only (requires a
  ScrapingBee account), no self-hosted open-source option. Fine if the
  project already pays for ScrapingBee; not a default recommendation
  since it creates a paid external dependency for what open alternatives
  above solve for free.
- **Low-star personal/demo repos** (e.g. single-digit-to-~20-star
  Streamlit/Selenium/LangChain combo projects found under the
  `web-scraping-ai` GitHub topic) — functional demos, not
  production-grade; the maintained, high-star options above supersede
  them for real use.

## Honesty

Stats above (stars, license, release version/date) were verified via
direct lookup at the time this file was written — re-check before citing
them as current if this file is old, since star counts and latest-release
versions drift.
