"""Schema delivery and anonymous browser access for the selected public reads."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.routing import Match

from backend.services.public_api_schema import (
    PUBLIC_ENDPOINTS,
    PUBLIC_SCHEMA_PATH,
    public_openapi,
)

router = APIRouter()


@router.get(PUBLIC_SCHEMA_PATH, include_in_schema=False)
def get_public_schema(request: Request):
    schema = getattr(request.app.state, "public_api_schema", None)
    if schema is None:
        schema = public_openapi(request.app)
        request.app.state.public_api_schema = schema
    return JSONResponse(schema, headers={"Cache-Control": "public, max-age=300"})


class PublicReadCorsMiddleware:
    """Match the actual GET route, so dynamic IDs cannot expose private routes."""

    def __init__(self, app, allowed_origins=()):
        self.app = app
        self.credentialed_origins = frozenset(allowed_origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"GET", "OPTIONS"}:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        origin = request.headers.get("origin")
        credentialed_origin = origin in self.credentialed_origins
        get_scope = {**scope, "method": "GET"}
        selected = self._is_public_route(get_scope)
        if selected is None and scope["app"].router.redirect_slashes:
            path = scope["path"]
            redirect_scope = {
                **get_scope,
                "path": path.rstrip("/") if path.endswith("/") else path + "/",
            }
            selected = self._is_public_route(redirect_scope)
        if not selected:
            await self.app(scope, receive, send)
            return
        if scope["method"] == "OPTIONS":
            if not origin or credentialed_origin:
                await self.app(scope, receive, send)
                return
            requested_method = request.headers.get("access-control-request-method", "")
            requested_headers = {
                name.strip().lower()
                for name in request.headers.get(
                    "access-control-request-headers", ""
                ).split(",")
                if name.strip()
            }
            if requested_method != "GET" or not requested_headers <= {
                "accept",
                "content-type",
            }:
                await self.app(scope, receive, send)
                return
            response = JSONResponse(
                None,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET",
                    "Access-Control-Allow-Headers": "Accept, Content-Type",
                    "Access-Control-Max-Age": "600",
                },
            )
            await response(scope, receive, send)
            return

        async def cors_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                vary = {
                    value.strip().lower()
                    for value in headers.get("Vary", "").split(",")
                }
                if "origin" not in vary:
                    headers.add_vary_header("Origin")
                if not origin:
                    await send(message)
                    return
                if credentialed_origin:
                    headers["Access-Control-Allow-Origin"] = origin
                    headers["Access-Control-Allow-Credentials"] = "true"
                else:
                    headers["Access-Control-Allow-Origin"] = "*"
                    if "Access-Control-Allow-Credentials" in headers:
                        del headers["Access-Control-Allow-Credentials"]
                exposed = headers.get("Access-Control-Expose-Headers", "")
                headers["Access-Control-Expose-Headers"] = (
                    f"{exposed}, Retry-After" if exposed else "Retry-After"
                )
            await send(message)

        await self.app(scope, receive, cors_send)

    @staticmethod
    def _is_public_route(scope):
        partial_match = False
        public_paths = {*PUBLIC_ENDPOINTS, PUBLIC_SCHEMA_PATH}
        for route in scope["app"].routes:
            match, _ = route.matches(scope)
            if match == Match.FULL:
                path = getattr(route, "path", "")
                if path in public_paths:
                    return True
                canonical = path + "/"
                return canonical in public_paths and any(
                    getattr(candidate, "path", None) == canonical
                    and candidate.endpoint is route.endpoint
                    for candidate in scope["app"].routes
                )
            partial_match |= match == Match.PARTIAL
        return False if partial_match else None
