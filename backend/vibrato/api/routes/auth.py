from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from ...services import auth_service
from ..deps import SESSION_COOKIE, User, get_current_user, require_owner
from ..errors import NotFound

router = APIRouter(tags=["auth"])


class InviteCreate(BaseModel):
    display_name: str = "Tester"


def _user_payload(user: User) -> dict[str, Any]:
    return {"id": user.id, "display_name": user.display_name, "is_owner": user.is_owner}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": _user_payload(user)}


@router.get("/auth/claim/{code}")
def claim(code: str, request: Request) -> RedirectResponse:
    try:
        user, token, max_age = auth_service.claim_invite(code)
    except KeyError:
        raise NotFound("This invite link is invalid or has been removed.") from None
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return response


@router.post("/auth/logout")
def logout(request: Request) -> JSONResponse:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        auth_service.logout(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/auth/invites")
def list_invites(user: User = Depends(require_owner)) -> dict[str, Any]:
    return {"invites": auth_service.list_tester_invites()}


@router.post("/auth/invites")
def create_invite(body: InviteCreate, user: User = Depends(require_owner)) -> dict[str, Any]:
    return {"invite": auth_service.create_tester_invite(body.display_name)}
