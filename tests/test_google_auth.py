import base64
import hashlib
import re
from datetime import datetime, timezone

from authlib.jose import JsonWebKey, jwt
import pytest
from sqlalchemy import select

import app.routers.auth as auth_router
import app.services.google_auth_service as google_service
from app.config import settings
from app.models import ExternalIdentity, User
from app.services.google_auth_service import GoogleAuthError, new_oauth_state, validate_oauth_state, verify_callback


def csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)', html).group(1)


@pytest.mark.asyncio
async def test_google_start_creates_state_nonce_pkce_and_safe_next(client, monkeypatch):
    monkeypatch.setattr(settings, "google_auth_enabled", True)
    captured = {}

    async def fake_authorization_url(oauth):
        captured.update(oauth)
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={oauth['state']}"

    monkeypatch.setattr(auth_router, "authorization_url", fake_authorization_url)
    response = await client.get("/auth/google?next=https://attacker.example")

    assert response.status_code == 302
    assert captured["next_path"] == "/"
    assert len(captured["state"]) >= 32
    assert len(captured["nonce"]) >= 32
    expected = base64.urlsafe_b64encode(hashlib.sha256(captured["code_verifier"].encode()).digest()).rstrip(b"=").decode()
    assert captured["code_challenge"] == expected
    assert "client_secret" not in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_rejects_state_reuse_or_mismatch(client, monkeypatch):
    monkeypatch.setattr(settings, "google_auth_enabled", True)
    async def fake_authorization_url(oauth):
        return f"https://accounts.google.com/auth?state={oauth['state']}"
    monkeypatch.setattr(auth_router, "authorization_url", fake_authorization_url)
    await client.get("/auth/google?next=/path-builder")

    rejected = await client.get("/auth/google/callback?state=wrong&code=code")
    assert rejected.status_code == 303
    assert rejected.headers["location"] == "/login?next=/path-builder"
    login = await client.get("/login?next=/path-builder")
    assert "could not be completed" in login.text


@pytest.mark.asyncio
async def test_google_callback_creates_user_and_redirects_to_safe_path(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "google_auth_enabled", True)
    captured = {}

    async def fake_authorization_url(oauth):
        captured.update(oauth)
        return f"https://accounts.google.com/auth?state={oauth['state']}"

    async def fake_verify_callback(code, oauth, received_state):
        assert code == "one-time-code"
        return {"sub": "callback-sub", "email": "new@example.com", "name": "New Member"}

    monkeypatch.setattr(auth_router, "authorization_url", fake_authorization_url)
    monkeypatch.setattr(auth_router, "verify_callback", fake_verify_callback)
    await client.get("/auth/google?next=/path-builder")
    response = await client.get(f"/auth/google/callback?state={captured['state']}&code=one-time-code")

    assert response.status_code == 303
    assert response.headers["location"] == "/path-builder"
    user = await db_session.scalar(select(User).where(User.email == "new@example.com"))
    assert user.role == "USER"
    assert user.password_hash is None
    assert await db_session.scalar(select(ExternalIdentity).where(ExternalIdentity.provider_subject == "callback-sub"))


@pytest.mark.asyncio
async def test_google_only_user_has_generic_password_failure(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "google_auth_enabled", False)
    user = User(full_name="Google Only", email="google-only@example.com", password_hash=None, role="USER")
    db_session.add(user)
    await db_session.commit()
    login = await client.get("/login")
    response = await client.post("/login", data={"email": user.email, "password": "anything", "csrf_token": csrf(login.text)})
    assert response.status_code == 200
    assert "Email or password is incorrect." in response.text


def test_oauth_state_rejects_future_and_expired_values(monkeypatch):
    state = new_oauth_state("/")
    state["created_at"] += 1
    with pytest.raises(GoogleAuthError):
        validate_oauth_state(state, state["state"])
    state["created_at"] -= 3
    monkeypatch.setattr(settings, "google_oauth_state_ttl_seconds", 1)
    with pytest.raises(GoogleAuthError):
        validate_oauth_state(state, state["state"])


@pytest.mark.asyncio
async def test_id_token_signature_audience_issuer_and_nonce_are_verified(monkeypatch):
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test-key"})
    claims = {
        "iss": "https://accounts.google.com",
        "sub": "verified-sub",
        "aud": "test-client",
        "exp": int(datetime.now(timezone.utc).timestamp()) + 600,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "nonce": "nonce-value",
        "email": "verified@example.com",
        "email_verified": True,
    }
    token = jwt.encode({"alg": "RS256", "kid": "test-key"}, claims, key).decode()
    metadata = {"authorization_endpoint": "https://accounts.google.com/auth", "token_endpoint": "https://accounts.google.com/token", "jwks_uri": "https://accounts.google.com/keys"}
    monkeypatch.setattr(settings, "google_client_id", "test-client")
    monkeypatch.setattr(google_service, "_discovery", lambda: _async_value(metadata))
    monkeypatch.setattr(google_service, "_exchange_code", lambda code, verifier, discovery: _async_value({"id_token": token}))
    monkeypatch.setattr(google_service.httpx, "AsyncClient", lambda **kwargs: _JWKSClient({"keys": [key.as_dict(is_private=False)]}))

    oauth = new_oauth_state("/")
    oauth["nonce"] = "nonce-value"
    verified = await verify_callback("code", oauth, oauth["state"])
    assert verified["sub"] == "verified-sub"

    oauth["nonce"] = "different-nonce"
    with pytest.raises(GoogleAuthError):
        await verify_callback("code", oauth, oauth["state"])


async def _async_value(value):
    return value


class _JWKSResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _JWKSClient:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url):
        return _JWKSResponse(self.payload)
