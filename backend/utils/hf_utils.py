import asyncio
import re
import time
from typing import Literal, Optional
from urllib.parse import urlparse, urlunparse

import aiohttp
from huggingface_hub.utils import build_hf_headers


HfArtifactKind = Literal["model", "dataset", "space"]


class HfArtifactDiscoveryError(RuntimeError):
    """The Hub could not conclusively answer an arXiv artifact lookup."""


_HF_NON_ARTIFACT_PATHS = {
    "",
    "api",
    "blog",
    "chat",
    "collections",
    "community",
    "docs",
    "enterprise",
    "join",
    "learn",
    "login",
    "models",
    "new",
    "papers",
    "posts",
    "pricing",
    "settings",
    "signup",
    "spaces",
    "tasks",
    "tos",
    "trending",
}


def normalize_hf_artifact_url(url: str) -> Optional[str]:
    """
    Normalize a Hugging Face artifact URL into a canonical, render-ready form.

    Returns the URL with scheme forced to https, host forced to
    `huggingface.co`, no query string, no fragment, and any trailing slash
    stripped. Returns None if the URL does not look like an HF artifact URL.
    """
    if not url:
        return None
    candidate = url.strip()
    if not candidate:
        return None

    if "://" not in candidate:
        candidate = "https://" + candidate

    parsed = urlparse(candidate)
    host = (parsed.netloc or "").lower()
    if host in {"www.huggingface.co", "hf.co", "www.hf.co"}:
        host = "huggingface.co"
    if host != "huggingface.co":
        return None

    path = parsed.path or ""
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    if not path or path == "/":
        return None

    return urlunparse(("https", host, path, "", "", ""))


