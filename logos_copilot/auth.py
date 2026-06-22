"""Pure-ASGI auth + rate-limit middleware for the MCP HTTP app.

Pure ASGI (not BaseHTTPMiddleware) so it never buffers streaming/SSE responses. Bearer auth is
enforced only when AUTH_TOKEN is set (loopback dev needs none; main() refuses a public bind without
it). Rate limiting is a per-process token bucket keyed by token-or-IP — fine for a single node; use a
Redis-backed limiter for multi-node (documented in DEPLOYMENT.md).
"""
from __future__ import annotations

import hmac
import json
import time

from .config import settings


async def _send_json(send, status: int, obj: dict, extra_headers: dict | None = None) -> None:
    body = json.dumps(obj).encode()
    headers = [(b"content-type", b"application/json"),
               (b"content-length", str(len(body)).encode())]
    for k, v in (extra_headers or {}).items():
        headers.append((k.encode(), v.encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class BearerAuthASGI:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and settings.auth_token:
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode("latin-1")
            if not hmac.compare_digest(auth, f"Bearer {settings.auth_token}"):  # timing-safe
                await _send_json(send, 401, {"error": "unauthorized"},
                                 {"www-authenticate": "Bearer"})
                return
        await self.app(scope, receive, send)


class RateLimitASGI:
    """Token bucket: `rate` requests refilled over `per` seconds, per token-or-IP."""

    def __init__(self, app, rate: int = 120, per: float = 60.0, max_keys: int = 20000):
        self.app = app
        self.rate = rate
        self.per = per
        self.max_keys = max_keys
        self.buckets: dict[str, tuple[float, float]] = {}

    def _key(self, scope) -> str:
        # Key on client IP, NOT the attacker-controlled Authorization header (rotating it would
        # otherwise mint a fresh bucket and bypass the limit). Behind a trusted proxy, configure it
        # to pass the real client IP (or read a vetted X-Forwarded-For).
        client = scope.get("client")
        return client[0] if client else "anon"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        key = self._key(scope)
        now = time.monotonic()
        if len(self.buckets) > self.max_keys:           # bound memory: drop least-recently-seen half
            keep = sorted(self.buckets.items(), key=lambda kv: kv[1][1])[len(self.buckets) // 2:]
            self.buckets = dict(keep)
        tokens, last = self.buckets.get(key, (self.rate, now))
        tokens = min(self.rate, tokens + (now - last) * (self.rate / self.per))
        if tokens < 1:
            self.buckets[key] = (tokens, now)
            await _send_json(send, 429, {"error": "rate_limited"},
                             {"retry-after": str(int(self.per / self.rate) + 1)})
            return
        self.buckets[key] = (tokens - 1, now)
        await self.app(scope, receive, send)
