from __future__ import annotations

from app.services.auth import _hash_password, _verify_password, create_jwt_token, decode_jwt_token


def test_hash_and_verify_password():
    pw_hash, salt = _hash_password("secret123")
    assert pw_hash
    assert salt
    assert _verify_password("secret123", pw_hash)


def test_verify_wrong_password():
    pw_hash, _ = _hash_password("correct")
    assert not _verify_password("wrong", pw_hash)


def test_jwt_roundtrip():
    # Uses default dev secret from settings
    token = create_jwt_token("user1", "admin")
    assert token
    payload = decode_jwt_token(token)
    assert payload is not None
    assert payload["sub"] == "user1"
    assert payload["role"] == "admin"


def test_decode_invalid_token():
    assert decode_jwt_token("not.a.valid.token") is None
