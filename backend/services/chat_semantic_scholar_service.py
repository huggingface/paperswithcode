"""Bounded Semantic Scholar Graph API access for the private chat gateway."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from backend.config import Settings

SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_PAPER_GRAPH_PATH = re.compile(
    r"^paper/[^/]{1,500}/(?:references|citations)$", re.IGNORECASE
)
_ALLOWED_QUERY_KEYS = frozenset({"query", "limit", "offset", "year", "fields"})
# Credentialed keyword searches. The gateway meters every one against the
# turn's direct-search allowance, so keep this the only place they are listed.
SEARCH_PATHS = frozenset({"paper/search", "paper/search/match"})


def is_search_path(path: str) -> bool:
    return path.strip("/") in SEARCH_PATHS


class SemanticScholarGatewayError(RuntimeError):
    def __init__(self, status_code: int, body: bytes):
        super().__init__(f"Semantic Scholar request failed ({status_code})")
        self.status_code = status_code
        self.body = body


def _validate_request(path: str, query: dict[str, Any]) -> tuple[str, dict[str, str]]:
    normalized_path = path.strip("/")
    if normalized_path not in SEARCH_PATHS and not (
        _PAPER_GRAPH_PATH.fullmatch(normalized_path)
    ):
        raise ValueError("Unsupported Semantic Scholar operation")
    if not set(query) <= _ALLOWED_QUERY_KEYS:
        raise ValueError("Unsupported Semantic Scholar query parameter")
    normalized_query = {key: str(value) for key, value in query.items()}
    if any(len(value) > 1000 for value in normalized_query.values()):
        raise ValueError("Semantic Scholar query parameter is too long")
    return normalized_path, normalized_query


def fetch_semantic_scholar(settings: Settings, path: str, query: dict[str, Any]) -> Any:
    normalized_path, normalized_query = _validate_request(path, query)
    api_key = settings.semantic_scholar_api_key.strip()
    if not api_key:
        raise RuntimeError("Semantic Scholar is not configured")
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.get(
            f"{SEMANTIC_SCHOLAR_API_URL}/{normalized_path}",
            params=normalized_query,
            headers={
                "Accept": "application/json",
                "User-Agent": "paperswithcode-chat/1",
                "x-api-key": api_key,
            },
        )
    body = response.content[: MAX_RESPONSE_BYTES + 1]
    if len(body) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Semantic Scholar response is too large")
    if response.status_code >= 400:
        raise SemanticScholarGatewayError(response.status_code, body[:4096])
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Semantic Scholar returned invalid JSON") from error
