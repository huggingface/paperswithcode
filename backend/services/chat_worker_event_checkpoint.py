"""In-process persistence receipts, excluded from public event JSON."""

from collections.abc import Awaitable, Callable
from typing import Any


class CheckpointedWorkerEvent(dict[str, Any]):
    def __init__(
        self, event: dict[str, Any], after_persist: Callable[[], Awaitable[None]]
    ) -> None:
        super().__init__(event)
        self.after_persist = after_persist
