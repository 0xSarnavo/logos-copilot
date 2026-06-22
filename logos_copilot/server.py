"""Logos Copilot MCP server (FastMCP, Streamable HTTP).

Phase-1 KNOW surface: resolve_component, search_docs, get_api_signature, status.
Every retrieval result is cited + freshness-stamped. BUILD/INTEGRATE/CODE tools are Phase-2.
"""
from __future__ import annotations

from contextlib import closing

from fastmcp import FastMCP

from . import doctest_runner, scaffold
from .config import is_loopback, settings
from .db import connect, fetch_dicts
from .guides import get_guide, list_guides
from .registry import resolve
from .retrieve import citation, search
from .symbols import lookup_symbol

mcp = FastMCP("logos-copilot")


@mcp.tool
def logos_resolve_component(name: str, version: str | None = None) -> dict:
    """Resolve a Logos component name to its CURRENT repo, handling the Nomos/Codex/Waku rebrand.
    Returns a deprecation warning when a legacy name (e.g. 'Nomos', 'Codex', 'js-waku') is used."""
    r = resolve(name)
    if not r:
        return {"found": False,
                "hint": "Try: Logos Blockchain, Logos Storage, Logos Messaging, Logos Core"}
    return {"found": True, **r}


@mcp.tool
def logos_search_docs(query: str, component: str | None = None, kind: str | None = None,
                      top_k: int = 8) -> dict:
    """Search Logos docs/specs/code. Returns ranked, CITED, freshness-stamped chunks.
    `component` filters to a component id; `kind` is one of code|doc|spec|sdk|example|openapi."""
    rows = search(query, component=component, kind=kind, top_k=top_k)
    from .querylog import log_query
    with closing(connect()) as conn:
        log_query(conn, query, kind, component, len(rows))
    return {
        "query": query,
        "count": len(rows),
        "results": [{"content": r["content"], "citation": citation(r)} for r in rows],
    }


@mcp.tool
def logos_get_api_signature(component: str, symbol_or_endpoint: str,
                            version: str | None = None) -> dict:
    """Look up an API signature/endpoint grounded in the symbol index + OpenAPI/source (never
    invented). Tries the exact symbol/endpoint index first, then falls back to retrieval."""
    comp = (resolve(component) or {}).get("component_id", component)
    with closing(connect()) as conn:
        syms = lookup_symbol(conn, symbol_or_endpoint, component=comp)
    if syms:
        return {
            "found": True,
            "component": comp,
            "symbol": symbol_or_endpoint,
            "source_of_truth": "symbol_index",
            "matches": [
                {"name": s["name"], "kind": s["kind"], "signature": s["signature"],
                 "language": s["language"],
                 "citation": {"repo": s["component"], "repo_full": s.get("repo"),
                              "path": s["file_path"], "lines": [s["line_start"], s["line_start"]],
                              "url": s["url"], "git_sha": (s.get("git_sha") or "")[:8]}}
                for s in syms
            ],
        }
    rows = search(symbol_or_endpoint, component=comp, top_k=20)
    ranked = sorted(rows, key=lambda r: {"openapi": 0, "code": 1}.get(r["kind"], 2))
    hit = next((r for r in ranked if r["kind"] in ("openapi", "code")),
               ranked[0] if ranked else None)
    if not hit:
        return {"found": False, "component": comp, "symbol": symbol_or_endpoint}
    return {
        "found": True,
        "component": comp,
        "symbol": symbol_or_endpoint,
        "source_of_truth": hit["kind"],
        "snippet": hit["content"][:1200],
        "citation": citation(hit),
    }


@mcp.tool
def logos_freshness(stale_hours: int = 48) -> dict:
    """Freshness SLA surface: per-component active/retired repo counts, last-indexed range, and how
    many repos are stale (not re-indexed within `stale_hours`). Backed by the self-update engine."""
    from .refresh import freshness
    with closing(connect()) as conn:
        return freshness(conn, stale_hours=stale_hours)


@mcp.tool
def logos_gaps() -> dict:
    """Knowledge gaps: down-voted queries that still return weak coverage — ingestion candidates
    that drive the self-evolving loop."""
    from .gaps import detect_gaps
    with closing(connect()) as conn:
        return detect_gaps(conn)


