"""Freshness engine: keep the knowledge base current and never stale.

- refresh_repo: compare the repo's latest commit SHA to what we last indexed; re-index only if changed,
  then tombstone chunks for files that disappeared from the source.
- reconcile: tombstone repos that dropped out of discovery (archived / removed / aged past the window).
- rediscover: re-run the org scrape and refresh everything (the nightly self-update loop).
- freshness: per-component coverage + staleness for the status surface.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime

from .config import settings
from .db import connect, fetch_dicts
from .ingest import FULL_NAME_RE, ingest_repo
from .registry import component_for_org
from .scrape import build_sources


def current_sha(full_name: str) -> str | None:
    """Latest commit SHA on the default branch, via gh. None if invalid/unreachable/empty/gone.

    `full_name` is validated before it reaches the gh path (the webhook path supplies it from
    untrusted JSON, and this runs before clone()'s own guard). gh auth gives a 5000/hr rate limit.
    """
    if not FULL_NAME_RE.match(full_name or ""):
        return None
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{full_name}/commits?per_page=1", "--jq", ".[0].sha"],
            capture_output=True, text=True, errors="replace", timeout=30,
        )
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def get_state(conn, repo: str) -> dict | None:
    cur = conn.cursor()
    cur.execute("SELECT last_sha, status FROM repo_state WHERE repo=%s", (repo,))
    r = cur.fetchone()
    return {"last_sha": r[0], "status": r[1]} if r else None


def set_state(conn, repo, component, branch, sha, n_chunks, n_symbols, status="active") -> None:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO repo_state
           (repo, component, default_branch, last_sha, last_indexed, status, n_chunks, n_symbols,
            updated_at)
           VALUES (%s,%s,%s,%s,now(),%s,%s,%s,now())
           ON CONFLICT (repo) DO UPDATE SET component=EXCLUDED.component,
             default_branch=COALESCE(EXCLUDED.default_branch, repo_state.default_branch),
             last_sha=EXCLUDED.last_sha, last_indexed=EXCLUDED.last_indexed,
             status=EXCLUDED.status, n_chunks=EXCLUDED.n_chunks, n_symbols=EXCLUDED.n_symbols,
             updated_at=now()""",
        (repo, component, branch, sha, status, n_chunks, n_symbols),
    )
    conn.commit()


def refresh_repo(conn, embedder, repo: str, component: str | None = None,
                 branch: str | None = None, force: bool = False) -> dict:
    if not FULL_NAME_RE.match(repo or ""):
        return {"repo": repo, "action": "invalid"}
    component = component or component_for_org(repo.split("/")[0])
    sha = current_sha(repo)
    if sha is None:
        return {"repo": repo, "action": "unreachable"}
    state = get_state(conn, repo)
    if state and state["last_sha"] == sha and not force:
        return {"repo": repo, "action": "unchanged", "sha": sha[:8]}

    cur = conn.cursor()
    # Serialize concurrent refreshes of the same repo (webhook worker vs nightly run).
    cur.execute("SELECT pg_try_advisory_lock(hashtext(%s)::bigint)", (repo,))
    if not cur.fetchone()[0]:
        return {"repo": repo, "action": "locked"}
    try:
        cur.execute("SELECT now()")
        run_start = cur.fetchone()[0]
        stats = ingest_repo(conn, embedder, repo, component)
        # tombstone chunks + symbols whose files vanished from source (not touched this run)
        cur.execute("UPDATE chunks SET deleted_at=now() "
                    "WHERE repo=%s AND deleted_at IS NULL AND last_seen < %s", (repo, run_start))
        tombstoned = cur.rowcount
        cur.execute("DELETE FROM symbols WHERE repo=%s AND indexed_at < %s", (repo, run_start))
        conn.commit()
        cur.execute("SELECT count(*) FROM chunks WHERE repo=%s AND deleted_at IS NULL", (repo,))
        nc = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM symbols WHERE repo=%s", (repo,))
        ns = cur.fetchone()[0]
        set_state(conn, repo, component, branch, sha, nc, ns)
    finally:
        cur.execute("SELECT pg_advisory_unlock(hashtext(%s)::bigint)", (repo,))
        conn.commit()
    return {"repo": repo, "action": "reindexed", "sha": sha[:8], "tombstoned": tombstoned,
            "new_or_changed": stats.get("new_or_changed"), "chunks": nc, "symbols": ns}


