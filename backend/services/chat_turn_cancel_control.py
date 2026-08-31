"""Typed evidence returned by detached turn cancellation control."""

from __future__ import annotations

from enum import Enum


class CancelControlResult(str, Enum):
    """Whether the exact running turn accepted a cancellation request."""

    REQUESTED = "requested"
    MISSING = "missing"
