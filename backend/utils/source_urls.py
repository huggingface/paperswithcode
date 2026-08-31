"""Canonical identities for authoritative curation source URLs."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from backend.utils.public_urls import normalize_public_url


def source_url_identity(url: str) -> str:
    """Collapse transport variants of one source document to one identity."""
    normalized = normalize_public_url(url)
    parsed = urlsplit(normalized)
    host = (parsed.hostname or "").casefold()
    parts = [part for part in parsed.path.split("/") if part]

    if (
        host in {"arxiv.org", "export.arxiv.org"}
        and len(parts) >= 2
        and parts[0].casefold() in {"abs", "html", "pdf", "e-print"}
    ):
        arxiv_id = re.sub(r"\.pdf$", "", "/".join(parts[1:]), flags=re.IGNORECASE)
        return f"arxiv:{re.sub(r'v\d+$', '', arxiv_id).casefold()}"

    if host == "huggingface.co" and len(parts) >= 2:
        if parts[0].casefold() == "papers":
            arxiv_id = re.sub(r"\.md$", "", parts[1], flags=re.IGNORECASE)
            return f"arxiv:{re.sub(r'v\d+$', '', arxiv_id).casefold()}"
        if len(parts) == 2 or (
            len(parts) >= 5
            and parts[2].casefold() in {"blob", "raw", "resolve"}
            and "/".join(parts[4:]).casefold()
            in {"readme", "readme.md", "readme.markdown"}
        ):
            return f"hf:{parts[0].casefold()}/{parts[1].casefold()}"

    if host == "github.com" and len(parts) >= 2:
        is_root = len(parts) == 2
        is_readme = (
            len(parts) >= 5
            and parts[2].casefold() in {"blob", "raw"}
            and "/".join(parts[4:]).casefold()
            in {"readme", "readme.md", "readme.markdown"}
        )
        if is_root or is_readme:
            repository = parts[1].removesuffix(".git").casefold()
            return f"github:{parts[0].casefold()}/{repository}"

    if (
        host == "raw.githubusercontent.com"
        and len(parts) >= 4
        and "/".join(parts[3:]).casefold() in {"readme", "readme.md", "readme.markdown"}
    ):
        return f"github:{parts[0].casefold()}/{parts[1].casefold()}"

    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc, path, parsed.query, ""))
