"""User/agent feedback capture — the explicit signal channel that seeds the Phase-5 eval/gap loop.

Feedback is intentionally lightweight (rating + optional comment + which source it was about). The
down-voted queries become gap-detection candidates.
"""
from __future__ import annotations

from .db import connect, fetch_dicts

SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
  id          bigserial PRIMARY KEY,
  query       text,
  rating      text NOT NULL,          -- 'up' | 'down'
  source_url  text,
  comment     text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS feedback_rating_idx ON feedback (rating);
"""


def ensure_feedback(conn) -> None:
    cur = conn.cursor()
    for stmt in filter(str.strip, SCHEMA.split(";")):
        cur.execute(stmt)
    conn.commit()


def submit_feedback(conn, *, query, rating, source_url=None, comment=None) -> bool:
    if rating not in ("up", "down"):
        raise ValueError("rating must be 'up' or 'down'")
    # backstop length caps (defense-in-depth alongside the web layer)
    query = (query or "")[:1000]
    source_url = source_url[:500] if source_url else None
    comment = comment[:2000] if comment else None
    ensure_feedback(conn)
    cur = conn.cursor()
    cur.execute("INSERT INTO feedback (query, rating, source_url, comment) VALUES (%s,%s,%s,%s)",
                (query, rating, source_url, comment))
    conn.commit()
    return True


def feedback_stats(conn) -> dict:
    ensure_feedback(conn)
    cur = conn.cursor()
    cur.execute("SELECT rating, count(*) FROM feedback GROUP BY rating")
    by = {r[0]: int(r[1]) for r in cur.fetchall()}
    cur.execute("""SELECT query, count(*) AS c FROM feedback
                   WHERE rating='down' AND coalesce(query,'') <> ''
                   GROUP BY query ORDER BY c DESC LIMIT 10""")
    gaps = fetch_dicts(cur)
    for g in gaps:
        g["c"] = int(g["c"])
    return {"up": by.get("up", 0), "down": by.get("down", 0), "top_negative_queries": gaps}
