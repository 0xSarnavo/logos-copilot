import hashlib
import hmac

from logos_copilot.webhook import repos_from_event, verify_signature


def _sig(secret, body):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_ok():
    body = b'{"hello":"world"}'
    assert verify_signature("s3cret", body, _sig("s3cret", body)) is True


def test_verify_signature_bad():
    body = b'{"hello":"world"}'
    assert verify_signature("s3cret", body, _sig("wrong", body)) is False
    assert verify_signature("s3cret", body, "garbage") is False
    assert verify_signature("s3cret", body, None) is False
    assert verify_signature("", body, _sig("", body)) is False


def test_repos_from_event():
    payload = {"repository": {"full_name": "logos-co/logos-rust-sdk"}}
    assert repos_from_event("push", payload) == ["logos-co/logos-rust-sdk"]
    assert repos_from_event("release", payload) == ["logos-co/logos-rust-sdk"]
    assert repos_from_event("issues", payload) == []          # ignored event
    assert repos_from_event("push", {}) == []                  # no repo
