from logos_copilot.registry import resolve, component_for_org


def test_resolve_legacy_alias_warns():
    r = resolve("Nomos")
    assert r and r["component_id"] == "logos-blockchain"
    assert r["is_legacy_name"] is True
    assert r["warning"]


def test_resolve_canonical_no_warning():
    r = resolve("logos-storage")
    assert r and r["current_repo"].startswith("logos-storage/")
    assert r["is_legacy_name"] is False
    assert r["warning"] is None


def test_resolve_unknown():
    assert resolve("definitely-not-a-thing") is None


def test_component_for_org():
    assert component_for_org("logos-blockchain") == "logos-blockchain"
    assert component_for_org("logos-co") == "logos-co"
    assert component_for_org("vacp2p") == "logos-co"
