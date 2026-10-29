# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "chandra-ocr==0.2.0",
#   "httpx>=0.28.1",
#   "pillow>=11.0.0",
#   "pypdf>=5.0.0",
#   "vllm==0.17.0",
# ]
# ///
"""Generate missing paper Markdown with Chandra OCR 2 on an HF Job.

The worker mirrors bounded state through the authenticated Bucket API. A
manifest is immutable, each paper is checkpointed independently, and canonical
Markdown is uploaded with its verified assets and status record.

With ``--layout-bucket-id`` the same OCR pass also stores page-aware layout for
reader citations in that bucket, keyed like the canonical object:

- ``<key>.layout.json``: Chandra's raw per-page output, the source of truth;
- ``<key>.md``: Markdown with a ``<!-- pwc:p{page}b{block} -->`` anchor per block;
- ``<key>.blocks.json``: anchor -> page, label, bbox (0-1000 grid), section.

Manifest entries marked ``layout_only`` already have canonical Markdown, which
is left untouched; they only gain the layout objects.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from PIL import Image

MODEL_ID = os.environ.get("PWC_MARKDOWN_MODEL_ID", "datalab-to/chandra-ocr-2")
MODEL_REVISION = os.environ.get(
    "PWC_MARKDOWN_MODEL_REVISION",
    "af93b47dba1b47b6640c86ccf487ed2260ab9a09",
)
MAX_PAGES = int(os.environ.get("PWC_MARKDOWN_MAX_PAGES", "30"))
USER_AGENT = "paperswithcode-paper-markdown/1.0 (https://paperswithcode.co)"
MAX_PDF_BYTES = 150 * 1024 * 1024
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 80_000_000
MARKDOWN_IMAGE = re.compile(r"(!\[[^\]]*\]\()(?P<source>[^)\s]+)(\))")
HTML_IMAGE = re.compile(
    r"(<img\b[^>]*\bsrc=[\"'])(?P<source>[^\"']+)([\"'][^>]*>)", re.IGNORECASE
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
FORMAT_EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
TITLE_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "or",
        "the",
        "to",
        "toward",
        "towards",
        "via",
        "with",
    }
)
IMAGE_FILENAME_ONLY = re.compile(
    r"\s*(?:!\[[^\]]*\]\()?[^\s()<>]+\.(?:png|jpe?g|webp)(?:\))?\s*",
    re.IGNORECASE,
)
# arXiv HTML pages that failed to convert are scraped with a figure file as their
# <title> and only a caption as their body.
SCRAPED_IMAGE_TITLE = re.compile(
    r"\.(?:svg|png|jpe?g|gif|webp|bmp|tiff?|eps|pdf)\s*$", re.IGNORECASE
)
# arXiv HTML footer that a failed conversion returns in place of the paper.
ARXIV_HTML_FEEDBACK = re.compile(
    r"^Instructions for reporting errors\r?\n-{3,}\r?\n.*",
    re.MULTILINE | re.DOTALL,
)
MIN_MARKDOWN_BODY_CHARS = 2000
STATUS_SCHEMA_VERSION = 2
MARKDOWN_MANIFEST_SCHEMA_VERSION = 1
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
MARKDOWN_MIGRATION_LOCK_KEY = "_content/migration.lock"
MAX_ATTEMPTS = int(os.environ.get("PWC_MARKDOWN_MAX_ATTEMPTS", "3"))
CHANDRA_PAGE_BATCH_SIZE = 28
CHANDRA_MAX_OUTPUT_TOKENS = 12384
LAYOUT_SCHEMA_VERSION = 1
LAYOUT_SKIPPED_LABELS = {"Blank-Page", "Page-Header", "Page-Footer"}
LAYOUT_NON_TEXT_LABELS = {"Image", "Figure"}
VLLM_SHUTDOWN_TIMEOUT_SECONDS = int(
    os.environ.get("PWC_MARKDOWN_VLLM_SHUTDOWN_TIMEOUT_SECONDS", "60")
)
_TERMINATION_REQUESTED = False
BUCKET_BRIDGE_HUB_VERSION = "1.23.0"
BUCKET_BRIDGE_CODE = r"""
import json
import sys
from pathlib import Path

from huggingface_hub import HfApi

request = json.load(sys.stdin)
api = HfApi()
bucket_id = request["bucket_id"]
operation = request["operation"]
if operation == "existing":
    paths = api.get_bucket_paths_info(bucket_id, request["keys"])
    response = {"paths": [str(item.path) for item in paths]}
elif operation == "download":
    files = [(key, Path(destination)) for key, destination in request["files"]]
    for _, destination in files:
        destination.parent.mkdir(parents=True, exist_ok=True)
    api.download_bucket_files(
        bucket_id,
        files,
        raise_on_missing_files=True,
    )
    response = {}
elif operation == "upload":
    api.batch_bucket_files(
        bucket_id,
        add=[(Path(source), destination) for source, destination in request["files"]],
    )
    response = {}
else:
    raise ValueError(f"unsupported bucket bridge operation: {operation}")
