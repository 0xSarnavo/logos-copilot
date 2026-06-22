"""GitHub webhook handling for real-time freshness.

Pure, testable core: HMAC-SHA256 signature verification + event→repo extraction. The actual HTTP
endpoint (Phase-3 deploy) should validate the signature, enqueue the repo, and return 2xx in <10s;
a worker then calls refresh.refresh_repo. `process` wires verify→parse→refresh for a simple worker.
"""
from __future__ import annotations

import hashlib
import hmac

REFRESH_EVENTS = {"push", "release", "create"}


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Validate the X-Hub-Signature-256 header against the raw request body."""
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def repos_from_event(event: str, payload: dict) -> list[str]:
    """Repos to refresh for a webhook event (empty for events we ignore)."""
    if event not in REFRESH_EVENTS:
        return []
    full = ((payload or {}).get("repository") or {}).get("full_name")
    return [full] if full else []


def process(conn, embedder, secret, event, body: bytes, signature_header, payload) -> dict:
    """Verify + parse + refresh. Returns a summary; raises PermissionError on bad signature."""
    if not verify_signature(secret, body, signature_header):
        raise PermissionError("invalid webhook signature")
    from .refresh import refresh_repo
    results = [refresh_repo(conn, embedder, r) for r in repos_from_event(event, payload)]
    return {"event": event, "refreshed": results}
