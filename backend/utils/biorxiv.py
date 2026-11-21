"""
bioRxiv / medRxiv metadata adapter.

The HTML pages on https://www.biorxiv.org and https://www.medrxiv.org are
served behind Cloudflare's bot challenge and return HTTP 403 to every
server-side request regardless of user agent. To support user submissions of
bio/medRxiv papers we instead pull metadata from the public bioRxiv API
(https://api.biorxiv.org), which is not behind the challenge.

For thumbnails, PDFs are fetched via Europe PMC mirrors when available, with
an optional fallback to the official requester-pays S3 TDM bucket
(s3://biorxiv-src-monthly / s3://medrxiv-src-monthly).
"""

from __future__ import annotations

import asyncio
import calendar
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional
from urllib.parse import urlparse

import aiohttp
import httpx

logger = logging.getLogger(__name__)

_API_HEADERS = {
    "User-Agent": (
        "paperswithcode.co external resource indexer (+https://paperswithcode.co)"
    ),
    "Accept": "application/json",
}

_EUROPEPMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_MAX_PDF_BYTES = 50 * 1024 * 1024


_DOI_IN_URL_RE = re.compile(
    r"((?:10\.1101|10\.64898)/[A-Za-z0-9._\-]+?)(?:v\d+)?(?:\.full(?:\.pdf)?)?(?:[/?#]|$)"
)

_EARLY_DOI_TAIL_RE = re.compile(r"^(\d{4}\.\d{2}\.\d{2}\.\d+)(?:v\d+)?(?:\.full)?$")

_PREPRINT_SERVERS = {
    "www.biorxiv.org": "biorxiv",
    "biorxiv.org": "biorxiv",
    "www.medrxiv.org": "medrxiv",
    "medrxiv.org": "medrxiv",
}


@dataclass
class BioRxivMetadata:
    """Normalized subset of the bioRxiv API response used for ingestion."""

    title: str
    abstract: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    date_published: Optional[date] = None
    doi: Optional[str] = None


def parse_biorxiv_doi(url: str) -> Optional[tuple[str, str]]:
    """
    Extract ``(server, doi)`` from a bio/medRxiv URL.

    Returns ``None`` if the URL is not a recognized bio/medRxiv link.
    ``server`` is the bioRxiv API server segment (``"biorxiv"`` or
    ``"medrxiv"``). ``doi`` is the canonical DOI without version suffix
    (e.g. ``"10.1101/2025.05.14.654049"``).
    """
    if not url:
        return None

    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    server = _PREPRINT_SERVERS.get(host)
    if not server:
        return None

    match = _DOI_IN_URL_RE.search(parsed.path)
    if match:
        return server, match.group(1)

    tail = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    early_match = _EARLY_DOI_TAIL_RE.match(tail)
    if early_match:
        return server, f"10.1101/{early_match.group(1)}"

    return None


def _split_author_string(raw: str) -> List[str]:
    """Convert the bioRxiv "Last, F.; ..." author string to ``["First Last", ...]``."""
    if not raw:
        return []

    out: List[str] = []
    for entry in raw.split(";"):
        name = entry.strip()
        if not name:
            continue
        if "," in name:
            last, _, first = name.partition(",")
            last = last.strip()
            first = first.strip()
            display = f"{first} {last}".strip() if first else last
        else:
            display = name
        if display:
            out.append(display)
    return out


