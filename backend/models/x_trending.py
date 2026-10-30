"""API models for papers trending on X."""

from pydantic import BaseModel, Field, model_validator


class XTrendingPaperInput(BaseModel):
    """One row of a day's "AI Papers on X" sheet tab."""

    rank: int = Field(..., ge=1)
    arxiv_id: str | None = Field(None, max_length=32)
    source_url: str | None = Field(None, max_length=2000)
    title: str | None = Field(None, max_length=1000)
    post_url: str | None = Field(None, max_length=500)
    post_author: str | None = Field(None, max_length=64)
    like_count: int | None = Field(None, ge=0)
    repost_count: int | None = Field(None, ge=0)
    view_count: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def require_identifier(self):
        if not self.arxiv_id and not self.source_url:
            raise ValueError("arxiv_id or source_url is required")
        return self


class XTrendingDayInput(BaseModel):
    papers: list[XTrendingPaperInput] = Field(..., max_length=100)


class XTrendingUnresolved(BaseModel):
    rank: int
    arxiv_id: str | None = None
    source_url: str | None = None
    title: str | None = None
    reason: str


class XTrendingDayResult(BaseModel):
    shared_on: str
    linked: int
    imported: list[str]
    unresolved: list[XTrendingUnresolved]
