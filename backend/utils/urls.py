"""
URL construction utilities for papers and ArXiv integration.

This module provides functions to construct URLs for ArXiv papers,
PDFs, and our own platform URLs, following the patterns described
in the DATABASE_SCHEMA_UML.md documentation.
"""

from typing import Any, Optional
from urllib.parse import urlparse

from backend.config import get_settings


LOCAL_PAPER_SOURCE_HOSTS = frozenset(
    {
        "",
        "localhost",
        "127.0.0.1",
        "paperswithcode.co",
        "www.paperswithcode.co",
    }
)


def local_paper_source_hosts() -> frozenset[str]:
    """Hosts whose paper links point at this site, plus PWC_LOCAL_HOST_ALIASES."""

    return LOCAL_PAPER_SOURCE_HOSTS | get_settings().local_host_alias_set


def get_arxiv_abs_url(arxiv_id: str, version: Optional[str] = None) -> Optional[str]:
    """
    Construct ArXiv abstract URL from ArXiv ID and version.
    Handles both modern (1805.10616) and legacy (cs.DS/0610046) formats.

    Args:
        arxiv_id: Base ArXiv ID (e.g., "1805.10616")
        version: Version string (e.g., "v2", "v3") - if None, returns latest version URL

    Returns:
        ArXiv abstract URL or None if arxiv_id is invalid
    """
    if not arxiv_id:
        return None

    settings = get_settings()

    if version and version != "v1":
        return f"{settings.arxiv_base_url}/abs/{arxiv_id}{version}"
    else:
        # No version returns latest version (ArXiv default behavior)
        return f"{settings.arxiv_base_url}/abs/{arxiv_id}"


def get_arxiv_pdf_url(arxiv_id: str, version: Optional[str] = None) -> Optional[str]:
    """
    Construct ArXiv PDF URL from ArXiv ID and version.
    Handles both modern and legacy formats.

    Args:
        arxiv_id: Base ArXiv ID (e.g., "1805.10616")
        version: Version string (e.g., "v2", "v3") - if None, returns latest version URL

    Returns:
        ArXiv PDF URL or None if arxiv_id is invalid
    """
    if not arxiv_id:
        return None

    settings = get_settings()

    if version and version != "v1":
        return f"{settings.arxiv_base_url}/pdf/{arxiv_id}{version}.pdf"
    else:
        # No version returns latest version (ArXiv default behavior)
        return f"{settings.arxiv_base_url}/pdf/{arxiv_id}.pdf"


def get_paper_url(
    paper_id: int, arxiv_id: Optional[str] = None, domain: Optional[str] = None
) -> str:
    """
    Construct your platform's paper URL.
    Prefer ArXiv ID for clean URLs, fallback to database ID.

    Args:
        paper_id: Database paper ID
        arxiv_id: ArXiv ID if available
        domain: Domain to use (defaults to app_domain from settings)

    Returns:
        Platform paper URL
    """
    settings = get_settings()
    domain = domain or settings.app_domain

    if arxiv_id:
        # Clean URL: paperswithcode.ai/papers/1805.10616
        return f"https://{domain}/papers/{arxiv_id}"
    else:
        # Fallback for non-ArXiv papers: paperswithcode.ai/papers/12345
        return f"https://{domain}/papers/{paper_id}"


def get_paper_abs_url(
    source: str,
    arxiv_id: Optional[str],
    version: Optional[str],
    source_url: Optional[str],
) -> Optional[str]:
    """
    Source-aware "abstract URL" for a paper row.

    For ArXiv rows this returns the generated `arxiv.org/abs/...` URL.
    For external rows this returns the canonical `source_url`.
    Returns ``None`` when neither identifier is available.
    """
    if source == "external":
        return source_url
    if arxiv_id:
        return get_arxiv_abs_url(arxiv_id, version)
    return source_url


def get_paper_pdf_url(
    source: str, arxiv_id: Optional[str], version: Optional[str]
) -> Optional[str]:
    """
    Source-aware "PDF URL" for a paper row.

    Only ArXiv rows have a derivable PDF URL; external rows return ``None``
    unless a future column tracks an explicit PDF link separately.
    """
    if source == "external":
        return None
    if arxiv_id:
        return get_arxiv_pdf_url(arxiv_id, version)
    return None


def get_paper_route_identifier(
    source: str, arxiv_id: Optional[str], paper_id: int
) -> str:
    """
    Public route identifier for a paper.

    ArXiv rows continue to use the ArXiv ID in URLs (e.g. `/paper/2504.12516`).
    External rows use the internal database ID (e.g. `/paper/12345`) because
    they have no ArXiv identifier.
    """
    if source == "arxiv" and arxiv_id:
        return arxiv_id
    return str(paper_id)


def normalize_local_paper_source_url(source_url: Optional[str]) -> Optional[str]:
    """
    Convert stored links to our own paper pages into canonical app-relative URLs.

    Some method source links were created while the app was reached via an IP
    preview host. Returning a relative route keeps those links on the current
    production/staging origin while preserving truly external source URLs.
    """
    if not source_url:
        return source_url

    parsed = urlparse(source_url)
    if parsed.scheme and (parsed.hostname or "") not in local_paper_source_hosts():
        return source_url

    path = parsed.path if parsed.scheme or parsed.netloc else source_url
    path = path.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    for prefix in ("/paper/", "/abs/", "/pdf/"):
        if path.startswith(prefix):
            source_ref = path.removeprefix(prefix).removesuffix(".pdf")
            if source_ref:
                return f"/paper/{source_ref}"

    return source_url


