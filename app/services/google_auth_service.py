from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from authlib.integrations.base_client import OAuthError
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import JsonWebKey, jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ExternalIdentity, User
from app.security import normalize_email

logger = logging.getLogger(__name__)
GOOGLE_PROVIDER = "GOOGLE"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


class GoogleAuthError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)



def new_oauth_state(next_path: str) -> dict[str, Any]:
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return {
        "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32),
        "code_verifier": verifier,
        "code_challenge": challenge,
        "next_path": next_path,
        "created_at": int(time.time()),
    }


def validate_oauth_state(oauth: dict[str, Any], received_state: str | None) -> None:
    if not received_state or not secrets.compare_digest(received_state, str(oauth.get("state", ""))):
        raise GoogleAuthError("invalid_state", "Google sign-in could not be completed. Please try again.")
    try:
        age = int(time.time()) - int(oauth.get("created_at", 0))
    except (TypeError, ValueError) as exc:
        raise GoogleAuthError("invalid_state", "Google sign-in could not be completed. Please try again.") from exc
    if age < 0 or age > settings.google_oauth_state_ttl_seconds:
        raise GoogleAuthError("expired_state", "Google sign-in could not be completed. Please try again.")


async def _discovery() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=settings.google_request_timeout_seconds) as client:
            response = await client.get(settings.google_oidc_discovery_url)
            response.raise_for_status()
            metadata = response.json()
    except (httpx.HTTPError, OAuthError, ValueError) as exc:
        raise GoogleAuthError("provider_unavailable", "Google sign-in is temporarily unavailable. You can still use your SmartReco email and password.") from exc
    required = ("authorization_endpoint", "token_endpoint", "jwks_uri")
    if any(not metadata.get(key) for key in required):
        raise GoogleAuthError("provider_invalid", "Google sign-in could not be completed. Please try again.")
    return metadata


async def authorization_url(oauth: dict[str, Any]) -> str:
    metadata = await _discovery()
    client = AsyncOAuth2Client(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
        scope="openid email profile",
    )
    try:
        url, _ = client.create_authorization_url(
            metadata["authorization_endpoint"],
            state=oauth["state"],
            nonce=oauth["nonce"],
            code_challenge=oauth["code_challenge"],
            code_challenge_method="S256",
            response_type="code",
            scope="openid email profile",
        )
        return url

    finally:
        await client.aclose()


async def _exchange_code(code: str, code_verifier: str, metadata: dict[str, Any]) -> dict[str, Any]:
    client = AsyncOAuth2Client(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
    )
    try:
        return await client.fetch_token(
            metadata["token_endpoint"],
            code=code,
            redirect_uri=settings.google_redirect_uri,
            code_verifier=code_verifier,
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise GoogleAuthError("token_exchange_failed", "Google sign-in could not be completed. Please try again.") from exc
    finally:
        await client.aclose()


async def verify_callback(code: str, oauth: dict[str, Any], received_state: str | None) -> dict[str, str]:
    validate_oauth_state(oauth, received_state)
    if not code or not oauth.get("code_verifier") or not oauth.get("nonce"):
        raise GoogleAuthError("invalid_callback", "Google sign-in could not be completed. Please try again.")

    metadata = await _discovery()
    token = await _exchange_code(code, oauth["code_verifier"], metadata)
    raw_id_token = token.get("id_token")
    if not raw_id_token:
        raise GoogleAuthError("missing_id_token", "Google sign-in could not be completed. Please try again.")
    try:
        async with httpx.AsyncClient(timeout=settings.google_request_timeout_seconds) as client:
            response = await client.get(metadata["jwks_uri"])
            response.raise_for_status()
            key_set = JsonWebKey.import_key_set(response.json())
        claims = jwt.decode(
            raw_id_token,
            key_set,
            claims_options={
                "iss": {"essential": True, "values": GOOGLE_ISSUERS},
                "sub": {"essential": True},
                "aud": {"essential": True, "values": [settings.google_client_id]},
                "exp": {"essential": True},
                "iat": {"essential": True},
                "nonce": {"essential": True, "value": oauth["nonce"]},
            },
        )
        claims.validate(leeway=60)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise GoogleAuthError("invalid_id_token", "Google sign-in could not be completed. Please try again.") from exc
    except Exception as exc:
        # Authlib raises protocol-specific claim/signature errors. Do not expose them.
        raise GoogleAuthError("invalid_id_token", "Google sign-in could not be completed. Please try again.") from exc

    email = claims.get("email")
    subject = claims.get("sub")
    if not subject or not email or claims.get("email_verified") is not True:
        raise GoogleAuthError("unverified_identity", "Google sign-in could not be completed. Please try again.")
    return {
        "sub": str(subject),
        "email": normalize_email(str(email)),
        "name": str(claims.get("name") or "").strip()[:120],
    }


def _check_login_policy(user: User) -> None:
    if not user.is_active:
        raise GoogleAuthError("inactive_account", "This account cannot be signed in at this time.")
    if user.role == "ADMIN":
        raise GoogleAuthError("admin_password_required", "This account requires the standard sign-in method.")


async def resolve_user(db: AsyncSession, identity_claims: dict[str, str]) -> tuple[User, str]:
    subject = identity_claims["sub"]
    email = identity_claims["email"]
    identity = await db.scalar(select(ExternalIdentity).where(ExternalIdentity.provider == GOOGLE_PROVIDER, ExternalIdentity.provider_subject == subject))
    if identity:
        user = await db.scalar(select(User).where(User.id == identity.user_id))
        if not user:
            raise GoogleAuthError("identity_unavailable", "Google sign-in could not be completed. Please try again.")
        _check_login_policy(user)
        identity.email_at_link_time = email
        identity.display_name_at_link_time = identity_claims["name"] or identity.display_name_at_link_time
        identity.last_login_at = datetime.now(timezone.utc)
        user.last_login_at = datetime.now(timezone.utc)
        return user, "GOOGLE_AUTH_SUCCEEDED"

    user = await db.scalar(select(User).where(User.email == email))
    if user:
        _check_login_policy(user)
        outcome = "GOOGLE_IDENTITY_LINKED"
    else:
        user = User(full_name=identity_claims["name"] or email.split("@", 1)[0][:120], email=email, password_hash=None, role="USER")
        outcome = "GOOGLE_ACCOUNT_CREATED"
        try:
            async with db.begin_nested():
                db.add(user)
                await db.flush()
        except IntegrityError:
            user = await db.scalar(select(User).where(User.email == email))
            if not user:
                raise GoogleAuthError("identity_conflict", "Google sign-in could not be completed. Please try again.")
            _check_login_policy(user)
            outcome = "GOOGLE_IDENTITY_LINKED"

    identity = ExternalIdentity(
        user_id=user.id,
        provider=GOOGLE_PROVIDER,
        provider_subject=subject,
        email_at_link_time=email,
        display_name_at_link_time=identity_claims["name"] or None,
        last_login_at=datetime.now(timezone.utc),
    )
    try:
        async with db.begin_nested():
            db.add(identity)
            await db.flush()
    except IntegrityError:
        identity = await db.scalar(select(ExternalIdentity).where(ExternalIdentity.provider == GOOGLE_PROVIDER, ExternalIdentity.provider_subject == subject))
        if not identity:
            raise GoogleAuthError("identity_conflict", "Google sign-in could not be completed. Please try again.")
        user = await db.scalar(select(User).where(User.id == identity.user_id))
        if not user:
            raise GoogleAuthError("identity_unavailable", "Google sign-in could not be completed. Please try again.")
        _check_login_policy(user)
    user.last_login_at = datetime.now(timezone.utc)
    return user, outcome
