"""
GitHub utility functions for URL parsing and repository operations.
"""

import logging
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def strip_git_suffix(name: str) -> str:
    """Drop a clone-style ``.git`` suffix; GitHub forbids it in repo names."""
    return name[:-4] if name.lower().endswith(".git") else name


def parse_github_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse GitHub URL to extract owner and repository name.

    Args:
        url: GitHub URL (e.g., "https://github.com/microsoft/DialoGPT")

    Returns:
        Tuple of (owner, name) or (None, None) if parsing fails

    Examples:
        >>> parse_github_url("https://github.com/microsoft/DialoGPT")
        ("microsoft", "DialoGPT")

        >>> parse_github_url("https://github.com/huggingface/transformers/tree/main/examples")
        ("huggingface", "transformers")

        >>> parse_github_url("https://github.com/wuzimeng/comp.git")
        ("wuzimeng", "comp")

        >>> parse_github_url("https://example.com/not-github")
        (None, None)
    """
    try:
        parsed = urlparse(url)
        if parsed.netloc != "github.com":
            return None, None

        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) >= 2:
            owner = path_parts[0]
            name = strip_git_suffix(path_parts[1])
            if owner and name:
                return owner, name

        return None, None

    except Exception as e:
        logger.debug(f"Error parsing GitHub URL {url}: {e}")
        return None, None


def normalize_github_url(url: str) -> Optional[str]:
    """
    Normalize GitHub URL to standard format with lowercase for case-insensitive comparison.

    GitHub URLs are case-insensitive in practice (they redirect), so we normalize to
    lowercase to avoid duplicate entries in the database.

    Args:
        url: GitHub URL in any format

    Returns:
        Normalized GitHub URL (lowercase) or None if invalid

    Examples:
        >>> normalize_github_url("https://github.com/microsoft/DialoGPT/tree/main/examples")
        "https://github.com/microsoft/dialogpt"

        >>> normalize_github_url("github.com/Microsoft/DialoGPT")
        "https://github.com/microsoft/dialogpt"

        >>> normalize_github_url("https://github.com/FaceBook/React")
        "https://github.com/facebook/react"
    """
    if not url:
        return None

    # Add https:// if missing
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    owner, name = parse_github_url(url)
    if owner and name:
        # Normalize to lowercase for case-insensitive comparison
        # GitHub URLs are case-insensitive and redirect to the proper case
        return f"https://github.com/{owner.lower()}/{name.lower()}"

    return None
