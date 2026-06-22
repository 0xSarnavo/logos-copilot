"""Postgres access via pg8000 (pure-Python driver — installs anywhere, incl. Python 3.14).

Vectors are passed as `'[...]'::vector` text literals so no driver-specific adapter is required.
"""
from __future__ import annotations

import urllib.parse

import pg8000.dbapi

from .config import settings


def connect():
    u = urllib.parse.urlparse(settings.database_url)
    return pg8000.dbapi.connect(
        user=u.username or "logos",
        password=u.password or "logos",
        host=u.hostname or "localhost",
        port=u.port or 5432,
        database=(u.path or "").lstrip("/") or "logos_copilot",
    )


def fetch_dicts(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def vec_literal(vec) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