def get_method_source_url(
    source_url: Optional[str],
    source_paper: Optional[Any] = None,
) -> Optional[str]:
    """
    Public source URL for a method.

    When a method points at a paper row, that relationship is the canonical
    internal route. The stored source_url is only used for external metadata or
    old rows that have not been backfilled yet.
    """
    if source_paper is not None:
        route_identifier = get_paper_route_identifier(
            source_paper.source,
            source_paper.arxiv_id,
            source_paper.id,
        )
        return f"/paper/{route_identifier}"

    return normalize_local_paper_source_url(source_url)


def normalize_paper_route_identifier(identifier: str) -> str:
    """
    Normalize a paper route segment from user-facing URLs.

    Accepts common variants such as dash-separated modern ArXiv IDs
    (``2606-02800`` -> ``2606.02800``) and strips trailing version suffixes.
    """
    import re

    candidate = (identifier or "").strip()
    if not candidate:
        return candidate

    dash_match = re.match(r"^(\d{4})-(\d{4,5})(v\d+)?$", candidate)
    if dash_match:
        candidate = (
            f"{dash_match.group(1)}.{dash_match.group(2)}{dash_match.group(3) or ''}"
        )

    version_match = re.match(r"^(\d{4}\.\d{4,5})(v\d+)$", candidate)
    if version_match:
        candidate = version_match.group(1)

    return candidate


def validate_arxiv_id(arxiv_id: str) -> bool:
    """
    Validate ArXiv ID format.
    Supports both modern (1805.10616) and legacy (cs.DS/0610046) formats.

    Args:
        arxiv_id: ArXiv ID to validate

    Returns:
        True if valid ArXiv ID format
    """
    import re

    if not arxiv_id:
        return False

    # Modern format: YYMM.NNNN (e.g., 1805.10616)
    modern_pattern = r"^\d{4}\.\d{4,5}$"

    # Legacy format: subject-class/YYMMnnn (e.g., cs.DS/0610046)
    legacy_pattern = r"^[a-z-]+(\.[A-Z]{2})?\/\d{7}$"

    return bool(
        re.match(modern_pattern, arxiv_id) or re.match(legacy_pattern, arxiv_id)
    )


def validate_version(version: str) -> bool:
    """
    Validate ArXiv version format.

    Args:
        version: Version string to validate (e.g., "v1", "v2", "v10")

    Returns:
        True if valid version format
    """
    import re

    if not version:
        return False

    # Version format: v followed by one or more digits
    version_pattern = r"^v\d+$"

    return bool(re.match(version_pattern, version))


# Utility functions for URL parsing


def parse_arxiv_url(url: str) -> Optional[tuple[str, Optional[str]]]:
    """
    Parse ArXiv URL to extract ArXiv ID and version.

    Args:
        url: ArXiv URL (abs or pdf)

    Returns:
        Tuple of (arxiv_id, version) or None if invalid URL
    """
    import re

    if not url:
        return None

    # Pattern for ArXiv URLs with optional version
    # Examples:
    # https://arxiv.org/abs/1805.10616
    # https://arxiv.org/abs/1805.10616v2
    # https://arxiv.org/html/2606.13141v1
    # https://arxiv.org/pdf/1805.10616v2.pdf
    arxiv_pattern = r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(v\d+)?(?:\.pdf)?"

    match = re.search(arxiv_pattern, url)
    if match:
        arxiv_id = match.group(1)
        version = match.group(2) if match.group(2) else None

        if validate_arxiv_id(arxiv_id):
            return arxiv_id, version

    return None


def external_source_url_to_paper_url(url: Optional[str]) -> Optional[str]:
    """
    Map an external evaluation source URL to our paper page when it cites ArXiv.

    ArXiv abs/pdf/html links are rewritten to ``/paper/{arxiv_id}`` so users
    stay on Papers with Code. Other URLs are returned unchanged.
    """
    if not url:
        return url

    parsed = parse_arxiv_url(url)
    if not parsed:
        return url

    arxiv_id, _version = parsed
    return f"/paper/{arxiv_id}"


def extract_arxiv_id_from_text(text: str) -> Optional[str]:
    """
    Extract ArXiv ID from free text (useful for parsing paper metadata).

    Args:
        text: Text that might contain an ArXiv ID

    Returns:
        ArXiv ID if found, None otherwise
    """
    import re

    if not text:
        return None

    # Look for ArXiv ID patterns in text
    patterns = [
        r"arXiv:(\d{4}\.\d{4,5})",  # arXiv:1805.10616
        r"arxiv:(\d{4}\.\d{4,5})",  # arxiv:1805.10616 (lowercase)
        r"(\d{4}\.\d{4,5})",  # 1805.10616 (standalone)
        r"arXiv:([a-z-]+(?:\.[A-Z]{2})?\/\d{7})",  # arXiv:cs.DS/0610046 (legacy)
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            arxiv_id = match.group(1)
            if validate_arxiv_id(arxiv_id):
                return arxiv_id

    return None
