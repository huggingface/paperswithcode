"""Bounded, deterministic URL-candidate extraction for remote enrichment jobs."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

from PyPDF2 import PdfReader

GITHUB_URL_PATTERN = r"\bhttps?:\/\/github\.com[^\s]*\b"
PROJECT_PAGE_URL_PATTERN = r"\bhttps?:\/\/[^\s\/]+\.github\.io[^\s]*\b"
MAX_TEXT_BYTES = 2_000_000
MAX_PDF_BYTES = 20_000_000
TIMEOUT_SECONDS = 20
TEMPLATE_REPOSITORIES = {"academicpages/academicpages.github.io", "alshedivat/al-folio"}
OCR_MARKDOWN_BUCKET_ID = "huggingface/pwc-papers-content"
OCR_MARKDOWN_TOKEN_ENV = "PWC_PAPER_MARKDOWN_HF_TOKEN"


class _BucketRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Strip bucket credentials before following a cross-origin redirect."""

    def redirect_request(self, request, _response, code, message, headers, newurl):
        redirected = super().redirect_request(
            request, _response, code, message, headers, newurl
        )
        if redirected is None:
            return None
        source = urllib.parse.urlsplit(request.full_url)
        destination = urllib.parse.urlsplit(redirected.full_url)
        if (
            source.scheme == destination.scheme
            and source.hostname == destination.hostname
            and source.port == destination.port
        ):
            return redirected
        return urllib.request.Request(
            redirected.full_url,
            headers={"User-Agent": "PapersWithCode-Curation/1.0"},
        )


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            value = dict(attrs).get("href")
            if value:
                self.urls.append(value)


def _fetch(url: str, limit: int) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "PapersWithCode-Curation/1.0"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        final_url = response.geturl()
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length > limit:
            raise ValueError(f"response exceeds {limit} bytes")
        body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError(f"response exceeds {limit} bytes")
        return body, final_url


def _fetch_ocr_markdown(
    arxiv_id: str,
    limit: int,
    *,
    token: str,
    bucket_id: str = OCR_MARKDOWN_BUCKET_ID,
) -> tuple[bytes, str]:
    """Read canonical OCR Markdown from the private Papers with Code bucket."""

    base_arxiv_id = re.sub(r"v\d+$", "", arxiv_id.strip())
    path = urllib.parse.quote(f"{base_arxiv_id[:4]}/{base_arxiv_id}.md", safe="")
    bucket = urllib.parse.quote(bucket_id, safe="/")
    url = f"https://huggingface.co/buckets/{bucket}/resolve/{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "PapersWithCode-Curation/1.0",
        },
    )
    opener = urllib.request.build_opener(_BucketRedirectHandler())
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length > limit:
            raise ValueError(f"response exceeds {limit} bytes")
        body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError(f"response exceeds {limit} bytes")
        # Do not persist the signed CDN URL after redirecting from the bucket.
        return body, url


def normalize_candidate(raw: str, base_url: str | None = None) -> str | None:
    raw = raw.strip().rstrip(".,;:!?)]}'\"")
    if base_url:
        raw = urllib.parse.urljoin(base_url, raw)
    try:
        parsed = urllib.parse.urlsplit(raw)
    except ValueError:
        # Markdown link syntax can leave a second URL attached to the first.
        # Ignore that malformed candidate without discarding the whole source.
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    if host == "github.com":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            return None
        return f"https://github.com/{parts[0]}/{parts[1].removesuffix('.git')}"
    if not host.endswith(".github.io"):
        return None
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit(("https", host, path, "", ""))


def _kind(url: str) -> str:
    return (
        "github"
        if urllib.parse.urlsplit(url).hostname == "github.com"
        else "project_page"
    )


def _hint(url: str) -> str | None:
    parsed = urllib.parse.urlsplit(url)
    identity = f"{parsed.path.strip('/')}".lower()
    return (
        "known_website_template_repository"
        if identity in TEMPLATE_REPOSITORIES
        else None
    )


def _matches(text: str) -> Iterable[str]:
    for pattern in (GITHUB_URL_PATTERN, PROJECT_PAGE_URL_PATTERN):
        yield from re.findall(pattern, text)


