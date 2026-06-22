"""Retrieval eval harness + CI gate (deterministic — no LLM needed, since the server is retrieval-only).

Runs each golden case through search() and scores Hit@k + MRR by whether a result matching `expect`
appears in the top-k. The CI gate fails the build if metrics regress below thresholds — so a chunking/
embedding/reranker change can't silently degrade retrieval.
"""
from __future__ import annotations

import json
import sys

import yaml

from .retrieve import citation, search


def _match(c: dict, expect: dict) -> bool:
    if "component" in expect and c.get("repo") != expect["component"]:
        return False
    if "kind" in expect and c.get("kind") != expect["kind"]:
        return False
    if "path_contains" in expect and expect["path_contains"] not in (c.get("path") or ""):
        return False
    if "url_contains" in expect and expect["url_contains"] not in (c.get("url") or ""):
        return False
    return True


def run_eval(golden_path: str, top_k: int = 8) -> dict:
    import os
    if not os.path.exists(golden_path):
        raise ValueError(f"golden file not found: {golden_path}")
    with open(golden_path) as f:
        doc = yaml.safe_load(f) or {}
    cases = doc.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"golden file has no top-level 'cases' list: {golden_path}")
    for idx, case in enumerate(cases):
        if not isinstance(case, dict) or "query" not in case or "expect" not in case:
            raise ValueError(f"golden case {idx} is missing 'query' or 'expect'")
    hits = 0
    rr = 0.0
    details = []
    for case in cases:
        rows = search(case["query"], component=case.get("component"),
                      kind=case.get("kind_filter"), top_k=top_k)
        rank = None
        for i, r in enumerate(rows):
            if _match(citation(r), case["expect"]):
                rank = i + 1
                break
        hits += 1 if rank else 0
        rr += (1.0 / rank) if rank else 0.0
        details.append({"query": case["query"], "rank": rank, "hit": rank is not None})
    n = len(cases) or 1
    return {"n": len(cases), "top_k": top_k, "hit_at_k": round(hits / n, 3),
            "mrr": round(rr / n, 3), "details": details}


def gate(metrics: dict, min_hit: float = 0.7, min_mrr: float = 0.4) -> bool:
    return metrics["hit_at_k"] >= min_hit and metrics["mrr"] >= min_mrr


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "eval/golden.yaml"
    try:
        m = run_eval(path)
    except ValueError as e:
        print("EVAL CONFIG ERROR:", e)
        sys.exit(2)
    print(json.dumps({k: m[k] for k in ("n", "top_k", "hit_at_k", "mrr")}, indent=2))
    for d in m["details"]:
        print(f"  {'HIT@'+str(d['rank']) if d['hit'] else 'MISS  ':<8} {d['query']}")
    ok = gate(m)
    print("GATE:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
