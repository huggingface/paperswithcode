"""Public research trends API contracts."""

from typing import List

from pydantic import BaseModel, Field


class TrendPoint(BaseModel):
    """One monthly percentage point on the public research trends page."""

    month: str = Field(
        ...,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Paper publication month in YYYY-MM format",
    )
    percent: float = Field(
        ...,
        ge=0,
        le=100,
        description="Share of eligible papers matching the trend, from 0 to 100",
    )


class TrendsResponse(BaseModel):
    """Monthly open-science trends for the public trends page."""

    code_availability: List[TrendPoint] = Field(
        ...,
        description="Papers with at least one official GitHub repository",
    )
    hf_artifacts: List[TrendPoint] = Field(
        ...,
        description="Papers linked to at least one Hugging Face artifact",
    )


__all__ = [
    "TrendPoint",
    "TrendsResponse",
]
