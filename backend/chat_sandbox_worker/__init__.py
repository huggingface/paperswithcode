"""Minimal worker payload installed in the immutable chat sandbox image."""

from backend.chat_sandbox_worker.contract import WORKER_CONTRACT_VERSION

__all__ = ["WORKER_CONTRACT_VERSION"]
