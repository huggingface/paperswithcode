"""Schema delivery and anonymous browser access for the selected public reads."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.routing import Match
from starlette.middleware.cors import CORSMiddleware

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

    def __init__(self, app, allowed_origins=(), allow_origin_regex=None):
        self.app = app
        self.existing_origins = CORSMiddleware(
            app, allow_origins=allowed_origins, allow_origin_regex=allow_origin_regex
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"GET", "OPTIONS"}:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        origin = request.headers.get("origin")
        if not origin or self.existing_origins.is_allowed_origin(origin):
            # Existing website/mirror clients may use credentialed cross-origin
            # requests. Preserve their exact-origin CORS and preflight contract.
            await self.app(scope, receive, send)
            return
        get_scope = {**scope, "method": "GET"}
        selected = False
        for route in scope["app"].routes:
            match, _ = route.matches(get_scope)
            if match == Match.FULL:
                selected = getattr(route, "path", None) in {
                    *PUBLIC_ENDPOINTS,
                    PUBLIC_SCHEMA_PATH,
                }
                break
        if not selected:
            await self.app(scope, receive, send)
            return
        if scope["method"] == "OPTIONS":
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
                # Preserve existing CORS rules for credentialed/administrative requests.
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
                headers["Access-Control-Allow-Origin"] = "*"
                if "Access-Control-Allow-Credentials" in headers:
                    del headers["Access-Control-Allow-Credentials"]
                headers["Access-Control-Expose-Headers"] = "Retry-After"
            await send(message)

        await self.app(scope, receive, cors_send)
