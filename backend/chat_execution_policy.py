"""Shared, bounded execution policy for research chat backends."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit

SYNTHESIS_RESERVE_TURNS = 2
FINALIZER_MAX_TURNS = 1
FINALIZER_MIN_REMAINING_SECONDS = 10.0
MAX_FETCHABLE_URLS = 256
MAX_FETCHABLE_URL_SEED_BYTES = 32 * 1024
MAX_PROVIDER_REQUESTS = 16
MAX_PROVIDER_TURN_TOKENS = 512_000
MAX_POSTER_PROVIDER_REQUESTS = 24
ANSWER_NOW_REASON = (
    "Research is complete. Answer now using the evidence already gathered."
)
FINALIZER_PROMPT_VERSION = "assistant-finalizer-v1"
FINALIZER_PROMPT = (
    "Finalize the answer to the user's current request now. Use only evidence "
    "already present in this conversation. Do not request or describe additional "
    "research. Be candid about any remaining uncertainty and return concise "
    "Markdown with the required paper/source citations."
)

_URL = re.compile(r'https?://[^\s<>"\\]+', re.IGNORECASE)
_TRAILING_URL_PUNCTUATION = ".,;:!?)\\]}'\""


def effective_tool_rounds(max_turns: int) -> int:
    return max(1, max_turns - SYNTHESIS_RESERVE_TURNS)


def validate_execution_limits(
    *,
    max_turns: int,
    max_tool_calls: int,
    max_direct_searches: int,
    max_web_searches: int,
) -> None:
    rounds = effective_tool_rounds(max_turns)
    if max_turns < 3 or rounds >= max_turns:
        raise ValueError("research chat requires at least one reserved synthesis turn")
    if max_direct_searches > max_tool_calls:
        raise ValueError("direct search limit exceeds the tool-call limit")
    if max_web_searches > max_tool_calls:
        raise ValueError("web search limit exceeds the tool-call limit")
    if MAX_PROVIDER_REQUESTS < max_turns + SYNTHESIS_RESERVE_TURNS:
        raise ValueError("provider request capability cannot cover bounded recovery")


def normalize_public_https_url(value: str) -> str | None:
    candidate = value
    for _ in range(4):
        try:
            parsed = urlsplit(candidate.rstrip(_TRAILING_URL_PUNCTUATION))
            host = parsed.hostname
            if (
                parsed.scheme != "https"
                or not host
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in {None, 443}
                or not host.isascii()
            ):
                return None
            lowered = host.lower().rstrip(".")
            if lowered == "localhost" or lowered.endswith(
                (".local", ".internal", ".localhost")
            ):
                return None
            try:
                address = ip_address(lowered)
            except ValueError:
                pass
            else:
                if not address.is_global:
                    return None
            normalized = urlunsplit(
                ("https", lowered, parsed.path or "/", parsed.query, "")
            )
        except ValueError:
            return None
        if normalized == candidate:
            return normalized
        candidate = normalized
    return None


def urls_in_text(value: str) -> list[str]:
    return [
        normalized
        for match in _URL.finditer(value)
        if (normalized := normalize_public_https_url(match.group())) is not None
    ]


def _seed_bytes(urls: list[str]) -> int:
    return len(json.dumps(urls, separators=(",", ":")).encode())


def bounded_url_seed(payloads: Iterable[str]) -> list[str]:
    """Retain most-recent eligible occurrences, then serialize deterministically."""

    recency: dict[str, int] = {}
    position = 0
    for payload in payloads:
        for url in urls_in_text(payload):
            recency[url] = position
            position += 1
    selected: list[str] = []
    for url, _ in sorted(recency.items(), key=lambda item: item[1], reverse=True):
        candidate = sorted([*selected, url])
        if len(candidate) > MAX_FETCHABLE_URLS:
            break
        if _seed_bytes(candidate) > MAX_FETCHABLE_URL_SEED_BYTES:
            continue
        selected.append(url)
    return sorted(selected)


def validate_url_seed(value: object) -> list[str]:
    if type(value) is not list or len(value) > MAX_FETCHABLE_URLS:
        raise ValueError("Invalid fetchable URL seed")
    urls: list[str] = []
    for item in value:
        if not isinstance(item, str) or normalize_public_https_url(item) != item:
            raise ValueError("Invalid fetchable URL seed")
        urls.append(item)
    if len(set(urls)) != len(urls) or urls != sorted(urls):
        raise ValueError("Invalid fetchable URL seed")
    if _seed_bytes(urls) > MAX_FETCHABLE_URL_SEED_BYTES:
        raise ValueError("Invalid fetchable URL seed")
    return urls


def prompt_contract_digest(research_prompt_digest: str) -> str:
    """Bind the private finalizer prompt to the worker prompt release contract."""

    payload = "\n".join(
        (research_prompt_digest, FINALIZER_PROMPT_VERSION, FINALIZER_PROMPT)
    )
    return hashlib.sha256(payload.encode()).hexdigest()