json.dump(response, sys.stdout)
"""


def run_bucket_bridge(token: str, request: dict[str, object]) -> dict[str, object]:
    """Run bucket I/O in an SDK environment isolated from vLLM's SDK ceiling."""
    environment = os.environ.copy()
    environment["HF_TOKEN"] = token
    completed = subprocess.run(
        [
            "uv",
            "run",
            "--no-project",
            "--with",
            f"huggingface-hub=={BUCKET_BRIDGE_HUB_VERSION}",
            "python",
            "-c",
            BUCKET_BRIDGE_CODE,
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip()[-2000:]
        raise RuntimeError(f"bucket bridge failed: {detail}")
    return json.loads(completed.stdout)


class BucketContentStore:
    """Mirror bounded worker state through the Bucket API without a volume."""

    def __init__(self, bucket_id: str, token: str, content_root: Path) -> None:
        self.bucket_id = bucket_id
        self.token = token
        self.content_root = content_root
        self.repairs: dict[str, dict[str, object]] = {}

    def existing(self, keys: list[str]) -> set[str]:
        if not keys:
            return set()
        response = run_bucket_bridge(
            self.token,
            {"operation": "existing", "bucket_id": self.bucket_id, "keys": keys},
        )
        return {str(path) for path in response["paths"]}

    def read(self, key: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="pwc-paper-read-") as directory:
            destination = Path(directory) / Path(key).name
            run_bucket_bridge(
                self.token,
                {
                    "operation": "download",
                    "bucket_id": self.bucket_id,
                    "files": [(key, str(destination))],
                },
            )
            return destination.read_bytes()

    def download(self, key: str) -> None:
        self.download_many([key])

    def download_many(self, keys: list[str]) -> None:
        if not keys:
            return
        destinations = []
        for key in keys:
            destination = self.content_root / key
            destination.parent.mkdir(parents=True, exist_ok=True)
            destinations.append((key, str(destination)))
        run_bucket_bridge(
            self.token,
            {
                "operation": "download",
                "bucket_id": self.bucket_id,
                "files": destinations,
            },
        )

    def prepare(self, manifest_key: str, entries: list[dict[str, object]]) -> None:
        run_id = Path(manifest_key).parent.name
        shard_id = Path(manifest_key).stem
        result_key = f"_jobs/results/{run_id}/{shard_id}.jsonl"
        progress_key = f"_jobs/progress/{run_id}/{shard_id}.json"
        status_keys = [entry_status_key(entry) for entry in entries]
        output_keys = [str(entry["output_key"]) for entry in entries]
        manifest_keys = [
            markdown_manifest_key(entry_paper_key(entry)) for entry in entries
        ]
        pdf_keys = [str(entry["pdf_key"]) for entry in entries if entry.get("pdf_key")]
        existing = self.existing(
            [
                MARKDOWN_MIGRATION_LOCK_KEY,
                result_key,
                progress_key,
                *status_keys,
                *output_keys,
                *manifest_keys,
                *pdf_keys,
            ]
        )
        if MARKDOWN_MIGRATION_LOCK_KEY in existing:
            raise ValueError("markdown_migration_locked")
        self.repairs = {
            str(entry["output_key"]): entry
            for entry in entries
            if entry.get("replace_invalid_sha256")
        }
        current_outputs = {
            str(entry["output_key"])
            for entry in entries
            if markdown_manifest_key(entry_paper_key(entry)) in existing
        }
        preserved_outputs = existing.intersection(current_outputs) - self.repairs.keys()
        for key in preserved_outputs:
            # process() only needs existence to preserve a canonical object.
            atomic_write(self.content_root / key, b"")
        self.download_many(sorted(existing - preserved_outputs))
        for key, entry in self.repairs.items():
            if key not in existing:
                raise ValueError("repair_original_missing")
            validate_repair_original(entry, (self.content_root / key).read_bytes())
        asset_keys: list[str] = []
        for status_key in status_keys:
            path = self.content_root / status_key
            if not path.exists():
                continue
            try:
                status = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            asset_keys.extend(str(key) for key in status.get("asset_keys") or [])
        self.download_many(sorted(self.existing(asset_keys)))

    def upload(self, keys: list[str]) -> None:
        unique = list(dict.fromkeys(keys))
        mutable_prefixes = ("_jobs/", "_content/manifests/")
        immutable = [key for key in unique if not key.startswith(mutable_prefixes)]
        for key in self.existing(immutable):
            local = (self.content_root / key).read_bytes()
            remote = self.read(key)
            if remote != local:
                entry = self.repairs.get(key)
                if entry is None:
                    raise ValueError(f"immutable_asset_conflict:{key}")
                validate_repair_original(entry, remote)
                validate_canonical_markdown(str(entry["title"]), local.decode("utf-8"))
                backup_key = (
                    f"_jobs/repair-originals/{entry['replace_invalid_sha256']}/{key}"
                )
                atomic_write(self.content_root / backup_key, remote)
                self.upload([backup_key])
                if self.read(backup_key) != remote:
                    raise ValueError("repair_backup_verification_failed")
                if self.read(key) != remote:
                    raise ValueError("repair_original_changed")
        additions = [
            (str(self.content_root / key), key)
            for key in unique
            if (self.content_root / key).is_file()
        ]
        if additions:
            run_bucket_bridge(
                self.token,
                {
                    "operation": "upload",
                    "bucket_id": self.bucket_id,
                    "files": additions,
                },
            )


def request_termination(_signum: int, _frame: object) -> None:
    global _TERMINATION_REQUESTED
    _TERMINATION_REQUESTED = True


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_bytes(data)
    temporary.replace(path)


def wait_for_vllm(process: subprocess.Popen[bytes], timeout: int = 900) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("vLLM exited during startup")
        try:
            if httpx.get("http://127.0.0.1:8000/health", timeout=2).is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise TimeoutError("vLLM startup timed out")


def start_vllm() -> subprocess.Popen[bytes]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            MODEL_ID,
            "--revision",
            MODEL_REVISION,
            "--served-model-name",
            "chandra",
            "--max-model-len",
            "18000",
            "--gpu-memory-utilization",
            "0.85",
            "--port",
            "8000",
            "--trust-remote-code",
            "--dtype",
            "bfloat16",
            "--max-num-seqs",
            "32",
            "--max_num_batched_tokens",
            "4096",
            "--enable-prefix-caching",
            "--mm-processor-kwargs",
            '{"min_pixels":3136,"max_pixels":6291456}',
            "--api-key",
            "EMPTY",
            "--no-enable-log-requests",
        ]
    )
    wait_for_vllm(process)
    return process


def _arxiv_version_candidates(version: str) -> list[str]:
    match = re.fullmatch(r"v([1-9][0-9]*)", version)
    if match is None:
        return [version]
    requested = int(match.group(1))
    lower_versions = range(min(requested - 1, 10), 0, -1)
    return [version, *(f"v{number}" for number in lower_versions)]


def download_pdf(arxiv_id: str, version: str) -> tuple[bytes, str]:
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=180, follow_redirects=True
    ) as client:
        candidates = _arxiv_version_candidates(version)
        for index, candidate in enumerate(candidates):
            url = f"https://arxiv.org/pdf/{arxiv_id}{candidate}.pdf"
            response = client.get(url)
            if response.status_code == 404 and index + 1 < len(candidates):
                continue
            response.raise_for_status()
            data = response.content
            if not data.startswith(b"%PDF-") or len(data) > 150 * 1024 * 1024:
                raise ValueError("invalid_pdf")
            return data, candidate
    raise RuntimeError("arxiv_version_candidates_exhausted")


