"""
Thumbnail service for generating paper thumbnails.
Each thumbnail is generated from the first page of the paper's PDF.

This service handles:
- Downloading PDFs from ArXiv
- Converting the full first page to an image
- Reading/writing thumbnails from local or Hugging Face bucket storage
- Serving cached thumbnails
"""

import asyncio
import logging
import re
import shutil
import time
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from huggingface_hub import HfFileSystem, batch_bucket_files, download_bucket_files
from PIL import Image, ImageDraw, ImageFont
from pdf2image import convert_from_bytes

from backend.config import get_settings
from backend.utils.exceptions import ThumbnailGenerationError
from backend.services.arxiv_service import ArxivService
from backend.utils.biorxiv import (
    BioRxivMetadata,
    download_biorxiv_pdf_bytes,
    fetch_biorxiv_metadata,
    parse_biorxiv_doi,
)

logger = logging.getLogger(__name__)

THUMBNAIL_RENDERER_CACHE_BUST = "fit9"
EXPECTED_THUMBNAIL_WIDTH = 400
EXPECTED_THUMBNAIL_FORMAT = "JPEG"
# Paper cards render thumbnails in a 160×220 box, but PDF pages have their own
# MediaBox/CropBox aspect ratio. Keep the page ratio in the JPEG and let the
# frontend containment frame handle the small per-page difference.
CARD_THUMB_ASPECT = 160 / 220
# Kept for card-sized non-PDF fallbacks and compatibility with callers that
# need the nominal card dimensions. PDF thumbnails use a native, variable
# height instead (e.g. US Letter at width 400 is about 518px tall).
EXPECTED_THUMBNAIL_HEIGHT = int(EXPECTED_THUMBNAIL_WIDTH / CARD_THUMB_ASPECT)
# Older renders produced squat thumbnails around H/W = 0.65 because the
# height was clipped. Keep validation deliberately permissive above the
# portrait threshold because PDF pages may use custom dimensions.
MIN_THUMBNAIL_HEIGHT_TO_WIDTH_RATIO = 1.0
# Only strip sparse footer rows from the bottom band of the page; without this
# limit, low-density body text (e.g. abstract paragraphs) can be mistaken for
# copyright/page-number footers and cropped away.
MAX_SPARSE_FOOTER_HEIGHT_FRACTION = 0.05


def is_thumbnail_valid(
    path: Path,
    expected_width: int = EXPECTED_THUMBNAIL_WIDTH,
    expected_height: int | None = None,
    min_height_to_width_ratio: float = MIN_THUMBNAIL_HEIGHT_TO_WIDTH_RATIO,
) -> bool:
    """
    Check whether a cached thumbnail file is a readable JPEG with the expected
    generated dimensions. PDF pages retain their native aspect ratio, so the
    height is variable; callers may pass ``expected_height`` for fixed-size
    non-PDF thumbnails.
    """
    try:
        if not path.exists() or path.stat().st_size == 0:
            return False
        with Image.open(path) as img:
            if img.format != EXPECTED_THUMBNAIL_FORMAT:
                return False
            if img.width != expected_width:
                return False
            if expected_height is not None and img.height != expected_height:
                return False
            return img.height / img.width >= min_height_to_width_ratio
    except Exception:
        return False


def _trim_blank_page_margins(image: Image.Image) -> Image.Image:
    """
    Remove blank PDF page margins while keeping all visible first-page content.
    """
    rgb_image = image.convert("RGB")
    mask = rgb_image.point(lambda value: 255 if value < 245 else 0).convert("L")
    bbox = mask.getbbox()
    if bbox is None:
        return image

    width, height = image.size
    left, top, right, bottom = bbox
    padding = max(4, int(max(width, height) * 0.025))
    crop_box = (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )

    if crop_box == (0, 0, width, height):
        return image

    return image.crop(crop_box)


