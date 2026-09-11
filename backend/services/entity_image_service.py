"""Download and store DB-backed hero images for taxonomy entities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image
from sqlalchemy.orm import Session

from backend.models.database import Conference as DBConference
from backend.models.database import Method as DBMethod
from backend.models.database import Task as DBTask
from backend.utils.entity_image_import import IMAGE_SEED_ROOT

MAX_IMAGE_BYTES = 20 * 1024 * 1024

ENTITY_CONFIG = {
    "task": (DBTask, "tasks"),
    "method": (DBMethod, "methods"),
    "conference": (DBConference, "conferences"),
}

IMAGE_FORMATS = {
    "GIF": ("image/gif", ".gif"),
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
}


@dataclass(frozen=True)
class EntityImageResult:
    entity: str
    slug: str
    image_url: str
    source: str
    mime_type: str
    byte_count: int
    seed_path: str

    def to_dict(self) -> dict:
        return asdict(self)


def _validate_image_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"image URL must be an http(s) URL: {url}")


def _download_image(client: httpx.Client, image_url: str) -> bytes:
    try:
        with client.stream("GET", image_url) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_IMAGE_BYTES:
                raise ValueError(
                    f"Image is larger than the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit"
                )

            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > MAX_IMAGE_BYTES:
                    raise ValueError(
                        f"Image is larger than the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit"
                    )
    except (httpx.HTTPError, ValueError) as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError(f"Could not download image: {error}") from error

    if not content:
        raise ValueError("Downloaded image is empty")
    return bytes(content)


def _detect_image_type(content: bytes) -> tuple[str, str]:
    try:
        with Image.open(BytesIO(content)) as image:
            image_format = image.format
            image.verify()
    except Exception as error:
        raise ValueError("Downloaded content is not a valid supported image") from error

    if image_format not in IMAGE_FORMATS:
        raise ValueError(f"Unsupported image format: {image_format or 'unknown'}")
    return IMAGE_FORMATS[image_format]


def add_entity_image(
    session: Session,
    entity: str,
    slug: str,
    image_url: str,
    source: str,
    *,
    client: httpx.Client | None = None,
    seed_root: Path = IMAGE_SEED_ROOT,
) -> EntityImageResult:
    """Download an entity image and update its DB row.

    The seed copy uses temporary storage by default.
    """
    _validate_image_url(image_url)
    if not source.strip():
        raise ValueError("source credit must not be empty")

    model, directory = ENTITY_CONFIG[entity]
    row = session.query(model).filter(model.slug == slug).first()
    if row is None:
        raise ValueError(f"No {entity} found with slug={slug!r}")

    owns_client = client is None
    http_client = client or httpx.Client(
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "paperswithcode-entity-image/1.0"},
    )
    try:
        content = _download_image(http_client, image_url)
    finally:
        if owns_client:
            http_client.close()

    mime_type, suffix = _detect_image_type(content)
    seed_path = seed_root / directory / f"{slug}{suffix}"
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.write_bytes(content)

    row.image_data = content
    row.image_mime_type = mime_type
    row.image_credit = source
    row.updated_at = datetime.now(timezone.utc)

    return EntityImageResult(
        entity=entity,
        slug=slug,
        image_url=image_url,
        source=source,
        mime_type=mime_type,
        byte_count=len(content),
        seed_path=str(seed_path),
    )