async def fetch_biorxiv_metadata(
    url: str, timeout_seconds: float = 12.0
) -> Optional[BioRxivMetadata]:
    """
    Fetch metadata for a bio/medRxiv URL via the public API.

    Returns ``None`` if the URL is not a bio/medRxiv link or the API call
    fails. Raised exceptions are swallowed and logged: callers should treat a
    ``None`` return as "fall back to generic extraction".
    """
    parsed = parse_biorxiv_doi(url)
    if parsed is None:
        return None

    server, doi = parsed
    api_url = f"https://api.biorxiv.org/details/{server}/{doi}"

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    try:
        async with aiohttp.ClientSession(
            headers=_API_HEADERS, timeout=timeout
        ) as session:
            async with session.get(api_url, allow_redirects=True) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        logger.warning("biorxiv api fetch failed for %s: %s", api_url, exc)
        return None
    except asyncio.CancelledError:
        return None

    collection = (payload or {}).get("collection") or []
    if not isinstance(collection, list) or not collection:
        return None

    def _version_key(item: dict) -> int:
        try:
            return int(str(item.get("version") or "1"))
        except (TypeError, ValueError):
            return 1

    entry = max(
        (e for e in collection if isinstance(e, dict)),
        key=_version_key,
        default=None,
    )
    if entry is None:
        return None

    title = (entry.get("title") or "").strip()
    if not title:
        return None

    abstract = (entry.get("abstract") or "").strip() or None
    authors = _split_author_string(entry.get("authors") or "")

    date_str = entry.get("date")
    parsed_date: Optional[date] = None
    if isinstance(date_str, str) and date_str:
        try:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            logger.warning("biorxiv api returned unparseable date %r", date_str)

    return BioRxivMetadata(
        title=title,
        abstract=abstract,
        authors=authors,
        date_published=parsed_date,
        doi=str(entry.get("doi") or doi),
    )


def build_biorxiv_pdf_url(
    server: str, doi: str, version: str | int = "1", date_str: str | None = None
) -> str:
    """
    Build the canonical ``*.full.pdf`` URL for a bio/medRxiv preprint.

    The URL is usually blocked by Cloudflare for server-side clients; callers
    should prefer :func:`download_biorxiv_pdf_bytes`.
    """
    host = "www.medrxiv.org" if server == "medrxiv" else "www.biorxiv.org"
    version_suffix = f"v{int(version)}"
    doi_suffix = doi.split("/", 1)[-1]
    if date_str:
        posted = datetime.strptime(date_str, "%Y-%m-%d").date()
        return (
            f"https://{host}/content/early/"
            f"{posted.year:04d}/{posted.month:02d}/{posted.day:02d}/"
            f"{doi_suffix}{version_suffix}.full.pdf"
        )
    return f"https://{host}/content/{doi}{version_suffix}.full.pdf"


