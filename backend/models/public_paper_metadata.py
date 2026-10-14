"""API models for public metadata about papers outside the catalog."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PublicPaperLink(BaseModel):
    """A labelled place where a paper can be read or explored."""

    label: str = Field(..., description="Human-readable link label")
    url: str = Field(..., description="Absolute URL")
    kind: Literal[
        "catalog", "abstract", "pdf", "huggingface", "doi", "code", "project_page"
    ] = Field(..., description="What the link points to")


class PublicPaperMetadata(BaseModel):
    """Paper metadata from the catalog or, when absent, from public sources.

    ``in_catalog`` is false when Papers With Code has not indexed the paper;
    the metadata then comes from Hugging Face Papers, arXiv, or Crossref and
    ``available_at`` lists where the paper can be read instead.
    """

    in_catalog: bool = Field(
        ..., description="True when the paper is indexed by Papers With Code"
    )
    catalog_id: Optional[str] = Field(
        None, description="Papers With Code paper ID when in_catalog is true"
    )
    catalog_url: Optional[str] = Field(
        None, description="Papers With Code paper page when in_catalog is true"
    )
    metadata_source: Literal["paperswithcode", "huggingface", "arxiv", "crossref"] = (
        Field(..., description="Where this metadata comes from")
    )
    note: str = Field(..., description="Plain-language summary of the result")
    id: str = Field(..., description="arXiv ID, DOI, or catalog ID")
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    title: str
    authors: List[str] = Field(default_factory=list)
    abstract: Optional[str] = None
    published: Optional[str] = Field(
        None, description="Publication date (YYYY-MM-DD, or coarser for Crossref)"
    )
    url: Optional[str] = Field(None, description="Canonical abstract page")
    pdf_url: Optional[str] = None
    hf_url: Optional[str] = Field(None, description="Hugging Face Papers page")
    repositories: List[str] = Field(default_factory=list)
    project_pages: List[str] = Field(default_factory=list)
    available_at: List[PublicPaperLink] = Field(
        default_factory=list,
        description="Labelled links where the paper can be read",
    )