def normalize_external_pdf_url(value: str) -> str:
    """Resolve common repository viewer URLs to their downloadable object."""
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("invalid_external_pdf_url")
    if parsed.username or parsed.password:
        raise ValueError("invalid_external_pdf_url")
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("invalid_external_pdf_url")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("invalid_external_pdf_url")
    parts = parsed.path.split("/")
    if hostname == "github.com" and len(parts) >= 6 and parts[3] == "blob":
        # github.com/<owner>/<repo>/raw/... redirects to the file itself, also
        # for Git LFS files, where raw.githubusercontent.com serves only the
        # LFS pointer.
        path = "/".join(["", parts[1], parts[2], "raw", *parts[4:]])
        return urlunsplit(("https", "github.com", path, parsed.query, ""))
    if hostname == "huggingface.co" and "/blob/" in parsed.path:
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path.replace("/blob/", "/resolve/", 1),
                parsed.query,
                "",
            )
        )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def validate_external_pdf_network_target(value: str) -> str:
    normalized = normalize_external_pdf_url(value)
    parsed = urlsplit(normalized)
    assert parsed.hostname is not None
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as error:
        raise ValueError("invalid_external_pdf_url") from error
    if not addresses:
        raise ValueError("invalid_external_pdf_url")
    for address in addresses:
        try:
            resolved = ipaddress.ip_address(address[4][0])
        except ValueError as error:
            raise ValueError("invalid_external_pdf_url") from error
        if not resolved.is_global:
            raise ValueError("invalid_external_pdf_url")
    return normalized


def download_external_pdf(
    pdf_url: str,
    *,
    timeout_seconds: float = 180,
    max_elapsed_seconds: float | None = None,
) -> bytes:
    started_at = time.monotonic()
    url = validate_external_pdf_network_target(pdf_url)

    def validate_request(request: httpx.Request) -> None:
        validate_external_pdf_network_target(str(request.url))

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=timeout_seconds,
        follow_redirects=True,
        event_hooks={"request": [validate_request]},
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > MAX_PDF_BYTES:
                        raise ValueError("invalid_pdf")
                except ValueError as error:
                    raise ValueError("invalid_pdf") from error

            data = bytearray()
            for chunk in response.iter_bytes():
                if (
                    max_elapsed_seconds is not None
                    and time.monotonic() - started_at > max_elapsed_seconds
                ):
                    raise httpx.TimeoutException(
                        "external PDF download deadline exceeded"
                    )
                if len(data) + len(chunk) > MAX_PDF_BYTES:
                    raise ValueError("invalid_pdf")
                data.extend(chunk)

    result = bytes(data)
    if not result.startswith(b"%PDF-"):
        raise ValueError("invalid_pdf")
    return result


def entry_paper_key(entry: dict[str, object]) -> str:
    return str(entry.get("paper_key") or entry["arxiv_id"])


def markdown_content_key(content_sha256: str) -> str:
    if SHA256_HEX.fullmatch(content_sha256) is None:
        raise ValueError("invalid_markdown_content_version")
    return f"_content/sha256/{content_sha256[:2]}/{content_sha256}.md"


def markdown_manifest_key(paper_key: str) -> str:
    if re.fullmatch(r"(?:\d{4}\.\d{4,5}|external/[1-9]\d{0,19})", paper_key) is None:
        raise ValueError("invalid_markdown_paper_key")
    return f"_content/manifests/{paper_key}.json"


def markdown_manifest(
    entry: dict[str, object], content_sha256: str, size_bytes: int
) -> dict[str, object]:
    paper_key = entry_paper_key(entry)
    if size_bytes < 1 or size_bytes > 64 * 1024 * 1024:
        raise ValueError("invalid_markdown_size")
    return {
        "schema_version": MARKDOWN_MANIFEST_SCHEMA_VERSION,
        "paper_key": paper_key,
        "source": "external" if paper_key.startswith("external/") else "arxiv",
        "content_sha256": content_sha256,
        "content_key": markdown_content_key(content_sha256),
        "size_bytes": size_bytes,
    }


def _alphanumeric_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)


def validate_markdown_semantics(title: str, body: str) -> None:
    """Reject Chandra output that lacks meaningful overlap with the paper title."""
    nonempty_lines = [line.strip() for line in body.splitlines() if line.strip()]
    if nonempty_lines and all(
        IMAGE_FILENAME_ONLY.fullmatch(line) for line in nonempty_lines
    ):
        raise ValueError("semantic_markdown_mismatch")
    title_tokens = [
        token for token in _alphanumeric_tokens(title) if token not in TITLE_STOP_WORDS
    ]
    required_matches = min(2, len(title_tokens))
    semantic_body = MARKDOWN_IMAGE.sub("", body)
    semantic_body = HTML_IMAGE.sub("", semantic_body)
    body_tokens = set(_alphanumeric_tokens(semantic_body))
    if required_matches == 0 or len(set(title_tokens) & body_tokens) < required_matches:
        raise ValueError("semantic_markdown_mismatch")


def validate_canonical_markdown(title: str, markdown: str) -> None:
    """Apply the worker's size and semantic contracts to a canonical object."""
    encoded = markdown.encode("utf-8")
    if len(encoded) < 120 or len(encoded) > 64 * 1024 * 1024:
        raise ValueError("invalid_markdown_size")
    marker = re.search(r"^Markdown Content:\r?\n", markdown, flags=re.MULTILINE)
    if marker is None:
        raise ValueError("semantic_markdown_mismatch")
    header_title = re.search(
        r"^Title:(.*)$", markdown[: marker.start()], flags=re.MULTILINE
    )
    if header_title and SCRAPED_IMAGE_TITLE.search(header_title.group(1).strip()):
        raise ValueError("scraped_figure_markdown")
    body = markdown[marker.end() :].lstrip("\r\n")
    validate_markdown_semantics(title, body)
    text = ARXIV_HTML_FEEDBACK.sub("", body)
    text = HTML_IMAGE.sub("", MARKDOWN_IMAGE.sub("", text))
    if len(" ".join(text.split())) < MIN_MARKDOWN_BODY_CHARS:
        raise ValueError("markdown_body_too_short")


