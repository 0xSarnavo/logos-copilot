from logos_copilot.scrape import classify_repo, is_fresh, should_include

NOW = "2026-06-22T00:00:00+00:00"


def _r(**kw):
    base = {
        "name": "logos-blockchain",
        "full_name": "logos-blockchain/logos-blockchain",
        "language": "Rust",
        "archived": False,
        "fork": False,
        "pushed_at": "2026-06-01T00:00:00Z",
    }
    base.update(kw)
    return base


def test_is_fresh():
    assert is_fresh("2026-06-01T00:00:00Z", NOW, 365) is True
    assert is_fresh("2025-07-01T00:00:00Z", NOW, 365) is True
    assert is_fresh("2024-01-01T00:00:00Z", NOW, 365) is False


def test_classify():
    assert classify_repo(_r(name="logos-blockchain", language="Rust")) == "code"
    assert classify_repo(_r(name="logos-blockchain-specs")) == "spec"
    assert classify_repo(_r(name="logos-lips")) == "spec"
    assert classify_repo(_r(name="docs.waku.org", language="JavaScript")) == "doc"
    assert classify_repo(_r(name="build.logos.co", language="JavaScript")) == "doc"
    assert classify_repo(_r(name="logos-rust-sdk")) == "sdk"
    assert classify_repo(_r(name="logos-storage-go-bindings", language="Go")) == "sdk"
    assert classify_repo(_r(name="ethcc-demo", language="Vue")) == "example"
    assert classify_repo(_r(name=".github", language=None)) is None
    assert classify_repo(_r(name="some-random-thing", language=None)) is None


def test_should_include_filters():
    assert should_include(_r(), NOW, 365) is True
    assert should_include(_r(archived=True), NOW, 365) is False
    assert should_include(_r(fork=True), NOW, 365) is False
    assert should_include(_r(pushed_at="2023-01-01T00:00:00Z"), NOW, 365) is False  # >1yr stale