def _row_white_fraction(image: Image.Image, row_index: int) -> float:
    """Return the fraction of near-white pixels on one horizontal scanline."""
    rgb_image = image.convert("RGB")
    width, _ = rgb_image.size
    white_pixels = 0
    for x in range(width):
        r, g, b = rgb_image.getpixel((x, row_index))
        if r > 245 and g > 245 and b > 245:
            white_pixels += 1
    return white_pixels / width


def _row_ink_fraction(image: Image.Image, row_index: int) -> float:
    """Return the fraction of non-white pixels on one horizontal scanline."""
    return 1.0 - _row_white_fraction(image, row_index)


def _trim_leading_blank_rows(
    image: Image.Image, min_white_fraction: float = 0.985
) -> Image.Image:
    """Remove blank rows from the top after the main bbox trim."""
    width, height = image.size
    top = 0
    while top < height:
        if _row_white_fraction(image, top) < min_white_fraction:
            break
        top += 1

    if top == 0:
        return image

    return image.crop((0, top, width, height))


def _trim_trailing_blank_rows(
    image: Image.Image, min_white_fraction: float = 0.985
) -> Image.Image:
    """
    Remove footer rows that are almost entirely blank after the main bbox trim.
    PDF footers often include faint gray text that prevents a tight bottom crop.
    """
    width, height = image.size
    bottom = height
    while bottom > 0:
        if _row_white_fraction(image, bottom - 1) < min_white_fraction:
            break
        bottom -= 1

    if bottom == height:
        return image

    return image.crop((0, 0, width, bottom))


def _trim_sparse_footer_rows(
    image: Image.Image,
    max_footer_ink_fraction: float = 0.25,
    max_footer_height_fraction: float = MAX_SPARSE_FOOTER_HEIGHT_FRACTION,
) -> Image.Image:
    """
    Drop thin copyright / page-number rows at the bottom so trailing whitespace
    above them can be removed by :func:`_trim_trailing_blank_rows`.

    Only rows in the bottom ``max_footer_height_fraction`` of the image are
    candidates; this prevents low-density body text higher on the page from
    being treated as footer content.
    """
    width, height = image.size
    min_bottom = int(height * (1 - max_footer_height_fraction))
    bottom = height
    while bottom > min_bottom:
        ink = _row_ink_fraction(image, bottom - 1)
        if ink <= 0:
            bottom -= 1
            continue
        if ink >= max_footer_ink_fraction:
            break
        bottom -= 1

    if bottom == height:
        return image

    return image.crop((0, 0, width, bottom))


def _crop_to_card_aspect(image: Image.Image) -> Image.Image:
    """
    Crop to the paper-card display aspect ratio (160×220).

    Width-heavy pages are center-cropped; height-heavy pages keep the top so
    titles remain visible.
    """
    width, height = image.size
    current_aspect = width / height
    if abs(current_aspect - CARD_THUMB_ASPECT) < 0.005:
        return image

    if current_aspect > CARD_THUMB_ASPECT:
        new_width = int(height * CARD_THUMB_ASPECT)
        left = (width - new_width) // 2
        return image.crop((left, 0, left + new_width, height))

    new_height = int(width / CARD_THUMB_ASPECT)
    return image.crop((0, 0, width, new_height))


def _resize_to_card_fill(
    image: Image.Image, target_width: int = EXPECTED_THUMBNAIL_WIDTH
) -> Image.Image:
    """
    Scale the trimmed first page to fit inside the card frame (160×220 aspect).

    Uses contain-style fitting so titles, figures, and abstract text stay visible.
    Any remaining slack is filled with white inside the JPEG so card
    ``object-fit: contain`` still fills the frame without clipping content.
    """
    target_height = int(target_width / CARD_THUMB_ASPECT)
    width, height = image.size
    scale = min(target_width / width, target_height / height)
    resized_width = max(1, int(width * scale + 0.5))
    resized_height = max(1, int(height * scale + 0.5))
    resized = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (target_width, target_height), "white")
    left = (target_width - resized_width) // 2
    canvas.paste(resized, (left, 0))
    return canvas


