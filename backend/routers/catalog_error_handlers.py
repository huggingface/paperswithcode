"""Central HTTP translation for typed catalog domain failures."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ExceptionHandler

from backend.routers.public_error_handlers import (
    is_public_request,
    public_error_response,
)
from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogPermissionError,
    CatalogRateLimitError,
    CatalogNotFoundError,
    CatalogPersistenceError,
    CatalogValidationError,
)


logger = logging.getLogger(__name__)


def _catalog_error_response(status_code: int) -> ExceptionHandler:
    async def handler(request: Request, error: Exception) -> JSONResponse:
        detail = getattr(error, "detail", str(error))
        if is_public_request(request):
            return public_error_response(status_code, detail)
        return JSONResponse(status_code=status_code, content={"detail": detail})

    return handler


async def _catalog_persistence_error_response(
    request: Request, error: Exception
) -> JSONResponse:
    logger.error("Catalog persistence operation failed", exc_info=error)
    if is_public_request(request):
        return public_error_response(500, "Internal server error")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def register_catalog_error_handlers(app: FastAPI) -> None:
    """Register the public HTTP contracts for catalog domain errors."""
    app.add_exception_handler(CatalogPermissionError, _catalog_error_response(403))
    app.add_exception_handler(CatalogRateLimitError, _catalog_error_response(429))
    app.add_exception_handler(
        CatalogNotFoundError, _catalog_error_response(status_code=404)
    )
    app.add_exception_handler(
        CatalogConflictError, _catalog_error_response(status_code=409)
    )
    app.add_exception_handler(
        CatalogValidationError, _catalog_error_response(status_code=400)
    )
    app.add_exception_handler(
        CatalogPersistenceError, _catalog_persistence_error_response
    )
