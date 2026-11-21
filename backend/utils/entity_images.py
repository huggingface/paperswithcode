"""
Helpers for DB-backed entity images (tasks, methods, conferences).

Curated hero/figure images used to live as static files under
`frontend/public/images/<entity>/<slug>.png` and seed PNGs under
`data/entity_image_seeds/<entity>/`. They now live in the database in
two columns per row:

  - `image_data`       BYTEA, deferred so list queries never load the blob.
  - `image_mime_type`  small VARCHAR, always loaded, also used as the
                       "this row has a DB image" flag.

`entity_image_url` turns that flag into the public URL the API returns, and
`load_entity_image` fetches the bytes for the serving endpoints.
"""

from datetime import datetime
from typing import Optional, Tuple, Type

from sqlalchemy.orm import Session, undefer

IMAGE_CACHE_HEADERS = {"Cache-Control": "public, s-maxage=604800, max-age=604800"}

IMAGE_MISSING_HEADERS = {"Cache-Control": "public, max-age=3600"}


def entity_image_url(
    entity_path: str,
    slug: Optional[str],
    has_db_image: bool,
    fallback_url: Optional[str],
    updated_at: Optional[datetime] = None,
) -> Optional[str]:
    """Resolve the `image_url` returned to API clients.

    When the row carries a DB-backed image (and has a slug to address it),
    point at the backend serving endpoint. Otherwise fall back to whatever
    external URL is stored (e.g. a third-party diagram we don't self-host).

    Args:
        entity_path: API path segment for the entity (`tasks`, `methods`,
            `conferences`).
        slug: Row slug used to address the image endpoint.
        has_db_image: True when the row has bytes stored in `image_data`.
        fallback_url: Existing `image_url` to return when no DB image exists.
    """
    if has_db_image and slug:
        url = f"/api/v1/{entity_path}/{slug}/image"
        if updated_at is not None:
            url = f"{url}?v={int(updated_at.timestamp())}"
        return url
    return fallback_url


def load_entity_image(
    db: Session, model: Type, identifier: str
) -> Optional[Tuple[bytes, str]]:
    """Load the stored image bytes + MIME type for an entity by id or slug.

    Returns None when the row does not exist or has no DB-backed image, so the
    caller can return a 404. `image_data` is explicitly undeferred here because
    it is the one place we actually need the blob.
    """
    query = db.query(model).options(undefer(model.image_data))

    if identifier.isdigit():
        row = query.filter(model.id == int(identifier)).first()
    else:
        row = query.filter(model.slug == identifier).first()

    if row is None or row.image_data is None:
        return None

    return row.image_data, row.image_mime_type or "application/octet-stream"
