from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..audio.errors import UserFacingError
from ..logging_setup import get_logger
from ..services.importer import DuplicateRecording

log = get_logger("api")
STATUS_BY_CODE = {
    "not_found": 404,
    "file_missing": 404,
    "duplicate": 409,
    "too_large": 413,
    "model_unavailable": 424,
    "canonical_missing": 410,
    "unauthorized": 401,
    "forbidden": 403,
}


class NotFound(UserFacingError):
    def __init__(self, what: str) -> None:
        super().__init__(
            what=what,
            why="It may have been deleted or never existed.",
            action="Refresh the view.",
            code="not_found",
        )


class Unauthorized(UserFacingError):
    def __init__(self, what: str = "Sign in to continue.") -> None:
        super().__init__(
            what=what,
            why="You are not signed in, or your session has expired.",
            action="Use your invite link to sign in again.",
            code="unauthorized",
        )


class Forbidden(UserFacingError):
    def __init__(self, what: str = "This action is restricted.") -> None:
        super().__init__(
            what=what,
            why="Only the site owner can do this.",
            action="Ask the site owner if you need this.",
            code="forbidden",
        )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(UserFacingError)
    async def user_facing(_: Request, exc: UserFacingError) -> JSONResponse:
        return JSONResponse(status_code=STATUS_BY_CODE.get(exc.code, 422), content={"error": exc.to_dict()})

    @app.exception_handler(DuplicateRecording)
    async def duplicate(_: Request, exc: DuplicateRecording) -> JSONResponse:
        existing = exc.existing
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "duplicate",
                    "what": f"This file is already in the project as '{existing.get('name')}'.",
                    "why": "Its audio content is identical (same content hash).",
                    "action": "Use the existing recording, or import it again with 'allow duplicate' if you really want a second copy.",
                    "details": [],
                    "existing_id": existing.get("id"),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "what": "The request was not understood.",
                    "why": "Some fields were missing or had the wrong type.",
                    "action": "Reload the page and try again.",
                    "details": [
                        str(e.get("msg")) + " at " + ".".join(str(p) for p in e.get("loc", []))
                        for e in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled API error")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "what": "Something went wrong on the analysis server.",
                    "why": f"{type(exc).__name__}: {exc}",
                    "action": "Try again. If it persists, export a debug bundle from Settings > Advanced.",
                    "details": [],
                }
            },
        )
