"""Turn-runner tests never persist durable turn state."""

import pytest

from backend.services.chat_external_pi_turn_runner import (
    ExternalPiChatTurnRunner,
)


@pytest.fixture(autouse=True)
def _isolate_durable_turn_state(monkeypatch):
    async def ignore(_runner, _state):
        return None

    monkeypatch.setattr(ExternalPiChatTurnRunner, "_persist_turn_state", ignore)
