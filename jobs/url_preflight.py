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
from PyPDF2.errors import PdfReadError

GITHUB_URL_PATTERN = r"\bhttps?:\/\/github\.com[^\s]*\b"
PROJECT_PAGE_URL_PATTERN = r"\bhttps?:\/\/[^\s\/]+\.github\.io[^\s]*\b"
MAX_TEXT_BYTES = 2_000_000
MAX_PDF_BYTES = 20_000_000
# Image-heavy technical reports often exceed MAX_PDF_BYTES; only page 1 is read.
MAX_FRONT_MATTER_PDF_BYTES = 60_000_000
TIMEOUT_SECONDS = 20
TEMPLATE_REPOSITORIES = {"academicpages/academicpages.github.io", "alshedivat/al-folio"}
OCR_MARKDOWN_BUCKET_ID = "huggingface/pwc-papers-content"
OCR_MARKDOWN_TOKEN_ENV = "PWC_PAPER_MARKDOWN_HF_TOKEN"

BENCHMARK_GAP_KINDS = {"review-benchmark-gaps", "add-benchmark"}
# Lab release pages publish their results tables as images, which the page
# Markdown keeps only as links: `[![alt](inline)](full-size)` or `![alt](src)`.
MARKDOWN_IMAGE_PATTERN = re.compile(
    r"\[?!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)[^)]*\)(?:\]\((?P<href>[^)\s]+)[^)]*\))?"
)
RESULTS_IMAGE_HINT = re.compile(
    r"bench|eval|result|leaderboard|score|chart|table|comparison|performance|metric",
    re.IGNORECASE,
)
MAX_RESULTS_IMAGES = 8
# Full-size results tables from release pages are often several megabytes.
MAX_IMAGE_BYTES = 20_000_000


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
        self.navigation_urls: list[str] = []
        self.navigation_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"nav", "header", "footer"}:
            self.navigation_depth += 1
        if tag == "a":
            value = dict(attrs).get("href")
            if value:
                if self.navigation_depth:
                    self.navigation_urls.append(value)
                else:
                    self.urls.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"nav", "header", "footer"}:
            self.navigation_depth = max(0, self.navigation_depth - 1)


def validate_paper_text(body: bytes) -> None:
    """Reject successful HTTP responses that contain a figure or empty wrapper."""
    text = body.decode("utf-8-sig", "replace").strip()
    title = re.search(r"^Title:\s*(.+)$", text, re.MULTILINE)
    if title and re.search(
        r"\.(?:svg|png|jpe?g|webp)(?:\?\S*)?$", title[1].strip(), re.I
    ):
        raise ValueError("paper endpoint returned an image caption")
    content = text.split("Markdown Content:", 1)[-1].strip()
    if len(content) < 800:
        raise ValueError("paper text is too short to establish source coverage")
    if re.match(
        r"(?:<!--.*?-->\s*)*<(?:svg\b|html\b|!doctype\b|\?xml\b)",
        content,
        re.I | re.S,
    ):
        raise ValueError("paper text is an image or HTML error page")


def _fetch(url: str, limit: int) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "PapersWithCode-Curation/1.0"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        final_url = response.geturl()
        prefix = response.read(12)
        # Project URLs can redirect to PDFs. Keep HTML bounded to the text
        # budget even when the caller allows a larger PDF or image response.
        if not prefix.startswith(b"%PDF-") and _image_suffix(prefix) is None:
            limit = min(limit, MAX_TEXT_BYTES)
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length > limit:
            raise ValueError(f"response exceeds {limit} bytes")
        body = prefix + response.read(limit + 1 - len(prefix))
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
    return _fetch_bucket_markdown(
        f"{base_arxiv_id[:4]}/{base_arxiv_id}.md",
        limit,
        token=token,
        bucket_id=bucket_id,
    )


def _fetch_external_markdown(
    paper_id: int,
    limit: int,
    *,
    token: str,
    bucket_id: str = OCR_MARKDOWN_BUCKET_ID,
) -> tuple[bytes, str]:
    """Read an external paper's prepared page or PDF Markdown from the bucket."""

    return _fetch_bucket_markdown(
        f"external/{int(paper_id)}.md", limit, token=token, bucket_id=bucket_id
    )


