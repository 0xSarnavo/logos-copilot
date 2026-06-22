# Logos Copilot

A self-updating **MCP + RAG** knowledge server for the Logos ecosystem. It scrapes the whole Logos
GitHub (auto-skipping anything not pushed in the last year), indexes docs/specs/code into Postgres +
pgvector, and serves **cited, version-pinned, freshness-stamped** answers to any agent over MCP —
so external developers' own agents (Claude, Cursor, VS Code, custom) can build on Logos correctly.

> Status: **Phase 0–5 complete.** Scrape → ingest → hybrid retrieve → MCP serving (Ph 0–1); BUILD
> `lgs` wrapper + ai-skills guides + recipes, CODE symbol index + `verify_snippet` (Ph 2); freshness
> engine (Ph 3); human web playground + feedback (Ph 4); **eval/CI gate, gap detection, bearer auth +
> rate-limit, MCP Registry manifest (Ph 5)**. **15 MCP tools, 54 tests.** Every phase passed an
> adversarial-review pass; see [PRD.md](PRD.md).

Not affiliated with the Logos / IFT core team. See [reuse](#reuse-not-rebuild).

## What works today (verified)
- **Org scrape with a 1-year freshness filter:** scanned 351 repos across 4 orgs → kept 241,
  dropped 26 as >1-yr stale, 21 archived, 38 forks. Invariant enforced: nothing older than 365 days.
- **Ingestion → pgvector** with content-hash skip-if-unchanged + a deprecated/legacy path filter.
- **Hybrid retrieval** (dense pgvector + BM25 full-text, fused with RRF), every result cited.
- **MCP server** (FastMCP, Streamable HTTP) — `initialize` handshake returns 200; tools callable
  in-memory and over HTTP.
- **Phase 2 BUILD:** `logos-ai-skills` → 359 cited `guide` chunks (52 guides); 3 cross-component
  `recipe`s; `lgs` scaffold CLI wrapped as allowlisted MCP tools (`deploy` correctly rejected;
  graceful when absent).
- **Phase 2 CODE:** symbol index (36+ signatures from one repo) backs exact `get_api_signature`;
  `verify_snippet` runs code through `logos-doctest` (passing → ok, failing/unmet-assert → not ok).
- **Phase 3 freshness:** per-repo SHA change-detection (re-index only changed repos; second run =
  "unchanged" cheap-skip), repo-scoped storage, tombstoning of vanished files, `reconcile` retiring
  dropped repos, nightly `rediscover`, GitHub webhook HMAC handler, `logos_freshness` SLA surface.
- **Phase 4 UX:** a thin human web playground (`logos_copilot.web`) — search → cited results stamped
  with how fresh the knowledge is, a coverage badge, and 👍/👎 feedback (XSS-hardened render).
- **Phase 5 evolve loop:** golden-set retrieval eval + CI gate (`make eval`, hit@8≈0.8), gap detection
  from feedback, `logos-doctest` snippet CI gate, bearer auth + per-IP rate-limit middleware, and an
  MCP Registry `server.json`.
- **54 unit tests green** + live integration verified across all 15 tools (eval gate PASS, auth 401→200).

## MCP tools (Phase 1)
| Tool | Does |
|---|---|
| `logos_resolve_component(name)` | maps Nomos/Codex/Waku → current repo, warns on legacy names |
| `logos_search_docs(query, component?, kind?, top_k)` | hybrid search → cited, freshness-stamped chunks |
| `logos_get_api_signature(component, symbol)` | exact match from the **symbol index** (OpenAPI + code), then retrieval fallback — grounded, not invented |
| `logos_status()` | per-component coverage + indexed-at (freshness surface) |
| `logos_freshness(stale_hours?)` | per-component active/retired repos + staleness SLA (self-update engine) |
| `logos_submit_feedback(query, rating, ...)` | record 👍/👎 feedback (seeds gap detection / eval loop) |
| `logos_gaps()` | down-voted + under-covered queries → ingestion candidates (self-evolve loop) |
| `logos_list_guides()` / `logos_get_guide(slug)` | curated build guides ingested from `logos-ai-skills` |
| `logos_list_recipes()` / `logos_get_recipe(slug)` | curated cross-component INTEGRATE recipes (Codex+Waku, run-a-node, scaffold-LEZ) |
| `logos_scaffold_status()` / `logos_scaffold(action,name?)` | wraps the `lgs` CLI (allowlisted: version/help/create/new/init/doctor/build/localnet_status) |
| `logos_verify_status()` / `logos_verify_snippet(language,code)` | run a snippet via `logos-doctest` — serve only code that actually runs |

## Quickstart (local, $0)
```bash
make install        # venv + deps (pg8000, fastmcp, pyyaml, httpx, pytest)
make test           # 18 unit tests
make db-up          # pgvector in Docker (host port 5433)
make scrape         # crawl Logos orgs -> sources.generated.yaml (1yr filter)
make e2e            # seed alias map + ingest a few core repos
make serve          # MCP at http://localhost:8000/mcp
```
Point any MCP client at `http://localhost:8000/mcp`.

The default embedder is a deps-free deterministic `HashEmbedder` (so it runs anywhere); BM25 carries
keyword relevance. For semantic quality set `EMBEDDER=voyage` (+ `VOYAGE_API_KEY`, `EMBED_DIM=1024`,
update the schema vector dim) or `EMBEDDER=fastembed`.

## Layout
```
logos_copilot/  config scrape registry chunk embedder db ingest retrieve server
db/schema.sql   pgvector schema (components alias map + chunks)
tests/          unit tests (pure logic) + filter regression
docker-compose.yml Dockerfile Caddyfile   deploy stack
PRD.md SPEC.md ARCHITECTURE.md DEPLOYMENT.md
```

## Reuse, not rebuild
Logos already ships pieces we **wrap/ingest** instead of duplicating: `logos-co/scaffold` (`lgs`,
project bootstrap), `logos-co/logos-doctest` (runnable-snippet gate), `logos-co/logos-ai-skills`
(builder guides + eval fixtures), `logos-co/logos-rag` (their source map). This project builds the
missing layer: the **public MCP + RAG serving + freshness + eval** engine. Coordinate with
`weboko` (ai-skills/scaffold) and `corpetty` (logos-rag) before extending into BUILD.

## Deploy
Free always-on path (Oracle Cloud Always Free VM + Caddy/DuckDNS): see [DEPLOYMENT.md](DEPLOYMENT.md).
