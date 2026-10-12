from __future__ import annotations

import pytest

from backend.config import Settings
from backend.services.chat_sandbox_spend_access import (
    assert_chat_sandbox_spend_available,
    chat_sandbox_spend_available,
    chat_sandbox_spend_status,
)
from backend.services.chat_sandbox_spend_service import ChatComputeDisabled


class _Session:
    def __init__(self, events: list[object]):
        self.events = events

    def __enter__(self):
        self.events.append("enter")
        return self

    def __exit__(self, exc_type, _exc, _traceback):
        self.events.append(("exit", exc_type))

    def begin(self):
        self.events.append("begin")
        return self

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")


def _settings() -> Settings:
    return Settings(_env_file=None, chat_workspace_snapshots_enabled=False)


def test_spend_access_commits_successful_admission_once():
    events: list[object] = []

    class Spend:
        @staticmethod
        def assert_available():
            events.append("available")

    assert_chat_sandbox_spend_available(
        _settings(),
        session_factory=lambda: _Session(events),
        spend_factory=lambda _db: Spend(),
    )

    assert events == ["enter", "available", "commit", ("exit", None)]


def test_spend_access_commits_circuit_trip_before_reraising_rejection():
    events: list[object] = []
    rejection = ChatComputeDisabled("Chat is paused")

    class Spend:
        @staticmethod
        def assert_available():
            events.append("trip")
            raise rejection

    with pytest.raises(ChatComputeDisabled) as raised:
        assert_chat_sandbox_spend_available(
            _settings(),
            session_factory=lambda: _Session(events),
            spend_factory=lambda _db: Spend(),
        )

    assert raised.value is rejection
    assert events == [
        "enter",
        "trip",
        "commit",
        ("exit", ChatComputeDisabled),
    ]


def test_spend_access_does_not_commit_unexpected_failure():
    events: list[object] = []

    class Spend:
        @staticmethod
        def assert_available():
            events.append("failure")
            raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        assert_chat_sandbox_spend_available(
            _settings(),
            session_factory=lambda: _Session(events),
            spend_factory=lambda _db: Spend(),
        )

    assert events == ["enter", "failure", ("exit", RuntimeError)]


def test_spend_status_refreshes_inside_one_transaction():
    events: list[object] = []
    payload = {"circuit_state": "armed"}

    class Spend:
        @staticmethod
        def status():
            events.append("status")
            return payload

    result = chat_sandbox_spend_status(
        _settings(),
        session_factory=lambda: _Session(events),
        spend_factory=lambda _db: Spend(),
    )

    assert result is payload
    assert events == [
        "enter",
        "begin",
        "enter",
        "status",
        ("exit", None),
        ("exit", None),
    ]


def test_spend_available_refreshes_and_commits_when_the_lock_is_free():
    events: list[object] = []

    class Spend:
        @staticmethod
        def assert_available(*, capacity_locked):
            events.append(("available", capacity_locked))

        @staticmethod
        def circuit_tripped_snapshot():
            raise AssertionError("snapshot must not be read when the lock is held")

    def locker(_db, *, wait):
        events.append(("lock", wait))
        return True

    assert (
        chat_sandbox_spend_available(
            _settings(),
            session_factory=lambda: _Session(events),
            spend_factory=lambda _db: Spend(),
            capacity_locker=locker,
        )
        is True
    )

    assert events == [
        "enter",
        ("lock", False),
        ("available", True),
        "commit",
        ("exit", None),
    ]


def test_spend_available_commits_a_trip_taken_under_the_lock():
    events: list[object] = []

    class Spend:
        @staticmethod
        def assert_available(*, capacity_locked):
            events.append("trip")
            raise ChatComputeDisabled("Chat is paused")

    assert (
        chat_sandbox_spend_available(
            _settings(),
            session_factory=lambda: _Session(events),
            spend_factory=lambda _db: Spend(),
            capacity_locker=lambda _db, *, wait: True,
        )
        is False
    )

    assert events == ["enter", "trip", "commit", ("exit", None)]


@pytest.mark.parametrize("tripped", [False, True])
def test_spend_available_reads_the_persisted_circuit_when_the_lock_is_busy(tripped):
    events: list[object] = []

    class Spend:
        @staticmethod
        def assert_available(**_kwargs):
            raise AssertionError("must not wait for the capacity lock")

        @staticmethod
        def circuit_tripped_snapshot():
            events.append("snapshot")
            return tripped

    assert chat_sandbox_spend_available(
        _settings(),
        session_factory=lambda: _Session(events),
        spend_factory=lambda _db: Spend(),
        capacity_locker=lambda _db, *, wait: False,
    ) is (not tripped)

    assert events == ["enter", "snapshot", "rollback", ("exit", None)]
