"""Component rename/alias map (verified 2026-06-22) + resolution.

Pure logic — no DB/network — so it is trivially testable and also seeds the `components` table.
"""
from __future__ import annotations

# id, canonical, current_repo, [aliases...], deprecation_note(for legacy aliases)
SEED: list[tuple[str, str, str, list[str], str]] = [
    (
        "logos-blockchain", "Logos Network", "logos-blockchain/logos-blockchain",
        ["nomos", "logos-co/nomos"],
        "'Nomos' is the legacy name; the project is now Logos Blockchain (logos-blockchain org).",
    ),
    (
        "logos-storage", "Logos Storage", "logos-storage/logos-storage-nim",
        ["codex", "codex-storage/nim-codex", "codex-storage/codex-js"],
        "'Codex' is the legacy name; the project is now Logos Storage (logos-storage org).",
    ),
    (
        "logos-messaging", "Logos Messaging", "logos-messaging/logos-delivery",
        ["waku", "waku-org", "vacp2p/waku", "js-waku"],
        "'Waku'/'js-waku' are legacy; use @waku/sdk under Logos Messaging (logos-delivery).",
    ),
    (
        "logos-co", "Logos Core", "logos-co",
        [], "",
    ),
]


def component_for_org(org: str) -> str:
    """Map a GitHub org to a component id (logos-co is the catch-all core)."""
    return org if org in {"logos-blockchain", "logos-storage", "logos-messaging"} else "logos-co"


def resolve(name: str) -> dict | None:
    """Resolve a user-supplied component/alias name to its canonical record.

    Returns None if unknown. Sets is_legacy_name/warning when matched via a legacy alias.
    """
    key = name.strip().lower()
    for cid, canonical, repo, aliases, note in SEED:
        alias_l = [a.lower() for a in aliases]
        if key == cid.lower() or key == canonical.lower() or key in alias_l:
            is_legacy = key in alias_l
            former = aliases[0].title() if aliases else None   # first alias = the legacy name
            return {
                "component_id": cid,
                "canonical_name": canonical,
                "display_name": f"{canonical} (formerly {former})" if former else canonical,
                "former_name": former,
                "current_repo": repo,
                "queried_as": name,
                "is_legacy_name": is_legacy,
                "warning": note if (is_legacy and note) else None,
            }
    return None
