"""Explicit CI-only image publication entry point.

This is never imported or called by the web service. The emitted immutable image
ID is copied into a later staging release manifest before allocation is enabled.
"""

import modal

from backend.chat_sandbox_worker.contract import IMAGE_PUBLISH_NAME, MODAL_APP_NAME
from backend.chat_sandbox_worker.image import app, image


def main() -> int:
    modal.App.lookup(MODAL_APP_NAME, create_if_missing=True)
    with app.run():
        built = image.build(app)
        built.publish(IMAGE_PUBLISH_NAME)
    if not built.object_id:
        raise RuntimeError("Modal image publication returned no immutable image ID")
    print(built.object_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
