"""Ingestion: clone a repo, chunk its files, content-hash gate, embed changed, upsert into pgvector.

The content-hash gate (skip-if-unchanged) is the foundation of the self-updating pipeline — re-runs
only re-embed what actually changed. Deletions/tombstones + webhooks are the Phase-3 upgrade.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

from .chunk import chunk_file, content_hash
from .db import connect, vec_literal
from .registry import SEED, component_for_org
from .symbols import ensure_symbols, extract_symbols, upsert_symbols

SKIP_DIRS = {".git", ".github", "node_modules", "target", "dist", "build", ".obsidian",
             "vendor", "__pycache__", ".venv", "result",
             "deprecated", "legacy", "archive", "archived", "old"}
# Belt-and-suspenders: also drop any path that *looks* deprecated/legacy (so we never serve it).
SKIP_PATH = re.compile(r"(deprecated|legacy|/archive|/old/|\.archive)", re.IGNORECASE)
MAX_FILE_BYTES = 200_000
FULL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _ctx(repo: str, path: str, anchor: str | None, content: str) -> str:
    """Prepend a compact context header (repo · path · heading) so the chunk's provenance is part of
    what gets embedded + BM25-indexed + shown — Anthropic 'contextual retrieval', deterministic."""
    head = f"[{repo} · {path}" + (f" · {anchor}" if anchor else "") + "]"
    return head + "\n" + content


def _read(path: str) -> str:
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return ""
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def clone(full_name: str, ref: str | None = None) -> tuple[str, str]:
    # Validate to prevent argument-injection / SSRF-shaped inputs (matters once webhooks drive this).
    if not FULL_NAME_RE.match(full_name or ""):
        raise ValueError(f"invalid repo full_name: {full_name!r}")
    if ref is not None and (ref.startswith("-") or not REF_RE.match(ref)):
        raise ValueError(f"invalid ref: {ref!r}")
    d = tempfile.mkdtemp(prefix="logoskb_")
    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += ["--", f"https://github.com/{full_name}.git", d]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=300)
    except subprocess.TimeoutExpired:
        shutil.rmtree(d, ignore_errors=True)
        raise RuntimeError(f"clone timed out for {full_name}")
    if r.returncode != 0:
        shutil.rmtree(d, ignore_errors=True)
        raise RuntimeError(f"clone failed for {full_name}: {r.stderr.strip()[:300]}")
    try:
        sha = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True,
                             text=True, errors="replace", timeout=30).stdout.strip()
    except subprocess.TimeoutExpired:
        sha = ""
    return d, sha


def collect(repo_dir: str, full_name: str, component: str, sha: str,
            kind_override: str | None = None) -> tuple[list[dict], list[dict]]:
    """Return (chunk_items, symbols)."""
    items: list[dict] = []
    symbols: list[dict] = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), repo_dir)
            if SKIP_PATH.search(rel):
                continue
            text = _read(os.path.join(root, fn))
            kind, chunks = chunk_file(rel, text)
            # kind_override re-tags prose (e.g. ai-skills markdown -> 'guide'); code stays code.
            if kind_override and kind == "doc":
                kind = kind_override
            for n, (content, anchor, ls, le) in enumerate(chunks):
                items.append({
                    "source_id": f"{full_name}:{rel}:{n}",   # repo-scoped (avoids cross-repo clash)
                    "repo": full_name,
                    "kind": kind,
                    "content": _ctx(full_name, rel, anchor, content),
                    "file_path": rel,
                    "heading_anchor": anchor,
                    "line_start": ls,
                    "line_end": le,
                    "url": f"https://github.com/{full_name}/blob/{sha}/{rel}",
                })
            for s in extract_symbols(rel, text):
                symbols.append({**s, "file_path": rel})
    return items, symbols


def upsert_chunks(conn, embedder, *, component, version, git_sha, items) -> dict:
    cur = conn.cursor()
    new = []
    for it in items:
        h = content_hash(it["content"])
        cur.execute(
            "SELECT 1 FROM chunks WHERE source_id=%s AND version=%s AND content_hash=%s",
            (it["source_id"], version, h),
        )
        if cur.fetchone():  # unchanged -> skip embedding (cheap re-runs)
            # refresh provenance (git_sha/url) so citations stay current even when content is stable;
            # also resurrect a reappeared file (clear deleted_at/deprecated).
            cur.execute("UPDATE chunks SET last_seen=now(), deleted_at=NULL, deprecated=false, "
                        "git_sha=%s, url=%s WHERE source_id=%s AND version=%s",
                        (git_sha, it.get("url"), it["source_id"], version))
            continue
        it["content_hash"] = h
        new.append(it)
    if new:
        vecs = embedder.embed_documents([it["content"] for it in new])
        for it, v in zip(new, vecs):
            cur.execute(
                """INSERT INTO chunks
                   (source_id, repo, component, version, git_sha, kind, content, content_hash,
                    embedding, embed_model, url, file_path, line_start, line_end, heading_anchor)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::vector,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (source_id, version) DO UPDATE SET
                     content=EXCLUDED.content, content_hash=EXCLUDED.content_hash,
                     embedding=EXCLUDED.embedding, git_sha=EXCLUDED.git_sha, repo=EXCLUDED.repo,
                     indexed_at=now(), last_seen=now(), deleted_at=NULL, deprecated=false""",
                (it["source_id"], it.get("repo"), component, version, git_sha, it["kind"],
                 it["content"], it["content_hash"], vec_literal(v), embedder.model_id,
                 it.get("url"), it["file_path"], it.get("line_start"), it.get("line_end"),
                 it.get("heading_anchor")),
            )
    conn.commit()
    return {"new_or_changed": len(new), "skipped": len(items) - len(new)}


def ingest_dir(conn, embedder, path: str, component: str, kind: str,
               url_prefix: str = "", repo: str = "logos-copilot/recipes") -> dict:
    """Ingest a LOCAL directory of files with a forced kind (e.g. curated recipes)."""
    items = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), path)
            if SKIP_PATH.search(rel):
                continue
            _, chunks = chunk_file(rel, _read(os.path.join(root, fn)))
            for n, (content, anchor, ls, le) in enumerate(chunks):
                items.append({
                    "source_id": f"{repo}:{rel}:{n}",
                    "repo": repo,
                    "kind": kind, "content": _ctx(repo, rel, anchor, content), "file_path": rel,
                    "heading_anchor": anchor, "line_start": ls, "line_end": le,
                    "url": (url_prefix + rel) if url_prefix else None,
                })
    stats = upsert_chunks(conn, embedder, component=component, version="latest",
                          git_sha=None, items=items)
    return {"path": path, "kind": kind, "files_chunks": len(items), **stats}


def seed_components(conn) -> None:
    cur = conn.cursor()
    for cid, canonical, repo, aliases, note in SEED:
        cur.execute(
            """INSERT INTO components (id, canonical_name, current_repo, aliases, deprecation_note)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET aliases=EXCLUDED.aliases,
                 current_repo=EXCLUDED.current_repo, deprecation_note=EXCLUDED.deprecation_note""",
            (cid, canonical, repo, aliases, note or None),
        )
    conn.commit()


def ingest_repo(conn, embedder, full_name: str, component: str | None = None,
                kind_override: str | None = None, version: str = "latest",
                ref: str | None = None) -> dict:
    """Ingest a repo. Pass ref=<git tag/branch> + version=<label> to index a specific release
    (chunks are UNIQUE per (source_id, version), so versions coexist)."""
    component = component or component_for_org(full_name.split("/")[0])
    ensure_symbols(conn)
    repo_dir, sha = clone(full_name, ref)
    try:
        items, symbols = collect(repo_dir, full_name, component, sha, kind_override=kind_override)
        stats = upsert_chunks(conn, embedder, component=component, version=version,
                              git_sha=sha, items=items)
        n_sym = upsert_symbols(
            conn, repo=full_name, component=component, version=version, git_sha=sha,
            url_for=lambda fp: f"https://github.com/{full_name}/blob/{sha}/{fp}", symbols=symbols)
        return {"repo": full_name, "component": component, "version": version, "sha": sha[:8],
                "files_chunks": len(items), "symbols": n_sym, **stats}
    finally:
        shutil.rmtree(repo_dir, ignore_errors=True)


if __name__ == "__main__":
    from .embedder import get_embedder

    conn = connect()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if cmd == "seed":
        seed_components(conn)
        print("seeded components")
    elif cmd == "repo":
        full = sys.argv[2]
        comp = sys.argv[3] if len(sys.argv) > 3 else None
        kind = sys.argv[4] if len(sys.argv) > 4 else None
        print(ingest_repo(conn, get_embedder(), full, comp, kind_override=kind))
    elif cmd == "guides":
        # ingest logos-co/logos-ai-skills as cited 'guide' knowledge
        print(ingest_repo(conn, get_embedder(), "logos-co/logos-ai-skills",
                          "logos-co", kind_override="guide"))
    elif cmd == "recipes":
        rdir = os.path.join(os.path.dirname(__file__), "..", "recipes")
        print(ingest_dir(conn, get_embedder(), os.path.abspath(rdir), "logos-co",
                         "recipe", url_prefix="recipes/"))
    else:
        print(f"unknown command: {cmd}")
