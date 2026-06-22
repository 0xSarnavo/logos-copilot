"""Query logging — records every search so gap detection sees real demand (not just explicit votes).

Logging must never break a query: all failures are swallowed.
"""
from __future__ import annotations

SCHEMA = """
CREATE TABLE IF NOT EXISTS query_log (
  id           bigserial PRIMARY KEY,
  query        text,
  kind         text,
  component    text,
  result_count int,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS query_log_created_idx ON query_log (created_at);
"""


def ensure_query_log(conn) -> None:
    cur = conn.cursor()
    for stmt in filter(str.strip, SCHEMA.split(";")):
        cur.execute(stmt)
    conn.commit()


def log_query(conn, query, kind, component, result_count) -> None:
    try:
        ensure_query_log(conn)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO query_log (query, kind, component, result_count) VALUES (%s,%s,%s,%s)",
            ((query or "")[:1000], kind, component, result_count))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def top_queries(conn, limit: int = 20) -> list[dict]:
    ensure_query_log(conn)
    cur = conn.cursor()
    cur.execute("""SELECT query, count(*) AS c, avg(result_count) AS ar FROM query_log
                   WHERE coalesce(query,'') <> '' GROUP BY query ORDER BY c DESC LIMIT %s""",
                (limit,))
    return [{"query": r[0], "count": int(r[1]), "avg_results": round(float(r[2] or 0), 1)}
            for r in cur.fetchall()]


def low_coverage_queries(conn, max_results: int = 2, limit: int = 20) -> list[dict]:
    ensure_query_log(conn)
    cur = conn.cursor()
    cur.execute("""SELECT query, count(*) AS c FROM query_log
                   WHERE result_count <= %s AND coalesce(query,'') <> ''
                   GROUP BY query ORDER BY c DESC LIMIT %s""", (max_results, limit))
    return [{"query": r[0], "count": int(r[1])} for r in cur.fetchall()]
