import asyncio
import re
import time
from typing import Literal, Optional
from urllib.parse import urlparse, urlunparse

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError
from huggingface_hub.utils import build_hf_headers


HfArtifactKind = Literal["model", "dataset", "space"]
USER_OVERVIEW_TIMEOUT_SECONDS = 10


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
        repo_segments = segments[1:]
    else:
        repo_segments = segments
    repo_id = "/".join(repo_segments[:2])
    if not repo_id:
        return None
    return kind, repo_id


def _hf_api_path_for_kind(kind: HfArtifactKind) -> str:
    return {"model": "models", "dataset": "datasets", "space": "spaces"}[kind]


_HF_METRIC_FIELDS: dict[HfArtifactKind, tuple[str, ...]] = {
    "model": ("trendingScore", "likes", "downloads"),
    "dataset": ("trendingScore", "likes", "downloads"),
    "space": ("trendingScore", "likes"),
}


def fetch_hf_artifact_metrics(
    kind: HfArtifactKind,
    repo_id: str,
    *,
    token: Optional[str] = None,
    timeout: float = 15.0,
) -> Optional[dict]:
    """Fetch Hub popularity metrics for one artifact.

    Uses ``expand[]=trendingScore`` (plus likes, and downloads for models and
    datasets) on the model/dataset/space detail endpoint. Returns
    ``{"trending_score", "likes", "downloads"}``, with ``downloads`` None for
    Spaces because the Hub exposes no such counter for them, or None only when
    the artifact is conclusively missing (404). Transient,
    authentication, throttling, and malformed-response failures raise so callers
    cannot checkpoint a failed fetch as healthy.
    """
    import requests

    base = _hf_api_path_for_kind(kind)
    url = f"https://huggingface.co/api/{base}/{repo_id}"
    params = [("expand[]", field) for field in _HF_METRIC_FIELDS[kind]]

    headers = build_hf_headers(token=token, user_agent={"is_ci": "true"})
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise HfArtifactDiscoveryError(f"Hub metrics request failed: {exc}") from exc

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise HfArtifactDiscoveryError(
            f"Hub metrics request returned HTTP {response.status_code}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise HfArtifactDiscoveryError("Hub metrics response was not JSON") from exc
    if not isinstance(data, dict):
        raise HfArtifactDiscoveryError("Hub metrics response was not an object")
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
    Get the names of the organizations a Hugging Face user belongs to.

    Returns an empty list when the user does not exist or the Hub does not
    answer in time.

    Example:
        >>> orgs = await get_user_organizations("phython96")
        >>> print(orgs)  # ["CraftJarvis"]
    """
    try:
        async with asyncio.timeout(USER_OVERVIEW_TIMEOUT_SECONDS):
            user = await asyncio.to_thread(
                HfApi().get_user_overview, username, token=False
            )
    except (HfHubHTTPError, TimeoutError) as e:
        print(f"Error fetching organizations for user {username}: {e}")
        return []
    return [org.name for org in user.orgs]


if __name__ == "__main__":
    import sys

    orgs = asyncio.run(get_user_organizations(sys.argv[1]))
    print(orgs)