def validate_repair_original(entry: dict[str, object], original: bytes) -> None:
    """Require the exact invalid object selected by the bounded repair plan."""
    if hashlib.sha256(original).hexdigest() != entry.get("replace_invalid_sha256"):
        raise ValueError("repair_original_changed")
    try:
        validate_canonical_markdown(str(entry["title"]), original.decode("utf-8"))
    except ValueError:
        return
    raise ValueError("repair_original_is_valid")


def download_pdf_for_entry(entry: dict[str, object]) -> tuple[bytes, str]:
    version = str(entry.get("version") or "v1")
    if entry.get("source") == "external":
        return download_external_pdf(str(entry["pdf_url"])), version
    return download_pdf(str(entry["arxiv_id"]), version)


def run_chandra(
    pdf: Path, pages: int
) -> tuple[str, dict[str, bytes], list[dict[str, object]]]:
    """OCR the leading pages once for canonical Markdown, images, and layout."""
    os.environ.update(
        VLLM_API_BASE="http://127.0.0.1:8000/v1",
        VLLM_MODEL_NAME="chandra",
        VLLM_API_KEY="EMPTY",
    )
    from chandra.input import load_pdf_images
    from chandra.model import InferenceManager
    from chandra.model.schema import BatchInputItem

    images = load_pdf_images(str(pdf), list(range(pages)))
    model = InferenceManager(method="vllm")
    markdown: list[str] = []
    assets: dict[str, bytes] = {}
    layout_pages: list[dict[str, object]] = []
    for start in range(0, len(images), CHANDRA_PAGE_BATCH_SIZE):
        batch = [
            BatchInputItem(image=image, prompt_type="ocr_layout")
            for image in images[start : start + CHANDRA_PAGE_BATCH_SIZE]
        ]
        results = model.generate(
            batch,
            max_output_tokens=CHANDRA_MAX_OUTPUT_TOKENS,
            include_images=True,
            include_headers_footers=False,
        )
        for offset, (item, result) in enumerate(zip(batch, results, strict=True)):
            markdown.append(result.markdown)
            for name, image in result.images.items():
                buffer = BytesIO()
                image.save(
                    buffer, format=Image.registered_extensions()[Path(name).suffix]
                )
                data = buffer.getvalue()
                if assets.get(name, data) != data:
                    raise ValueError(f"ambiguous_chandra_asset:{name}")
                assets[name] = data
            layout_pages.append(
                {
                    "page": start + offset + 1,
                    "image_size": [item.image.width, item.image.height],
                    "raw": result.raw,
                    "token_count": result.token_count,
                    "error": bool(result.error),
                }
            )
    return "".join(markdown), assets, layout_pages


def build_paged_markdown(
    pages: list[dict[str, object]],
) -> tuple[str, dict[str, dict[str, object]]]:
    """Turn raw Chandra pages into anchored Markdown plus a block sidecar.

    Anchors are ``p{page}b{block}`` where ``block`` is the 1-based position of
    the layout block on its page, so they stay stable against the raw layout.
    Bboxes stay on Chandra's 0-1000 grid, which maps onto any rendered page size.
    """
    from bs4 import BeautifulSoup
    from chandra.output import parse_markdown

    parts: list[str] = []
    blocks: dict[str, dict[str, object]] = {}
    section: str | None = None
    for page in pages:
        page_number = int(page["page"])
        parts.append(f"<!-- pwc:page {page_number} -->")
        soup = BeautifulSoup(str(page["raw"]), "html.parser")
        for index, div in enumerate(soup.find_all("div", recursive=False), 1):
            label = div.get("data-label") or "block"
            if label in LAYOUT_SKIPPED_LABELS:
                continue
            try:
                bbox = [int(value) for value in str(div.get("data-bbox")).split()]
            except ValueError:
                continue
            if len(bbox) != 4:
                continue
            anchor = f"p{page_number}b{index}"
            if label == "Section-Header":
                section = anchor
            text = BeautifulSoup(div.decode_contents(), "html.parser").get_text(" ")
            blocks[anchor] = {
                "page": page_number,
                "label": label,
                "bbox": bbox,
                "section": section,
                "text": " ".join(text.split())[:2000],
            }
            if label in LAYOUT_NON_TEXT_LABELS:
                continue
            body = parse_markdown(str(div), include_images=False)
            if body:
                parts.append(f"<!-- pwc:{anchor} -->\n{body}")
    return "\n\n".join(parts) + "\n", blocks


def write_layout(
    entry: dict[str, object],
    layout_root: Path,
    *,
    page_count: int,
    pages: list[dict[str, object]],
    resolved_version: str,
) -> list[str]:
    """Write a paper's layout objects; the anchored Markdown is listed last."""
    stem = str(entry["output_key"]).removesuffix(".md")
    markdown, blocks = build_paged_markdown(pages)
    meta = {
        "schema_version": LAYOUT_SCHEMA_VERSION,
        "paper_key": stem,
        "source": entry.get("source", "arxiv"),
        "arxiv_version": resolved_version
        if entry.get("source") != "external"
        else None,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "page_count": page_count,
        "processed_pages": len(pages),
        "page_errors": sum(1 for page in pages if page["error"]),
        "bbox_scale": 1000,
        "created_at": datetime.now(UTC).isoformat(),
    }
    objects = {
        f"{stem}.layout.json": json.dumps({**meta, "pages": pages}, ensure_ascii=False),
        f"{stem}.blocks.json": json.dumps(
            {**meta, "blocks": blocks}, ensure_ascii=False
        ),
        # Its presence marks the paper's layout as complete, so it goes last.
        f"{stem}.md": markdown,
    }
    for key, text in objects.items():
        atomic_write(layout_root / key, text.encode("utf-8"))
    return list(objects)