def reconcile(conn, active_repos: set[str]) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT repo FROM repo_state WHERE status='active'")
    known = {r[0] for r in cur.fetchall()}
    retired = known - active_repos
    tombstoned = 0
    for repo in retired:
        cur.execute("UPDATE chunks SET deleted_at=now() WHERE repo=%s AND deleted_at IS NULL", (repo,))
        tombstoned += cur.rowcount
        cur.execute("DELETE FROM symbols WHERE repo=%s", (repo,))
        cur.execute("UPDATE repo_state SET status='retired', updated_at=now() WHERE repo=%s", (repo,))
    conn.commit()
    return {"retired": sorted(retired), "tombstoned_chunks": tombstoned}


def rediscover(conn, embedder, now: str | None = None, limit: int | None = None) -> dict:
    now = now or datetime.now().astimezone().replace(microsecond=0).isoformat()
    data = build_sources(settings.orgs, now, settings.max_age_days)
    all_repos = data["github_repos"]
    full_active = {r["repo"] for r in all_repos}          # FULL discovered set (never truncated)
    repos = all_repos[:limit] if limit else all_repos
    tally: dict = {"reindexed": 0, "unchanged": 0, "unreachable": 0,
                   "failed": 0, "invalid": 0, "locked": 0}
    for r in repos:
        try:
            res = refresh_repo(conn, embedder, r["repo"], r["component"], r.get("default_branch"))
            tally[res["action"]] = tally.get(res["action"], 0) + 1
        except Exception:               # one bad repo must not abort the whole run
            conn.rollback()             # clear the aborted transaction before continuing
            tally["failed"] += 1
    # Reconcile ONLY against the full set, and ONLY on a full run — never retire against a partial set.
    rec = (reconcile(conn, full_active) if not limit
           else {"skipped": "limited run — reconcile is unsafe on a partial set"})
    return {"scanned": len(repos), **tally, "reconcile": rec}


def freshness(conn, stale_hours: int = 48) -> dict:
    cur = conn.cursor()
    cur.execute(
        """SELECT component, count(*) AS n, min(last_indexed) AS oldest, max(last_indexed) AS newest,
                  count(*) FILTER (WHERE last_indexed < now() - make_interval(hours => %s)) AS stale
           FROM repo_state WHERE status='active'
           GROUP BY component ORDER BY n DESC""",
        (stale_hours,),
    )
    rows = fetch_dicts(cur)
    cur.execute("SELECT count(*) FROM repo_state WHERE status='active'")
    active = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM repo_state WHERE status='retired'")
    retired = cur.fetchone()[0]
    for r in rows:
        r["n"], r["stale"] = int(r["n"]), int(r["stale"])
        r["oldest"], r["newest"] = str(r["oldest"]), str(r["newest"])
    return {"active_repos": int(active), "retired_repos": int(retired),
            "stale_threshold_hours": stale_hours, "by_component": rows}


if __name__ == "__main__":
    import sys

    from .embedder import get_embedder

    conn = connect()
    emb = get_embedder()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "repo":
        print(refresh_repo(conn, emb, sys.argv[2], force=("--force" in sys.argv)))
    elif cmd == "all":
        limit = next((int(a) for a in sys.argv[2:] if a.isdigit()), None)
        print(rediscover(conn, emb, limit=limit))
    elif cmd == "freshness":
        print(json.dumps(freshness(conn), indent=2))
    else:
        print(f"unknown command: {cmd}")
