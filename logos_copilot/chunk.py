"""Document/code chunking + content hashing (pure logic).

MVP chunkers: markdown split on headings (carrying the nearest heading anchor), code split into
overlapping line windows. tree-sitter / cAST is the Phase-2 upgrade (see SPEC).
"""
from __future__ import annotations

import hashlib
import re

CODE_EXT = {".rs", ".nim", ".go", ".ts", ".tsx", ".js", ".mjs", ".py", ".c", ".cpp", ".h",
            ".hpp", ".sol", ".sh", ".nix", ".qml", ".rb", ".java", ".kt"}
DOC_EXT = {".md", ".mdx", ".markdown", ".rst", ".txt"}
OPENAPI_HINTS = ("openapi.yaml", "openapi.yml", "openapi.json")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.strip("# \n").lower()).strip("-")


def chunk_markdown(text: str, max_chars: int = 1500):
    """Yield (content, heading_anchor, line_start, line_end) splitting near headings/size."""
    out = []
    buf: list[str] = []
    anchor = None
    start_line = 1
    for i, line in enumerate(text.splitlines(keepends=True), start=1):
        if line.startswith("#") and buf:
            out.append(("".join(buf), anchor, start_line, i - 1))
            buf, start_line = [], i
        if line.startswith("#"):
            anchor = _slug(line)
        buf.append(line)
        if sum(len(b) for b in buf) >= max_chars:
            out.append(("".join(buf), anchor, start_line, i))
            buf, start_line = [], i + 1
    if buf:
        out.append(("".join(buf), anchor, start_line, start_line + len(buf) - 1))
    return [c for c in out if c[0].strip()]


def chunk_code(text: str, max_lines: int = 120, overlap: int = 20):
    """Yield (content, None, line_start, line_end) as overlapping line windows."""
    lines = text.splitlines()
    out = []
    i = 0
    step = max(1, max_lines - overlap)
    while i < len(lines):
        block = lines[i:i + max_lines]
        if any(b.strip() for b in block):
            out.append(("\n".join(block), None, i + 1, i + len(block)))
        i += step
    return out


def file_kind(path: str) -> str | None:
    """Classify a file path into a chunk kind, or None to skip."""
    p = path.lower()
    if any(p.endswith(h) for h in OPENAPI_HINTS) or "openapi" in p:
        return "openapi"
    dot = p.rfind(".")
    ext = p[dot:] if dot != -1 else ""
    if ext in DOC_EXT:
        return "doc"
    if ext in CODE_EXT:
        return "code"
    return None


def chunk_file(path: str, text: str):
    """Dispatch a file to the right chunker. Returns (kind, [chunks]) or (None, [])."""
    kind = file_kind(path)
    if kind is None:
        return None, []
    if kind == "doc":
        return kind, chunk_markdown(text)
    # code + openapi treated as code windows for the MVP
    return kind, chunk_code(text)