@mcp.tool
def logos_status() -> dict:
    """Freshness/coverage surface: per-component chunk counts and indexed-at range."""
    with closing(connect()) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT component, count(*) AS n, min(indexed_at) AS oldest, max(indexed_at) AS newest
               FROM chunks WHERE deleted_at IS NULL GROUP BY component ORDER BY n DESC""")
        rows = fetch_dicts(cur)
        cur.execute("SELECT count(*) FROM chunks WHERE deleted_at IS NULL")
        total = cur.fetchone()[0]
    for r in rows:
        r["n"] = int(r["n"])
        r["oldest"] = str(r["oldest"])
        r["newest"] = str(r["newest"])
    return {"total_chunks": int(total), "embedder": settings.embedder, "by_component": rows}


# ── BUILD: curated guides (ingested from logos-co/logos-ai-skills) ──

@mcp.tool
def logos_list_guides(component: str | None = None) -> dict:
    """List curated build guides (from logos-ai-skills) — one entry per guide, with its slug."""
    guides = list_guides(component)
    return {"count": len(guides), "guides": guides}


@mcp.tool
def logos_get_guide(slug: str) -> dict:
    """Fetch a full curated guide by slug (file path from logos_list_guides), with citation."""
    g = get_guide(slug)
    if not g:
        return {"found": False, "slug": slug}
    return {"found": True, **g}


@mcp.tool
def logos_list_recipes() -> dict:
    """List curated cross-component INTEGRATE recipes (e.g. Codex+Waku file sharing)."""
    recipes = list_guides(kind="recipe")
    return {"count": len(recipes), "recipes": recipes}


@mcp.tool
def logos_get_recipe(slug: str) -> dict:
    """Fetch a full curated recipe by slug (from logos_list_recipes), with citation."""
    g = get_guide(slug, kind="recipe")
    if not g:
        return {"found": False, "slug": slug}
    return {"found": True, **g}


# ── BUILD: scaffolding via the logos-co/scaffold CLI (lgs) ──

@mcp.tool
def logos_scaffold_status() -> dict:
    """Whether the Logos scaffold CLI (lgs) is available on this host, and its version."""
    if not scaffold.available():
        return {"installed": False, "hint": scaffold.INSTALL_HINT}
    return {"installed": True, **scaffold.version()}


@mcp.tool
def logos_scaffold(action: str, name: str | None = None,
                   project_path: str | None = None) -> dict:
    """Run an allowlisted Logos scaffold (lgs) action: version | help | create | new | init |
    doctor | build | localnet_status. `create`/`new` require a project `name`. Wraps the real
    `lgs` CLI (logos-co/scaffold) — returns structured stdout/stderr; never arbitrary passthrough."""
    return scaffold.run(action, name=name, project_path=project_path)


# ── CODE: verify a snippet actually runs (via logos-doctest) ──

@mcp.tool
def logos_verify_status() -> dict:
    """Whether snippet verification (logos-doctest) is configured on this host."""
    if not doctest_runner.available():
        return {"enabled": False, "hint": doctest_runner.INSTALL_HINT}
    return {"enabled": True, "supported_languages": sorted(set(doctest_runner.RUNTIME))}


@mcp.tool
def logos_verify_snippet(language: str, code: str,
                         expect_contains: list[str] | None = None) -> dict:
    """Execute a code snippet through logos-doctest and report pass/fail (so an agent only trusts
    code that actually runs). Supports python/javascript/bash; Rust/Nim/Go need a toolchain
    (use logos_scaffold). Requires DOCTEST_BIN configured; sandbox for public use."""
    return doctest_runner.verify_snippet(language, code, expect_contains=expect_contains)


# ── feedback (explicit signal channel; seeds the eval/gap loop) ──

@mcp.tool
def logos_submit_feedback(query: str, rating: str, source_url: str | None = None,
                          comment: str | None = None) -> dict:
    """Record feedback on an answer (rating 'up' or 'down', optional source_url + comment) so the
    system can detect gaps and improve. Down-votes become gap-detection candidates."""
    if rating not in ("up", "down"):
        return {"ok": False, "error": "rating must be 'up' or 'down'"}
    from .feedback import submit_feedback
    with closing(connect()) as conn:
        submit_feedback(conn, query=query, rating=rating, source_url=source_url, comment=comment)
    return {"ok": True}


# ── Resources (URI-addressable) + Prompts (slash-command templates) ──

@mcp.resource("logos://guides")
def res_guides() -> str:
    """Index of curated build guides (ingested from logos-ai-skills)."""
    return "\n".join(f"- {g['slug']}  ({g['component']})" for g in list_guides()) or "(none)"


@mcp.resource("logos://recipes")
def res_recipes() -> str:
    """Index of curated cross-component integration recipes."""
    return "\n".join(f"- {g['slug']}" for g in list_guides(kind="recipe")) or "(none)"


@mcp.prompt
def scaffold_codex_waku_app() -> str:
    return ("Help me build a Logos app that stores a file in Logos Storage (Codex) and broadcasts the "
            "CID over Logos Messaging (Waku). First call logos_get_recipe('codex-waku-file-share.md'), "
            "then logos_get_api_signature for exact SDK signatures, and logos_scaffold to bootstrap. "
            "Use only cited, version-pinned APIs.")


@mcp.prompt
def run_local_logos_node() -> str:
    return ("Walk me through running a local Logos Blockchain node. Call "
            "logos_get_recipe('run-local-logos-node.md') and ground every endpoint via "
            "logos_get_api_signature — do not invent endpoints.")


def main() -> None:
    # Don't expose code-exec / scaffold / filesystem tools to the network unauthenticated.
    if not is_loopback(settings.mcp_host) and not settings.auth_token:
        raise SystemExit(
            f"Refusing to bind MCP_HOST={settings.mcp_host} without auth. Either set AUTH_TOKEN, "
            f"or use MCP_HOST=127.0.0.1 (loopback) and front it with an authenticating proxy.")
    import uvicorn
    from starlette.middleware import Middleware

    from .auth import BearerAuthASGI, RateLimitASGI
    # rate-limit outermost (throttles even unauthenticated probes), then bearer auth.
    app = mcp.http_app(path="/mcp", middleware=[
        Middleware(RateLimitASGI),
        Middleware(BearerAuthASGI),
    ])
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
