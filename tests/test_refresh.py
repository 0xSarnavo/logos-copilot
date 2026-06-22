from logos_copilot import refresh
from logos_copilot.refresh import current_sha


def test_current_sha_rejects_bad_name():
    # validated before any subprocess/network — these return at the guard
    assert current_sha("not-a-repo") is None
    assert current_sha("a/b?inject") is None
    assert current_sha("../etc/passwd") is None
    assert current_sha("") is None


def test_refresh_repo_rejects_bad_name():
    # FULL_NAME_RE guard returns before touching conn/embedder (so None args are fine)
    assert refresh.refresh_repo(None, None, "bad name") == {"repo": "bad name", "action": "invalid"}
    assert refresh.refresh_repo(None, None, "a/b/c")["action"] == "invalid"
