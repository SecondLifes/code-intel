---
name: qdrant-search-quality
description: "Diagnoses and improves Qdrant search relevance. Use when someone reports 'search results are bad', 'wrong results', 'low precision', 'low recall', 'irrelevant matches', 'missing expected results', or asks 'how to improve search quality?', 'which embedding model?', 'should I use hybrid search?', 'should I use reranking?', 'how to measure retrieval quality?', 'build a golden set', 'ground truth dataset', or 'how to score recall@k?'. Also use when search quality degrades after quantization, model change, or data growth."
allowed-tools:
  - Read
  - Grep
  - Glob
---

# Qdrant Search Quality

## Usage

| You say | What happens |
|---|---|
| "Search results are bad/irrelevant" / "which embedding model" / "recall@k" | Check chunk quality first — CodeIntel's own chunker (`src/chunker.py`) already splits at statement boundaries specifically to avoid mid-sentence splits (this skill's own #1 quality killer), so a real regression usually means a chunker bug, not a Qdrant tuning issue. |
| "Should we add reranking / change hybrid fusion?" | This repo already does hybrid dense+sparse with its own weighted RRF fusion in `src/retrieval.py` — **not** Qdrant's built-in RRF query feature this skill assumes. Use its guidance to inform tuning decisions on top of that custom implementation, not as a drop-in Qdrant-side config change. |
| Ambiguous/no specific quality question | Test with exact search first to isolate whether the issue is retrieval or ranking. |

First determine whether the problem is the embedding model, Qdrant configuration, or the query strategy. Most quality issues come from the model or data, not from Qdrant itself. If search quality is low, inspect how chunks are being passed to Qdrant before tuning any parameters. Splitting mid-sentence can drop quality 30-40%.

- Start by testing with exact search to isolate the problem [Search API](https://skills.qdrant.tech/md/documentation/search/search/?s=search-api)


## Diagnosis and Tuning

Isolate the source of quality issues, establish labeled baselines to measure recall and relevance, tune HNSW parameters, and choose the right embedding model. [Diagnosis and Tuning](diagnosis/SKILL.md)


## Search Strategies

Hybrid search, reranking, relevance feedback, and exploration APIs for improving result quality. [Search Strategies](search-strategies/SKILL.md)