def _fetch_bucket_markdown(
    key: str, limit: int, *, token: str, bucket_id: str
) -> tuple[bytes, str]:
    path = urllib.parse.quote(key, safe="")
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


def extract_front_matter(pdf: bytes) -> str:
    """Return page 1 text and hyperlinks, where author affiliations live."""
    page = PdfReader(io.BytesIO(pdf), strict=False).pages[0]
    text = (page.extract_text() or "").strip()
    if not text:
        raise ValueError("first PDF page has no extractable text")
    links: list[str] = []
    try:
        for annotation_ref in page.get("/Annots") or []:
            uri = (annotation_ref.get_object().get("/A") or {}).get("/URI")
            if uri and str(uri) not in links:
                links.append(str(uri))
    except (PdfReadError, AttributeError, TypeError, KeyError):
        pass
    lines = ["# PDF page 1 (author affiliations and release links)", "", text]
    if links:
        lines += ["", "## Hyperlinks on page 1", ""] + [f"- {link}" for link in links]
    return "\n".join(lines) + "\n"


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
    if re.search(r"\.(?:svg|png|jpe?g|webp|gif|pdf)$", path, re.I):
        return None
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


def _image_suffix(body: bytes) -> str | None:
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if body.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if body.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return ".webp"
    return None


def results_image_links(markdown: str, base_url: str) -> list[tuple[str, list[str]]]:
    """Return (alt text, URLs to try) for images that look like benchmark results.

    A linked image tries its full-size target first, then the inline copy.
    """
    images: dict[str, tuple[str, list[str]]] = {}
    for match in MARKDOWN_IMAGE_PATTERN.finditer(markdown):
        alt = match.group("alt").strip()
        urls = [
            urllib.parse.urljoin(base_url, value)
            for value in (match.group("href"), match.group("src"))
            if value
        ]
        urls = [
            url
            for url in dict.fromkeys(urls)
            if url.startswith(("http://", "https://"))
        ]
        names = " ".join(
            urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1] for url in urls
        )
        if urls and RESULTS_IMAGE_HINT.search(f"{alt} {names}"):
            images.setdefault(urls[0], (alt, urls))
    return list(images.values())[:MAX_RESULTS_IMAGES]


def fetch_results_images(
    markdown: str, base_url: str, cache_dir: Path, *, fetch=_fetch
) -> tuple[list[dict], list[dict]]:
    """Download results images for the curator to view; return documents and errors."""
    documents: list[dict] = []
    errors: list[dict] = []
    for alt, urls in results_image_links(markdown, base_url):
        error = None
        for url in urls:
            try:
                body, _final_url = fetch(url, MAX_IMAGE_BYTES)
            except Exception as exc:
                error = type(exc).__name__
                continue
            suffix = _image_suffix(body)
            if suffix is None:
                error = "NotAnImage"
                continue
            sha256 = hashlib.sha256(body).hexdigest()
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached = cache_dir / f"{sha256}{suffix}"
            cached.write_bytes(body)
            documents.append(
                {
                    "kind": "results_image",
                    "url": url,
                    "alt": alt[:300],
                    "page_url": base_url,
                    "local_path": str(cached.resolve()),
                    "sha256": sha256,
                }
            )
            break
        else:
            errors.append({"source": "results_image", "url": urls[0], "error": error})
    return documents, errors


