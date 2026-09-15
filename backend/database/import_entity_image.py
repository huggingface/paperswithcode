#!/usr/bin/env python3
"""Import a single curated entity image into the database.

Usage:
  uv run --env-file backend/keys.env python backend/database/import_entity_image.py \\
      tasks video-matting /tmp/paperswithcode_entity_image_seeds/tasks/video-matting.png

  uv run --env-file backend/keys.env python backend/database/import_entity_image.py \\
      methods transformer /tmp/transformer.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.database.connection import db_manager
from backend.utils.entity_image_import import ENTITY_MODELS, store_entity_image


def main() -> None:
    parser = argparse.ArgumentParser(description="Import an entity hero image into SQL")
    parser.add_argument(
        "entity",
        choices=sorted(ENTITY_MODELS),
        help="Entity type (tasks, methods, conferences)",
    )
    parser.add_argument("slug", help="Row slug to update")
    parser.add_argument("image_path", type=Path, help="Local image file to import")
    args = parser.parse_args()

    image_path = args.image_path
    if not image_path.is_file():
        print(f"ERROR: file not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    model = ENTITY_MODELS[args.entity]
    session = db_manager.session_local()
    try:
        updated = store_entity_image(session, model, args.slug, image_path)
        if not updated:
            print(
                f"ERROR: no {args.entity} row with slug={args.slug!r}",
                file=sys.stderr,
            )
            session.rollback()
            sys.exit(1)
        session.commit()
        print(f"Stored {image_path} -> {args.entity}({args.slug})")
    except Exception as exc:
        session.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
