"""Validated Hugging Face organization metadata and paper-list fetching."""

from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from huggingface_hub.utils import build_hf_headers

from backend.services.entity_image_service import _detect_image_type

HF_BASE = "https://huggingface.co"
MAX_LOGO_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 4
EXPECTED_AVATAR_HOST_SUFFIX = ".huggingface.co"


class HFOrganizationError(RuntimeError):
    """Raised when an upstream organization response is incomplete or invalid."""


@dataclass(frozen=True)
class HFOrganizationPaper:
    arxiv_id: str
    title: str


@dataclass(frozen=True)
class HFOrganizationData:
    hf_slug: str
    name: str
    logo_url: str | None
    website_url: str | None
    upstream_paper_count: int
    papers: tuple[HFOrganizationPaper, ...]


def normalize_arxiv_id(value: str) -> str:
    return re.sub(r"v\d+$", "", value.strip(), flags=re.IGNORECASE)


def extract_balanced_array(text: str, start_key: str = '"orgPapers"') -> str:
    """Extract the JSON array following ``start_key`` or fail closed."""
    key_index = text.find(start_key)
    if key_index < 0:
        raise HFOrganizationError(f"Missing {start_key} payload")
    open_index = text.find("[", key_index + len(start_key))
    if open_index < 0:
        raise HFOrganizationError(f"Missing array after {start_key}")

    depth = 0
    in_string = False
    escaped = False
    for index in range(open_index, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[open_index : index + 1]
            if depth < 0:
                break
    raise HFOrganizationError(f"Truncated or malformed {start_key} array")


def parse_org_papers_html(
    text: str,
) -> tuple[tuple[HFOrganizationPaper, ...], str | None]:
    decoded = html.unescape(text)
    try:
        payload = json.loads(extract_balanced_array(decoded))
    except json.JSONDecodeError as exc:
        raise HFOrganizationError("Malformed orgPapers JSON") from exc
    if not isinstance(payload, list):
        raise HFOrganizationError("orgPapers must be an array")

    papers: list[HFOrganizationPaper] = []
    for entry in payload:
        if not isinstance(entry, dict) or not isinstance(entry.get("paper"), dict):
            raise HFOrganizationError("Malformed orgPapers entry")
        raw_id = entry["paper"].get("id")
        if not isinstance(raw_id, str) or not normalize_arxiv_id(raw_id):
            raise HFOrganizationError("orgPapers entry is missing an ArXiv ID")
        papers.append(
            HFOrganizationPaper(
                arxiv_id=normalize_arxiv_id(raw_id),
                title=str(entry.get("title") or "").strip(),
            )
        )

    return tuple(papers), parse_org_website(decoded)


@dataclass(frozen=True)
class HFOrganizationProfile:
    hf_slug: str
    name: str
    logo_url: str | None
    website_url: str | None
    is_verified: bool
    followers: int


def parse_org_website(text: str) -> str | None:
    match = re.search(
        r'rel="nofollow"[^>]*>\s*(https?://[^<\s]+)\s*</a>', html.unescape(text)
    )
    return match.group(1).strip() if match else None


class HFOrganizationClient:
    def __init__(self, client: httpx.Client | None = None, attempts: int = 6):
        self.attempts = attempts
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(30),
            headers=build_hf_headers(),
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        response = None
        for attempt in range(self.attempts):
            response = self.client.get(url, params=params)
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
            if attempt < self.attempts - 1:
                retry_after = response.headers.get("retry-after")
                reset_match = re.search(
                    r"(?:^|;)t=(\d+)", response.headers.get("ratelimit", "")
                )
                if retry_after and retry_after.isdigit():
                    delay = int(retry_after) + 1
                elif reset_match:
                    delay = int(reset_match.group(1)) + 1
                else:
                    delay = min(2**attempt, 60)
                time.sleep(delay)
        assert response is not None
        return response

    def fetch(self, hf_slug: str) -> HFOrganizationData:
        overview_response = self._get(f"{HF_BASE}/api/organizations/{hf_slug}/overview")
        overview_response.raise_for_status()
        overview = overview_response.json()
        if not isinstance(overview, dict) or not isinstance(
            overview.get("numPapers"), int
        ):
            raise HFOrganizationError("Organization overview is missing numPapers")

        papers_response = self._get(f"{HF_BASE}/{hf_slug}/papers")
        papers_response.raise_for_status()
        papers, website_url = parse_org_papers_html(papers_response.text)
        if len(papers) != overview["numPapers"]:
            raise HFOrganizationError(
                f"orgPapers count {len(papers)} differs from overview "
                f"numPapers {overview['numPapers']}"
            )

        name = str(overview.get("fullname") or overview.get("name") or hf_slug).strip()
        if not name:
            raise HFOrganizationError("Organization overview is missing a name")
        logo_url = overview.get("avatarUrl")
        if logo_url is not None and not isinstance(logo_url, str):
            raise HFOrganizationError("Organization avatarUrl must be a string")
        return HFOrganizationData(
            hf_slug=hf_slug,
            name=name,
            logo_url=logo_url,
            website_url=website_url,
            upstream_paper_count=overview["numPapers"],
            papers=papers,
        )

    def fetch_profile(self, hf_slug: str) -> HFOrganizationProfile | None:
        """Return an organization's public profile, or None when it does not exist."""
        response = self._get(f"{HF_BASE}/api/organizations/{hf_slug}/overview")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        overview = response.json()
        if not isinstance(overview, dict) or not isinstance(overview.get("name"), str):
            raise HFOrganizationError("Organization overview is missing a name")
        page = self._get(f"{HF_BASE}/{overview['name']}")
        page.raise_for_status()
        logo_url = overview.get("avatarUrl")
        return HFOrganizationProfile(
            hf_slug=overview["name"],
            name=str(overview.get("fullname") or overview["name"]).strip(),
            logo_url=logo_url if isinstance(logo_url, str) else None,
            website_url=parse_org_website(page.text),
            is_verified=overview.get("isVerified") is True,
            followers=int(overview.get("numFollowers") or 0),
        )

    def search(self, query: str, limit: int = 10) -> list[str]:
        """Return HF organization handles matching ``query``."""
        response = self._get(
            f"{HF_BASE}/api/quicksearch",
            params={"q": query, "type": "org", "limit": limit},
        )
        response.raise_for_status()
        return [
            item["name"]
            for item in response.json().get("orgs", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]

    def fetch_logo(self, url: str) -> tuple[bytes, str]:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            _validate_avatar_url(current)
            with self.client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise HFOrganizationError("Avatar redirect is missing Location")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > MAX_LOGO_BYTES:
                    raise HFOrganizationError("Organization logo exceeds 5 MB")
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_LOGO_BYTES:
                        raise HFOrganizationError("Organization logo exceeds 5 MB")
                if not content:
                    raise HFOrganizationError("Organization logo is empty")
                mime_type, _ = _detect_image_type(bytes(content))
                return bytes(content), mime_type
        raise HFOrganizationError("Too many organization-logo redirects")


def _validate_avatar_url(url: str) -> None:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not hostname:
        raise HFOrganizationError("Avatar URL must use HTTPS")
    if hostname != "huggingface.co" and not hostname.endswith(
        EXPECTED_AVATAR_HOST_SUFFIX
    ):
        raise HFOrganizationError(f"Unexpected avatar host: {hostname}")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise HFOrganizationError(f"Could not resolve avatar host: {hostname}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise HFOrganizationError("Avatar URL resolves to a non-public address")
