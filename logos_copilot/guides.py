"""Curated 'guide'/'recipe' knowledge (ingested from logos-ai-skills + hand-authored recipes).

Guides/recipes are chunks with kind='guide'/'recipe'. `list_guides` enumerates one entry per source
file (slug = file path); `get_guide` reassembles a full document from its ordered chunks.
"""
from __future__ import annotations

from contextlib import closing

from .db import connect, fetch_dicts


def list_guides(component: str | None = None, kind: str = "guide", limit: int = 200) -> list[dict]:
    with closing(connect()) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT component, file_path, min(url) AS url, max(indexed_at) AS indexed_at,
                      count(*) AS chunks
               FROM chunks
               WHERE kind = %s AND deleted_at IS NULL
                 AND (%s::text IS NULL OR component = %s::text)
               GROUP BY component, file_path
               ORDER BY component, file_path
               LIMIT %s""",
            (kind, component, component, limit),
        )
        rows = fetch_dicts(cur)
    return [{"slug": r["file_path"], "component": r["component"], "url": r["url"],
             "indexed_at": str(r["indexed_at"]), "chunks": int(r["chunks"])} for r in rows]


def get_guide(slug: str, kind: str = "guide") -> dict | None:
    with closing(connect()) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT content, url, component, git_sha FROM chunks
               WHERE kind = %s AND file_path = %s AND deleted_at IS NULL
               ORDER BY line_start NULLS FIRST, id""",
            (kind, slug),
        )
        rows = fetch_dicts(cur)
    if not rows:
        return None
    return {
        "slug": slug,
        "component": rows[0]["component"],
        "url": rows[0]["url"],
        "git_sha": (rows[0].get("git_sha") or "")[:8],
        "content": "\n".join(r["content"] for r in rows),
    }
