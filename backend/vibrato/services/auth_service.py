from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from ..db import get_db
from ..logging_setup import get_logger
from ..store import auth as auth_store

log = get_logger("auth")
SESSION_TTL = timedelta(days=90)
INVITE_TTL = timedelta(days=14)


class InviteInvalid(Exception):
    pass


class AccessDenied(Exception):
    pass


def _invite_cutoff() -> str:
    return (datetime.now(UTC) - INVITE_TTL).isoformat(timespec="milliseconds")


def bootstrap_owner() -> str | None:
    with get_db().tx() as conn:
        auth_store.purge_expired_sessions(conn)
        owner = auth_store.find_owner(conn)
        if owner is None:
            owner = auth_store.create_user(conn, "Owner", is_owner=True)
        if auth_store.find_usable_invite(conn, owner["id"], _invite_cutoff()) is not None:
            return None
        return auth_store.create_invite(conn, owner["id"])["code"]


def claim_invite(code: str) -> tuple[dict[str, Any], str, int]:
    with get_db().tx() as conn:
        invite = auth_store.get_invite(conn, code)
        if invite is None:
            raise InviteInvalid(code)
        user = auth_store.get_user(conn, invite["user_id"])
        if user is None or user["disabled"]:
            raise InviteInvalid(code)
        if not auth_store.consume_invite(conn, code, _invite_cutoff()):
            raise InviteInvalid(code)
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(UTC) + SESSION_TTL).isoformat(timespec="milliseconds")
        auth_store.create_session(conn, user["id"], token, expires_at)
    return user, token, int(SESSION_TTL.total_seconds())


def logout(token: str) -> None:
    with get_db().tx() as conn:
        auth_store.delete_session(conn, token)


def create_tester(display_name: str, never_expires: bool = False) -> dict[str, Any]:
    with get_db().tx() as conn:
        user = auth_store.create_user(conn, display_name.strip()[:60] or "Tester", is_owner=False)
        return auth_store.create_invite(conn, user["id"], never_expires)


def list_testers() -> list[dict[str, Any]]:
    with get_db().read() as conn:
        return auth_store.list_testers(conn, _invite_cutoff())


def issue_new_link(user_id: str, keep_token: str | None) -> dict[str, Any]:
    with get_db().tx() as conn:
        user = auth_store.get_user(conn, user_id)
        if user is None:
            raise KeyError(user_id)
        auth_store.delete_invites(conn, user_id)
        auth_store.delete_sessions(conn, user_id, keep_token if user["is_owner"] else None)
        auth_store.set_disabled(conn, user_id, False)
        return auth_store.create_invite(conn, user_id)


def revoke(user_id: str) -> None:
    with get_db().tx() as conn:
        user = auth_store.get_user(conn, user_id)
        if user is None:
            raise KeyError(user_id)
        if user["is_owner"]:
            raise AccessDenied(user_id)
        auth_store.set_disabled(conn, user_id, True)
        auth_store.delete_invites(conn, user_id)
        auth_store.delete_sessions(conn, user_id)
