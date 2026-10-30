#!/usr/bin/env python3
"""Store a Wikimedia Commons portrait as an author's photo, with its credit.

Usage:
  uv run --env-file backend/keys.env python backend/database/import_author_photo.py \\
      25 "Yoshua Bengio 2019 cropped.jpg"

Only freely licensed files are accepted (CC BY, CC BY-SA, CC0, public domain).
The photo is cropped to a square near the top, where portraits put the face;
--zoom crops tighter when the face is small.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import re

import httpx
from PIL import Image

from backend.database.connection import db_manager
from backend.models.database import Author, AuthorPhoto

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "PapersWithCode/1.0 (https://paperswithcode.co)"}
FREE_LICENSES = re.compile(r"^(CC BY(-SA)? \d\.\d|CC0|Public domain)", re.I)
SIZE = 256


def commons_file(name: str) -> dict:
    response = httpx.get(
        COMMONS_API,
        params={
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 2 * SIZE,
            "titles": f"File:{name}",
        },
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    page = next(iter(response.json()["query"]["pages"].values()))
    if "imageinfo" not in page:
        raise SystemExit(f"No Commons file named {name!r}")
    return page["imageinfo"][0]


def square_jpeg(data: bytes, zoom: float = 1.0) -> bytes:
    image = Image.open(io.BytesIO(data)).convert("RGB")
    side = int(min(image.size) / zoom)
    left = (image.width - side) // 2
    # Portraits frame the face high, so keep the top of a tall photo.
    top = (image.height - side) // 6
    image = image.crop((left, top, left + side, top + side)).resize(
        (SIZE, SIZE), Image.LANCZOS
    )
    out = io.BytesIO()
    image.save(out, "JPEG", quality=88)
    return out.getvalue()


def plain(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", value)).split())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("author_id", type=int)
    parser.add_argument("commons_file", help="Commons file name, without File:")
    parser.add_argument(
        "--zoom", type=float, default=1.0, help="Crop tighter for a small face"
    )
    args = parser.parse_args()

    info = commons_file(args.commons_file)
    meta = info["extmetadata"]
    license_name = meta.get("LicenseShortName", {}).get("value", "")
    if not FREE_LICENSES.match(license_name):
        raise SystemExit(f"Not a free license: {license_name!r}")
    credit = plain(meta.get("Artist", {}).get("value", "")) or "Wikimedia Commons"
    image = httpx.get(info["thumburl"], headers=HEADERS, timeout=60)
    image.raise_for_status()
    data = square_jpeg(image.content, args.zoom)

    with db_manager.session_local() as session:
        if session.get(Author, args.author_id) is None:
            raise SystemExit(f"No author {args.author_id}")
        session.merge(
            AuthorPhoto(
                author_id=args.author_id,
                image_data=data,
                mime_type="image/jpeg",
                sha256=hashlib.sha256(data).hexdigest(),
                source_url=info["descriptionurl"],
                credit=credit[:500],
                license=license_name,
                license_url=meta.get("LicenseUrl", {}).get("value"),
            )
        )
        session.commit()
    print(
        f"Stored {args.commons_file} ({license_name}, {credit}) for author {args.author_id}"
    )


if __name__ == "__main__":
    main()
