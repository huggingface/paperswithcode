"""Shared API error response contracts."""

from typing import List

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    error: str = Field(default="Validation error", description="Error type")
    detail: List[dict] = Field(..., description="Validation error details")


__all__ = [
    "ErrorResponse",
    "ValidationErrorResponse",
]
