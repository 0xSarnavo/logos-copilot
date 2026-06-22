import asyncio

from logos_copilot import auth
from logos_copilot.auth import BearerAuthASGI, RateLimitASGI


async def _ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _run(mw, scope):
    sent = []

    async def send(m):
        sent.append(m)

    async def receive():
        return {"type": "http.request"}

    asyncio.run(mw(scope, receive, send))
    return [m.get("status") for m in sent if m.get("type") == "http.response.start"]


def test_rate_limit_blocks_after_burst():
    rl = RateLimitASGI(_ok_app, rate=2, per=60.0)
    scope = {"type": "http", "client": ("1.2.3.4", 0), "headers": []}
    assert _run(rl, scope) == [200]
    assert _run(rl, scope) == [200]
    assert _run(rl, scope) == [429]        # bucket empty -> throttled


def test_bearer_blocks_without_token(monkeypatch):
    monkeypatch.setattr(auth, "settings", type("S", (), {"auth_token": "secret"})())
    ba = BearerAuthASGI(_ok_app)
    assert _run(ba, {"type": "http", "headers": []}) == [401]
    # correct token passes
    scope = {"type": "http", "headers": [(b"authorization", b"Bearer secret")]}
    assert _run(ba, scope) == [200]


def test_bearer_noop_without_configured_token(monkeypatch):
    monkeypatch.setattr(auth, "settings", type("S", (), {"auth_token": None})())
    ba = BearerAuthASGI(_ok_app)
    assert _run(ba, {"type": "http", "headers": []}) == [200]   # loopback dev: no auth required
