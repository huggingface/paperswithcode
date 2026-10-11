#!/usr/bin/env python3
"""Add Image super-resolution and Video super-resolution tasks."""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.taxonomy import TaskCreateRequest
from backend.services.task_service import TaskService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

VISION_AREA_ID = 1
VIDEO_AREA_ID = 9

IMAGE_SUPER_RESOLUTION_IMAGE_URL = (
    "https://paperswithcode.co/images/tasks/image-super-resolution.png"
)
IMAGE_SUPER_RESOLUTION_IMAGE_CREDIT = "https://jitezzrawat99.medium.com/image-super-resolution-using-convolutional-neural-networks-review-and-summary-74af53c0a343"

TASKS = [
    {
        "slug": "image-super-resolution",
        "name": "Image super-resolution",
        "area_id": VISION_AREA_ID,
        "description": (
            "Image super-resolution reconstructs high-resolution images from "
            "low-resolution inputs. Methods upsample single images while recovering "
            "fine detail and reducing artifacts."
        ),
        "keywords": "image super resolution,image super-resolution",
        "image_url": IMAGE_SUPER_RESOLUTION_IMAGE_URL,
        "image_credit": IMAGE_SUPER_RESOLUTION_IMAGE_CREDIT,
    },
    {
        "slug": "video-super-resolution",
        "name": "Video super-resolution",
        "area_id": VIDEO_AREA_ID,
        "description": (
            "Video super-resolution upsamples low-resolution video frames or sequences "
            "to higher spatial resolution while preserving temporal consistency across "
            "frames."
        ),
        "keywords": "video super resolution,video super-resolution",
    },
]


def ensure_task(session, spec: dict) -> int:
    row = session.execute(
        text(
            "SELECT id, area_id, image_url, image_credit FROM tasks WHERE slug = :slug"
        ),
        {"slug": spec["slug"]},
    ).first()
    if row:
        task_id = int(row[0])
        current_area_id = row[1]
        current_image_url = row[2]
        current_image_credit = row[3]
        updates: dict[str, object] = {"id": task_id}
        changed_fields: list[str] = []

        if current_area_id != spec["area_id"]:
            updates["area_id"] = spec["area_id"]
            changed_fields.append("area_id")

        desired_image_url = spec.get("image_url")
        if desired_image_url is not None and current_image_url != desired_image_url:
            updates["image_url"] = desired_image_url
            changed_fields.append("image_url")

        desired_image_credit = spec.get("image_credit")
        if (
            desired_image_credit is not None
            and current_image_credit != desired_image_credit
        ):
            updates["image_credit"] = desired_image_credit
            changed_fields.append("image_credit")

        if changed_fields:
            set_clause = ", ".join(f"{field} = :{field}" for field in changed_fields)
            session.execute(
                text(f"UPDATE tasks SET {set_clause} WHERE id = :id"),
                updates,
            )
            logger.info(
                "Updated %s (id=%s): %s",
                spec["name"],
                task_id,
                ", ".join(changed_fields),
            )
        else:
            logger.info("Task already exists: %s (id=%s)", spec["name"], task_id)
        return task_id

    task = TaskService(session).create_task(
        TaskCreateRequest(
            name=spec["name"],
            description=spec["description"],
            keywords=spec["keywords"],
            area_id=spec["area_id"],
            image_url=spec.get("image_url"),
            image_credit=spec.get("image_credit"),
        )
    )
    logger.info("Created task: %s (id=%s)", spec["name"], task.id)
    return int(task.id)


def main() -> None:
    session = db_manager.session_local()
    try:
        for spec in TASKS:
            ensure_task(session, spec)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
