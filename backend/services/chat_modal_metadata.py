"""Bounded, process-local metadata reuse; never holds or creates sandboxes."""

from __future__ import annotations

import asyncio
import os
from functools import lru_cache

import modal
from modal.client import Client

from backend.chat_sandbox_worker.contract import MODAL_APP_NAME


class _Metadata:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.resources: tuple[object, object] | None = None


@lru_cache(maxsize=8)
def _entry(
    pid: int, loop: object, client: object, environment: str, image_id: str
) -> _Metadata:
    # Include the loop and client so locks and credentials cannot cross lifetimes.
    return _Metadata()


async def executor_metadata(environment: str, image_id: str) -> tuple[object, object]:
    """Resolve an immutable image once per client/environment/event loop."""
    if not environment or not image_id.startswith("im-"):
        raise ValueError("Executor metadata requires an environment and pinned image")
    client = await Client.from_env.aio()
    entry = _entry(
        os.getpid(), asyncio.get_running_loop(), client, environment, image_id
    )
    async with entry.lock:
        if entry.resources is None:
            app = await modal.App.lookup.aio(
                MODAL_APP_NAME,
                client=client,
                environment_name=environment,
                create_if_missing=False,
            )
            image = modal.Image.from_id(image_id, client=client)
            # For an existing im-ID this only fetches metadata (ImageFromId).
            # Hydration prevents Sandbox.create from repeating that lookup.
            await image.build.aio(app)
            entry.resources = app, image
        return entry.resources
