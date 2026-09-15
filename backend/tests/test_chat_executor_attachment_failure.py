import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from backend.services.chat_executor_runtime import ChatExecutorRuntime
from backend.services.chat_sandbox_provider import SandboxError


@pytest.mark.parametrize(
    "error",
    [asyncio.IncompleteReadError(b"", 4), TimeoutError(), asyncio.CancelledError()],
)
def test_attachment_failure_settles_claim_and_keeps_cancellation(monkeypatch, error):
    runtime = ChatExecutorRuntime(
        SimpleNamespace(
            environment="staging",
            chat_executor_harness_key_id="harness",
            chat_executor_authorization_key_id="authorization",
        ),
        session_factory=lambda: None,
    )
    registration = SimpleNamespace(
        id=uuid.uuid4(),
        environment_id="environment",
        environment_generation=1,
        shard_generation=1,
        public_key_id="public",
        public_noise_key={},
    )
    manifest = SimpleNamespace(protocol_version=1, schema_digest="00" * 32)
    monkeypatch.setattr(
        runtime,
        "_wait_for_registration",
        AsyncMock(return_value=(registration, manifest)),
    )
    monkeypatch.setattr(runtime, "_claim_liveness", AsyncMock(return_value="nonce"))
    monkeypatch.setattr(runtime, "_claim_workspace", lambda *args: object())
    channel = SimpleNamespace(
        attach_environment=AsyncMock(side_effect=error),
        settle=AsyncMock(),
        aclose=AsyncMock(),
    )
    monkeypatch.setattr(
        "backend.services.chat_executor_runtime._RegistryBackedExecutorChannel",
        lambda *args, **kwargs: channel,
    )
    expected = (
        asyncio.CancelledError
        if isinstance(error, asyncio.CancelledError)
        else SandboxError
    )
    with pytest.raises(expected) as caught:
        asyncio.run(
            runtime._attach_channel(
                object(), SimpleNamespace(turn_id=uuid.uuid4()), 240
            )
        )
    if expected is SandboxError:
        assert caught.value.code == "sandbox_executor_attachment_failed"
        assert caught.value.__cause__ is error
    channel.settle.assert_awaited_once_with("executor_transport_unavailable")
    channel.aclose.assert_awaited_once()
