# Logos Copilot — Technical Spec (SPEC)

Contract for the build. Phase 0–1 is implemented and tested; later phases are scaffolded with TODOs.

## Stack
Python 3.12+ · Postgres 16 + pgvector · FastMCP (Streamable HTTP) · `pg8000` (pure-Python driver,
no build deps) · PyYAML · httpx. Embedder is pluggable; default `hash` (deps-free, deterministic) for
local runs, `voyage`/`fastembed` for production. Vectors are passed to Postgres as `'[...]'::vector`
text so no driver-specific adapter is needed.

## Repo layout (flat package; runnable with `python -m logos_copilot.*` from repo root)
```
logos-copilot/
  PRD.md SPEC.md README.md ARCHITECTURE.md DEPLOYMENT.md
  requirements.txt  docker-compose.yml  Dockerfile  Caddyfile  Makefile
  db/schema.sql
  logos_copilot/
    __init__.py config.py registry.py scrape.py chunk.py embedder.py
    db.py ingest.py retrieve.py server.py
  tests/  test_registry.py test_chunk.py test_scrape.py test_embedder.py
          test_retrieve_int.py  (integration; skipped unless DATABASE_URL reachable)
  sources.generated.yaml   (produced by the scraper)
```

## Data model (`db/schema.sql`)
- `components(id, canonical_name, current_repo, aliases[], is_deprecated, deprecation_note, latest_version)`
- `chunks(id, source_id, component, version, git_sha, kind, content, content_hash,
   embedding vector(EMBED_DIM), embed_model, tsv tsvector GENERATED, url, file_path,
   line_start, line_end, heading_anchor, deprecated, created_at, last_seen, valid_until,
   deleted_at, indexed_at)` — UNIQUE(source_id, version).
- Indexes: HNSW(embedding cosine), GIN(tsv), (component,version) partial, (content_hash).
- `EMBED_DIM` default 256 (hash). Must match the active embedder; switching dim ⇒ re-embed.

## Interfaces
**Embedder** (`embedder.py`): `model_id: str`, `dim: int`, `embed_documents(texts)->list[list[float]]`,
`embed_query(text)->list[float]`. Implementations: `HashEmbedder` (default), `FastEmbedEmbedder`,
`VoyageEmbedder`. Factory `get_embedder()` reads `EMBEDDER`/`EMBED_DIM`.

**Scraper** (`scrape.py`): pure helpers `is_fresh(pushed_at, now, max_age_days)`,
`classify_repo(repo)->kind|None`, `should_include(repo, now, max_age_days)->bool`; impure
`fetch_org_repos(org)` (via `gh api --paginate --slurp`), `build_sources(orgs, now)->dict`,
`write_sources(path)`. **Hard filter:** drop `archived`, `fork`, and `pushed_at` older than
`max_age_days` (default 365). `kind ∈ {spec, doc, sdk, code, example}` else skipped.

**Retrieval** (`retrieve.py`): `search(query, component=None, kind=None, top_k=8)` → hybrid
dense(pgvector `<=>`) top-50 + BM25(`websearch_to_tsquery`) top-50 → RRF fuse → top_k, filtered
`deleted_at IS NULL AND NOT deprecated` and optional component/kind. Each row returns provenance +
`indexed_at`.

## MCP surface (Phase 1 implemented; rest TODO-stubbed)
All tools namespaced `logos_`, return `structuredContent` + mirrored text, each result citation-bearing.
- `logos_resolve_component(name, version?)` → current repo + legacy-name warning (alias map).
- `logos_search_docs(query, component?, kind?, top_k=8)` → ranked cited chunks + freshness.
- `logos_get_api_signature(component, symbol_or_endpoint, version?)` → from OpenAPI/symbol index *(Phase 2)*.
- `logos_status()` → per-source last-indexed + counts (freshness surface).
Later: `answer`, `scaffold`(=lgs), `verify_snippet`(=doctest), `diff_versions`, `submit_feedback`.

## Config (`config.py`, stdlib only)
`DATABASE_URL`, `EMBEDDER` (hash|fastembed|voyage), `EMBED_DIM`, `LOCAL_MODEL`, `VOYAGE_API_KEY`,
`VOYAGE_MODEL`, `LOGOS_ORGS` (csv), `MAX_AGE_DAYS` (365).

## Test plan / acceptance criteria
- **Unit (no net/db):** registry resolve+legacy warning; chunkers + content-hash stability;
  classifier (archived/fork/old → skip; rust→code; specs→spec; docs→doc; sdk→sdk; .github→skip);
  hash embedder dim/determinism/normalization. → `pytest` green.
- **Live scrape:** `python -m logos_copilot.scrape` produces `sources.generated.yaml`, **0 repos
  older than 365 days, 0 archived, 0 forks**, >0 repos per active org. (asserted by a checker)
- **Integration (db):** bring up pgvector via compose, apply schema, ingest ≥1 real repo, `search()`
  returns relevant cited rows; MCP tools callable. Skipped if no DB.
- **Done = all green, looped until no failures.**
