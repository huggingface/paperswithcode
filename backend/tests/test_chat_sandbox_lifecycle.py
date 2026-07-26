from __future__ import annotations

import asyncio
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.services import chat_sandbox_service
from backend.services.chat_sandbox_service import SandboxSessionManager


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _DB(_Context):
    def __init__(self, rows=None):
        self.rows = rows or []

    def begin(self):
        return _Context()

    def add(self, _value):
        return None

    def execute(self, _query):
        return _Result(list(self.rows))


class _LeaseStore:
    def __init__(self):
        self.lease = None
        self.add_calls = 0
        self.advisory_lock = threading.Lock()
        self.first_missing_read = threading.Event()


class _Transaction(_Context):
    def __init__(self, db):
        self.db = db

    def __exit__(self, error_type, *_args):
        if error_type is None and self.db.pending is not None:
            self.db.store.lease = self.db.pending
        if self.db.holds_advisory_lock:
            self.db.store.advisory_lock.release()
        return False


class _TransactionalDB(_Context):
    def __init__(self, store):
        self.store = store
        self.pending = None
        self.holds_advisory_lock = False

    def begin(self):
        return _Transaction(self)

    def add(self, value):
        self.store.add_calls += 1
        self.pending = value

    def execute(self, _query):
        self.store.advisory_lock.acquire()
        self.holds_advisory_lock = True
        return _Result([])


class _AsyncCall:
    def __init__(self, function):
        self.aio = function


class _Probe:
    returncode = 0

    def __init__(self):
        self.wait = _AsyncCall(self._wait)

    async def _wait(self):
        return None


class _Sandbox:
    def __init__(self, object_id: str):
        self.object_id = object_id
        self.poll = _AsyncCall(self._poll)
        self.exec = _AsyncCall(self._exec)
        self.terminate = _AsyncCall(self._terminate)

    async def _poll(self):
        return None

    async def _exec(self, *_args, **_kwargs):
        return _Probe()

    async def _terminate(self, *, wait):
        assert wait is False


def _lease(*, state: str, sandbox_id: str | None):
    return SimpleNamespace(
        modal_sandbox_id=sandbox_id,
        app_release_id="old-release",
        image_version="im-current",
        worker_contract_version="worker-v1",
        state=state,
        lease_token_hash=None,
        lease_expires_at=None,
        last_activity_at=datetime.now(UTC),
        workspace_snapshot_id=None,
        snapshot_image_version=None,
        snapshot_updated_at=None,
        workspace_dirty=False,
        failure_code=None,
        updated_at=datetime.now(UTC),
    )


def _manager(lease, *, rows=None):
    manager = SandboxSessionManager.__new__(SandboxSessionManager)
    manager.settings = SimpleNamespace(
        release_id="current-release",
        chat_modal_image_version="im-current",
        chat_worker_contract_version="worker-v1",
        chat_workspace_snapshots_enabled=False,
        chat_sandbox_ready_timeout_seconds=2,
    )
    manager.session_factory = lambda: _DB(rows)
    manager.snapshots = SimpleNamespace()
    manager._lease = lambda _db, _session_id, *, lock: lease

    async def enforce_warm_cap():
        return 0

    manager.enforce_warm_cap = enforce_warm_cap
    return manager


def test_concurrent_startup_waits_for_the_existing_owner(monkeypatch):
    async def run():
        lease = _lease(state="terminated", sandbox_id=None)
        manager = _manager(lease)
        created = _Sandbox("sb-created")
        creation_started = asyncio.Event()
        allow_creation = asyncio.Event()
        create_calls = 0

        async def create(*_args, **_kwargs):
            nonlocal create_calls
            create_calls += 1
            creation_started.set()
            await allow_creation.wait()
            return created

        async def from_id(sandbox_id):
            assert sandbox_id == "sb-created"
            return created

        monkeypatch.setattr(chat_sandbox_service, "create_isolated_sandbox", create)
        monkeypatch.setattr(
            chat_sandbox_service.modal.Sandbox,
            "from_id",
            _AsyncCall(from_id),
        )

        session_id = uuid.uuid4()
        owner = asyncio.create_task(manager.ensure_ready(session_id))
        await creation_started.wait()
        waiter = asyncio.create_task(manager.ensure_ready(session_id))
        await asyncio.sleep(0.1)

        assert create_calls == 1
        assert lease.state == "starting"

        allow_creation.set()
        owner_result, waiter_result = await asyncio.gather(owner, waiter)
        assert owner_result[2] is True
        assert waiter_result[2] is False
        assert lease.state == "ready"
        assert lease.modal_sandbox_id == "sb-created"
        assert create_calls == 1

    asyncio.run(run())


