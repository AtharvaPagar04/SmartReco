import pytest
from sqlalchemy import select

from app.models import ExternalIdentity, User
from app.services.google_auth_service import GoogleAuthError, resolve_user


def claims(subject="google-sub", email="member@example.com", name="Google Member"):
    return {"sub": subject, "email": email, "name": name}


@pytest.mark.asyncio
async def test_verified_google_identity_links_existing_member(db_session, regular_user):
    identity_claims = claims(email=regular_user.email, name="Verified Name")
    user, outcome = await resolve_user(db_session, identity_claims)
    await db_session.commit()

    assert user.id == regular_user.id
    assert outcome == "GOOGLE_IDENTITY_LINKED"
    identity = await db_session.scalar(select(ExternalIdentity).where(ExternalIdentity.provider_subject == "google-sub"))
    assert identity.user_id == regular_user.id
    assert user.password_hash


@pytest.mark.asyncio
async def test_new_google_identity_creates_regular_user_without_password(db_session):
    user, outcome = await resolve_user(db_session, claims(email="new@example.com"))
    await db_session.commit()

    assert outcome == "GOOGLE_ACCOUNT_CREATED"
    assert user.role == "USER"
    assert user.password_hash is None
    assert await db_session.scalar(select(ExternalIdentity).where(ExternalIdentity.user_id == user.id))


@pytest.mark.asyncio
async def test_google_does_not_auto_link_admin(db_session, admin_user):
    with pytest.raises(GoogleAuthError, match="standard sign-in"):
        await resolve_user(db_session, claims(email=admin_user.email))


@pytest.mark.asyncio
async def test_existing_subject_remains_same_user_when_email_changes(db_session, regular_user):
    identity = ExternalIdentity(user_id=regular_user.id, provider="GOOGLE", provider_subject="stable-sub", email_at_link_time=regular_user.email)
    db_session.add(identity)
    await db_session.commit()

    user, outcome = await resolve_user(db_session, claims(subject="stable-sub", email="changed@example.com"))
    await db_session.commit()

    assert user.id == regular_user.id
    assert outcome == "GOOGLE_AUTH_SUCCEEDED"
    assert identity.email_at_link_time == "changed@example.com"
