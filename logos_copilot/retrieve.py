"""Hybrid retrieval: dense (pgvector cosine) + BM25 (Postgres full-text) fused with RRF.

BM25 supplies exact-token relevance (function names, flags, CIDs) that pure dense search misses —
and carries the local demo since the default HashEmbedder is non-semantic.
"""
from __future__ import annotations

from .db import connect, fetch_dicts, vec_literal
from .embedder import get_embedder
from .rerank import get_reranker

_COLS = ("id, source_id, content, url, file_path, line_start, line_end, "
         "component, repo, version, kind, indexed_at, git_sha")


def _rrf(rankings: list[list[dict]], k: int = 60) -> list[dict]:
    scores: dict = {}
    for ranked in rankings:
        for rank, row in enumerate(ranked):
            entry = scores.setdefault(row["id"], [0.0, row])
            entry[0] += 1.0 / (k + rank + 1)
    return [row for _, row in sorted(scores.values(), key=lambda x: -x[0])]


def search(query: str, component: str | None = None, kind: str | None = None,
           top_k: int = 8, version: str | None = None) -> list[dict]:
    vec = vec_literal(get_embedder().embed_query(query))
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""SELECT {_COLS} FROM chunks
                WHERE deleted_at IS NULL AND NOT deprecated
                  AND (%s::text IS NULL OR component = %s::text)
                  AND (%s::text IS NULL OR kind = %s::text)
                  AND (%s::text IS NULL OR version = %s::text)
                ORDER BY embedding <=> %s::vector LIMIT 50""",
            (component, component, kind, kind, version, version, vec),
        )
        dense = fetch_dicts(cur)
        cur.execute(
            f"""SELECT {_COLS} FROM chunks
                WHERE deleted_at IS NULL AND NOT deprecated
                  AND tsv @@ websearch_to_tsquery('english', %s)
                  AND (%s::text IS NULL OR component = %s::text)
                  AND (%s::text IS NULL OR kind = %s::text)
                  AND (%s::text IS NULL OR version = %s::text)
                ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', %s)) DESC LIMIT 50""",
            (query, component, component, kind, kind, version, version, query),
        )
        bm25 = fetch_dicts(cur)
    finally:
        conn.close()
    fused = _rrf([dense, bm25])
    rr = get_reranker()
    if rr:                                  # rerank the shortlist, then cut to top_k
        fused = rr.rerank(query, fused[:30])
    return fused[:top_k]


def citation(row: dict) -> dict:
    return {
        "repo": row["component"],            # component id (e.g. logos-storage)
        "repo_full": row.get("repo"),        # exact GitHub repo (e.g. logos-storage/logos-storage-js)
        "version": row["version"],
        "path": row["file_path"],
        "lines": [row.get("line_start"), row.get("line_end")],
        "url": row.get("url"),
        "git_sha": (row.get("git_sha") or "")[:8],
        "indexed_at": str(row.get("indexed_at")),
        "kind": row["kind"],
    }
