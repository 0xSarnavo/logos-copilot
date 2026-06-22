"""Org-wide GitHub discovery for the Logos ecosystem.

Enumerates every repo in the configured orgs and emits a curated `sources.generated.yaml`.

HARD FILTERS (per PRD):
  - drop archived repos
  - drop forks
  - drop any repo NOT pushed within `max_age_days` (default 365)  <-- the "no >1yr-stale code" rule
  - classify the rest; keep kind in {spec, doc, sdk, code, example}, skip the rest

Pure helpers (is_fresh / classify_repo / should_include) are unit-tested without network.
`fetch_org_repos` shells out to the authenticated `gh` CLI.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta

from .config import settings
from .registry import SEED, component_for_org

CODE_LANGS = {
    "Rust", "Nim", "Go", "TypeScript", "JavaScript", "C++", "C", "Python", "QML",
    "Solidity", "Shell", "Nix", "Makefile", "Vue", "Java", "Kotlin", "Ruby", "C#",
    "Circom", "Haskell", "Smarty", "Dockerfile",
}
HARD_SKIP = {".github", "nixpkgs", "scratch"}
PM_HINTS = ("-pm", "milestone", "project-management")
SPEC_HINTS = ("spec", "specs", "rfc", "lip", "lips", "cip", "cips")
DOC_HINTS = ("docs", "doc", "documentation", "wiki", "awesome", "tutorial")
SDK_HINTS = ("sdk", "bindings", "api-client", "-client")
EXAMPLE_HINTS = ("example", "demo", "poc", "sample", "template", "skeleton", "doctest",
                 "starter", "test", "tests", "boilerplate")
INCLUDE_KINDS = {"spec", "doc", "sdk", "code", "example"}


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def is_fresh(pushed_at: str, now: str, max_age_days: int = 365) -> bool:
    """True iff pushed within max_age_days of `now` (both ISO-8601)."""
    return _parse(pushed_at) >= _parse(now) - timedelta(days=max_age_days)


def classify_repo(repo: dict) -> str | None:
    """Return a kind for an includable repo, or None to skip (ignores freshness/archived/fork)."""
    name = (repo.get("name") or "").lower()
    lang = repo.get("language")
    if name in HARD_SKIP:
        return None
    if any(h in name for h in PM_HINTS) or name in {"pm", "ideas", "rfp", "assembly", "bounties",
                                                    "challenges", "anoncomms-pm"}:
        return None
    if any(name == h or name.startswith(h) or name.endswith("-" + h) or h in name.split("-")
           for h in SPEC_HINTS):
        return "spec"
    if name.endswith(".org") or name.endswith(".co") or any(h in name for h in DOC_HINTS):
        return "doc"
    if any(h in name for h in SDK_HINTS):
        return "sdk"
    if any(h in name for h in EXAMPLE_HINTS):
        return "example"
    if lang in CODE_LANGS:
        return "code"
    return None


def should_include(repo: dict, now: str, max_age_days: int = 365) -> bool:
    if repo.get("archived") or repo.get("fork"):
        return False
    pushed = repo.get("pushed_at")
    if not pushed or not is_fresh(pushed, now, max_age_days):
        return False
    return classify_repo(repo) in INCLUDE_KINDS


def fetch_org_repos(org: str) -> list[dict]:
    """All repos in an org via the authenticated gh CLI (paginated, slurped into one array)."""
    out = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", f"orgs/{org}/repos?per_page=100"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"gh api failed for {org}: {out.stderr.strip()[:300]}")
    data = json.loads(out.stdout)
    # `gh --paginate --slurp` returns a list of pages (each a list of repos); flatten one level.
    repos: list[dict] = []
    for page in data:
        repos.extend(page) if isinstance(page, list) else repos.append(page)
    return repos


def build_sources(orgs: tuple[str, ...], now: str, max_age_days: int = 365) -> dict:
    components = [
        {"id": cid, "canonical": canonical, "current_repo": repo, "aliases": aliases}
        for cid, canonical, repo, aliases, _ in SEED
    ]
    repos_out: list[dict] = []
    stats = {"scanned": 0, "kept": 0, "dropped_age": 0, "dropped_archived": 0,
             "dropped_fork": 0, "dropped_kind": 0}
    for org in orgs:
        for r in fetch_org_repos(org):
            stats["scanned"] += 1
            if r.get("archived"):
                stats["dropped_archived"] += 1
                continue
            if r.get("fork"):
                stats["dropped_fork"] += 1
                continue
            pushed = r.get("pushed_at")
            if not pushed or not is_fresh(pushed, now, max_age_days):
                stats["dropped_age"] += 1
                continue
            kind = classify_repo(r)
            if kind not in INCLUDE_KINDS:
                stats["dropped_kind"] += 1
                continue
            stats["kept"] += 1
            repos_out.append({
                "id": r["name"],
                "repo": r["full_name"],
                "component": component_for_org(org),
                "kind": kind,
                "lang": r.get("language"),
                "pushed_at": pushed[:10],
                "default_branch": r.get("default_branch", "main"),
            })
    repos_out.sort(key=lambda x: (x["component"], x["id"]))
    return {
        "meta": {"generated_at": now, "max_age_days": max_age_days, "orgs": list(orgs),
                 "stats": stats},
        "components": components,
        "github_repos": repos_out,
        "exclude": {"globs": ["*deprecated*", "*legacy*", "*archive*", "CHANGELOG*", "LICENSE*"],
                    "packages": ["js-waku"]},
    }


def write_sources(path: str = "sources.generated.yaml", now: str | None = None) -> dict:
    import yaml  # local import keeps pure helpers dependency-free

    now = now or datetime.now().astimezone().replace(microsecond=0).isoformat()
    data = build_sources(settings.orgs, now, settings.max_age_days)
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False, width=100)
    return data["meta"]["stats"]


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "sources.generated.yaml"
    stats = write_sources(out)
    print(f"wrote {out}: {stats}")