def normalize_hf_artifact_bucket(
    urls: list[str],
    expected_kind: HfArtifactKind,
    *,
    bucket_label: str,
) -> list[str]:
    """Normalize and validate a list of HF artifact URLs for one bucket.

    Raises ``ValueError`` when a URL is invalid or classified into a different
    artifact kind than ``expected_kind``.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw_url in urls or []:
        normalized = normalize_hf_artifact_url(raw_url)
        if normalized is None:
            raise ValueError(f"Invalid Hugging Face {bucket_label} URL: {raw_url!r}")
        kind = classify_hf_artifact_url(normalized)
        if kind != expected_kind:
            raise ValueError(
                f"URL {raw_url!r} is not a Hugging Face {bucket_label} link"
            )
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def normalize_hf_artifact_payload(
    hf_models: list[str],
    hf_datasets: list[str],
    hf_spaces: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """Normalize three HF artifact URL lists for storage on ``papers``."""
    models = normalize_hf_artifact_bucket(hf_models, "model", bucket_label="model")
    datasets = normalize_hf_artifact_bucket(
        hf_datasets, "dataset", bucket_label="dataset"
    )
    spaces = normalize_hf_artifact_bucket(hf_spaces, "space", bucket_label="space")
    return models, datasets, spaces


def classify_hf_artifact_url(url: str) -> Optional[HfArtifactKind]:
    """
    Determine whether a Hugging Face URL points to a model, dataset, or space.

    Returns None for URLs that do not look like HF artifact URLs (e.g.
    profile, papers, blog, or arxiv filter URLs).
    """
    normalized = normalize_hf_artifact_url(url)
    if normalized is None:
        return None

    path = urlparse(normalized).path.lstrip("/")
    segments = [seg for seg in path.split("/") if seg]
    if not segments:
        return None

    head = segments[0].lower()
    if head == "datasets" and len(segments) >= 2:
        return "dataset"
    if head == "spaces" and len(segments) >= 2:
        return "space"
    if head in _HF_NON_ARTIFACT_PATHS:
        return None
    # `huggingface.co/<namespace>/<name>` is a model; bare `huggingface.co/<name>`
    # is a user/org profile and is not considered an artifact link.
    if len(segments) >= 2:
        return "model"
    return None


def hf_artifact_repo_id(url: str) -> Optional[tuple[HfArtifactKind, str]]:
    """Return ``(kind, repo_id)`` for a Hugging Face artifact URL, or None.

    The ``repo_id`` is the canonical Hub id used by the API, e.g.
    ``deepseek-ai/DeepSeek-V4-Pro`` for a model, ``squad`` or
    ``org/name`` for a dataset, ``org/name`` for a space (the
    ``datasets/`` and ``spaces/`` prefixes are stripped).
    """
    normalized = normalize_hf_artifact_url(url)
    if normalized is None:
        return None
    kind = classify_hf_artifact_url(normalized)
    if kind is None:
        return None

    path = urlparse(normalized).path.lstrip("/")
    segments = [seg for seg in path.split("/") if seg]
    if kind in ("dataset", "space"):
        # Drop the leading 'datasets'/'spaces' segment.
        repo_segments = segments[1:]
    else:
        repo_segments = segments
    # Repo ids are 'namespace/name' (2 segments) or a bare canonical name.
    repo_id = "/".join(repo_segments[:2])
    if not repo_id:
        return None
    return kind, repo_id


def _hf_api_path_for_kind(kind: HfArtifactKind) -> str:
    return {"model": "models", "dataset": "datasets", "space": "spaces"}[kind]


def fetch_hf_artifact_metrics(
    kind: HfArtifactKind,
    repo_id: str,
    *,
    token: Optional[str] = None,
    timeout: float = 15.0,
) -> Optional[dict]:
    """Fetch Hub popularity metrics for one artifact.

    Uses ``expand[]=trendingScore`` (plus likes/downloads) on the model/dataset/
    space detail endpoint. Returns ``{"trending_score", "likes", "downloads"}``
    or None when the artifact cannot be fetched (404, transient error, etc.).
    """
    import requests

    base = _hf_api_path_for_kind(kind)
    url = f"https://huggingface.co/api/{base}/{repo_id}"
    params = [
        ("expand[]", "trendingScore"),
        ("expand[]", "likes"),
        ("expand[]", "downloads"),
    ]

    headers = build_hf_headers(token=token, user_agent={"is_ci": "true"})
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except Exception:
        return None

    if response.status_code != 200:
        return None

    data = response.json()
    if not isinstance(data, dict):
        return None
    return {
        "trending_score": data.get("trendingScore"),
        "likes": data.get("likes"),
        "downloads": data.get("downloads"),
    }


def fetch_hf_artifacts_for_arxiv(
    arxiv_id: str,
    *,
    token: Optional[str] = None,
    timeout: float = 15.0,
    max_retries: int = 3,
    retry_backoff_seconds: float = 1.0,
) -> list[tuple[HfArtifactKind, str, str]]:
    """Discover HF artifacts linked to an arXiv paper via the Hub arxiv endpoint.

    Returns a list of ``(kind, repo_id, url)`` tuples. The Hub groups artifacts
    under ``models`` / ``datasets`` / ``spaces`` keys at
    ``https://huggingface.co/api/arxiv/{id}/repos``.

    A successful response containing empty lists returns ``[]``. Request
    failures and invalid responses raise ``HfArtifactDiscoveryError`` so callers
    do not persist a transient Hub failure as a conclusive negative result.
    """
    import requests

    canonical = re.sub(r"v\d+$", "", arxiv_id.strip())
    url = f"https://huggingface.co/api/arxiv/{canonical}/repos"
    headers = build_hf_headers(token=token, user_agent={"is_ci": "true"})
    response = None
    data = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise HfArtifactDiscoveryError(
                    f"Hub request failed for arXiv {canonical}"
                ) from exc
            time.sleep(retry_backoff_seconds * (2**attempt))
            continue

        if response.status_code != 200:
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == max_retries:
                raise HfArtifactDiscoveryError(
                    f"Hub returned HTTP {response.status_code} for arXiv {canonical}"
                )

            retry_after = response.headers.get("Retry-After")
            rate_limit = response.headers.get("RateLimit", "")
            delay = None
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    pass
            if delay is None:
                reset_match = re.search(
                    r"(?:^|[;,])\s*t\s*=\s*(\d+(?:\.\d+)?)", rate_limit
                )
                if reset_match:
                    delay = float(reset_match.group(1))
            if delay is None:
                delay = retry_backoff_seconds * (2**attempt)
            time.sleep(max(delay, 0.0))
            continue

        try:
            data = response.json()
        except ValueError as exc:
            if attempt == max_retries:
                raise HfArtifactDiscoveryError(
                    f"Hub returned invalid JSON for arXiv {canonical}"
                ) from exc
            time.sleep(retry_backoff_seconds * (2**attempt))
            continue

        if not isinstance(data, dict):
            if attempt == max_retries:
                raise HfArtifactDiscoveryError(
                    f"Hub returned an invalid payload for arXiv {canonical}"
                )
            time.sleep(retry_backoff_seconds * (2**attempt))
            continue
        if not all(
            isinstance(data.get(key), list) for key in ("models", "datasets", "spaces")
        ):
            if attempt == max_retries:
                raise HfArtifactDiscoveryError(
                    f"Hub returned an incomplete payload for arXiv {canonical}"
                )
            time.sleep(retry_backoff_seconds * (2**attempt))
            continue
        break

    if data is None:
        raise HfArtifactDiscoveryError(
            f"Hub did not return a result for arXiv {canonical}"
        )

    kind_by_key: dict[str, HfArtifactKind] = {
        "models": "model",
        "datasets": "dataset",
        "spaces": "space",
    }
    out: list[tuple[HfArtifactKind, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for key, kind in kind_by_key.items():
        entries = data.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            repo_id = None
            if isinstance(entry, dict):
                repo_id = entry.get("id") or entry.get("repoId")
            elif isinstance(entry, str):
                repo_id = entry
            if not repo_id:
                continue
            key_tuple = (kind, repo_id)
            if key_tuple in seen:
                continue
            seen.add(key_tuple)
            base = _hf_api_path_for_kind(kind)
            if kind == "model":
                artifact_url = f"https://huggingface.co/{repo_id}"
            else:
                artifact_url = f"https://huggingface.co/{base}/{repo_id}"
            out.append((kind, repo_id, artifact_url))
    return out


async def get_user_organizations(username: str) -> list[str]:
    """
    Get all organizations that a Hugging Face user belongs to by parsing their HF profile page.

    Args:
        username (str): The Hugging Face username

    Returns:
        list[str]: List of organization names the user belongs to

    Example:
        >>> orgs = await get_user_organizations("phython96")
        >>> print(orgs)  # ["CraftJarvis"]
    """
    url = f"https://huggingface.co/{username}"

    async def _fetch_profile():
        headers = build_hf_headers(token=False, user_agent={"is_ci": "true"})
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                return await response.text()

    try:
        # Shield from cancellation to prevent cancel scope propagation
        html_content = await asyncio.shield(_fetch_profile())

        organizations = []

        # Look for the Organizations section in the HTML
        # The HTML structure typically has an Organizations heading followed by organization links
        # Pattern 1: Look for text "Organizations" followed by links
        orgs_section_pattern = r"(?i)organizations.*?(?=<h[1-6]|$)"
        orgs_section_match = re.search(orgs_section_pattern, html_content, re.DOTALL)

        if orgs_section_match:
            orgs_section = orgs_section_match.group(0)
            # Look for organization profile links in this section
            # Organizations typically appear as href="/{org_name}" links
            org_links_pattern = r'href="/([^/\s"]+)"'
            org_matches = re.findall(org_links_pattern, orgs_section)

            # Filter out common non-organization paths and the username itself
            for org in org_matches:
                if (
                    org != username
                    and org
                    not in [
                        "models",
                        "datasets",
                        "spaces",
                        "papers",
                        "docs",
                        "settings",
                        "join",
                        "pricing",
                        "enterprise",
                        "community",
                        "login",
                        "signup",
                    ]
                    and not org.startswith("http")
                    and len(org) > 1
                ):
                    organizations.append(org)

        # Fallback pattern: Look for organization-style links throughout the page
        if not organizations:
            # Look for links that could be organizations (simple names without special characters)
            all_links_pattern = r'href="/([a-zA-Z0-9][a-zA-Z0-9_-]*)"'
            all_matches = re.findall(all_links_pattern, html_content)

            # Count occurrences and filter likely organization names
            link_counts = {}
            for link in all_matches:
                if (
                    link != username
                    and link
                    not in [
                        "models",
                        "datasets",
                        "spaces",
                        "papers",
                        "docs",
                        "settings",
                        "join",
                        "spaces",
                        "new",
                        "pricing",
                        "enterprise",
                        "community",
                        "login",
                        "signup",
                    ]
                    and not link.startswith("http")
                    and len(link) > 1
                ):
                    link_counts[link] = link_counts.get(link, 0) + 1

            # Organizations typically appear multiple times on a profile page
            # (in different sections like "Recent Activity", etc.)
            for link, count in link_counts.items():
                if count >= 2:  # Appears multiple times, likely an organization
                    organizations.append(link)

        # Remove duplicates while preserving order
        seen = set()
        unique_orgs = []
        for org in organizations:
            if org not in seen:
                seen.add(org)
                unique_orgs.append(org)

        return unique_orgs

    except asyncio.CancelledError:
        print(f"Request cancelled while fetching organizations for user {username}")
        return []
    except Exception as e:
        print(f"Error fetching organizations for user {username}: {e}")
        return []


if __name__ == "__main__":
    orgs = asyncio.run(get_user_organizations("nielsr"))
    print(orgs)
