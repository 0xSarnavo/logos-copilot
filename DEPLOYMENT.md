# Deployment

Two paths. Both run the same `docker-compose.yml` (db + server + caddy).

## A) Truly-$0, always-on — Oracle Cloud Always Free VM (recommended)

An Ampere A1 Always Free VM (up to 4 cores / 24 GB RAM, free indefinitely) runs Postgres + the MCP
server + Caddy on one box, with no cold starts.

1. **Create the VM.** Oracle Cloud → Always Free → Ampere A1, Ubuntu 22.04/24.04.
   (Card needed for verification, not charged. If A1 capacity is unavailable, try another
   Availability Domain/region.)
2. **Open ports** 80 + 443 in the VCN security list, and on the host:
   `sudo iptables -I INPUT -p tcp -m multiport --dports 80,443 -j ACCEPT` (persist it).
3. **Install Docker** + compose plugin.
4. **Free domain + TLS:** create a DuckDNS subdomain pointing at the VM's public IP. Caddy fetches
   a Let's Encrypt cert automatically.
5. **Deploy:**
   ```bash
   git clone <your-repo> logos-copilot && cd logos-copilot
   cp .env.example .env       # set POSTGRES_PASSWORD + PUBLIC_DOMAIN (your DuckDNS name)
   docker compose up -d        # db + server + caddy
   ```
6. **Populate the KB** (once, then on a schedule):
   ```bash
   docker compose exec server python -m logos_copilot.ingest seed
   docker compose exec server python -m logos_copilot.scrape sources.generated.yaml
   # ingest the repos you want (loop over sources.generated.yaml github_repos), e.g.:
   docker compose exec server python -m logos_copilot.ingest repo logos-blockchain/logos-blockchain
   ```
7. Endpoint: **`https://<your-name>.duckdns.org/mcp`**. Point any MCP client at it.

**Keep it fresh (Phase 3):** the freshness engine re-indexes only repos whose latest commit SHA
changed, tombstones files/repos that disappear, and re-discovers new repos.

```bash
docker compose exec server python -m logos_copilot.migrate           # one-time (idempotent)
# nightly self-update (cron): re-scrape orgs + re-index changed repos + reconcile
0 3 * * *  docker compose exec -T server python -m logos_copilot.refresh all
docker compose exec server python -m logos_copilot.refresh freshness  # SLA report
```

For real-time updates, point a GitHub org webhook (push/release/create, secret = `WEBHOOK_SECRET`)
at an endpoint that calls `logos_copilot.webhook.process` (HMAC-verified) → enqueues
`refresh.refresh_repo`. The nightly `refresh all` is the backstop for missed webhooks.

**Web playground (Phase 4):** `python -m logos_copilot.web` serves a human search/feedback UI on
`WEB_PORT` (default 8800), loopback by default. The render is XSS-hardened, but it has no auth — to
expose it publicly, add a route in the Caddyfile (`reverse_proxy web:8800`) behind basic-auth/OAuth.

## B) Railway (~$5/mo, zero-ops)
Push the repo; add a Postgres plugin (enable `vector`); set `DATABASE_URL`, `EMBEDDER`, `MCP_PORT`;
deploy the `server` service; `railway run python -m logos_copilot.ingest seed` then ingest. Railway
gives you a public HTTPS domain — no Caddy/DuckDNS needed.

## Config
| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | local 5433 / compose `db:5432` | Postgres + pgvector |
| `EMBEDDER` | `hash` | `hash`\|`fastembed`\|`voyage` |
| `EMBED_DIM` | `256` | **must match** `db/schema.sql` `vector(...)` |
| `VOYAGE_API_KEY` / `VOYAGE_MODEL` | — | for `EMBEDDER=voyage` |
| `LOGOS_ORGS` | the 4 orgs | comma-separated |
| `MAX_AGE_DAYS` | `365` | repo freshness cutoff |
| `MCP_HOST`/`MCP_PORT` | `127.0.0.1`/`8000` | **loopback by default**; non-loopback requires `AUTH_TOKEN` |
| `AUTH_TOKEN` | — | required to bind a public host; front with an authenticating proxy |
| `ALLOW_CODE_EXEC` | off | gates `logos_verify_snippet` (executes code) — set `1` to enable |
| `SANDBOX_CMD` | — | wraps snippet execution (e.g. `firejail --net=none --read-only=/`) |
| `DOCTEST_BIN` | — | path to the logos-doctest engine (enables `verify_snippet`) |
| `LGS_WORKDIR` | — | confines `logos_scaffold` `project_path` under this root |
| `LGS_BIN` | PATH | path to the `lgs` (logos-scaffold) CLI |

## Switching to production embeddings
1. `ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1024);` (Voyage) — and recreate the HNSW index.
2. Set `EMBEDDER=voyage`, `EMBED_DIM=1024`, `VOYAGE_API_KEY`, `VOYAGE_MODEL=voyage-3-large`.
3. Re-ingest (a full re-embed; required because the dimension changed).

## Hardening before public exposure
The server is **loopback-only by default** and refuses to bind a non-loopback `MCP_HOST` unless
`AUTH_TOKEN` is set — so the code-exec/scaffold tools are never network-reachable out of the box.
Before exposing publicly:
- Put an **authenticating reverse proxy** (or FastMCP OAuth, Phase 5) in front; set `AUTH_TOKEN`.
- Keep `ALLOW_CODE_EXEC` **off** unless you also set `SANDBOX_CMD` (firejail/bubblewrap/gVisor/container
  with no network, read-only FS, non-root uid). `logos_verify_snippet` runs code.
- Set `LGS_WORKDIR` so `logos_scaffold` can only operate under a dedicated workspace root.
- `gh` auth (a `GITHUB_TOKEN`) raises the scraper's API rate limit.

**Built-in auth + rate-limit (Phase 5):** the MCP server wraps its HTTP app with bearer auth (enforced
when `AUTH_TOKEN` is set) + a per-IP token-bucket rate limiter (`auth.py`, 120 req/min default). It's
SSE-safe (pure ASGI). For multi-node, swap the in-process bucket for a Redis-backed limiter; for full
OAuth 2.1 (vs a static bearer token), front it with a managed IdP / OAuth proxy. SSRF egress controls
still belong on any future URL-fetching tools.

**Quality gates (Phase 5):**
```bash
make eval          # golden-set retrieval eval + CI gate (fails build on regression)
make ci-snippets   # run executable code blocks in recipes/ through logos-doctest
make gaps          # down-voted + under-covered queries -> ingestion candidates
```
Wire `make eval` (and `make ci-snippets` with `ALLOW_CODE_EXEC=1` + `DOCTEST_BIN`) into CI to block
index promotion on a metric regression.

**Publish to the MCP Registry:** edit `server.json` (set your `remotes[].url`), then publish with the
`mcp-publisher` CLI per `https://registry.modelcontextprotocol.io` so other agents can discover it.

## Ops checks
- `logos_status()` → coverage + indexed-at per component.
- `docker compose logs -f server` for serving; `docker compose logs db` for Postgres.
- `make test` in CI before deploy.
