# Logos Copilot — Product Requirements (PRD)

## Problem
Logos builder knowledge is fragmented across ~250 GitHub repos (4 orgs, mid-rebrand), several
doc sites, and a few internal AI efforts (a Keycloak-gated chatbot, a skills library, a scaffold
CLI, an executable-docs runner). There is **no public, MCP-native, always-current knowledge
endpoint** that an external developer's own agent (Claude, Cursor, VS Code, custom) can call to get
**cited, version-pinned** answers and **runnable** build/integration help.

## Product
A single **MCP server** backed by a **self-updating RAG knowledge base** over the whole Logos
GitHub + docs. It serves four modes to any connecting agent:
- **KNOW** — understand Logos, find specs/docs (hybrid RAG).
- **BUILD** — scaffold runnable apps / run a node (wraps `logos-co/scaffold` `lgs`).
- **INTEGRATE** — wire components together (golden recipes + multi-hop).
- **CODE** — exact signatures + verified runnable snippets (OpenAPI/symbol index + `logos-doctest`).

## Users
External developers building on Logos, via their own AI agents (primary) and a thin human web
playground (secondary, for onboarding/trust/feedback).

## Goals
1. **Never serve stale data.** Org-wide scrape + continuous change detection; every answer stamped
   with source commit + `indexed_at`; visible freshness/status.
2. **Never hallucinate APIs.** Signatures grounded in `openapi.yaml` + a tree-sitter symbol index.
3. **Never serve code that doesn't run.** Snippets gated by `logos-doctest` execution in CI.
4. **Reuse, don't rebuild.** Wrap scaffold, use doctest, ingest ai-skills + logos-rag source map.
5. **Cheap/free to run.** Oracle Always-Free VM, Postgres+pgvector, swappable embedder, $0 default.

## Non-goals
- We do **not** run a generative LLM (consumers bring their own agent).
- We do **not** rebuild scaffolding, executable-docs, or the skills content that already exist.
- Live on-chain/node data is a **later** phase (architecture leaves a clean seam for it).

## Freshness policy (hard rule)
The scraper **excludes any repo not pushed in the last 365 days**, plus archived repos and forks.
Repo discovery re-runs on a schedule so new repos are picked up and retired repos drop out.

## Principles
Server is the only thing we control → every result is self-describing, citation-bearing,
version-pinned, freshness-stamped, and abstains rather than bluffs.

## Success metrics
- Retrieval: Recall@5 / nDCG on a golden set (seeded from `logos-ai-skills/evals`).
- Faithfulness ≥ 0.9 (Ragas) on sampled production traces.
- Freshness lag p95 < 24h per source; 0 answers citing a >365-day-stale or archived repo.
- Snippet CI pass-rate gate before any index promotion.

## Scope by phase
0. Foundation + **org scrape (1-yr filter)** + schema + embedder + alias map.
1. MVP serving: FastMCP + KNOW tools, cited + freshness-stamped. ← shippable
2. BUILD/INTEGRATE/CODE: wrap `lgs`, golden recipes + ai-skills guides, symbol index, `verify_snippet` via doctest.
3. Freshness engine: webhooks + diff + tag/npm watch + docs crawler + nightly re-discovery + status page.
4. UX: human web playground + feedback capture; tool-ergonomics polish.
5. Evolve: OTel→Langfuse, golden set, doctest CI gate, gap loop, OAuth + rate limits, MCP Registry.

## Coordination
Talk to `weboko` (ai-skills + scaffold) and `corpetty` (logos-rag) before Phase 2 — this should be a
contribution/coordination, not a parallel effort.
