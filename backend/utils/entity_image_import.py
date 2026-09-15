"""Import curated entity hero images into DB-backed BYTEA columns."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Type

from sqlalchemy.orm import Session

from backend.models.database import Conference as DBConference
from backend.models.database import Method as DBMethod
from backend.models.database import Task as DBTask

ENTITY_MODELS = {
    "tasks": DBTask,
    "methods": DBMethod,
    "conferences": DBConference,
}

MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}

# Temporary seed directory for one-off imports and bulk backfill.
IMAGE_SEED_ROOT = Path(tempfile.gettempdir()) / "paperswithcode_entity_image_seeds"


def mime_type_for_path(image_path: Path) -> str | None:
    return MIME_BY_SUFFIX.get(image_path.suffix.lower())


def store_entity_image(
    session: Session,
    model: Type,
    slug: str,
    image_path: Path,
) -> bool:
    """Read *image_path* and store bytes on the row matching *slug*.

    Returns True when a row was updated, False when no matching row exists.
    """
    mime = mime_type_for_path(image_path)
    if mime is None:
        raise ValueError(f"Unsupported image type: {image_path}")

    row = session.query(model).filter(model.slug == slug).first()
    if row is None:
        return False

    row.image_data = image_path.read_bytes()
    row.image_mime_type = mime
    row.updated_at = datetime.now(timezone.utc)
    return True