def canonicalize_assets(
    paper_key: str,
    body: str,
    assets: dict[str, bytes],
    *,
    allow_missing_images: bool = False,
) -> tuple[str, dict[str, bytes], list[str], list[str]]:
    """Validate images and replace Chandra-local references with public URLs."""
    source_to_url: dict[str, str] = {}
    canonical_assets: dict[str, bytes] = {}
    asset_keys: list[str] = []
    omitted_sources: list[str] = []
    for source_name, data in sorted(assets.items()):
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("image_too_large")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("image_too_many_pixels")
                image.verify()
                extension = FORMAT_EXTENSIONS.get(image.format or "")
        except ValueError:
            raise
        except Exception as error:
            raise ValueError("invalid_extracted_image") from error
        if extension is None:
            raise ValueError("unsupported_extracted_image")
        filename = f"{hashlib.sha256(data).hexdigest()[:16]}{extension}"
        asset_prefix = (
            paper_key
            if paper_key.startswith("external/")
            else f"{paper_key[:4]}/{paper_key}"
        )
        key = f"{asset_prefix}/images/{filename}"
        url = f"https://paperswithcode.co/paper-assets/{key}"
        source_to_url[Path(source_name).name] = url
        canonical_assets[key] = data
        asset_keys.append(key)

    def replace(match: re.Match[str]) -> str:
        source = match.group("source")
        if source.startswith(("https://", "http://", "data:")):
            return match.group(0)
        replacement = source_to_url.get(Path(source).name)
        if replacement is None:
            if allow_missing_images:
                omitted_sources.append(source)
                return ""
            raise ValueError(f"missing_extracted_image:{source}")
        return f"{match.group(1)}{replacement}{match.group(3)}"

    rewritten = MARKDOWN_IMAGE.sub(replace, body)
    rewritten = HTML_IMAGE.sub(replace, rewritten)
    return (
        rewritten,
        canonical_assets,
        sorted(set(asset_keys)),
        sorted(set(omitted_sources)),
    )


def publish(
    entry: dict[str, object],
    body: str,
    assets: dict[str, bytes],
    content_root: Path,
    *,
    page_count: int | None = None,
    processed_pages: int | None = None,
    allow_missing_images: bool = False,
) -> dict:
    if (content_root / MARKDOWN_MIGRATION_LOCK_KEY).exists():
        raise ValueError("markdown_migration_locked")
    paper_key = entry_paper_key(entry)
    arxiv_id = entry.get("arxiv_id")
    version = str(entry["version"])
    validate_markdown_semantics(str(entry["title"]), body)
    body, canonical_assets, asset_keys, omitted_sources = canonicalize_assets(
        paper_key,
        body,
        assets,
        allow_missing_images=allow_missing_images,
    )
    if omitted_sources:
        body = (
            f"> **Image note:** {len(omitted_sources)} generated image "
            f"reference{'s were' if len(omitted_sources) != 1 else ' was'} omitted "
            f"because Chandra did not produce a corresponding validated asset.\n\n"
            f"{body}"
        )
    if page_count and processed_pages and page_count > processed_pages:
        complete_pdf_url = (
            str(entry["pdf_url"])
            if entry.get("source") == "external"
            else f"https://arxiv.org/pdf/{arxiv_id}{version}.pdf"
        )
        body = (
            f"> **Truncated rendition:** This Markdown contains the first "
            f"{processed_pages} of {page_count} pages. Read the complete paper "
            f"at {complete_pdf_url}.\n\n{body}"
        )
    source_url = (
        str(entry.get("source_url") or entry["pdf_url"])
        if entry.get("source") == "external"
        else f"https://arxiv.org/abs/{arxiv_id}{version}"
    )
    markdown = (
        f"Title: {str(entry['title']).strip()}\n\n"
        f"URL Source: {source_url}\n\n"
        f"Markdown Content:\n\n{body.strip()}\n"
    ).encode()
    if len(markdown) < 120 or len(markdown) > 64 * 1024 * 1024:
        raise ValueError("invalid_markdown_size")
    validate_canonical_markdown(str(entry["title"]), markdown.decode("utf-8"))
    content_sha256 = hashlib.sha256(markdown).hexdigest()
    content_key = markdown_content_key(content_sha256)
    manifest_key = markdown_manifest_key(paper_key)

    for key, data in canonical_assets.items():
        destination = content_root / key
        if destination.exists() and destination.read_bytes() != data:
            raise ValueError(f"immutable_asset_conflict:{key}")
        if not destination.exists():
            atomic_write(destination, data)
        if destination.read_bytes() != data:
            raise ValueError(f"asset_verification_failed:{key}")

    output = content_root / str(entry["output_key"])
    immutable_output = content_root / content_key
    if immutable_output.exists() and immutable_output.read_bytes() != markdown:
        raise ValueError(f"immutable_asset_conflict:{content_key}")
    if not immutable_output.exists():
        atomic_write(immutable_output, markdown)
    if immutable_output.read_bytes() != markdown:
        raise ValueError("markdown_version_verification_failed")
    atomic_write(output, markdown)
    if output.read_bytes() != markdown:
        raise ValueError("markdown_verification_failed")
    manifest = markdown_manifest(entry, content_sha256, len(markdown))
    atomic_write(
        content_root / manifest_key,
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode(),
    )
    return {
        "paper_key": paper_key,
        "paper_id": entry.get("paper_id"),
        "source": entry.get("source", "arxiv"),
        "arxiv_id": arxiv_id,
        "pdf_key": entry.get("pdf_key"),
        "status": "succeeded",
        "page_count": page_count,
        "processed_page_count": processed_pages,
        "truncated": bool(
            page_count and processed_pages and page_count > processed_pages
        ),
        "image_count": len(asset_keys),
        "omitted_image_count": len(omitted_sources),
        "omitted_image_sources": omitted_sources,
        "asset_keys": asset_keys,
        "asset_sha256": {
            key: hashlib.sha256(canonical_assets[key]).hexdigest() for key in asset_keys
        },
        "markdown_sha256": content_sha256,
        "markdown_size_bytes": len(markdown),
        "markdown_content_key": content_key,
        "markdown_manifest_key": manifest_key,
    }


