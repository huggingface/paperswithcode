"""Metadata reuse must not reuse work or leak across provider contexts."""

import asyncio
from types import SimpleNamespace

import pytest

from backend.services import chat_modal_metadata as metadata


@pytest.fixture
def fake_sdk(monkeypatch):
    metadata._entry.cache_clear()
    state = SimpleNamespace(
        client=object(), lookups=[], builds=[], fail=False, gate=None
    )

    async def client():
        return state.client

    async def lookup(name, **kwargs):
        state.lookups.append(kwargs)
        return object()

    def image(image_id, **kwargs):
        async def build(app):
            state.builds.append((image_id, kwargs))
            if state.gate is not None:
                await state.gate.wait()
            if state.fail:
                raise RuntimeError("lookup failed")

        return SimpleNamespace(build=SimpleNamespace(aio=build))

    monkeypatch.setattr(metadata.Client, "from_env", SimpleNamespace(aio=client))
    monkeypatch.setattr(metadata.modal.App, "lookup", SimpleNamespace(aio=lookup))
    monkeypatch.setattr(metadata.modal.Image, "from_id", image)
    yield state
    metadata._entry.cache_clear()


def test_concurrent_callers_share_only_metadata(fake_sdk):
    async def run():
        results = await asyncio.gather(
            *(metadata.executor_metadata("staging", "im-one") for _ in range(32))
        )
        assert all(result is results[0] for result in results)
        assert len(fake_sdk.lookups) == len(fake_sdk.builds) == 1
        assert fake_sdk.lookups[0]["create_if_missing"] is False

    asyncio.run(run())


def test_environment_image_client_and_loop_are_isolated(fake_sdk):
    async def run():
        await metadata.executor_metadata("staging", "im-one")
        await metadata.executor_metadata("production", "im-one")
        await metadata.executor_metadata("staging", "im-two")
        fake_sdk.client = object()
        await metadata.executor_metadata("staging", "im-one")

    asyncio.run(run())
    asyncio.run(metadata.executor_metadata("staging", "im-one"))
    assert len(fake_sdk.lookups) == 5


def test_failure_is_not_cached(fake_sdk):
    async def run():
        fake_sdk.fail = True
        with pytest.raises(RuntimeError, match="lookup failed"):
            await metadata.executor_metadata("staging", "im-one")
        fake_sdk.fail = False
        await metadata.executor_metadata("staging", "im-one")
        assert len(fake_sdk.builds) == 2

    asyncio.run(run())


def test_cancelled_resolution_releases_waiter(fake_sdk):
    async def run():
        fake_sdk.gate = asyncio.Event()
        first = asyncio.create_task(metadata.executor_metadata("staging", "im-one"))
        await asyncio.sleep(0)
        second = asyncio.create_task(metadata.executor_metadata("staging", "im-one"))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        fake_sdk.gate.set()
        await asyncio.wait_for(second, 1)
        assert len(fake_sdk.builds) == 2

    asyncio.run(run())


def test_cache_is_bounded_and_pid_scoped(fake_sdk, monkeypatch):
    async def run():
        monkeypatch.setattr(metadata.os, "getpid", lambda: 1)
        await metadata.executor_metadata("staging", "im-one")
        monkeypatch.setattr(metadata.os, "getpid", lambda: 2)
        await metadata.executor_metadata("staging", "im-one")
        assert len(fake_sdk.lookups) == 2
        for i in range(20):
            await metadata.executor_metadata("staging", f"im-{i}")
        assert metadata._entry.cache_info().currsize == 8

    asyncio.run(run())


@pytest.mark.parametrize(
    ("environment", "image"), [("", "im-one"), ("staging", "named")]
)
def test_rejects_mutable_or_unscoped_metadata(fake_sdk, environment, image):
    with pytest.raises(ValueError):
        asyncio.run(metadata.executor_metadata(environment, image))
    assert not fake_sdk.lookups
