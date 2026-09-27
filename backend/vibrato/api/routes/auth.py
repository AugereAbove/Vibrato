from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from ...services import auth_service
from ..deps import SESSION_COOKIE, User, get_current_user, require_owner
from ..errors import Forbidden, NotFound

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
        _, token, max_age = auth_service.claim_invite(code)
    except auth_service.InviteInvalid:
        return RedirectResponse(url="/?invite=invalid", status_code=302)
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


@router.get("/auth/users")
def list_users(user: User = Depends(require_owner)) -> dict[str, Any]:
    return {"users": auth_service.list_testers()}


@router.post("/auth/invites")
def create_invite(body: InviteCreate, user: User = Depends(require_owner)) -> dict[str, Any]:
    return {"invite": auth_service.create_tester(body.display_name)}


@router.post("/auth/users/{user_id}/link")
def new_link(user_id: str, request: Request, user: User = Depends(require_owner)) -> dict[str, Any]:
    try:
        invite = auth_service.issue_new_link(user_id, request.cookies.get(SESSION_COOKIE))
    except KeyError:
        raise NotFound("This account does not exist.") from None
    return {"invite": invite}


@router.post("/auth/users/{user_id}/revoke")
def revoke(user_id: str, user: User = Depends(require_owner)) -> dict[str, Any]:
    try:
        auth_service.revoke(user_id)
    except KeyError:
        raise NotFound("This account does not exist.") from None
    except auth_service.AccessDenied:
        raise Forbidden("The owner account can't be revoked. Issue a new owner link instead.") from None
    return {"revoked": True}
