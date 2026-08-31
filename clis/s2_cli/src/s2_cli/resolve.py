"""Normalize Semantic Scholar paper identifiers and titles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from s2_cli.transport import Client, NotFoundError, ResponseError

MATCH_FIELDS = "title,year,citationCount,externalIds,url"

ARXIV_ID_RE = re.compile(
    r"^(?:arXiv:)?(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})(?:v\d+)?$",
    re.IGNORECASE,
)
DOI_RE = re.compile(r"^(?:doi:)?(10\.\d{4,9}/\S+)$", re.IGNORECASE)
HEX_ID_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
PREFIXED_RE = re.compile(
    r"^(ARXIV|DOI|CorpusId|PMID|PMCID|ACL|MAG|URL):(.+)$",
    re.IGNORECASE,
)
ARXIV_URL_RE = re.compile(
    r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/"
    r"(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})(?:v\d+)?(?:\.pdf)?$",
    re.IGNORECASE,
)
S2_URL_RE = re.compile(
    r"^https?://(?:www\.)?semanticscholar\.org/paper/(?:[^/]+/)?"
    r"([0-9a-f]{40})/?$",
    re.IGNORECASE,
)
HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


@dataclass(frozen=True)
class ResolvedPaper:
    id: str
    title: str | None = None
    arxiv: str | None = None
    match_score: float | None = None
    payload: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id}
        if self.title is not None:
            data["title"] = self.title
        if self.arxiv is not None:
            data["arxiv"] = self.arxiv
        if self.match_score is not None:
            data["matchScore"] = self.match_score
        return data


def normalize_paper_id(value: str) -> str | None:
    """Return an S2 paper id if `value` looks like an identifier, else None."""
    text = value.strip()
    if not text:
        return None
    prefixed = PREFIXED_RE.fullmatch(text)
    if prefixed:
        kind, remainder = prefixed.group(1), prefixed.group(2).strip()
        if kind.upper() == "ARXIV":
            arxiv = _strip_arxiv_version(remainder)
            return f"ARXIV:{arxiv}" if arxiv else f"ARXIV:{remainder}"
        if kind.upper() == "DOI":
            return f"DOI:{remainder}"
        return f"{kind}:{remainder}"
    arxiv = ARXIV_ID_RE.fullmatch(text)
    if arxiv:
        return f"ARXIV:{_strip_arxiv_version(arxiv.group(1))}"
    doi = DOI_RE.fullmatch(text)
    if doi:
        return f"DOI:{doi.group(1)}"
    if HEX_ID_RE.fullmatch(text):
        return text.lower()
    arxiv_url = ARXIV_URL_RE.fullmatch(text)
    if arxiv_url:
        return f"ARXIV:{_strip_arxiv_version(arxiv_url.group(1))}"
    s2_url = S2_URL_RE.fullmatch(text)
    if s2_url:
        return s2_url.group(1).lower()
    if HTTP_URL_RE.match(text):
        return f"URL:{text}"
    return None


def encode_paper_path(paper_id: str) -> str:
    return quote(paper_id, safe=":")


def arxiv_from_external_ids(external_ids: Any) -> str | None:
    if not isinstance(external_ids, dict):
        return None
    value = external_ids.get("ArXiv") or external_ids.get("arxiv")
    if not value:
        return None
    return _strip_arxiv_version(str(value))


def resolve_paper(client: Client, value: str) -> ResolvedPaper:
    paper_id = normalize_paper_id(value)
    if paper_id is not None:
        return ResolvedPaper(id=paper_id)
    try:
        payload = client.get(
            "paper/search/match",
            {"query": value.strip(), "fields": MATCH_FIELDS},
        ).json()
    except NotFoundError as error:
        raise NotFoundError(f"Title match not found: {value.strip()}") from error
    paper = _match_paper(payload)
    return ResolvedPaper(
        id=str(paper["paperId"]),
        title=paper.get("title"),
        arxiv=arxiv_from_external_ids(paper.get("externalIds")),
        match_score=_match_score(paper.get("matchScore")),
        payload=paper,
    )


def _match_paper(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            paper = data[0]
        elif payload.get("paperId"):
            paper = payload
        else:
            paper = None
        if paper and paper.get("paperId"):
            return paper
    raise ResponseError("API response did not contain a title match")


def _match_score(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _strip_arxiv_version(value: str) -> str:
    return re.sub(r"v\d+$", "", value.strip(), flags=re.IGNORECASE)
