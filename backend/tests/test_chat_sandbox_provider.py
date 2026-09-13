from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from modal.exception import NotFoundError
from modal.stream_type import StreamType

from backend.chat_sandbox_worker.contract import (
    CHAT_SANDBOX_REGION,
    CONTROL_PORT,
    MODAL_APP_NAME,
)
from backend.chat_sandbox_worker.executor_daemon import EXECUTOR_SOCKET
from backend.chat_sandbox_worker.executor_protocol import PROTOCOL as EXECUTOR_PROTOCOL
from backend.config import Settings
from backend.services import chat_sandbox_provider, chat_sandbox_service
from backend.services.chat_sandbox_provider import (
    ModalSandboxProviderAdapter,
    ExecutorLaunchBundle,
    SandboxLaunchMode,
    SandboxError,
    sandbox_environment,
)
from backend.services.chat_sandbox_service import SandboxSessionManager


class _AsyncCall:
    def __init__(self, function):
        self.aio = function


def _settings(**overrides) -> Settings:
    values = {
        "environment": "staging",
        "release_id": "release-test",
        "chat_gateway_url": "https://gateway.example.test/api/internal/chat-gateway",
        "chat_modal_image_version": "im-test",
        "chat_workspace_snapshots_enabled": False,
        "chat_sandbox_cpu": 0.125,
        "chat_sandbox_cpu_limit": 1,
        "chat_sandbox_memory_mib": 512,
        "chat_sandbox_memory_limit_mib": 2048,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("tags", "expected_lifetime"),
    (
        ({"service": "pwc-chat"}, 3600),
        (
            {
                "service": "pwc-chat",
                "qualification_profile": "32-functional-turns",
            },
            120,
        ),
    ),
)
def test_create_nonpersistent_sandbox_preserves_provider_isolation_contract(
    monkeypatch, tags, expected_lifetime
):
    captured: dict[str, object] = {}
    app = object()
    image = object()
    sandbox = SimpleNamespace(object_id="sb-created")

    async def lookup(name, *, create_if_missing):
        captured["lookup"] = (name, create_if_missing)
        return app

    async def resolve_image(reference):
        captured["image_reference"] = reference
        return image

    async def create(*command, **options):
        captured["command"] = command
        captured["options"] = options
        return sandbox

    monkeypatch.setattr(
        chat_sandbox_provider.modal.App,
        "lookup",
        _AsyncCall(lookup),
    )
    monkeypatch.setattr(
        chat_sandbox_provider.modal.Sandbox,
        "create",
        _AsyncCall(create),
    )
    settings = _settings(chat_persistent_worker_enabled=False)
    provider = ModalSandboxProviderAdapter(settings, image_resolver=resolve_image)

    result = asyncio.run(
        provider.create(
            name="chat-test",
            tags=tags,
            worker_generation="generation-a",
        )
    )

    assert result is sandbox
    assert captured["lookup"] == (MODAL_APP_NAME, False)
    assert captured["image_reference"] == "im-test"
    assert captured["command"] == ("sleep", "infinity")
    options = captured["options"]
    assert options["app"] is app
    assert options["image"] is image
    assert options["name"] == "chat-test"
    assert options["tags"] == tags
    assert options["timeout"] == expected_lifetime
    if "qualification_profile" in tags:
        assert options["idle_timeout"] == expected_lifetime
    assert options["region"] == CHAT_SANDBOX_REGION
    assert options["cpu"] == (0.125, 1)
    assert options["memory"] == (512, 2048)
    assert options["outbound_domain_allowlist"] == ["gateway.example.test"]
    assert options["env"]["PWC_CHAT_EXCALIDRAW_ENABLED"] == "false"
    assert options["env"]["PWC_CHAT_EGRESS_POLICY_DIGEST"] == (
        "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    )
    assert options["inbound_cidr_allowlist"] == []
    assert options["encrypted_ports"] == []
    assert options["unencrypted_ports"] == []
    assert options["include_oidc_identity_token"] is False
    assert options["env"]["PWC_CHAT_WORKER_GENERATION"] == "generation-a"
    assert options["env"]["PWC_CHAT_SHOW_REASONING"] == "true"


def test_create_executor_sandbox_uses_root_daemon_and_pinned_contract(monkeypatch):
    captured: dict[str, object] = {}

    class Sandbox:
        object_id = "sb-executor"

    async def lookup(*_args, **_options):
        return object()

    async def resolve_image(_reference):
        return object()

    async def create(*command, **options):
        captured["command"] = command
        captured["options"] = options
        return Sandbox()

    monkeypatch.setattr(chat_sandbox_provider.modal.App, "lookup", _AsyncCall(lookup))
    monkeypatch.setattr(
        chat_sandbox_provider.modal.Sandbox,
        "create",
        _AsyncCall(create),
    )
    provider = ModalSandboxProviderAdapter(
        _settings(
            chat_sandbox_executor_enabled=True,
            chat_sandbox_executor_contract_version=EXECUTOR_PROTOCOL,
        ),
        image_resolver=resolve_image,
    )

    result = asyncio.run(
        provider.create(
            name="chat-executor-test",
            tags={
                "service": "pwc-chat",
                "qualification_profile": "32-functional-turns",
            },
            worker_generation="generation-a",
            launch_mode=SandboxLaunchMode.EXECUTOR,
            executor_launch=ExecutorLaunchBundle(
                b"signed-launch", shard_generation=7, authorization_keys_json="{}"
            ),
        )
    )

    assert result.object_id == "sb-executor"
    assert captured["command"] == (
        "/usr/local/bin/pwc-executor-environment",
        "--connect",
        "wss://chat-executor.staging.paperswithcode.co/v1/generations/7/environment",
        "--admission-env",
        "PWC_CHAT_EXECUTOR_ADMISSION",
        "--authorization-env",
        "PWC_CHAT_EXECUTOR_AUTHORIZATION_KEYS",
    )
    options = captured["options"]
    assert options["env"]["PWC_CHAT_EXECUTOR_CONTRACT_VERSION"] == EXECUTOR_PROTOCOL
    assert options["env"]["PWC_CHAT_WORKER_GENERATION"] == "generation-a"
    assert options["env"]["PWC_CHAT_EXECUTOR_ADMISSION"] == "c2lnbmVkLWxhdW5jaA=="
    assert options["env"]["PWC_CHAT_EXECUTOR_AUTHORIZATION_KEYS"] == "{}"
    assert "OPENAI_API_KEY" not in options["env"]
    assert "OPENROUTER_API_KEY" not in options["env"]
    assert "HF_TOKEN" not in options["env"]
    assert options["inbound_cidr_allowlist"] == []
    assert options["outbound_domain_allowlist"] == [
        "gateway.example.test",
        "chat-executor.staging.paperswithcode.co",
    ]


def test_executor_launch_mode_requires_its_independent_kill_switch():
    provider = ModalSandboxProviderAdapter(
        _settings(chat_sandbox_executor_enabled=False)
    )

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(
            provider.create(
                name="chat-executor-test",
                tags={"service": "pwc-chat"},
                launch_mode=SandboxLaunchMode.EXECUTOR,
            )
        )

    assert exc_info.value.code == "sandbox_executor_disabled"


def test_executor_launch_mode_requires_the_pinned_wire_contract():
    provider = ModalSandboxProviderAdapter(
        _settings(
            chat_sandbox_executor_enabled=True,
            chat_sandbox_executor_contract_version="sandbox-executor-v0",
        )
    )

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(
            provider.create(
                name="chat-executor-test",
                tags={"service": "pwc-chat"},
                launch_mode=SandboxLaunchMode.EXECUTOR,
            )
        )

    assert exc_info.value.code == "sandbox_executor_contract_invalid"


def test_enabled_excalidraw_passes_reviewed_hostname_to_modal(monkeypatch):
    captured: dict[str, object] = {}

    async def lookup(name, *, create_if_missing):
        return object()

    async def resolve_image(_reference):
        return object()

    async def create(*_command, **options):
        captured["options"] = options
        return SimpleNamespace(object_id="sb-created")

    monkeypatch.setattr(chat_sandbox_provider.modal.App, "lookup", _AsyncCall(lookup))
    monkeypatch.setattr(
        chat_sandbox_provider.modal.Sandbox,
        "create",
        _AsyncCall(create),
    )
    settings = _settings(
        chat_persistent_worker_enabled=False,
        chat_excalidraw_enabled=True,
        chat_mcp_apps_host_enabled=True,
    )
    provider = ModalSandboxProviderAdapter(settings, image_resolver=resolve_image)
    asyncio.run(provider.create(name="chat-test", tags={"service": "pwc-chat"}))

    options = captured["options"]
    assert options["outbound_domain_allowlist"] == [
        "gateway.example.test",
        "mcp.excalidraw.com",
    ]
    assert options["env"]["PWC_CHAT_EXCALIDRAW_ENABLED"] == "true"
    assert "OPENROUTER_API_KEY" not in options["env"]
    assert "HF_TOKEN" not in options["env"]
    digest = options["env"]["PWC_CHAT_EGRESS_POLICY_DIGEST"]
    assert digest != "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    assert len(digest) == 64


def test_pi_prewarm_environment_is_pool_only_and_contains_no_credential():
    settings = _settings(
        chat_pi_prewarm_enabled=True,
        chat_pi_prewarm_model="deepseek/profile",
        chat_pi_prewarm_reasoning_effort="low",
    )

    direct = sandbox_environment(settings)
    blank = sandbox_environment(settings, pi_prewarm=True)

    assert direct["PWC_CHAT_PI_PREWARM_ENABLED"] == "false"
    assert blank["PWC_CHAT_PI_PREWARM_ENABLED"] == "true"
    assert blank["PWC_CHAT_PI_PREWARM_MODEL"] == "deepseek/profile"
    assert (
        not {
            "OPENROUTER_API_KEY",
            "HF_TOKEN",
            "PWC_CHAT_CAPABILITY",
        }
        & blank.keys()
    )


def test_create_persistent_sandbox_waits_for_successful_worker_health(monkeypatch):
    probes: list[tuple[tuple[object, ...], dict[str, object]]] = []
    launches: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class Sandbox:
        object_id = "sb-persistent"

        def __init__(self):
            self.exec = _AsyncCall(self._exec)
            self.poll = _AsyncCall(self._poll)

        async def _exec(self, *command, **options):
            probes.append((command, options))

            async def wait():
                return None

            return SimpleNamespace(
                returncode=0,
                wait=_AsyncCall(wait),
            )

        async def _poll(self):
            raise AssertionError("a successful readiness probe must not poll")

    sandbox = Sandbox()

    async def lookup(*_args, **_options):
        return object()

    async def resolve_image(_reference):
        return object()

    async def create(*command, **options):
        launches.append((command, options))
        return sandbox

    monkeypatch.setattr(
        chat_sandbox_provider.modal.App,
        "lookup",
        _AsyncCall(lookup),
    )
    monkeypatch.setattr(
        chat_sandbox_provider.modal.Sandbox,
        "create",
        _AsyncCall(create),
    )
    provider = ModalSandboxProviderAdapter(
        _settings(chat_persistent_worker_enabled=True),
        image_resolver=resolve_image,
    )

    result = asyncio.run(
        provider.create(
            name="chat-test",
            tags={},
            worker_generation="generation-a",
        )
    )

    assert result is sandbox
    assert launches[0][0] == (
        "python",
        "-m",
        "backend.chat_sandbox_worker.control_daemon",
    )
    assert "PWC_CHAT_EXECUTOR_CONTRACT_VERSION" not in launches[0][1]["env"]
    assert probes == [
        (
            (
                "python",
                "-m",
                "backend.chat_sandbox_worker.relay",
                "--ping",
                "generation-a",
            ),
            {"timeout": 5},
        )
    ]


def test_create_persistent_readiness_timeout_terminates_created_sandbox(
    monkeypatch,
):
    termination_wait: list[bool] = []

    class Sandbox:
        object_id = "sb-not-ready"

        def __init__(self):
            self.exec = _AsyncCall(self._exec)
            self.poll = _AsyncCall(self._poll)
            self.terminate = _AsyncCall(self._terminate)

        async def _exec(self, *_command, **_options):
            async def wait():
                return None

            return SimpleNamespace(returncode=1, wait=_AsyncCall(wait))

        async def _poll(self):
            return None

        async def _terminate(self, *, wait):
            termination_wait.append(wait)

    async def lookup(*_args, **_options):
        return object()

    async def resolve_image(_reference):
        return object()

    async def create(*_command, **_options):
        return Sandbox()

    monkeypatch.setattr(
        chat_sandbox_provider.modal.App,
        "lookup",
        _AsyncCall(lookup),
    )
    monkeypatch.setattr(
        chat_sandbox_provider.modal.Sandbox,
        "create",
        _AsyncCall(create),
    )
    provider = ModalSandboxProviderAdapter(
        _settings(
            chat_persistent_worker_enabled=True,
            chat_worker_ready_timeout_seconds=0.001,
            chat_sandbox_spend_enforcement_enabled=True,
        ),
        image_resolver=resolve_image,
    )

    with pytest.raises(SandboxError) as exc_info:
        asyncio.run(provider.create(name="chat-test", tags={}))

    assert exc_info.value.code == "sandbox_worker_not_ready"
    assert str(exc_info.value) == "Persistent worker readiness timed out"
    assert termination_wait == [True]


@pytest.mark.parametrize(
    ("spend_enforcement", "expected_wait"),
    [(False, False), (True, True)],
)
def test_terminate_uses_configured_confirmation_mode(spend_enforcement, expected_wait):
    waits: list[bool] = []

    async def terminate(*, wait):
        waits.append(wait)

    sandbox = SimpleNamespace(terminate=_AsyncCall(terminate))
    provider = ModalSandboxProviderAdapter(
        _settings(chat_sandbox_spend_enforcement_enabled=spend_enforcement)
    )

    assert asyncio.run(provider.terminate("sb-test", sandbox)) is True
    assert waits == [expected_wait]


def test_terminate_returns_false_when_resolution_or_provider_confirmation_fails(
    monkeypatch,
):
    async def missing(_sandbox_id):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        chat_sandbox_provider.modal.Sandbox,
        "from_id",
        _AsyncCall(missing),
    )
    provider = ModalSandboxProviderAdapter(_settings())

    assert asyncio.run(provider.terminate("sb-missing")) is False

    async def fail_termination(*, wait):
        assert wait is False
        raise RuntimeError("termination failed")

    sandbox = SimpleNamespace(terminate=_AsyncCall(fail_termination))
    assert asyncio.run(provider.terminate("sb-test", sandbox)) is False


