"""CSRF defence for cookie-authenticated requests.

Browsers only attach a custom header to a cross-origin request after a CORS
preflight, and the backend accepts no cross-origin callers. So requiring
`X-JetStream-Client: web` on every unsafe cookie-authenticated request blocks
form posts and multipart uploads from other sites, which SameSite=Lax alone
would not. Bearer-authenticated requests carry no ambient credentials and are
exempt.
"""

from __future__ import annotations

from fastapi import Request

CLIENT_HEADER = "X-JetStream-Client"
CLIENT_HEADER_VALUE = "web"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CSRFError(Exception):
    """The request needs the client header and did not send it."""


def has_client_header(request: Request) -> bool:
    return request.headers.get(CLIENT_HEADER) == CLIENT_HEADER_VALUE


def enforce_csrf(request: Request, *, cookie_authenticated: bool) -> None:
    """Raise `CSRFError` for an unsafe, cookie-authenticated request missing the header."""
    if request.method in SAFE_METHODS or not cookie_authenticated:
        return
    if not has_client_header(request):
        raise CSRFError


def enforce_client_header(request: Request) -> None:
    """For unauthenticated browser endpoints (login, signup, public accept)."""
    if request.method not in SAFE_METHODS and not has_client_header(request):
        raise CSRFError