def extract_candidates(
    context: dict,
    *,
    fetch=_fetch,
    fetch_ocr_markdown=_fetch_ocr_markdown,
) -> dict:
    paper = context["paper"]
    arxiv_id = paper.get("arxiv_id")
    extracted_at = datetime.now(UTC).isoformat()
    candidates: dict[str, dict] = {}
    errors: list[dict] = []
    sources: list[dict] = []

    def fetched(source: str, url: str, body: bytes, final_url: str) -> None:
        sources.append(
            {
                "source": source,
                "url": url,
                "final_url": final_url,
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )

    def add(raw: str, source: str, base_url: str | None = None) -> None:
        normalized = normalize_candidate(raw, base_url)
        if not normalized:
            return
        current = candidates.setdefault(
            normalized,
            {
                "kind": _kind(normalized),
                "url": raw,
                "normalized_url": normalized,
                "source_layers": [],
                "live": None,
                "extracted_at": extracted_at,
                "rejection_hint": _hint(normalized),
            },
        )
        if source not in current["source_layers"]:
            current["source_layers"].append(source)

    for raw in _matches(paper.get("abstract") or ""):
        add(raw, "stored_abstract")

    for repository in paper.get("repositories") or []:
        if repository.get("is_official") and repository.get("url"):
            add(
                repository["url"],
                f"job_context.repository.{repository.get('source') or 'unknown'}",
            )
    for project_page in paper.get("project_pages") or []:
        if project_page.get("is_official") and project_page.get("url"):
            add(
                project_page["url"],
                f"job_context.project_page.{project_page.get('source') or 'unknown'}",
            )

    def check_liveness() -> None:
        for item in candidates.values():
            if item["live"] is not None:
                continue
            try:
                request = urllib.request.Request(
                    item["normalized_url"],
                    method="HEAD",
                    headers={"User-Agent": "PapersWithCode-Curation/1.0"},
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    item["live"] = response.status < 400
            except urllib.error.HTTPError as exc:
                item["live"] = exc.code in {401, 403, 405, 429}
            except Exception:
                item["live"] = False

    def has_live(kind: str) -> bool:
        return any(
            item["kind"] == kind and item["live"] and not item["rejection_hint"]
            for item in candidates.values()
        )

    check_liveness()

    project_pages: list[str] = []
    markdown_attempted = False
    hf_markdown_available = False
    if arxiv_id and not (has_live("github") and has_live("project_page")):
        try:
            url = f"https://huggingface.co/api/papers/{arxiv_id}"
            metadata_raw, final_url = fetch(url, MAX_TEXT_BYTES)
            fetched("hf_api", url, metadata_raw, final_url)
            metadata = json.loads(metadata_raw)
            for field in ("githubRepo", "projectPage"):
                if metadata.get(field):
                    add(metadata[field], f"hf_api.{field}")
            if metadata.get("projectPage"):
                project_pages.append(metadata["projectPage"])
        except Exception as exc:
            errors.append({"source": "hf_api", "error": type(exc).__name__})
        check_liveness()
    if arxiv_id:
        markdown_attempted = True
        try:
            url = f"https://huggingface.co/papers/{arxiv_id}.md"
            markdown, final_url = fetch(url, MAX_TEXT_BYTES)
            hf_markdown_available = True
            fetched("hf_markdown", url, markdown, final_url)
            for raw in _matches(markdown.decode("utf-8", "replace")):
                add(raw, "hf_markdown")
        except Exception as exc:
            errors.append({"source": "hf_markdown", "error": type(exc).__name__})
        check_liveness()
    ocr_markdown_available = False
    if arxiv_id and not hf_markdown_available:
        token = os.environ.get(OCR_MARKDOWN_TOKEN_ENV)
        if token:
            try:
                markdown, final_url = fetch_ocr_markdown(
                    arxiv_id, MAX_TEXT_BYTES, token=token
                )
                fetched(
                    "ocr_markdown",
                    f"hf://buckets/{OCR_MARKDOWN_BUCKET_ID}",
                    markdown,
                    final_url,
                )
                for raw in _matches(markdown.decode("utf-8", "replace")):
                    add(raw, "ocr_markdown")
                errors = [item for item in errors if item["source"] != "hf_markdown"]
                ocr_markdown_available = True
            except Exception as exc:
                errors.append({"source": "ocr_markdown", "error": type(exc).__name__})
            check_liveness()
    if (
        arxiv_id
        and not hf_markdown_available
        and not ocr_markdown_available
        and not (has_live("github") or has_live("project_page"))
    ):
        try:
            url = f"https://arxiv.org/pdf/{arxiv_id}"
            pdf, final_url = fetch(url, MAX_PDF_BYTES)
            fetched("pdf_first_two_pages", url, pdf, final_url)
            reader = PdfReader(io.BytesIO(pdf), strict=False)
            for page_number, page in enumerate(reader.pages[:2], start=1):
                for raw in _matches(page.extract_text() or ""):
                    add(raw, f"pdf_page_{page_number}_text")
                annotations = page.get("/Annots") or []
                for annotation_ref in annotations:
                    annotation = annotation_ref.get_object()
                    uri = (annotation.get("/A") or {}).get("/URI")
                    if uri:
                        add(str(uri), f"pdf_page_{page_number}_hyperlink")
        except Exception as exc:
            errors.append(
                {"source": "pdf_first_two_pages", "error": type(exc).__name__}
            )
        check_liveness()

    if not has_live("github"):
        project_pages.extend(
            page.get("url", "")
            for page in paper.get("project_pages", [])
            if page.get("url")
        )
        project_pages.extend(
            item["normalized_url"]
            for item in candidates.values()
            if item["kind"] == "project_page" and item["live"]
        )
        for project_url in dict.fromkeys(project_pages):
            try:
                html, final_url = fetch(project_url, MAX_TEXT_BYTES)
                fetched("project_page_html", project_url, html, final_url)
                parser = _Links()
                parser.feed(html.decode("utf-8", "replace"))
                for raw in parser.urls:
                    add(raw, "project_page_html", final_url)
            except Exception as exc:
                errors.append(
                    {
                        "source": "project_page_html",
                        "url": project_url,
                        "error": type(exc).__name__,
                    }
                )

    check_liveness()

    source_documents: list[dict[str, str]] = []
    seen_documents: set[str] = set()

    def document(kind: str, url: str | None) -> None:
        if not url or url in seen_documents:
            return
        normalized = url.strip()
        if not normalized.startswith(("http://", "https://")):
            return
        seen_documents.add(normalized)
        source_documents.append({"kind": kind, "url": normalized})

    document("paper_source", paper.get("source_url"))
    source_candidate = context.get("source_candidate") or {}
    document("model_card", source_candidate.get("model_card_url"))
    for repository in paper.get("repositories") or []:
        if repository.get("is_official"):
            document("github_readme", repository.get("url"))
    for project_page in paper.get("project_pages") or []:
        if project_page.get("is_official"):
            document("project_page", project_page.get("url"))
    for source in sources:
        if source.get("source") in {"hf_markdown", "ocr_markdown"}:
            document("paper_markdown", source.get("url"))

    markdown_available = hf_markdown_available or ocr_markdown_available
    official_source_available = has_live("github") or has_live("project_page")

    def is_nonblocking(error: dict) -> bool:
        source = error.get("source")
        if source == "hf_api":
            # This endpoint only adds link metadata; paper text or verified
            # first-party links are sufficient evidence for enrichment.
            return markdown_available or official_source_available
        if source in {"hf_markdown", "ocr_markdown"}:
            return official_source_available
        if source == "pdf_first_two_pages":
            return markdown_available or official_source_available
        return False

    blocking_errors = [error for error in errors if not is_nonblocking(error)]

    return {
        "schema_version": "url-candidates.v1",
        "paper_id": paper["id"],
        "complete": not blocking_errors,
        "markdown_available": markdown_available,
        "awaiting_markdown": markdown_attempted
        and not (markdown_available or official_source_available),
        "candidates": list(candidates.values())[:50],
        "sources": sources[:20],
        "source_documents": source_documents[:20],
        "errors": errors[:20],
    }


def main() -> None:
    import sys

    if len(sys.argv) != 3:
        raise SystemExit("usage: url_preflight.py CONTEXT.json OUTPUT.json")
    context = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    Path(sys.argv[2]).write_text(
        json.dumps(extract_candidates(context), indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