def publish_existing_markdown(
    entry: dict[str, object], content_root: Path
) -> dict[str, object]:
    """Complete an interrupted versioned publication from its canonical alias."""
    if (content_root / MARKDOWN_MIGRATION_LOCK_KEY).exists():
        raise ValueError("markdown_migration_locked")
    output = content_root / str(entry["output_key"])
    markdown = output.read_bytes()
    if not markdown or len(markdown) > 64 * 1024 * 1024:
        raise ValueError("invalid_markdown_size")
    try:
        markdown.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("invalid_markdown_utf8") from error
    paper_key = entry_paper_key(entry)
    content_sha256 = hashlib.sha256(markdown).hexdigest()
    content_key = markdown_content_key(content_sha256)
    immutable_output = content_root / content_key
    if immutable_output.exists() and immutable_output.read_bytes() != markdown:
        raise ValueError(f"immutable_asset_conflict:{content_key}")
    if not immutable_output.exists():
        atomic_write(immutable_output, markdown)
    if immutable_output.read_bytes() != markdown:
        raise ValueError("markdown_version_verification_failed")
    manifest_key = markdown_manifest_key(paper_key)
    manifest = markdown_manifest(entry, content_sha256, len(markdown))
    atomic_write(
        content_root / manifest_key,
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode(),
    )
    return {
        "paper_key": paper_key,
        "paper_id": entry.get("paper_id"),
        "source": entry.get("source", "arxiv"),
        "arxiv_id": entry.get("arxiv_id"),
        "status": "succeeded",
        "image_count": 0,
        "asset_keys": [],
        "markdown_sha256": content_sha256,
        "markdown_size_bytes": len(markdown),
        "markdown_content_key": content_key,
        "markdown_manifest_key": manifest_key,
    }


def process(
    entry: dict[str, object],
    content_root: Path,
    run_root: Path,
    *,
    allow_missing_images: bool = False,
    layout_root: Path | None = None,
) -> dict:
    started = time.monotonic()
    paper_key = entry_paper_key(entry)
    version = str(entry["version"])
    layout_only = bool(entry.get("layout_only"))
    if layout_only and layout_root is None:
        raise ValueError("layout_bucket_required")
    output = content_root / str(entry["output_key"])
    if output.exists() and not layout_only:
        if entry.get("replace_invalid_sha256"):
            validate_repair_original(entry, output.read_bytes())
        elif not (content_root / markdown_manifest_key(paper_key)).exists():
            return publish_existing_markdown(entry, content_root)
        else:
            return {
                "paper_key": paper_key,
                "paper_id": entry.get("paper_id"),
                "source": entry.get("source", "arxiv"),
                "arxiv_id": entry.get("arxiv_id"),
                "status": "already_exists",
            }

    from pypdf import PdfReader

    paper_dir = run_root / paper_key
    archived_pdf = (
        content_root / str(entry["pdf_key"]) if entry.get("pdf_key") else None
    )
    downloaded_pdf = False
    if archived_pdf is not None and archived_pdf.exists():
        pdf_data = archived_pdf.read_bytes()
        resolved_version = version
    else:
        pdf_data, resolved_version = download_pdf_for_entry(entry)
        downloaded_pdf = True
    page_count = len(PdfReader(BytesIO(pdf_data), strict=True).pages)
    if downloaded_pdf and archived_pdf is not None:
        atomic_write(archived_pdf, pdf_data)
    processed_pages = min(page_count, MAX_PAGES)
    pdf_path = paper_dir / "paper.pdf"
    atomic_write(pdf_path, pdf_data)
    body, assets, layout_pages = run_chandra(pdf_path, processed_pages)
    if layout_only:
        # The canonical object stays as it is; the title check still guards
        # against storing the layout of the wrong PDF.
        validate_markdown_semantics(str(entry["title"]), body)
        result = {
            "paper_key": paper_key,
            "paper_id": entry.get("paper_id"),
            "source": entry.get("source", "arxiv"),
            "arxiv_id": entry.get("arxiv_id"),
            "pdf_key": entry.get("pdf_key"),
            "status": "succeeded",
            "page_count": page_count,
            "processed_page_count": processed_pages,
        }
    else:
        result = publish(
            {**entry, "version": resolved_version},
            body,
            assets,
            content_root,
            page_count=page_count,
            processed_pages=processed_pages,
            allow_missing_images=allow_missing_images,
        )
    if layout_root is not None:
        result["layout_keys"] = write_layout(
            entry,
            layout_root,
            page_count=page_count,
            pages=layout_pages,
            resolved_version=resolved_version,
        )
    return {
        **result,
        "layout_only": layout_only,
        "requested_version": version,
        "resolved_version": resolved_version,
        "version_fallback_attempted": True,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "duration_seconds": round(time.monotonic() - started, 3),
        "completed_at": datetime.now(UTC).isoformat(),
    }


def entry_status_key(entry: dict[str, object]) -> str:
    """Layout-only work keeps its own retry record beside the canonical one."""
    folder = "layout-status" if entry.get("layout_only") else "status"
    return f"_jobs/{folder}/{entry_paper_key(entry)}.json"


def _prior_status(content_root: Path, status_key: str) -> dict:
    path = content_root / status_key
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def should_omit_missing_images(prior: dict, attempt_count: int) -> bool:
    """Allow one full retry before publishing with phantom image refs omitted."""
    return attempt_count >= MAX_ATTEMPTS or (
        attempt_count >= 2 and prior.get("error_class") == "missing_extracted_image"
    )


def classify_failure(error: Exception, attempt_count: int) -> tuple[str, bool]:
    """Classify a paper failure without requiring scheduler string parsing."""
    message = str(error)
    error_class = type(error).__name__
    retryable = False
    if isinstance(error, httpx.TimeoutException):
        error_class, retryable = "arxiv_timeout", True
    elif isinstance(error, (httpx.NetworkError, httpx.RemoteProtocolError)):
        error_class, retryable = "arxiv_transport", True
    elif isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        error_class = f"arxiv_http_{status}"
        retryable = status == 429 or status >= 500
    elif message.startswith("missing_extracted_image:"):
        error_class, retryable = "missing_extracted_image", True
    elif message.startswith(
        (
            "asset_verification_failed:",
            "markdown_verification_failed",
            "markdown_version_verification_failed",
            "markdown_migration_locked",
        )
    ):
        error_class, retryable = "artifact_verification_io", True
    elif message.startswith("immutable_asset_conflict:"):
        error_class = "immutable_asset_conflict"
    elif message.startswith("ambiguous_chandra_asset:"):
        error_class = "ambiguous_chandra_asset"
    elif message == "semantic_markdown_mismatch":
        error_class = "semantic_markdown_mismatch"
        retryable = attempt_count < MAX_ATTEMPTS
    elif message == "invalid_pdf":
        error_class = message
    elif message in {
        "invalid_extracted_image",
        "unsupported_extracted_image",
        "image_too_large",
        "image_too_many_pixels",
        "invalid_markdown_size",
        "markdown_body_too_short",
        "scraped_figure_markdown",
    }:
        error_class = message
    elif isinstance(error, OSError):
        error_class, retryable = "transient_io", True
    if attempt_count >= MAX_ATTEMPTS:
        retryable = False
    return error_class, retryable