def test_terminate_treats_provider_not_found_as_confirmed_absence(monkeypatch):
    async def missing(_sandbox_id):
        raise NotFoundError("sandbox no longer exists")

    monkeypatch.setattr(
        chat_sandbox_provider.modal.Sandbox,
        "from_id",
        _AsyncCall(missing),
    )
    provider = ModalSandboxProviderAdapter(_settings())

    assert asyncio.run(provider.terminate("sb-missing")) is True


def test_resolve_and_poll_delegate_to_provider(monkeypatch):
    calls: list[str] = []

    async def poll():
        calls.append("poll")
        return 17

    sandbox = SimpleNamespace(poll=_AsyncCall(poll))

    async def resolve(sandbox_id):
        calls.append(f"resolve:{sandbox_id}")
        return sandbox

    monkeypatch.setattr(
        chat_sandbox_provider.modal.Sandbox,
        "from_id",
        _AsyncCall(resolve),
    )
    provider = ModalSandboxProviderAdapter(_settings())

    assert asyncio.run(provider.resolve("sb-test")) is sandbox
    assert asyncio.run(provider.poll(sandbox)) == 17
    assert calls == ["resolve:sb-test", "poll"]


@pytest.mark.parametrize(
    ("persistent", "worker_generation", "expected_command"),
    [
        (False, None, ("test", "-x", "/usr/local/bin/pwc")),
        (
            True,
            "generation-a",
            (
                "python",
                "-m",
                "backend.chat_sandbox_worker.relay",
                "--ping",
                "generation-a",
            ),
        ),
    ],
)
def test_health_checks_running_sandbox_and_expected_worker_probe(
    persistent, worker_generation, expected_command
):
    calls: list[tuple[object, ...] | str] = []

    async def execute(*command, **options):
        calls.append(command)
        assert options == {"timeout": 5}

        async def wait():
            calls.append("wait")

        return SimpleNamespace(returncode=0, wait=_AsyncCall(wait))

    sandbox = SimpleNamespace(exec=_AsyncCall(execute))
    provider = ModalSandboxProviderAdapter(_settings())

    assert (
        asyncio.run(
            provider.health(
                sandbox,
                persistent=persistent,
                worker_generation=worker_generation,
            )
        )
        is True
    )
    assert calls == [expected_command, "wait"]


