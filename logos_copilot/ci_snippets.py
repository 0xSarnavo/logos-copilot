"""Snippet CI gate: extract fenced code blocks from docs/recipes and run them through logos-doctest,
so the system only ships code that actually executes. Unsupported languages (Rust/Nim/TS) are
reported as skipped (they need a toolchain — use logos_scaffold/localnet for those).
"""
from __future__ import annotations

import os
import re
import sys

from .doctest_runner import RUNTIME, verify_snippet

# language tag optional so untagged ```...``` blocks are still counted (as skipped), not dropped
FENCE = re.compile(r"```([A-Za-z0-9_+-]*)\n(.*?)```", re.DOTALL)


def extract_blocks(markdown: str) -> list[dict]:
    return [{"lang": m.group(1).lower(), "code": m.group(2)} for m in FENCE.finditer(markdown)]


def verify_markdown(markdown: str) -> list[dict]:
    out = []
    for b in extract_blocks(markdown):
        if not b["lang"]:
            out.append({"lang": "", "ok": None, "skipped": "no language tag"})
        elif b["lang"] in RUNTIME:
            r = verify_snippet(b["lang"], b["code"])
            out.append({"lang": b["lang"], "ok": r["ok"], "error": r.get("error")})
        else:
            out.append({"lang": b["lang"], "ok": None, "skipped": "no runtime for this language"})
    return out


def verify_dir(path: str) -> dict:
    ran = passed = failed = skipped = 0
    files = []
    for root, _, names in os.walk(path):
        for fn in names:
            if not fn.endswith((".md", ".mdx")):
                continue
            with open(os.path.join(root, fn), encoding="utf-8", errors="ignore") as f:
                res = verify_markdown(f.read())
            for r in res:
                if r["ok"] is True:
                    passed += 1
                    ran += 1
                elif r["ok"] is False:
                    failed += 1
                    ran += 1
                else:
                    skipped += 1
            if res:
                files.append({"file": fn, "blocks": res})
    return {"ran": ran, "passed": passed, "failed": failed, "skipped": skipped, "files": files}


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "recipes"
    summary = verify_dir(target)
    print(f"snippets ran={summary['ran']} passed={summary['passed']} "
          f"failed={summary['failed']} skipped={summary['skipped']}")
    sys.exit(1 if summary["failed"] else 0)
