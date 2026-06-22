"""Idempotent schema migrations. Run before ingest/refresh (also done by `make db-up` on fresh DBs).

Adds the repo-scoping column + repo_state table to an already-initialized DB, and rebuilds the
symbols table with repo-scoped uniqueness (symbols are derived, so dropping is safe).
"""
from __future__ import annotations

from .db import connect
from .feedback import ensure_feedback
from .symbols import SCHEMA as SYMBOLS_SCHEMA

_CHUNK_DDL = [
    "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS repo text",
    "CREATE INDEX IF NOT EXISTS chunks_repo_idx ON chunks (repo) WHERE deleted_at IS NULL",
]
_STATE_DDL = """
CREATE TABLE IF NOT EXISTS repo_state (
  repo text PRIMARY KEY, component text NOT NULL, default_branch text,
  last_sha text, last_indexed timestamptz, status text NOT NULL DEFAULT 'active',
  n_chunks int DEFAULT 0, n_symbols int DEFAULT 0, updated_at timestamptz NOT NULL DEFAULT now()
)
"""


def migrate(conn) -> None:
    cur = conn.cursor()
    for stmt in _CHUNK_DDL:
        cur.execute(stmt)
    cur.execute(_STATE_DDL)
    # Rebuild symbols ONLY if it predates repo-scoping (missing the `repo` column). This keeps the
    # migration idempotent: re-running on a healthy DB does NOT drop existing symbols.
    cur.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name='symbols' AND column_name='repo'""")
    has_repo = cur.fetchone() is not None
    if not has_repo:
        cur.execute("DROP TABLE IF EXISTS symbols")
        for stmt in filter(str.strip, SYMBOLS_SCHEMA.split(";")):
            cur.execute(stmt)
        # symbols are now empty; clear the SHA cache so the next refresh re-ingests + repopulates
        # (otherwise the unchanged-SHA short-circuit would leave the symbol index permanently empty).
        cur.execute("UPDATE repo_state SET last_sha = NULL")
    conn.commit()
    ensure_feedback(conn)
    from .querylog import ensure_query_log
    ensure_query_log(conn)


if __name__ == "__main__":
    migrate(connect())
    print("migrated")