def test_health_uses_executor_socket_probe_for_executor_sandbox():
    calls: list[tuple[object, ...] | str] = []

    async def execute(*command, **options):
        calls.append(command)
        assert options == {"timeout": 5}

        async def wait():
            calls.append("wait")

        return SimpleNamespace(returncode=0, wait=_AsyncCall(wait))

    sandbox = SimpleNamespace(exec=_AsyncCall(execute))
    provider = ModalSandboxProviderAdapter(_settings())

    assert asyncio.run(
        provider.health(
            sandbox,
            persistent=True,
            worker_generation="generation-a",
            launch_mode=SandboxLaunchMode.EXECUTOR,
        )
    )
    assert calls == [("test", "-S", str(EXECUTOR_SOCKET)), "wait"]


def test_health_reports_failed_worker_probe():
    async def execute(*_command, **_options):
        async def wait():
            return None

        return SimpleNamespace(returncode=1, wait=_AsyncCall(wait))

    sandbox = SimpleNamespace(exec=_AsyncCall(execute))
    provider = ModalSandboxProviderAdapter(_settings())
    assert (
        asyncio.run(
            provider.health(
                sandbox,
                persistent=False,
                worker_generation=None,
            )
        )
        is False
    )


def test_health_leaves_provider_failures_for_the_orchestrator_to_classify():
    async def execute(*_command, **_options):
        raise RuntimeError("provider unavailable")

    sandbox = SimpleNamespace(exec=_AsyncCall(execute))
    provider = ModalSandboxProviderAdapter(_settings())

    with pytest.raises(RuntimeError, match="provider unavailable"):
        asyncio.run(
            provider.health(
                sandbox,
                persistent=False,
                worker_generation=None,
            )
        )


