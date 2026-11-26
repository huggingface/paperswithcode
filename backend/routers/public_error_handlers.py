"""Give every public-API error a stable top-level ``code`` beside ``detail``."""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.services.public_api_schema import PUBLIC_ENDPOINTS

STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    416: "range_not_satisfiable",
    422: "invalid_request",
    429: "rate_limited",
    503: "service_unavailable",
}


def error_code(status_code: int, detail: object) -> str:
    if isinstance(detail, dict) and isinstance(detail.get("code"), str):
        return detail["code"]
    return STATUS_CODES.get(
        status_code, "internal_error" if status_code >= 500 else "error"
    )


def is_public_request(request: Request) -> bool:
    route = request.scope.get("route")
    return (
        request.method in {"GET", "HEAD"}
        and getattr(route, "path", None) in PUBLIC_ENDPOINTS
    )


def public_error_response(
    status_code: int,
    detail: object,
    headers: dict[str, str] | None = None,
    code: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": jsonable_encoder(detail),
            "code": code or error_code(status_code, detail),
        },
        headers=headers,
    )


def is_unrouted_api_request(request: Request) -> bool:
    return request.scope.get("route") is None and request.scope["path"].startswith(
        "/api/v1/"
    )


async def _http_error(request: Request, error: StarletteHTTPException):
    public = is_public_request(request) or is_unrouted_api_request(request)
    if not public or error.status_code < 400:
        return await http_exception_handler(request, error)
    return public_error_response(error.status_code, error.detail, error.headers)


async def _validation_error(request: Request, error: RequestValidationError):
    if not is_public_request(request):
        return await request_validation_exception_handler(request, error)
    return public_error_response(422, error.errors(), code="validation_error")


def register_public_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
