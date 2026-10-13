"""Refuses state-changing requests another site could make a signed-in browser send (ADR 0007)."""

from collections.abc import Iterable
from urllib.parse import urlsplit

from fastapi import Request, status
from starlette.types import ASGIApp, Receive, Scope, Send

from scopesteps.api.errors import error_response

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
JSON = "application/json"
MULTIPART = "multipart/form-data"
# What a browser reports for a request the page's own origin made, or the user typed.
SAME_ORIGIN_FETCH_SITES = frozenset({"same-origin", "none"})


class CrossSiteRequestGuard:
    """Mutating requests carry JSON, or prove they do not come from another origin.

    A page on another origin cannot send `application/json` without a CORS preflight, which only
    the configured origins pass, so a JSON body needs no further check. A form can be posted
    across origins freely, so form-encoded and plain-text bodies are refused outright. Multipart
    uploads and requests without a body are accepted only from a trusted origin, or from a client
    that sends no browser origin headers at all and so holds no ambient cookie to abuse.
    """

    def __init__(self, app: ASGIApp, trusted_origins: Iterable[str]) -> None:
        self.app = app
        self.trusted_origins = frozenset(origin.rstrip("/").lower() for origin in trusted_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type == JSON:
            await self.app(scope, receive, send)
            return
        if media_type not in {"", MULTIPART}:
            refusal = error_response(
                request,
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                code="UNSUPPORTED_MEDIA_TYPE",
                message="Requests that change data must send a JSON body",
            )
            await refusal(scope, receive, send)
            return
        if not self._is_from_a_trusted_origin(request):
            refusal = error_response(
                request,
                status.HTTP_403_FORBIDDEN,
                code="CROSS_SITE_REQUEST",
                message="This request came from another site and was refused",
            )
            await refusal(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _is_from_a_trusted_origin(self, request: Request) -> bool:
        origin = request.headers.get("origin")
        if origin is None:
            # Browsers send Origin on every request that is not a GET or HEAD; Sec-Fetch-Site
            # covers one that somehow omits it. Neither header means a non-browser client.
            fetch_site = request.headers.get("sec-fetch-site")
            return fetch_site is None or fetch_site.lower() in SAME_ORIGIN_FETCH_SITES
        origin = origin.rstrip("/").lower()
        if origin in self.trusted_origins:
            return True
        # The page's origin is the host the request was sent to: same origin, including through
        # the development proxy, which forwards the browser's Host header unchanged.
        host = request.headers.get("host", "").lower()
        return bool(host) and urlsplit(origin).netloc == host
