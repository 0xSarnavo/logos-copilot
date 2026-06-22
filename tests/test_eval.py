from logos_copilot.eval import _match, gate


def test_match():
    c = {"repo": "logos-storage", "kind": "recipe",
         "path": "recipes/codex-waku.md", "url": "http://x/codex"}
    assert _match(c, {"kind": "recipe"})
    assert _match(c, {"component": "logos-storage", "path_contains": "codex-waku"})
    assert not _match(c, {"kind": "doc"})
    assert not _match(c, {"path_contains": "nope"})
    assert not _match(c, {"component": "logos-messaging"})


def test_gate():
    assert gate({"hit_at_k": 0.8, "mrr": 0.6})
    assert not gate({"hit_at_k": 0.5, "mrr": 0.6})       # hit too low
    assert not gate({"hit_at_k": 0.8, "mrr": 0.2})       # mrr too low