def test_open_persistent_connection_uses_authenticated_hardened_websocket():
    calls: dict[str, object] = {}
    connection = object()

    async def create_connect_token(*, user_metadata, port):
        calls["token"] = (user_metadata, port)
        return SimpleNamespace(
            url="https://connect.modal.test/control",
            token="secret-token",
        )

    async def connect(url, **options):
        calls["connect"] = (url, options)
        return connection

    sandbox = SimpleNamespace(
        create_connect_token=_AsyncCall(create_connect_token),
    )
    provider = ModalSandboxProviderAdapter(_settings(), websocket_connector=connect)

    assert (
        asyncio.run(provider.open_persistent_connection(sandbox, "generation-a"))
        is connection
    )
    assert calls["token"] == ({"worker_generation": "generation-a"}, CONTROL_PORT)
    url, options = calls["connect"]
    assert url == "wss://connect.modal.test/control"
    assert options == {
        "additional_headers": {"Authorization": "Bearer secret-token"},
        "compression": None,
        "proxy": None,
        "open_timeout": 5,
        "ping_interval": 20,
        "ping_timeout": 20,
        "max_size": 1024 * 1024,
    }


def test_open_turn_process_preserves_supervisor_execution_options():
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    process = object()

    async def execute(*command, **options):
        calls.append((command, options))
        return process

    sandbox = SimpleNamespace(exec=_AsyncCall(execute))
    provider = ModalSandboxProviderAdapter(_settings())

    assert (
        asyncio.run(provider.open_turn_process(sandbox, timeout_seconds=42)) is process
    )
    assert calls == [
        (
            (
                "python",
                "-m",
                "backend.chat_sandbox_worker.supervisor",
            ),
            {
                "stdout": StreamType.PIPE,
                "stderr": StreamType.PIPE,
                "timeout": 42,
                "workdir": "/workspace",
                "text": False,
            },
        )
    ]