def _prepare_first_page_for_card(image: Image.Image) -> Image.Image:
    """Render the complete PDF page at a fixed width, preserving page ratio."""
    if image.width == EXPECTED_THUMBNAIL_WIDTH:
        return image.convert("RGB")
    height = max(1, round(image.height * EXPECTED_THUMBNAIL_WIDTH / image.width))
    return image.convert("RGB").resize(
        (EXPECTED_THUMBNAIL_WIDTH, height), Image.Resampling.LANCZOS
    )


def build_thumbnail_filename(arxiv_id: str, version: str = "v1") -> str:
    """
    Build the canonical thumbnail filename for an ArXiv paper.
    """
    safe_id = arxiv_id.replace("/", "_").replace(".", "_")
    return f"{safe_id}_{version}.jpg"


def build_external_thumbnail_filename(paper_id: int | str) -> str:
    """
    Build the stable thumbnail filename for a non-ArXiv external paper.
    """
    return f"external_{paper_id}.jpg"


def build_thumbnail_url(filename: str, cache_bust: str | None = None) -> str:
    """
    Build the public thumbnail URL with a renderer cache-bust marker.
    """
    url = f"/api/thumbnails/{filename}?fit={THUMBNAIL_RENDERER_CACHE_BUST}"
    if cache_bust:
        url += f"&v={cache_bust}"
    return url


def build_custom_thumbnail_url(filename: str, cache_bust: str | None = None) -> str:
    """
    Build the public URL for an explicitly stored non-ArXiv thumbnail.
    """
    url = f"/api/thumbnails/custom/{filename}?fit={THUMBNAIL_RENDERER_CACHE_BUST}"
    if cache_bust:
        url += f"&v={cache_bust}"
    return url


