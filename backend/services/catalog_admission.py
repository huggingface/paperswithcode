"""Bound concurrent catalog reads before they allocate DB and response state."""

from starlette.responses import JSONResponse
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


def is_catalog_read(scope: Scope) -> bool:
    if scope["type"] != "http" or scope["method"] not in {"GET", "HEAD"}:
        return False
    path = scope["path"]
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
            await JSONResponse(
                {"detail": "Catalog is busy. Please retry shortly."},
                status_code=503,
                headers={"Retry-After": "1", "Cache-Control": "no-store"},
            )(scope, receive, send)
            return
        self.active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.active -= 1