def test_open_executor_relay_uses_bounded_binary_process():
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    process = object()

    async def execute(*command, **options):
        calls.append((command, options))
        return process

    sandbox = SimpleNamespace(exec=_AsyncCall(execute))
    provider = ModalSandboxProviderAdapter(_settings())

    assert (
        asyncio.run(provider.open_executor_relay(sandbox, timeout_seconds=31))
        is process
    )
    assert calls == [
        (
            (
                "python",
                "-m",
                "backend.chat_sandbox_worker.executor_relay",
            ),
            {
                "stdout": StreamType.PIPE,
                "stderr": StreamType.DEVNULL,
                "timeout": 31,
                "workdir": "/workspace",
                "env": {"PYTHONPATH": "/opt/pwc"},
                "text": False,
            },
        )
    ]


def test_list_and_get_tags_are_provider_passthroughs(monkeypatch):
    listed_sandbox = object()
    tagged_sandbox = SimpleNamespace()
    calls: list[object] = []

    async def listed(*, tags):
        calls.append(("list", tags))
        yield listed_sandbox

    async def get_tags():
        calls.append("tags")
        return {"pool": "blank", "release": "release-test"}

    tagged_sandbox.get_tags = _AsyncCall(get_tags)
    monkeypatch.setattr(
        chat_sandbox_provider.modal.Sandbox,
        "list",
        _AsyncCall(listed),
    )
    provider = ModalSandboxProviderAdapter(_settings())

    async def exercise():
        sandboxes = [
            sandbox
            async for sandbox in provider.iter_sandboxes(
                tags={"service": "pwc-chat", "pool": "blank"}
            )
        ]
        tags = await provider.get_tags(tagged_sandbox)
        return sandboxes, tags

    sandboxes, tags = asyncio.run(exercise())
    assert sandboxes == [listed_sandbox]
    assert tags == {"pool": "blank", "release": "release-test"}
    assert calls == [
        ("list", {"service": "pwc-chat", "pool": "blank"}),
        "tags",
    ]


