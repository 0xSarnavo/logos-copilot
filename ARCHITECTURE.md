# Architecture

```
   IDE / AGENTS (Claude, Cursor, VS Code) ─── MCP (Streamable HTTP)
                       │
 ┌─────────────────────▼──────── SERVING (logos_copilot/server.py · FastMCP) ───────────────┐
 │  logos_resolve_component · logos_search_docs · logos_get_api_signature · logos_status     │
 │  every result: structuredContent + citation{repo,path,lines,git_sha,url,indexed_at}       │
 └─────────────────────┬─────────────────────────────────────────────────────────────────---┘
                       ▼  retrieve.py: dense(pgvector <=>) top50 + BM25(websearch) top50 → RRF
 ┌──────────────── KNOWLEDGE BASE · Postgres + pgvector (db/schema.sql) ─────────────────────┐
 │  components (rename/alias map)      chunks (content, embedding vector, tsv, provenance,    │
 │                                     version, deprecated, content_hash, indexed_at, …)      │
 └─────────────────────▲─────────────────────────────────────────────────────────────────---┘
                       │  ingest.py: clone → chunk → content-hash gate → embed changed → upsert
 ┌──────────────── FRESHNESS / DISCOVERY (scrape.py) ────────────────────────────────────────┐
 │  gh org enumerate → filter(!archived, !fork, pushed≤365d) → classify → sources.generated   │
 │  refresh.py: per-repo SHA compare → re-index only if changed → tombstone vanished files;   │
 │  reconcile retires dropped repos; rediscover (nightly) re-scrapes + refreshes all;         │
 │  repo_state tracks last_sha/last_indexed/status; webhook.py: HMAC verify → real-time push  │
 └───────────────────────────────────────────────────────────────────────────────────────---─┘
```

## Modules
| File | Responsibility |
|---|---|
| `config.py` | env-driven settings (stdlib dataclass, no pydantic) |
| `scrape.py` | org-wide repo discovery + classify + **1-yr/archived/fork filter** → `sources.generated.yaml` |
| `registry.py` | component rename/alias map (Nomos→logos-blockchain, …) + `resolve()` |
| `chunk.py` | markdown/code chunking + content hashing |
| `embedder.py` | `Embedder` protocol + Hash (default) / FastEmbed / Voyage; `get_embedder()` |
| `db.py` | pg8000 connect + dict rows + `vec_literal` |
| `ingest.py` | clone → collect (skips deprecated/legacy paths) → content-hash upsert; seeds alias map |
| `retrieve.py` | hybrid dense+BM25 → RRF; `citation()` |
| `guides.py` | curated 'guide'/'recipe' knowledge (logos-ai-skills + hand-authored recipes) |
| `symbols.py` | regex symbol/signature index → exact `get_api_signature` (lookup_symbol) |
| `scaffold.py` | safe allowlisted wrapper around the `lgs` (logos-co/scaffold) CLI |
| `doctest_runner.py` | `verify_snippet` — runs code through logos-doctest (serve only code that runs) |
| `refresh.py` | freshness engine — SHA-based change detection, tombstoning, reconcile, rediscover, freshness |
| `webhook.py` | GitHub webhook HMAC verify + event→repo parsing (real-time refresh) |
| `migrate.py` | idempotent schema migrations (repo-scoping + repo_state + feedback) |
| `feedback.py` | feedback store + stats/gaps (explicit signal for the eval loop) |
| `web.py` | thin human web playground (Starlette): search + freshness + 👍/👎, XSS-hardened |
| `auth.py` | pure-ASGI bearer auth + per-IP token-bucket rate-limit (SSE-safe) |
| `eval.py` | golden-set retrieval eval (Hit@k/MRR) + CI gate |
| `gaps.py` | gap detection from feedback (under-covered down-votes → ingestion candidates) |
| `ci_snippets.py` | extract + run doc/recipe code blocks through logos-doctest (snippet gate) |
| `server.py` | FastMCP tools over Streamable HTTP (15 tools); auth+rate-limit wrap in main() |

## Key decisions
- **pg8000 + `'[...]'::vector` literals** — pure-Python driver installs on any Python (incl. 3.14),
  no adapter dependency. Confirmed paramstyle `format` (`%s`).
- **Hash embedder default** — keeps the whole pipeline runnable with zero ML wheels; BM25 supplies
  real keyword relevance. Production swaps to Voyage/fastembed via one env var (+ re-embed).
- **Hybrid + RRF** — BM25 catches exact tokens (function names, CIDs, flags) dense search misses.
- **Freshness is structural** — the 1-yr/archived/fork filter lives in the scraper and is unit-tested;
  every chunk carries `indexed_at`; `logos_status` exposes coverage.
- **Deprecated never served** — `ingest.py` prunes `deprecated/legacy/archive/old` dirs and paths
  (regression-tested) so stale APIs can't surface.
- **Reuse** — scaffolding (`lgs`), executable-docs (`logos-doctest`), and guides (`logos-ai-skills`)
  are wrapped/ingested in later phases, not rebuilt.

## Data flow (self-update)
`scrape` refreshes the repo set → `ingest` re-clones and the **content-hash gate** re-embeds only
changed chunks (cheap re-runs) → unchanged chunks just bump `last_seen`. Phase 3 adds webhooks,
tombstone-on-missing + nightly reconciliation, and a public freshness/status page.

## Roadmap
**Phase 0–5 complete ✅** — scrape/ingest/retrieve/serve; `lgs` wrapper; ai-skills guides; recipes;
symbol index; `verify_snippet`; freshness engine; web playground + feedback; eval/CI gate + gap
detection + bearer-auth/rate-limit + MCP Registry manifest. Every phase passed an adversarial review.
Future: managed embeddings (Voyage) for semantic quality, OAuth 2.1 (vs static bearer), Redis-backed
rate-limit for multi-node, live node/on-chain data tools. See [PRD.md](PRD.md).
