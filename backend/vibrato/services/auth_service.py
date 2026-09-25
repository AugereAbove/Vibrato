from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from ..db import get_db
from ..logging_setup import get_logger
from ..store import auth as auth_store

log = get_logger("auth")
SESSION_TTL = timedelta(days=90)


def bootstrap_owner() -> str | None:
    """Ensure a single owner user exists and has an unused invite code.

    Returns the code when one is freshly minted (so the caller can log it
    once), or None when an unused owner invite already exists.
    """
    with get_db().tx() as conn:
        owner = auth_store.find_owner(conn)
        if owner is None:
            owner = auth_store.create_user(conn, "Owner", is_owner=True)
        if auth_store.find_unused_invite_for_user(conn, owner["id"]) is not None:
            return None
        invite = auth_store.create_invite(conn, owner["id"])
        return invite["code"]


def claim_invite(code: str) -> tuple[dict[str, Any], str, int]:
    """Claim an invite code, returning (user, session_token, max_age_seconds)."""
    with get_db().tx() as conn:
        invite = auth_store.get_invite(conn, code)
        if invite is None:
            raise KeyError(code)
        user = auth_store.get_user(conn, invite["user_id"])
        if user is None:
            raise KeyError(code)
        auth_store.mark_invite_used(conn, code)
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(UTC) + SESSION_TTL).isoformat(timespec="milliseconds")
        auth_store.create_session(conn, user["id"], token, expires_at)
    return user, token, int(SESSION_TTL.total_seconds())


def logout(token: str) -> None:
    with get_db().tx() as conn:
        auth_store.delete_session(conn, token)


def create_tester_invite(display_name: str) -> dict[str, Any]:
    with get_db().tx() as conn:
        user = auth_store.create_user(conn, display_name.strip() or "Tester", is_owner=False)
        invite = auth_store.create_invite(conn, user["id"])
    return invite


def list_tester_invites() -> list[dict[str, Any]]:
    with get_db().read() as conn:
        return auth_store.list_tester_invites(conn)
