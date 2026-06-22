from logos_copilot.ingest import SKIP_PATH, SKIP_DIRS


def test_skip_path_matches_deprecated_legacy():
    assert SKIP_PATH.search("deprecated/carnot/spec.md")
    assert SKIP_PATH.search("src/legacy/old_api.rs")
    assert SKIP_PATH.search("docs/archive/notes.md")
    assert SKIP_PATH.search("a/old/b.md")


def test_skip_path_allows_normal():
    assert not SKIP_PATH.search("src/data/data.ts")
    assert not SKIP_PATH.search("specs/cryptarchia/consensus.md")
    assert not SKIP_PATH.search("openapi.yaml")


def test_skip_dirs_prunes_deprecated():
    assert "deprecated" in SKIP_DIRS and "legacy" in SKIP_DIRS and "node_modules" in SKIP_DIRS