def test_manager_injected_provider_and_public_create_shim_remain_late_bound(
    monkeypatch,
):
    created = object()
    calls: list[tuple[object, ...]] = []

    class Provider:
        async def terminate(self, sandbox_id, sandbox=None):
            calls.append(("terminate", sandbox_id, sandbox))
            return True

    manager = SandboxSessionManager(
        _settings(),
        sandbox_provider=Provider(),
    )
    injected = manager._provider_adapter()
    assert manager._worker_transport().provider is injected
    supplied_sandbox = object()
    assert asyncio.run(injected.terminate("sb-test", supplied_sandbox)) is True
    assert calls == [("terminate", "sb-test", supplied_sandbox)]

    class Adapter:
        def __init__(self, settings, **_options):
            self.settings = settings

        async def create(self, *, name, tags, worker_generation=None):
            calls.append(("create", self.settings, name, tags, worker_generation))
            return created

    monkeypatch.setattr(chat_sandbox_service, "ModalSandboxProviderAdapter", Adapter)
    settings = _settings()
    result = asyncio.run(
        chat_sandbox_service.create_isolated_sandbox(
            settings,
            name="chat-test",
            tags={"service": "pwc-chat"},
            worker_generation="generation-a",
        )
    )

    assert result is created
    assert calls[1] == (
        "create",
        settings,
        "chat-test",
        {"service": "pwc-chat"},
        "generation-a",
    )
