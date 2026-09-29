"""Domain errors. Services raise these; `main` renders them as `{detail, code}`."""

from __future__ import annotations

from typing import Any, NoReturn


class DomainError(Exception):
    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> None:
        self.detail = detail or self.default_detail()
        if code is not None:
            self.code = code
        self.fields = fields
        super().__init__(self.detail)

    def default_detail(self) -> str:
        return self.code.replace("_", " ").capitalize()


class NotFound(DomainError):
    """Also used for other workspaces' rows, so their IDs never leak."""

    status_code = 404
    code = "not_found"


class Forbidden(DomainError):
    status_code = 403
    code = "forbidden"


class Unauthorized(DomainError):
    status_code = 401
    code = "not_authenticated"


class Conflict(DomainError):
    """State conflicts, including optimistic-lock version mismatches."""

    status_code = 409
    code = "conflict"


class Gone(DomainError):
    status_code = 410
    code = "gone"


class Unprocessable(DomainError):
    status_code = 422
    code = "unprocessable"


class PayloadTooLarge(DomainError):
    status_code = 413
    code = "payload_too_large"


class RateLimited(DomainError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, retry_after_s: int, detail: str | None = None) -> None:
        super().__init__(detail or "Too many requests, try again later")
        self.retry_after_s = retry_after_s


class NotImplementedYet(DomainError):
    status_code = 501
    code = "not_implemented"


def not_implemented(feature: str) -> NoReturn:
    """The single 501 helper for endpoints whose service is not built yet."""
    raise NotImplementedYet(f"{feature} is not implemented yet")
