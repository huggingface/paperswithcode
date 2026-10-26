"""Bound concurrent catalog reads before they allocate DB and response state."""

from starlette.datastructures import Headers
from starlette.responses import HTMLResponse, JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


_CATALOG_RESOURCES = frozenset(
    {
        "papers",
        "tasks",
        "methods",
        "datasets",
        "evaluations",
        "metrics",
        "conferences",
        "organizations",
        "frameworks",
        "repositories",
        "authors",
        "areas",
        "search",
        "stats",
    }
)
_CATALOG_PAGES = _CATALOG_RESOURCES | {"paper", "orgs"}


# Read-only catalog queries sent as POST because their input is a large body.
_CATALOG_POST_READS = frozenset({"/api/v1/papers/lookup"})


def is_catalog_read(scope: Scope) -> bool:
    if scope["type"] != "http":
        return False
    path = scope["path"]
    if scope["method"] == "POST":
        return path.rstrip("/") in _CATALOG_POST_READS
    if scope["method"] not in {"GET", "HEAD"}:
        return False
    if path.startswith("/api/v1/"):
        return path.removeprefix("/api/v1/").split("/", 1)[0] in _CATALOG_RESOURCES
    return path == "/" or path.strip("/").split("/", 1)[0] in _CATALOG_PAGES


class CatalogAdmissionMiddleware:
    """Shed excess reads without queueing; reserve capacity for chat/control.

    Eight catalog requests per worker leaves room in the 15-connection DB pool
    for chat. Keep the slot until the ASGI response and dependency cleanup finish,
    including streaming responses. Counters are local to each worker/event loop.
    """

    def __init__(self, app: ASGIApp, limit: int = 8) -> None:
        self.app = app
        self.limit = limit
        self.active = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not is_catalog_read(scope):
            await self.app(scope, receive, send)
            return
        # No await between checking and reserving: admission is atomic on the
        # worker's event loop and never creates an unbounded waiting queue.
        if self.active >= self.limit:
            response = JSONResponse(
                {"detail": "Catalog is busy. Please retry shortly."},
                status_code=503,
                headers={"Retry-After": "1", "Cache-Control": "no-store"},
            )
            if not scope["path"].startswith("/api/") and "text/html" in Headers(
                scope=scope
            ).get("accept", ""):
                response = HTMLResponse(
                    '<!doctype html><html lang="en"><head>'
                    '<meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width, initial-scale=1">'
                    "<title>Please try again · Papers with Code</title>"
                    '</head><body style="font:18px system-ui;max-width:36rem;'
                    'margin:12vh auto;padding:24px">'
                    "<h1>Please try again</h1>"
                    "<p>Papers with Code is busy. Please try again in a moment.</p>"
                    '<a href="">Try again</a></body></html>',
                    status_code=503,
                    headers={"Retry-After": "1", "Cache-Control": "no-store"},
                )
            await response(scope, receive, send)
            return
        self.active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.active -= 1
