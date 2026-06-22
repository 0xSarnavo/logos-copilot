"""Symbol/signature index for exact `get_api_signature` lookups (grounded, never invented).

MVP uses language-aware regexes (no heavy tree-sitter wheels — keeps it runnable on any Python).
tree-sitter / cAST is the documented upgrade. OpenAPI endpoints are extracted from path keys.
"""
from __future__ import annotations

import re

from .db import fetch_dicts

LANG_BY_EXT = {
    ".rs": "rust", ".ts": "ts", ".tsx": "ts", ".js": "js", ".mjs": "js",
    ".py": "python", ".nim": "nim", ".go": "go", ".sol": "solidity",
}

# (compiled regex capturing the symbol name in group 'n', kind)
_PATTERNS: dict[str, list[tuple[re.Pattern, str]]] = {
    "rust": [
        (re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(?P<n>[A-Za-z_]\w*)"), "fn"),
        (re.compile(r"^\s*(?:pub\s+)?struct\s+(?P<n>[A-Za-z_]\w*)"), "struct"),
        (re.compile(r"^\s*(?:pub\s+)?enum\s+(?P<n>[A-Za-z_]\w*)"), "enum"),
        (re.compile(r"^\s*(?:pub\s+)?trait\s+(?P<n>[A-Za-z_]\w*)"), "trait"),
    ],
    "ts": [
        (re.compile(r"^\s*export\s+(?:async\s+)?function\s+(?P<n>[A-Za-z_$]\w*)"), "fn"),
        (re.compile(r"^\s*export\s+(?:abstract\s+)?class\s+(?P<n>[A-Za-z_$]\w*)"), "class"),
        (re.compile(r"^\s*export\s+const\s+(?P<n>[A-Za-z_$]\w*)\s*=\s*(?:async\s*)?\("), "fn"),
        (re.compile(r"^\s*export\s+interface\s+(?P<n>[A-Za-z_$]\w*)"), "interface"),
    ],
    "python": [
        (re.compile(r"^\s*(?:async\s+)?def\s+(?P<n>[A-Za-z_]\w*)"), "fn"),
        (re.compile(r"^\s*class\s+(?P<n>[A-Za-z_]\w*)"), "class"),
    ],
    "nim": [
        (re.compile(r"^\s*(?:proc|func|method|template|macro)\s+(?P<n>[A-Za-z_]\w*)\*?"), "proc"),
    ],
    "go": [
        (re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(?P<n>[A-Za-z_]\w*)\s*\("), "fn"),
    ],
    "solidity": [
        (re.compile(r"^\s*function\s+(?P<n>[A-Za-z_]\w*)\s*\("), "fn"),
    ],
}
_JS_FOR_TS = _PATTERNS["ts"]
_OPENAPI_PATH = re.compile(r"""^\s*["']?(?P<p>/[^"'\s:]+)["']?\s*:\s*$""")


def _lang(path: str) -> str | None:
    dot = path.rfind(".")
    return LANG_BY_EXT.get(path[dot:].lower()) if dot != -1 else None


def extract_symbols(path: str, text: str) -> list[dict]:
    """Return [{name, kind, signature, language, line_start}] for a source/OpenAPI file."""
    out: list[dict] = []
    p = path.lower()
    if "openapi" in p and (p.endswith(".yaml") or p.endswith(".yml") or p.endswith(".json")):
        for i, line in enumerate(text.splitlines(), start=1):
            m = _OPENAPI_PATH.match(line)
            if m:
                out.append({"name": m.group("p"), "kind": "endpoint",
                            "signature": m.group("p"), "language": "openapi", "line_start": i})
        return out
    lang = _lang(path)
    if not lang:
        return out
    patterns = _JS_FOR_TS if lang == "js" else _PATTERNS.get(lang, [])
    for i, line in enumerate(text.splitlines(), start=1):
        for rx, kind in patterns:
            m = rx.match(line)
            if m:
                out.append({"name": m.group("n"), "kind": kind,
                            "signature": line.strip()[:240], "language": lang, "line_start": i})
                break
    return out


SCHEMA = """
CREATE TABLE IF NOT EXISTS symbols (
  id bigserial PRIMARY KEY,
  repo text,
  component text NOT NULL,
  version text NOT NULL DEFAULT 'latest',
  file_path text NOT NULL,
  name text NOT NULL,
  kind text NOT NULL,
  signature text NOT NULL,
  language text,
  line_start int,
  git_sha text,
  url text,
  indexed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (repo, file_path, name, line_start)
);
CREATE INDEX IF NOT EXISTS symbols_name_idx ON symbols (component, lower(name));
CREATE INDEX IF NOT EXISTS symbols_name_only_idx ON symbols (lower(name));
"""


def ensure_symbols(conn) -> None:
    cur = conn.cursor()
    for stmt in filter(str.strip, SCHEMA.split(";")):
        cur.execute(stmt)
    conn.commit()


def upsert_symbols(conn, *, repo, component, version, git_sha, url_for, symbols) -> int:
    cur = conn.cursor()
    # Authoritative per (repo, file): clear old rows for each file in this batch so moved/renamed/
    # removed symbols don't linger. Scoped by repo so same-named files in sibling repos don't clash.
    for fp in {s["file_path"] for s in symbols}:
        cur.execute("DELETE FROM symbols WHERE repo=%s AND file_path=%s", (repo, fp))
    n = 0
    for s in symbols:
        cur.execute(
            """INSERT INTO symbols
               (repo, component, version, file_path, name, kind, signature, language, line_start,
                git_sha, url)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (repo, file_path, name, line_start) DO UPDATE SET
                 signature=EXCLUDED.signature, kind=EXCLUDED.kind, git_sha=EXCLUDED.git_sha,
                 indexed_at=now()""",
            (repo, component, version, s["file_path"], s["name"], s["kind"], s["signature"],
             s["language"], s["line_start"], git_sha, url_for(s["file_path"])),
        )
        n += 1
    conn.commit()
    return n


def lookup_symbol(conn, name: str, component: str | None = None, limit: int = 10) -> list[dict]:
    raw = (name or "").strip().lower()
    bare = raw.lstrip("/")
    if not bare:                       # empty / whitespace / '/'-only -> no match (not "everything")
        return []
    # endpoint queries may or may not carry a leading slash; match all forms exactly
    variants = list({raw, bare, "/" + bare})
    esc = bare.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")  # neutralize LIKE metachars
    ph = ",".join(["%s"] * len(variants))
    cur = conn.cursor()
    cur.execute(
        f"""SELECT repo, component, file_path, name, kind, signature, language, line_start, url,
                   git_sha
            FROM symbols
            WHERE (lower(name) IN ({ph})
                   OR lower(name) LIKE %s ESCAPE '\\'
                   OR lower(name) LIKE %s ESCAPE '\\')
              AND (%s::text IS NULL OR component = %s::text)
            ORDER BY (lower(name) IN ({ph})) DESC, length(name) ASC
            LIMIT %s""",
        (*variants, esc + "%", "%" + esc + "%", component, component, *variants, limit),
    )
    return fetch_dicts(cur)
