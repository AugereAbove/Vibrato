from __future__ import annotations

from typing import Any


class UserFacingError(Exception):
    def __init__(
        self, what: str, why: str, action: str, code: str = "error", details: list[str] | None = None
    ):
        super().__init__(what)
        self.what = what
        self.why = why
        self.action = action
        self.code = code
        self.details = details or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "what": self.what,
            "why": self.why,
            "action": self.action,
            "details": self.details,
        }


class AudioDecodeError(UserFacingError):
    pass


class AudioValidationError(UserFacingError):
    pass