class ThumbnailService:
    """
    Service for generating and managing PDF thumbnails.
    """

    def __init__(self):
        self.settings = get_settings()
        self.storage_backend = self.settings.thumbnail_storage_backend.lower()
        self.legacy_cache_dir = Path(self.settings.thumbnail_cache_dir)
        self.temp_cache_dir = Path(self.settings.thumbnail_temp_cache_dir)
        self.bucket_id = self.settings.thumbnail_hf_bucket_id.strip()
        self.bucket_prefix = self.settings.thumbnail_hf_bucket_prefix.strip("/")
        self.hf_token = self.settings.hf_token or None
        self.hf_fs = (
            HfFileSystem(token=self.hf_token)
            if self.storage_backend == "hf_bucket"
            else None
        )

        if self.storage_backend == "hf_bucket":
            if not self.bucket_id:
                raise ThumbnailGenerationError(
                    "PWC_THUMBNAIL_HF_BUCKET_ID is required for hf_bucket storage"
                )
            if self.settings.thumbnail_mutations_enabled:
                self.temp_cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            if self.settings.thumbnail_mutations_enabled:
                self.legacy_cache_dir.mkdir(parents=True, exist_ok=True)

        # Thumbnail settings
        self.thumbnail_width = EXPECTED_THUMBNAIL_WIDTH  # Target width in pixels
        self.thumbnail_quality = 85  # JPEG quality
        self.pdf_timeout = 30  # Timeout for PDF downloads in seconds
        self.max_pdf_size = 50 * 1024 * 1024  # 50MB max PDF size
        self.external_page_screenshot_timeout = 45
        self.external_page_viewport = (1200, 1680)

        # ArXiv service for API interactions
        self.arxiv_service = ArxivService()

    def parse_filename(self, filename: str) -> tuple[str, str]:
        """
        Parse a thumbnail filename into ArXiv ID and version.
        """
        if "/" in filename or "\\" in filename:
            raise ThumbnailGenerationError("Invalid thumbnail filename")

        match = re.fullmatch(
            r"(?P<base>[A-Za-z0-9_.-]+?)_(?P<version>v\d+)\.jpg",
            filename,
        )
        if not match:
            raise ThumbnailGenerationError("Invalid thumbnail filename")

        safe_id = match.group("base")
        if "_" not in safe_id:
            raise ThumbnailGenerationError("Invalid thumbnail filename")

        arxiv_id = safe_id.replace("_", ".")
        return arxiv_id, match.group("version")

    def validate_custom_filename(self, filename: str) -> None:
        """
        Validate a manually captured thumbnail filename.
        """
        if "/" in filename or "\\" in filename:
            raise ThumbnailGenerationError("Invalid custom thumbnail filename")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.jpg", filename):
            raise ThumbnailGenerationError("Invalid custom thumbnail filename")

    def get_filename(self, arxiv_id: str, version: str = "v1") -> str:
        """
        Get the stable thumbnail filename for a given ArXiv paper.
        """
        return build_thumbnail_filename(arxiv_id, version)

    def get_external_filename(self, paper_id: int | str) -> str:
        """
        Get the stable thumbnail filename for a non-ArXiv paper.
        """
        return build_external_thumbnail_filename(paper_id)

    def _get_cache_path(self, arxiv_id: str, version: str = "v1") -> Path:
        """
        Get the active local cache file path for a given ArXiv paper.
        """
        return self._get_active_cache_path(self.get_filename(arxiv_id, version))

    def _get_active_cache_path(self, filename: str) -> Path:
        cache_dir = (
            self.temp_cache_dir
            if self.storage_backend == "hf_bucket"
            else self.legacy_cache_dir
        )
        return cache_dir / filename

    def _get_legacy_cache_path(self, filename: str) -> Path:
        return self.legacy_cache_dir / filename

    def _get_bucket_key(self, filename: str) -> str:
        return f"{self.bucket_prefix}/{filename}" if self.bucket_prefix else filename

    def _get_bucket_uri(self, filename: str) -> str:
        return f"hf://buckets/{self.bucket_id}/{self._get_bucket_key(filename)}"

    def _download_from_bucket(self, filename: str) -> Optional[Path]:
        if self.storage_backend != "hf_bucket":
            return None

        cache_path = self._get_active_cache_path(filename)
        if cache_path.exists():
            return cache_path
        if not self.settings.thumbnail_mutations_enabled:
            return None

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        download_bucket_files(
            self.bucket_id,
            [(self._get_bucket_key(filename), cache_path)],
            raise_on_missing_files=False,
            token=self.hf_token,
        )

        return cache_path if cache_path.exists() else None

    def _upload_to_bucket(self, thumbnail_path: Path, filename: str) -> None:
        if self.storage_backend != "hf_bucket":
            return
        if not self.settings.thumbnail_mutations_enabled:
            raise ThumbnailGenerationError("thumbnail mutations are disabled")

        batch_bucket_files(
            self.bucket_id,
            add=[(thumbnail_path, self._get_bucket_key(filename))],
            token=self.hf_token,
        )

    def _bucket_thumbnail_exists(self, filename: str) -> bool:
        if self.storage_backend != "hf_bucket" or self.hf_fs is None:
            return False

        try:
            return bool(self.hf_fs.exists(self._get_bucket_uri(filename)))
        except Exception as exc:
            logger.warning(
                "Failed to check thumbnail bucket object %s: %s", filename, exc
            )
            return False

    def _convert_pdf_to_thumbnail(self, pdf_content: bytes) -> Image.Image:
        """
        Convert PDF first page to thumbnail image.

        Args:
            pdf_content: PDF file content as bytes

        Returns:
            PIL Image of the thumbnail

        Raises:
            ThumbnailGenerationError: If conversion fails
        """
        try:
            # Convert first page only with reasonable DPI
            images = convert_from_bytes(
                pdf_content,
                first_page=1,
                last_page=1,
                dpi=150,  # Good balance of quality and performance
                fmt="jpeg",
            )

            if not images:
                raise ThumbnailGenerationError("No pages found in PDF")

            image = images[0]
            return _prepare_first_page_for_card(image)

        except Exception as e:
            raise ThumbnailGenerationError(f"Failed to convert PDF to image: {str(e)}")

    def _convert_screenshot_to_thumbnail(self, image: Image.Image) -> Image.Image:
        """
        Resize a browser screenshot to the same card-friendly width as PDF thumbnails.
        """
        try:
            if image.mode != "RGB":
                image = image.convert("RGB")
            return _resize_to_card_fill(image)
        except Exception as e:
            raise ThumbnailGenerationError(
                f"Failed to convert screenshot to thumbnail: {str(e)}"
            )

    def _render_biorxiv_metadata_thumbnail(
        self, metadata: BioRxivMetadata, server: str
    ) -> Image.Image:
        """
        Render a readable card thumbnail from bioRxiv API metadata when the PDF
        is not available via Europe PMC or the requester-pays S3 mirror.
        """
        width = self.thumbnail_width
        height = int(width * 1.35)
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        font_title = ImageFont.load_default(size=18)
        font_body = ImageFont.load_default(size=13)
        font_label = ImageFont.load_default(size=12)

        margin = 20
        y = margin
        label = "medRxiv" if server == "medrxiv" else "bioRxiv"
        draw.text((margin, y), label, fill="#2563eb", font=font_label)
        y += 22

        title = (metadata.title or "Untitled preprint").strip()
        for line in self._wrap_text(title, font_title, width - 2 * margin):
            draw.text((margin, y), line, fill="#111827", font=font_title)
            y += 22
            if y > height - 120:
                break

        if metadata.authors:
            author_line = ", ".join(metadata.authors[:3])
            if len(metadata.authors) > 3:
                author_line += ", et al."
            for line in self._wrap_text(author_line, font_body, width - 2 * margin):
                draw.text((margin, y), line, fill="#4b5563", font=font_body)
                y += 18
                if y > height - 80:
                    break

        if metadata.abstract and y < height - 70:
            y += 8
            snippet = metadata.abstract.strip()
            if len(snippet) > 320:
                snippet = snippet[:317].rstrip() + "..."
            for line in self._wrap_text(snippet, font_body, width - 2 * margin):
                draw.text((margin, y), line, fill="#374151", font=font_body)
                y += 17
                if y > height - margin:
                    break

        return image

    def _wrap_text(
        self, text: str, font: ImageFont.ImageFont, max_width: int
    ) -> list[str]:
        words = text.split()
        if not words:
            return []

        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            bbox = font.getbbox(candidate)
            if bbox[2] - bbox[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _normalize_external_pdf_url(self, source_url: str) -> str:
        """
        Convert common browser-facing PDF URLs to direct downloadable URLs.
        """
        parsed = urlparse(source_url)
        if parsed.netloc == "huggingface.co" and "/blob/" in parsed.path:
            path = parsed.path.replace("/blob/", "/resolve/", 1)
            return parsed._replace(path=path).geturl()
        if (
            parsed.netloc in {"github.com", "www.github.com"}
            and "/blob/" in parsed.path
        ):
            path = parsed.path.replace("/blob/", "/raw/", 1)
            return parsed._replace(path=path).geturl()
        return source_url

    def _looks_like_pdf_url(self, source_url: str) -> bool:
        return urlparse(source_url).path.lower().endswith(".pdf")

    async def _download_external_pdf(self, source_url: str) -> Optional[bytes]:
        """
        Download an external PDF when the source URL is directly PDF-like.
        """
        pdf_url = self._normalize_external_pdf_url(source_url)
        headers = {
            "Accept": "application/pdf,text/html;q=0.8,*/*;q=0.5",
            "User-Agent": "paperswithcode-thumbnail-bot/1.0",
        }
        timeout = httpx.Timeout(self.pdf_timeout)

        async with httpx.AsyncClient(
            follow_redirects=True, timeout=timeout, headers=headers
        ) as client:
            if not self._looks_like_pdf_url(pdf_url):
                try:
                    head = await client.head(pdf_url)
                except httpx.HTTPError:
                    return None
                content_type = head.headers.get("content-type", "").lower()
                if "application/pdf" not in content_type:
                    return None

            try:
                response = await client.get(pdf_url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ThumbnailGenerationError(
                    f"Failed to download external PDF: {exc}"
                )

        content_type = response.headers.get("content-type", "").lower()
        if "application/pdf" not in content_type and not self._looks_like_pdf_url(
            str(response.url)
        ):
            return None
        if len(response.content) > self.max_pdf_size:
            raise ThumbnailGenerationError("External PDF is too large")
        if not response.content.startswith(b"%PDF"):
            return None
        return response.content

    async def _capture_external_page_screenshot(self, source_url: str) -> Image.Image:
        """
        Capture the first viewport of an external project page with headless Chrome.
        """
        chrome_path = (
            shutil.which("google-chrome")
            or shutil.which("chromium")
            or shutil.which("chromium-browser")
        )
        if chrome_path is None:
            raise ThumbnailGenerationError("No headless Chrome executable found")

        width, height = self.external_page_viewport
        with tempfile.TemporaryDirectory(prefix="pwc_external_thumb_") as tmp_dir:
            screenshot_path = Path(tmp_dir) / "page.jpg"
            process = await asyncio.create_subprocess_exec(
                chrome_path,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--hide-scrollbars",
                f"--window-size={width},{height}",
                "--force-device-scale-factor=1",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000",
                f"--screenshot={screenshot_path}",
                source_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.external_page_screenshot_timeout,
                )
            except asyncio.TimeoutError as exc:
                process.kill()
                try:
                    await asyncio.wait_for(process.communicate(), timeout=5)
                except asyncio.TimeoutError:
                    pass
                raise ThumbnailGenerationError(
                    "Timed out capturing external page screenshot"
                ) from exc

            if process.returncode != 0 or not screenshot_path.exists():
                error = stderr.decode("utf-8", errors="ignore").strip()
                raise ThumbnailGenerationError(
                    f"Failed to capture external page screenshot: {error[-500:]}"
                )

            with Image.open(screenshot_path) as image:
                return image.convert("RGB")

    def _save_thumbnail(self, image: Image.Image, cache_path: Path) -> None:
        """
        Save thumbnail image to cache.

        Args:
            image: PIL Image to save
            cache_path: Path where to save the image
        """
        try:
            # Convert to RGB if necessary (for JPEG)
            if image.mode != "RGB":
                image = image.convert("RGB")

            image.save(
                cache_path, "JPEG", quality=self.thumbnail_quality, optimize=True
            )
            # The shared cache is written by cron/admin processes but served by
            # the unprivileged production backend. Thumbnail contents are
            # public, so make every generated JPEG readable across service users
            # regardless of the writer's umask.
            cache_path.chmod(0o644)
        except Exception as e:
            raise ThumbnailGenerationError(f"Failed to save thumbnail: {str(e)}")

    def get_existing_thumbnail_path(self, filename: str) -> Optional[Path]:
        """
        Return an existing thumbnail path from active cache, bucket, or legacy cache.
        """
        self.parse_filename(filename)
        return self._get_existing_thumbnail_path_unchecked(filename)

    def get_local_thumbnail_path(self, filename: str) -> Optional[Path]:
        """
        Return an existing thumbnail path from on-disk caches only.

        Used by the request-serving path to guarantee that no per-request HF
        bucket round-trip happens; the bucket is kept in sync with the active
        local cache by the `mirror_thumbnails_to_disk` cron.
        """
        self.parse_filename(filename)
        active_cache_path = self._get_active_cache_path(filename)
        if active_cache_path.exists():
            return active_cache_path

        legacy_cache_path = self._get_legacy_cache_path(filename)
        if legacy_cache_path.exists():
            return legacy_cache_path

        return None

    def get_existing_custom_thumbnail_path(self, filename: str) -> Optional[Path]:
        """
        Return an existing manually captured thumbnail path.
        """
        self.validate_custom_filename(filename)
        return self._get_existing_thumbnail_path_unchecked(filename)

    def get_local_custom_thumbnail_path(self, filename: str) -> Optional[Path]:
        """
        Disk-only variant of :meth:`get_existing_custom_thumbnail_path`.

        Used by latency-sensitive paths (e.g. social-preview HTML rendering)
        that must not trigger a per-request HF bucket round-trip just to
        decide whether the thumbnail JPEG already exists on the VPS mirror.
        """
        self.validate_custom_filename(filename)
        active_cache_path = self._get_active_cache_path(filename)
        if active_cache_path.exists():
            return active_cache_path
        legacy_cache_path = self._get_legacy_cache_path(filename)
        if legacy_cache_path.exists():
            return legacy_cache_path
        return None

    def _get_existing_thumbnail_path_unchecked(self, filename: str) -> Optional[Path]:
        active_cache_path = self._get_active_cache_path(filename)
        if active_cache_path.exists():
            return active_cache_path

        bucket_path = self._download_from_bucket(filename)
        if bucket_path:
            return bucket_path

        legacy_cache_path = self._get_legacy_cache_path(filename)
        if legacy_cache_path.exists():
            try:
                self._upload_to_bucket(legacy_cache_path, filename)
            except Exception as exc:
                logger.warning(
                    "Failed to upload legacy thumbnail %s to bucket: %s",
                    filename,
                    exc,
                )
            return legacy_cache_path

        return None

    async def get_or_generate_thumbnail(self, filename: str) -> Path:
        """
        Return an existing thumbnail or generate it from the filename's ArXiv ID.
        """
        arxiv_id, version = self.parse_filename(filename)
        existing_path = self.get_existing_thumbnail_path(filename)
        if existing_path:
            return existing_path

        return await self.generate_thumbnail(arxiv_id, version)

    async def generate_thumbnail(
        self, arxiv_id: str, version: str = "v1", force: bool = False
    ) -> Path:
        """
        Generate thumbnail for a paper using ArXiv service.

        Args:
            arxiv_id: ArXiv ID of the paper
            version: Paper version
            force: Regenerate and overwrite the cached thumbnail if it exists

        Returns:
            Path to the generated thumbnail file

        Raises:
            ThumbnailGenerationError: If generation fails
        """
        filename = self.get_filename(arxiv_id, version)
        if not force:
            existing_path = self.get_existing_thumbnail_path(filename)
            if existing_path:
                return existing_path

        cache_path = self._get_cache_path(arxiv_id, version)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Download PDF using ArXiv service (handles rate limiting)
            pdf_content = await self.arxiv_service.download_pdf(arxiv_id, version)

            if pdf_content is None:
                raise ThumbnailGenerationError(
                    f"Could not download PDF for ArXiv ID {arxiv_id}"
                )

            # Convert to thumbnail
            thumbnail = self._convert_pdf_to_thumbnail(pdf_content)

            # Save to cache
            self._save_thumbnail(thumbnail, cache_path)
            self._upload_to_bucket(cache_path, filename)

            return cache_path

        except ThumbnailGenerationError:
            raise
        except Exception as e:
            raise ThumbnailGenerationError(
                f"Unexpected error generating thumbnail: {str(e)}"
            )

    async def generate_external_thumbnail(
        self, paper_id: int | str, source_url: str, force: bool = False
    ) -> Path:
        """
        Generate a thumbnail for a non-ArXiv external paper.

        Direct PDFs are rendered from their first page. Other source URLs fall
        back to a first-viewport screenshot of the project page.
        """
        filename = self.get_external_filename(paper_id)
        if not force:
            existing_path = self.get_existing_custom_thumbnail_path(filename)
            if existing_path:
                return existing_path

        cache_path = self._get_active_cache_path(filename)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        biorxiv_paper = parse_biorxiv_doi(source_url)
        pdf_content = None
        if biorxiv_paper is not None:
            server, _ = biorxiv_paper
            settings = get_settings()
            pdf_content = await download_biorxiv_pdf_bytes(
                source_url,
                aws_access_key_id=settings.biorxiv_aws_access_key_id,
                aws_secret_access_key=settings.biorxiv_aws_secret_access_key,
            )
        if pdf_content is None:
            pdf_content = await self._download_external_pdf(source_url)
        if pdf_content is not None:
            thumbnail = self._convert_pdf_to_thumbnail(pdf_content)
        elif biorxiv_paper is not None:
            server, _ = biorxiv_paper
            metadata = await fetch_biorxiv_metadata(source_url)
            if metadata is None:
                raise ThumbnailGenerationError(
                    "Could not download bioRxiv/medRxiv PDF or metadata"
                )
            thumbnail = self._render_biorxiv_metadata_thumbnail(metadata, server)
        else:
            screenshot = await self._capture_external_page_screenshot(source_url)
            thumbnail = self._convert_screenshot_to_thumbnail(screenshot)

        self._save_thumbnail(thumbnail, cache_path)
        self._upload_to_bucket(cache_path, filename)
        return cache_path

    def get_thumbnail_url(self, arxiv_id: str, version: str = "v1") -> Optional[str]:
        """
        Get the URL for a cached thumbnail.

        Args:
            arxiv_id: ArXiv ID of the paper
            version: Paper version

        Returns:
            URL to the thumbnail or None if not cached
        """
        filename = self.get_filename(arxiv_id, version)

        active_cache_path = self._get_active_cache_path(filename)
        legacy_cache_path = self._get_legacy_cache_path(filename)
        if (
            active_cache_path.exists()
            or legacy_cache_path.exists()
            or self._bucket_thumbnail_exists(filename)
        ):
            return build_thumbnail_url(filename)

        return None

    def get_external_thumbnail_url(self, paper_id: int | str) -> Optional[str]:
        """
        Get the URL for a cached non-ArXiv paper thumbnail.
        """
        filename = self.get_external_filename(paper_id)
        if self.get_existing_custom_thumbnail_path(filename):
            return build_custom_thumbnail_url(filename)
        return None

    def cleanup_old_thumbnails(self, max_age_days: int = 30) -> int:
        """
        Clean up old cached thumbnails.

        Args:
            max_age_days: Maximum age in days for cached thumbnails

        Returns:
            Number of files deleted
        """
        deleted_count = 0
        max_age_seconds = max_age_days * 24 * 60 * 60
        current_time = time.time()

        cache_dir = (
            self.temp_cache_dir
            if self.storage_backend == "hf_bucket"
            else self.legacy_cache_dir
        )

        for thumbnail_file in cache_dir.glob("*.jpg"):
            try:
                file_age = current_time - thumbnail_file.stat().st_mtime
                if file_age > max_age_seconds:
                    thumbnail_file.unlink()
                    deleted_count += 1
            except Exception:
                # Skip files that can't be processed
                continue

        return deleted_count

    def get_cache_stats(self) -> dict:
        """
        Get statistics about the thumbnail cache.

        Returns:
            Dictionary with cache statistics
        """
        try:
            cache_dir = (
                self.temp_cache_dir
                if self.storage_backend == "hf_bucket"
                else self.legacy_cache_dir
            )
            thumbnail_files = list(cache_dir.glob("*.jpg"))
            total_files = len(thumbnail_files)

            total_size = sum(f.stat().st_size for f in thumbnail_files)
            total_size_mb = total_size / (1024 * 1024)

            stats = {
                "total_files": total_files,
                "total_size_mb": round(total_size_mb, 2),
                "cache_dir": str(cache_dir),
                "storage_backend": self.storage_backend,
            }
            if self.storage_backend == "hf_bucket":
                stats.update(
                    {
                        "bucket_id": self.bucket_id,
                        "bucket_prefix": self.bucket_prefix,
                        "legacy_cache_dir": str(self.legacy_cache_dir),
                    }
                )
            return stats
        except Exception:
            return {
                "total_files": 0,
                "total_size_mb": 0,
                "cache_dir": str(
                    self.temp_cache_dir
                    if self.storage_backend == "hf_bucket"
                    else self.legacy_cache_dir
                ),
                "storage_backend": self.storage_backend,
            }