def test_concurrent_startup_single_flights_initial_lease_insert(monkeypatch):
    store = _LeaseStore()
    manager = _manager(None)
    manager.session_factory = lambda: _TransactionalDB(store)

    def read_lease(_db, _session_id, *, lock):
        assert lock is True
        lease = store.lease
        if lease is None and not store.first_missing_read.is_set():
            store.first_missing_read.set()
            time.sleep(0.1)
        return lease

    manager._lease = read_lease
    created = _Sandbox("sb-created")
    create_calls = 0
    create_lock = threading.Lock()

    async def create(*_args, **_kwargs):
        nonlocal create_calls
        with create_lock:
            create_calls += 1
        return created

    async def from_id(sandbox_id):
        assert sandbox_id == "sb-created"
        return created

    monkeypatch.setattr(chat_sandbox_service, "create_isolated_sandbox", create)
    monkeypatch.setattr(
        chat_sandbox_service.modal.Sandbox,
        "from_id",
        _AsyncCall(from_id),
    )

    session_id = uuid.uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(asyncio.run, manager.ensure_ready(session_id))
        assert store.first_missing_read.wait(timeout=1)
        waiter = pool.submit(asyncio.run, manager.ensure_ready(session_id))
        owner_result = owner.result(timeout=3)
        waiter_result = waiter.result(timeout=3)

    assert store.add_calls == 1
    assert create_calls == 1
    assert {owner_result[2], waiter_result[2]} == {True, False}
    assert store.lease.state == "ready"
    assert store.lease.modal_sandbox_id == "sb-created"


def test_stale_termination_cannot_clear_a_successor_lease(monkeypatch):
    async def run():
        lease = _lease(state="ready", sandbox_id="sb-old")
        manager = _manager(lease)
        termination_started = asyncio.Event()
        allow_termination = asyncio.Event()

        class BlockingSandbox(_Sandbox):
            async def _terminate(self, *, wait):
                assert wait is False
                termination_started.set()
                await allow_termination.wait()

        async def from_id(sandbox_id):
            assert sandbox_id == "sb-old"
            return BlockingSandbox(sandbox_id)

        monkeypatch.setattr(
            chat_sandbox_service.modal.Sandbox,
            "from_id",
            _AsyncCall(from_id),
        )

        stale_operation = asyncio.create_task(manager.terminate(uuid.uuid4()))
        await termination_started.wait()
        lease.state = "ready"
        lease.modal_sandbox_id = "sb-new"
        lease.lease_token_hash = None
        lease.lease_expires_at = None
        allow_termination.set()
        await stale_operation

        assert lease.state == "ready"
        assert lease.modal_sandbox_id == "sb-new"

    asyncio.run(run())


def test_reconcile_does_not_mark_a_replaced_sandbox_lost(monkeypatch):
    async def run():
        session_id = uuid.uuid4()
        lease = _lease(state="ready", sandbox_id="sb-old")
        rows = [(session_id, "sb-old", "ready", None)]
        manager = _manager(lease, rows=rows)
        poll_started = asyncio.Event()
        allow_poll = asyncio.Event()

        class LostSandbox(_Sandbox):
            async def _poll(self):
                poll_started.set()
                await allow_poll.wait()
                return 1

        async def from_id(sandbox_id):
            assert sandbox_id == "sb-old"
            return LostSandbox(sandbox_id)

        monkeypatch.setattr(
            chat_sandbox_service.modal.Sandbox,
            "from_id",
            _AsyncCall(from_id),
        )

        stale_reconcile = asyncio.create_task(manager.reconcile())
        await poll_started.wait()
        lease.state = "ready"
        lease.modal_sandbox_id = "sb-new"
        allow_poll.set()

        assert await stale_reconcile == 0
        assert lease.state == "ready"
        assert lease.modal_sandbox_id == "sb-new"

    asyncio.run(run())