def extract_candidates(
    context: dict,
    *,
    fetch=_fetch,
    fetch_ocr_markdown=_fetch_ocr_markdown,
    fetch_external_markdown=_fetch_external_markdown,
    source_cache_dir: Path | None = None,
) -> dict:
    paper = context["paper"]
    arxiv_id = paper.get("arxiv_id")
    extracted_at = datetime.now(UTC).isoformat()
    candidates: dict[str, dict] = {}
    errors: list[dict] = []
    sources: list[dict] = []

    front_matter_pdf: tuple[str, bytes] | None = None

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
        if source_cache_dir is not None and source in {
            "hf_markdown",
            "ocr_markdown",
            "external_markdown",
        }:
            source_cache_dir.mkdir(parents=True, exist_ok=True)
            cached = source_cache_dir / f"{hashlib.sha256(body).hexdigest()}.md"
            cached.write_bytes(body)
            sources[-1]["local_path"] = str(cached.resolve())

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
            validate_paper_text(markdown)
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
                validate_paper_text(markdown)
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
    external_markdown_available = False
    if paper.get("source") == "external" and not arxiv_id and paper.get("id"):
        # First-party release sites often refuse the runner, so the backend's
        # prepared copy of the page is the readable source.
        markdown_attempted = bool(paper.get("markdown_expected"))
        token = os.environ.get(OCR_MARKDOWN_TOKEN_ENV)
        if token:
            try:
                markdown, final_url = fetch_external_markdown(
                    paper["id"], MAX_TEXT_BYTES, token=token
                )
                validate_paper_text(markdown)
                fetched(
                    "external_markdown",
                    f"hf://buckets/{OCR_MARKDOWN_BUCKET_ID}",
                    markdown,
                    final_url,
                )
                for raw in _matches(markdown.decode("utf-8", "replace")):
                    add(raw, "external_markdown")
                external_markdown_available = True
            except Exception as exc:
                errors.append(
                    {"source": "external_markdown", "error": type(exc).__name__}
                )
            check_liveness()
    paper_pdf_available = False
    if arxiv_id and not hf_markdown_available and not ocr_markdown_available:
        try:
            url = f"https://arxiv.org/pdf/{arxiv_id}"
            pdf, final_url = fetch(url, MAX_PDF_BYTES)
            reader = PdfReader(io.BytesIO(pdf), strict=False)
            text = "\n".join(page.extract_text() or "" for page in reader.pages[:2])
            validate_paper_text(text.encode())
            paper_pdf_available = True
            front_matter_pdf = (url, pdf)
            fetched("paper_pdf", url, pdf, final_url)
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
            errors.append({"source": "paper_pdf", "error": type(exc).__name__})
        check_liveness()

    # Organization tagging reads author affiliations, which arXiv HTML copies of
    # the Markdown frequently drop. Page 1 of the PDF keeps them.
    front_matter: dict | None = None
    if (
        (context.get("job") or {}).get("kind") == "enrich-paper"
        and arxiv_id
        and source_cache_dir is not None
        and (hf_markdown_available or ocr_markdown_available or paper_pdf_available)
    ):
        try:
            if front_matter_pdf is None:
                url = f"https://arxiv.org/pdf/{arxiv_id}"
                front_matter_pdf = (url, fetch(url, MAX_FRONT_MATTER_PDF_BYTES)[0])
            url, pdf = front_matter_pdf
            body = extract_front_matter(pdf).encode()
            sha256 = hashlib.sha256(body).hexdigest()
            source_cache_dir.mkdir(parents=True, exist_ok=True)
            cached = source_cache_dir / f"{sha256}.front-matter.md"
            cached.write_bytes(body)
            front_matter = {
                "kind": "paper_front_matter",
                "url": url,
                "local_path": str(cached.resolve()),
                "sha256": sha256,
            }
        except Exception as exc:
            errors.append({"source": "paper_front_matter", "error": type(exc).__name__})

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
                html, final_url = fetch(project_url, MAX_PDF_BYTES)
                if html.startswith(b"%PDF-"):
                    reader = PdfReader(io.BytesIO(html), strict=False)
                    pages = reader.pages[:2]
                    text = "\n".join(page.extract_text() or "" for page in pages)
                    validate_paper_text(text.encode())
                    fetched("project_page_pdf", project_url, html, final_url)
                    for raw in _matches(text):
                        add(raw, "project_page_pdf")
                    for page in pages:
                        # Hyperlinks supplement the validated text. Broken
                        # annotation objects must not invalidate readable PDFs.
                        try:
                            for annotation_ref in page.get("/Annots") or []:
                                annotation = annotation_ref.get_object()
                                uri = (annotation.get("/A") or {}).get("/URI")
                                if uri:
                                    add(str(uri), "project_page_pdf")
                        except (PdfReadError, AttributeError, TypeError, KeyError):
                            continue
                    continue
                fetched("project_page_html", project_url, html, final_url)
                parser = _Links()
                parser.feed(html.decode("utf-8", "replace"))
                for raw in parser.urls:
                    add(raw, "project_page_html", final_url)
                # Header Code buttons can be valid; sibling project links in
                # shared site navigation are not evidence of paper ownership.
                for raw in parser.navigation_urls:
                    normalized = normalize_candidate(raw, final_url)
                    if normalized and _kind(normalized) == "github":
                        add(raw, "project_page_navigation", final_url)
            except Exception as exc:
                errors.append(
                    {
                        "source": "project_page_html",
                        "url": project_url,
                        "error": type(exc).__name__,
                        "http_status": exc.code
                        if isinstance(exc, urllib.error.HTTPError)
                        else None,
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
    if paper.get("source") == "external" and not source_candidate:
        # Release-page papers often keep their scores on the model card.
        hf_models = paper.get("hf_models") or []
        if hf_models:
            model = str(hf_models[0]).strip().strip("/")
            document(
                "model_card",
                model
                if model.startswith("http")
                else f"https://huggingface.co/{model}",
            )
    for repository in paper.get("repositories") or []:
        if repository.get("is_official"):
            document("github_readme", repository.get("url"))
    for project_page in paper.get("project_pages") or []:
        if project_page.get("is_official"):
            document("project_page", project_page.get("url"))
    for source in sources:
        if source.get("source") == "external_markdown" and source.get("local_path"):
            # A validated local copy of the paper source page itself.
            for entry in source_documents:
                if entry["kind"] == "paper_source":
                    entry["local_path"] = source["local_path"]
                    entry["sha256"] = source["sha256"]
        elif source.get("source") in {"hf_markdown", "ocr_markdown"}:
            document("paper_markdown", source.get("final_url"))
            if source.get("local_path"):
                for entry in source_documents:
                    if entry["url"] == source["final_url"]:
                        entry["local_path"] = source["local_path"]
                        entry["sha256"] = source["sha256"]
        elif source.get("source") == "project_page_pdf":
            document("paper_pdf", source.get("final_url"))
        elif source.get("source") == "paper_pdf":
            document("paper_pdf", source.get("url"))

    if front_matter is not None:
        source_documents.append(front_matter)

    if (
        (context.get("job") or {}).get("kind") == "add-evals"
        and source_cache_dir is not None
        and paper.get("source_url")
    ):
        for source in sources:
            if source.get("source") == "external_markdown" and source.get("local_path"):
                images, image_errors = fetch_results_images(
                    Path(source["local_path"]).read_text(
                        encoding="utf-8", errors="replace"
                    ),
                    paper["source_url"],
                    source_cache_dir / "images",
                    fetch=fetch,
                )
                source_documents.extend(images)
                errors.extend(image_errors)

    markdown_available = (
        hf_markdown_available or ocr_markdown_available or external_markdown_available
    )
    paper_text_available = markdown_available or paper_pdf_available
    official_source_available = has_live("github") or has_live("project_page")

    def is_nonblocking(error: dict) -> bool:
        source = error.get("source")
        if source == "hf_api":
            # This endpoint only adds link metadata; paper text or verified
            # first-party links are sufficient evidence for enrichment.
            return paper_text_available or official_source_available
        if source in {"hf_markdown", "ocr_markdown"}:
            return paper_text_available
        if source == "external_markdown":
            # The live page remains the fallback when no copy exists.
            return True
        if source == "paper_pdf":
            return paper_text_available
        if source == "paper_front_matter":
            # Only organization tagging uses it; the skill falls back to the
            # Markdown header and the paper's release links.
            return True
        if source == "results_image":
            # The page Markdown still names the image; the agent can fetch it.
            return True
        if source == "project_page_html" and error.get("http_status") in {404, 410}:
            return paper_text_available
        return False

    blocking_errors = [error for error in errors if not is_nonblocking(error)]

    return {
        "schema_version": "url-candidates.v1",
        "paper_id": paper["id"],
        "complete": not blocking_errors,
        "markdown_available": markdown_available,
        "paper_text_available": paper_text_available,
        "awaiting_markdown": markdown_attempted and not paper_text_available,
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
    if (context.get("job") or {}).get("kind") in BENCHMARK_GAP_KINDS:
        # Benchmark-gap jobs have no scoped paper; the agent reads sources itself.
        result = {
            "complete": True,
            "candidates": [],
            "source_documents": [],
            "errors": [],
        }
    else:
        result = extract_candidates(
            context,
            source_cache_dir=Path(sys.argv[2]).resolve().parent / "paper-sources",
        )
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
