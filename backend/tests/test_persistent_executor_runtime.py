from __future__ import annotations

import threading
import time
from pathlib import Path

from backend.loadtests.persistent_executor_runtime import TurnExecutionRuntime


class Broker:
    def __init__(self, *, clear_succeeds: bool = True) -> None:
        self.requests: list[tuple[str, str]] = []
        self.active = False
        self.clear_succeeds = clear_succeeds
        self.lock = threading.Lock()

    def __call__(self, operation: str, capability: str) -> bool:
        with self.lock:
            self.requests.append((operation, capability))
            if operation == "install":
                assert not self.active
                self.active = True
                return True
            assert operation == "clear"
            if not self.clear_succeeds:
                return False
            assert self.active
            self.active = False
            return True


def _runtime(
    broker: Broker, *, terminator=lambda: True, deadline_seconds: float = 10
) -> TurnExecutionRuntime:
    runtime = TurnExecutionRuntime(broker=broker, sandbox_terminator=terminator)
    runtime.authorize(
        "turn-capability", absolute_deadline_unix=time.time() + deadline_seconds
    )
    return runtime


def test_four_real_processes_overlap_with_one_turn_capability(tmp_path: Path) -> None:
    broker = Broker()
    runtime = _runtime(broker)
    release = tmp_path / "release"
    results = []

    def execute(index: int) -> None:
        marker = tmp_path / f"ready-{index}"
        results.append(
            runtime.execute(
                f"operation-{index}",
                f"touch {marker}; while [ ! -f {release} ]; do sleep 0.01; done",
            )
        )

    threads = [threading.Thread(target=execute, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 2
    while len(tuple(tmp_path.glob("ready-*"))) != 4:
        assert time.monotonic() < deadline
        time.sleep(0.005)
    release.touch()
    for thread in threads:
        thread.join(timeout=2)
    runtime.close()

    assert all(not thread.is_alive() for thread in threads)
    assert [item.status for item in results] == ["completed"] * 4
    assert broker.requests == [
        ("install", "turn-capability"),
        ("clear", "turn-capability"),
    ]


def test_ten_sequential_operations_keep_capability_until_turn_close() -> None:
    broker = Broker()
    runtime = _runtime(broker)

    results = [runtime.execute(f"operation-{index}", "true") for index in range(10)]
    assert broker.active
    assert broker.requests == [("install", "turn-capability")]

    runtime.close()
    assert all(item.status == "completed" for item in results)
    assert broker.requests[-1] == ("clear", "turn-capability")


def test_sibling_failure_does_not_revoke_shared_capability() -> None:
    broker = Broker()
    runtime = _runtime(broker)

    failed = runtime.execute("failed", "exit 7")
    succeeded = runtime.execute("succeeded", "true")

    assert failed.status == "failed"
    assert succeeded.status == "completed"
    assert broker.active
    runtime.close()


def test_fifth_operation_waits_without_blocking_turn_cancellation(
    tmp_path: Path,
) -> None:
    broker = Broker()
    runtime = _runtime(broker)
    release = tmp_path / "never-release"
    results = []

    def execute(index: int) -> None:
        results.append(
            runtime.execute(
                f"operation-{index}",
                f"while [ ! -f {release} ]; do sleep 0.01; done",
            )
        )

    threads = [threading.Thread(target=execute, args=(index,)) for index in range(5)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 2
    while sum(thread.is_alive() for thread in threads) != 5:
        assert time.monotonic() < deadline
    evidence = runtime.cancel(transport_connected=True, remote_acknowledged=True)
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 5
    assert all(item.status == "cancelled" for item in results)
    assert evidence.capability_revoked_at is not None
    assert broker.requests.count(("clear", "turn-capability")) == 1


def test_disconnected_cancel_confirms_control_plane_termination() -> None:
    broker = Broker()
    termination_calls = 0

    def terminate() -> bool:
        nonlocal termination_calls
        termination_calls += 1
        return True

    runtime = _runtime(broker, terminator=terminate)
    thread = threading.Thread(
        target=lambda: runtime.execute("operation", "trap '' TERM; sleep 10")
    )
    thread.start()
    time.sleep(0.05)

    evidence = runtime.cancel(transport_connected=False, remote_acknowledged=False)
    thread.join(timeout=2)

    assert termination_calls == 1
    assert evidence.sandbox_termination_requested_at is not None
    assert evidence.sandbox_termination_confirmed_at is not None
    assert not evidence.reservation_retained
    assert not evidence.unknown_outcome


def test_unconfirmed_disconnected_cancel_retains_reservation() -> None:
    broker = Broker(clear_succeeds=False)
    runtime = _runtime(broker, terminator=lambda: False)

    evidence = runtime.cancel(transport_connected=False, remote_acknowledged=False)

    assert evidence.capability_revoked_at is None
    assert evidence.sandbox_termination_confirmed_at is None
    assert evidence.reservation_retained
    assert evidence.unknown_outcome


def test_failed_capability_revocation_retains_reservation_when_connected() -> None:
    broker = Broker(clear_succeeds=False)
    runtime = _runtime(broker)

    evidence = runtime.cancel(transport_connected=True, remote_acknowledged=True)

    assert evidence.capability_revoked_at is None
    assert evidence.reservation_retained
    assert evidence.unknown_outcome


def test_executor_local_deadline_watchdog_cancels_without_transport() -> None:
    broker = Broker()
    terminated = threading.Event()
    runtime = _runtime(
        broker,
        terminator=lambda: terminated.set() is None,
        deadline_seconds=0.1,
    )
    result = runtime.execute("operation", "trap '' TERM; sleep 10")

    assert result.status == "cancelled"
    assert result.cancellation_observed_at is not None
    assert result.process_contained_at is not None
    assert terminated.wait(timeout=1)
    runtime.close()
    assert broker.requests[-1] == ("clear", "turn-capability")


def test_saturated_output_is_drained_after_capture_limit() -> None:
    broker = Broker()
    runtime = _runtime(broker)

    result = runtime.execute(
        "saturated-output",
        "head -c 262144 /dev/zero | tr '\\0' x",
    )
    runtime.close()

    assert result.status == "completed"
    assert len(result.output) == 64 * 1024


def test_fixture_subprocess_does_not_inherit_parent_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-enter-operation")
    broker = Broker()
    runtime = _runtime(broker)

    result = runtime.execute(
        "environment",
        'test -z "${OPENAI_API_KEY:-}" && printf safe',
    )
    runtime.close()

    assert result.status == "completed"
    assert result.output == b"safe"