def status_record(
    result: dict,
    *,
    prior: dict,
    error: Exception | None = None,
    attempted_at: datetime | None = None,
) -> dict:
    """Add retry metadata while retaining all legacy result fields."""
    observed_at = attempted_at or datetime.now(UTC)
    attempt_count = max(0, int(prior.get("attempt_count") or 0)) + 1
    retryable = False
    error_class = None
    next_retry_at = None
    if error is not None:
        error_class, retryable = classify_failure(error, attempt_count)
        if retryable:
            delay = timedelta(hours=min(24, 2 ** (attempt_count - 1)))
            next_retry_at = (observed_at + delay).isoformat()
    return {
        **result,
        "schema_version": STATUS_SCHEMA_VERSION,
        "attempt_count": attempt_count,
        "error_class": error_class,
        "retryable": retryable,
        "attempted_at": observed_at.isoformat(),
        "next_retry_at": next_retry_at,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
    }


def stop_vllm(process: subprocess.Popen[bytes] | None) -> str:
    if process is None:
        return "not_started"
    if process.poll() is not None:
        return "already_exited"
    process.terminate()
    try:
        process.wait(timeout=VLLM_SHUTDOWN_TIMEOUT_SECONDS)
        return "terminated"
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=30)
            return "killed"
        except subprocess.TimeoutExpired:
            return "kill_timed_out"


def progress_payload(
    *,
    run_id: str,
    shard_id: str,
    total_papers: int,
    results: list[dict],
    status: str,
    started_at: str,
    fatal_error: str | None = None,
    termination_requested: bool = False,
    cleanup_state: str | None = None,
) -> dict:
    succeeded = [item for item in results if item.get("status") == "succeeded"]
    failed = [item for item in results if item.get("status") == "failed"]
    already_existed = [
        item for item in results if item.get("status") == "already_exists"
    ]
    return {
        "run_id": run_id,
        "shard_id": shard_id,
        "hf_job_id": os.environ.get("JOB_ID"),
        "status": status,
        "total_papers": total_papers,
        "processed_papers": len(results),
        "succeeded_papers": len(succeeded),
        "failed_papers": len(failed),
        "already_existed_papers": len(already_existed),
        "extracted_images": sum(int(item.get("image_count") or 0) for item in results),
        "omitted_images": sum(
            int(item.get("omitted_image_count") or 0) for item in results
        ),
        "error_samples": [
            {
                "arxiv_id": item.get("arxiv_id"),
                "error": str(item.get("error") or "")[:500],
            }
            for item in failed[:5]
        ],
        "fatal_error": fatal_error,
        "termination_requested": termination_requested,
        "cleanup_state": cleanup_state,
        "paper_duration_p50_seconds": percentile_duration(results, 0.50),
        "paper_duration_p95_seconds": percentile_duration(results, 0.95),
        "started_at": started_at,
        "updated_at": datetime.now(UTC).isoformat(),
    }


