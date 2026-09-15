"""Content-free stage timings for persistent executor startup diagnostics."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

logger = logging.getLogger("uvicorn.error")
Stage = Literal[
    "provider_lookup",
    "provider_create",
    "registration",
    "liveness",
    "claim",
    "attachment",
    "acquire",
    "health",
    "workspace",
]


@contextmanager
def executor_stage(stage: Stage, identity: str) -> Iterator[None]:
    """Correlate opaque runtime identities without logging commands or credentials."""
    started = time.monotonic()
    success = False
    try:
        yield
        success = True
    finally:
        logger.info(
            "chat executor timing stage=%s identity=%s duration_ms=%d success=%s",
            stage,
            identity,
            max(0, round((time.monotonic() - started) * 1000)),
            success,
        )
