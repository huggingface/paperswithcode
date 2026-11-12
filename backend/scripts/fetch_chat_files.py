#!/usr/bin/env python3
"""Copy one chat's uploaded files into a local directory for a chat-health audit.

Read-only: it never changes the database or the stored files. Reports built
from these files must not quote their contents.

    uv run --env-file backend/keys.env python -m backend.scripts.fetch_chat_files \\
        --session-id <uuid> --out-dir "$SCRATCHPAD/chat-files"
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from sqlalchemy import select, text

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import ChatUploadedFile
from backend.services.chat_file_service import chat_file_storage_from_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session-id", type=uuid.UUID, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    arguments = parser.parse_args()

    settings = get_settings()
    storage = chat_file_storage_from_settings(settings)
    destination = arguments.out_dir / str(arguments.session_id)
    destination.mkdir(parents=True, exist_ok=True)
    with db_manager.session_local() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        rows = list(
            db.scalars(
                select(ChatUploadedFile)
                .where(ChatUploadedFile.session_id == arguments.session_id)
                .order_by(ChatUploadedFile.created_at)
            )
        )
    for row in rows:
        path = destination / f"{row.id}-{row.filename}"
        path.write_bytes(storage.read(row.storage_key))
        print(
            json.dumps(
                {
                    "file_id": str(row.id),
                    "path": str(path),
                    "media_type": row.media_type,
                    "size_bytes": row.size_bytes,
                    "page_count": row.page_count,
                    "state": row.state,
                }
            )
        )


if __name__ == "__main__":
    main()
