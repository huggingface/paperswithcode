"""Explicit CI-only image publication entry point.

This is never imported or called by the web service. The emitted immutable image
ID is copied into a later staging release manifest before allocation is enabled.
"""

from backend.chat_sandbox_worker.contract import IMAGE_PUBLISH_NAME
from backend.chat_sandbox_worker.image import app, image


def main() -> int:
    built = image.build(app)
    built.publish(IMAGE_PUBLISH_NAME)
    print(built.object_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