def percentile_duration(results: list[dict], percentile: float) -> float | None:
    values = sorted(
        float(item["duration_seconds"])
        for item in results
        if item.get("duration_seconds") is not None
    )
    if not values:
        return None
    index = max(0, min(len(values) - 1, int((len(values) - 1) * percentile + 0.999)))
    return round(values[index], 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--bucket-id")
    parser.add_argument("--manifest-key")
    parser.add_argument(
        "--layout-bucket-id", help="Also store page-aware layout in this bucket"
    )
    parser.add_argument("--content-root", type=Path, default=Path("/content"))
    parser.add_argument("--stub-root", type=Path)
    parser.add_argument("--stub-delay-seconds", type=float, default=0)
    parser.add_argument(
        "--soft-deadline-seconds",
        type=int,
        required=True,
    )
    args = parser.parse_args()
    if args.soft_deadline_seconds < 0:
        parser.error("--soft-deadline-seconds must not be negative")
    bucket_mode = bool(args.bucket_id or args.manifest_key)
    if bucket_mode != bool(args.bucket_id and args.manifest_key):
        parser.error("--bucket-id and --manifest-key must be provided together")
    if bucket_mode == bool(args.manifest):
        parser.error("provide either --manifest or Bucket API arguments")
    if args.layout_bucket_id and not bucket_mode:
        parser.error("--layout-bucket-id requires Bucket API arguments")

    temporary: tempfile.TemporaryDirectory[str] | None = None
    store: BucketContentStore | None = None
    layout_root: Path | None = None
    if bucket_mode:
        token = os.environ.get("HF_TOKEN")
        if not token:
            parser.error("HF_TOKEN is required for Bucket API transport")
        temporary = tempfile.TemporaryDirectory(prefix="pwc-paper-markdown-")
        content_root = Path(temporary.name) / "content"
        manifest = content_root / str(args.manifest_key)
        store = BucketContentStore(str(args.bucket_id), token, content_root)
        store.download(str(args.manifest_key))
        if args.layout_bucket_id:
            layout_root = Path(temporary.name) / "layout"
    else:
        content_root = args.content_root
        manifest = args.manifest
    assert manifest is not None

    global _TERMINATION_REQUESTED
    _TERMINATION_REQUESTED = False
    signal.signal(signal.SIGTERM, request_termination)
    deadline = time.monotonic() + args.soft_deadline_seconds

    entries = [
        json.loads(line)
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if store:
        store.prepare(str(args.manifest_key), entries)
    run_id = manifest.parent.name
    shard_id = manifest.stem
    result_path = content_root / "_jobs" / "results" / run_id / f"{shard_id}.jsonl"
    progress_path = content_root / "_jobs" / "progress" / run_id / f"{shard_id}.json"
    result_key = f"_jobs/results/{run_id}/{shard_id}.jsonl"
    progress_key = f"_jobs/progress/{run_id}/{shard_id}.json"

    def upload_checkpoint(keys: list[str]) -> None:
        if store:
            store.upload(keys)

    completed: dict[str, dict] = {}
    if result_path.exists():
        completed = {
            str(item.get("paper_key") or item["arxiv_id"]): item
            for item in map(json.loads, result_path.read_text().splitlines())
        }

    started_at = datetime.now(UTC).isoformat()
    results = list(completed.values())
    server = None
    fatal_error = None
    cleanup_state = None
    atomic_write(
        progress_path,
        json.dumps(
            progress_payload(
                run_id=run_id,
                shard_id=shard_id,
                total_papers=len(entries),
                results=results,
                status="starting",
                started_at=started_at,
            ),
            sort_keys=True,
            indent=2,
        ).encode(),
    )
    upload_checkpoint([progress_key])
    try:
        if not args.stub_root:
            server = start_vllm()
        atomic_write(
            progress_path,
            json.dumps(
                progress_payload(
                    run_id=run_id,
                    shard_id=shard_id,
                    total_papers=len(entries),
                    results=results,
                    status="running",
                    started_at=started_at,
                ),
                sort_keys=True,
                indent=2,
            ).encode(),
        )
        upload_checkpoint([progress_key])
        for entry in entries:
            paper_key = entry_paper_key(entry)
            if paper_key in completed:
                continue
            if _TERMINATION_REQUESTED or time.monotonic() >= deadline:
                break
            status_key = entry_status_key(entry)
            prior = _prior_status(content_root, status_key)
            attempt_count = max(0, int(prior.get("attempt_count") or 0)) + 1
            allow_missing_images = should_omit_missing_images(prior, attempt_count)
            attempted_at = datetime.now(UTC)
            paper_started = time.monotonic()
            failure = None
            try:
                if args.stub_root:
                    body = (args.stub_root / f"{paper_key}.md").read_text(
                        encoding="utf-8"
                    )
                    asset_dir = args.stub_root / paper_key
                    assets = (
                        {
                            path.name: path.read_bytes()
                            for path in asset_dir.iterdir()
                            if path.is_file()
                        }
                        if asset_dir.exists()
                        else {}
                    )
                    started = time.monotonic()
                    result = publish(
                        entry,
                        body,
                        assets,
                        content_root,
                        allow_missing_images=allow_missing_images,
                    )
                    result["duration_seconds"] = round(time.monotonic() - started, 3)
                    if args.stub_delay_seconds:
                        time.sleep(args.stub_delay_seconds)
                else:
                    result = process(
                        entry,
                        content_root,
                        result_path.parent,
                        allow_missing_images=allow_missing_images,
                        layout_root=layout_root,
                    )
            except Exception as error:  # noqa: BLE001 - isolate failures per paper
                failure = error
                result = {
                    "paper_key": paper_key,
                    "paper_id": entry.get("paper_id"),
                    "source": entry.get("source", "arxiv"),
                    "arxiv_id": entry.get("arxiv_id"),
                    "status": "failed",
                    "error": str(error)[:1000],
                    "requested_version": entry["version"],
                    "version_fallback_attempted": not bool(args.stub_root),
                    "lfs_pdf_url_attempted": not bool(args.stub_root),
                }
            result.setdefault(
                "duration_seconds", round(time.monotonic() - paper_started, 3)
            )
            result = status_record(
                result,
                prior=prior,
                error=failure,
                attempted_at=attempted_at,
            )
            results.append(result)
            atomic_write(
                content_root / status_key,
                json.dumps(result, sort_keys=True, indent=2).encode(),
            )
            atomic_write(
                result_path,
                (
                    "\n".join(json.dumps(item, sort_keys=True) for item in results)
                    + "\n"
                ).encode(),
            )
            atomic_write(
                progress_path,
                json.dumps(
                    progress_payload(
                        run_id=run_id,
                        shard_id=shard_id,
                        total_papers=len(entries),
                        results=results,
                        status="running",
                        started_at=started_at,
                    ),
                    sort_keys=True,
                    indent=2,
                ).encode(),
            )
            published_keys = [status_key, result_key, progress_key]
            pdf_key = entry.get("pdf_key")
            if pdf_key and (content_root / str(pdf_key)).is_file():
                published_keys.append(str(pdf_key))
            # Layout goes before the canonical checkpoint: once canonical
            # Markdown exists, a retried shard skips the paper's OCR.
            if result.get("layout_keys"):
                run_bucket_bridge(
                    token,
                    {
                        "operation": "upload",
                        "bucket_id": args.layout_bucket_id,
                        "files": [
                            (str(layout_root / key), key)
                            for key in result["layout_keys"]
                        ],
                    },
                )
            if result.get("status") == "succeeded" and not result.get("layout_only"):
                content_keys = [str(key) for key in result.get("asset_keys") or []]
                content_keys.extend(
                    [
                        str(entry["output_key"]),
                        str(result["markdown_content_key"]),
                    ]
                )
                upload_checkpoint(content_keys)
                published_keys.append(str(result["markdown_manifest_key"]))
            upload_checkpoint(published_keys)
    except Exception as error:
        fatal_error = str(error)[:1000]
        raise
    finally:
        cleanup_state = stop_vllm(server)
        final_status = (
            "failed"
            if fatal_error
            else "completed"
            if len(
                {str(item.get("paper_key") or item.get("arxiv_id")) for item in results}
            )
            >= len(entries)
            else "partial"
        )
        atomic_write(
            progress_path,
            json.dumps(
                progress_payload(
                    run_id=run_id,
                    shard_id=shard_id,
                    total_papers=len(entries),
                    results=results,
                    status=final_status,
                    started_at=started_at,
                    fatal_error=fatal_error,
                    termination_requested=_TERMINATION_REQUESTED,
                    cleanup_state=cleanup_state,
                ),
                sort_keys=True,
                indent=2,
            ).encode(),
        )
        upload_checkpoint([progress_key])
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    main()