async def fetch_europepmc_pdf_url(
    doi: str, timeout_seconds: float = 20.0
) -> Optional[str]:
    """
    Resolve a Europe PMC-hosted PDF URL for a bio/medRxiv DOI, if indexed.
    """
    params = {
        "query": f"DOI:{doi}",
        "format": "json",
        "resultType": "core",
        "pageSize": 1,
    }
    headers = {"User-Agent": _API_HEADERS["User-Agent"], "Accept": "application/json"}
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        response = await client.get(_EUROPEPMC_SEARCH_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    results = (payload or {}).get("resultList", {}).get("result") or []
    if not results:
        return None

    for entry in results[0].get("fullTextUrlList", {}).get("fullTextUrl", []):
        if entry.get("documentStyle") != "pdf":
            continue
        url = (entry.get("url") or "").strip()
        if not url:
            continue
        host = (urlparse(url).hostname or "").lower()
        if host.endswith("biorxiv.org") or host.endswith("medrxiv.org"):
            continue
        return url
    return None


async def _download_pdf_url(url: str, timeout_seconds: float = 60.0) -> Optional[bytes]:
    from backend.services.safe_outbound_http_service import (
        SafeOutboundHttpError,
        fetch_public_resource,
    )

    try:
        result = await fetch_public_resource(
            url,
            allowed_content_types=frozenset(
                {"application/pdf", "application/octet-stream"}
            ),
            max_bytes=_MAX_PDF_BYTES,
            timeout_seconds=timeout_seconds,
            allowed_hosts=frozenset(
                {
                    "europepmc.org",
                    "ftp.ncbi.nlm.nih.gov",
                    "www.ebi.ac.uk",
                    "www.europepmc.org",
                }
            ),
        )
    except SafeOutboundHttpError as exc:
        logger.warning("bioRxiv PDF safe fetch failed: %s", exc)
        return None
    content = result.body
    if not content.startswith(b"%PDF"):
        logger.warning("bioRxiv PDF URL did not return PDF bytes: %s", url)
        return None
    return content


def _month_folder_from_date(date_str: str) -> str:
    posted = datetime.strptime(date_str, "%Y-%m-%d").date()
    last_day = calendar.monthrange(posted.year, posted.month)[1]
    if posted.day == last_day:
        posted = posted + timedelta(days=1)
    return posted.strftime("%B_%Y")


def _extract_pdf_from_meca(data: bytes) -> Optional[bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".pdf"):
                if archive.getinfo(name).file_size > _MAX_PDF_BYTES:
                    return None
                return archive.read(name)
    return None


def _download_biorxiv_pdf_from_s3(
    server: str,
    doi: str,
    date_str: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
) -> Optional[bytes]:
    import boto3
    from botocore.config import Config

    bucket = "medrxiv-src-monthly" if server == "medrxiv" else "biorxiv-src-monthly"
    prefix = f"Current_Content/{_month_folder_from_date(date_str)}/"
    token = doi.split("/")[-1].lower()

    s3 = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name="us-east-1",
        config=Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 2}),
    )

    paginator = s3.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(
        Bucket=bucket, Prefix=prefix, RequestPayer="requester"
    ):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".meca"):
                keys.append(key)

    if not keys:
        return None

    candidate_keys = [key for key in keys if token in key.lower()]
    if not candidate_keys:
        candidate_keys = keys[: min(200, len(keys))]

    for key in candidate_keys:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key, RequestPayer="requester")
            if int(obj.get("ContentLength") or 0) > 2 * _MAX_PDF_BYTES:
                continue
            archive_bytes = obj["Body"].read(2 * _MAX_PDF_BYTES + 1)
            if len(archive_bytes) > 2 * _MAX_PDF_BYTES:
                continue
            pdf_bytes = _extract_pdf_from_meca(archive_bytes)
            if pdf_bytes and pdf_bytes.startswith(b"%PDF"):
                return pdf_bytes
        except Exception as exc:
            logger.debug("Failed to read MECA object %s: %s", key, exc)
    return None


async def download_biorxiv_pdf_bytes(
    source_url: str,
    aws_access_key_id: str = "",
    aws_secret_access_key: str = "",
    timeout_seconds: float = 60.0,
) -> Optional[bytes]:
    """
    Download a bio/medRxiv PDF using API metadata plus allowed mirrors.

    Resolution order:
    1. Europe PMC ``fulltextRepo`` PDF (when indexed)
    2. Official requester-pays S3 TDM bucket (when AWS credentials are set)
    """
    parsed = parse_biorxiv_doi(source_url)
    if parsed is None:
        return None

    server, doi = parsed
    metadata = await fetch_biorxiv_metadata(
        source_url, timeout_seconds=min(20.0, timeout_seconds)
    )
    if metadata is None or not metadata.doi:
        return None

    epmc_url = await fetch_europepmc_pdf_url(metadata.doi, timeout_seconds=20.0)
    if epmc_url:
        try:
            pdf_bytes = await _download_pdf_url(
                epmc_url, timeout_seconds=timeout_seconds
            )
            if pdf_bytes is not None:
                return pdf_bytes
        except httpx.HTTPError as exc:
            logger.warning(
                "Europe PMC PDF download failed for %s: %s", metadata.doi, exc
            )

    if aws_access_key_id and aws_secret_access_key and metadata.date_published:
        date_str = metadata.date_published.isoformat()
        loop = asyncio.get_running_loop()
        pdf_bytes = await loop.run_in_executor(
            None,
            _download_biorxiv_pdf_from_s3,
            server,
            metadata.doi,
            date_str,
            aws_access_key_id,
            aws_secret_access_key,
        )
        if pdf_bytes is not None:
            return pdf_bytes

    return None
