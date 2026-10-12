"""Sandbox image publication, control websocket, and persistent sandbox launch."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.chat_sandbox_worker import (
    control_websocket,
    publish_image,
)
from backend.chat_sandbox_worker.contract import (
    IMAGE_PUBLISH_NAME,
    MODAL_APP_NAME,
)
from backend.config import Settings
from backend.services.chat_sandbox_service import (
    SandboxSessionManager,
    create_isolated_sandbox,
    resolve_modal_image,
)


def test_image_makes_copied_worker_readable_and_installs_skill():
    source = (
        Path(__file__).resolve().parents[2] / "chat_sandbox_worker" / "image.py"
    ).read_text()

    assert 'WORKER / "PWC_CLI_SKILL.md", "/opt/pwc/PWC_CLI_SKILL.md"' in source
    assert 'WORKER / "S2_CLI_SKILL.md", "/opt/pwc/S2_CLI_SKILL.md"' in source
    assert (
        'BACKEND / "chat_execution_policy.py",\n'
        '        "/opt/pwc/backend/chat_execution_policy.py"'
    ) in source
    assert '"chmod -R a+rX /opt/pwc/backend"' in source
    assert '"chmod -R a+rX /opt/pwc/restricted_hf_cli"' in source
    assert '"chmod 0644 /opt/pwc/PWC_CLI_SKILL.md"' in source
    assert "PWC_CLI_SOURCE_COMMIT" in source
    assert "https://github.com/huggingface/pwc-cli.git" in source
    assert "cli-source rev-parse HEAD" in source
    assert (
        '"python -m pip install --no-deps /opt/pwc/cli-source/standalone_cli"' in source
    )
    assert "runuser -u pwc-chat -- pwc version" in source
    assert source.index('"mkdir -p /opt/pwc"') < source.index(
        "https://github.com/huggingface/pwc-cli.git"
    )
    assert '"runuser -u pwc-chat -- hf --help >/dev/null"' in source
    assert '"python -m pip install --no-deps /opt/pwc/s2_cli"' in source
    assert "runuser -u pwc-chat -- hf version" in source
    assert (
        "\"PYTHONPATH=/opt/pwc python -c 'import backend.chat_execution_policy'\""
    ) in source
    assert '"chown pwc-broker:pwc-broker /var/empty/pwc-broker"' in source
    assert '"websockets==16.0"' in source
    assert "import backend.chat_sandbox_worker.executor_daemon" in source
    assert "import backend.chat_sandbox_worker.executor_relay" in source
    assert (
        "from backend.chat_sandbox_worker.executor_command import "
        "DEFAULT_EXECUTOR_PIDS_MAX, EXECUTOR_USER"
    ) in source
    assert "EXECUTOR_USER == 'pwc-chat'" in source
    assert "DEFAULT_EXECUTOR_PIDS_MAX == 64" in source


def test_control_websocket_requires_verified_worker_generation(monkeypatch):
    monkeypatch.setenv("PWC_CHAT_WORKER_GENERATION", "generation-a")

    def connection(metadata):
        return SimpleNamespace(
            request=SimpleNamespace(
                headers={
                    control_websocket.VERIFIED_METADATA_HEADER: json.dumps(metadata)
                }
            )
        )

    control_websocket._verify_generation(
        connection({"worker_generation": "generation-a"})
    )
    with pytest.raises(PermissionError, match="generation mismatch"):
        control_websocket._verify_generation(
            connection({"worker_generation": "generation-b"})
        )
    with pytest.raises(PermissionError, match="Missing verified"):
        control_websocket._verify_generation(
            SimpleNamespace(request=SimpleNamespace(headers={}))
        )


def test_persistent_control_uses_authenticated_connect_token(monkeypatch):
    calls: dict = {}

    class Connection:
        def __init__(self):
            self.sent = []
            self.closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def send(self, payload):
            self.sent.append(payload)

        async def close(self):
            self.closed = True

    connection = Connection()

    async def create_connect_token(*, user_metadata, port):
        calls["token"] = (user_metadata, port)
        return SimpleNamespace(
            url="https://connect.modal.test/control",
            token="secret-token",
        )

    async def connect(url, **options):
        calls["connect"] = (url, options)
        return connection

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.websocket_connect", connect
    )
    manager = SandboxSessionManager(
        Settings(_env_file=None, chat_workspace_snapshots_enabled=False)
    )
    sandbox = SimpleNamespace(
        object_id="sb-test",
        create_connect_token=SimpleNamespace(aio=create_connect_token),
    )

    async def exercise():
        control = await manager._worker_transport().open_persistent_control(
            sandbox,
            "generation-a",
        )
        control.process.stdin.write(b"first")
        control.process.stdin.write(b"-second")
        await control.process.stdin.drain.aio()
        await control.process.aclose()
        if control.reader_task is not None:
            await control.reader_task
        return control

    control = asyncio.run(exercise())

    assert calls["token"] == ({"worker_generation": "generation-a"}, 8080)
    url, options = calls["connect"]
    assert url == "wss://connect.modal.test/control"
    assert options["additional_headers"] == {"Authorization": "Bearer secret-token"}
    assert options["compression"] is None
    assert options["proxy"] is None
    assert connection.sent == [b"first-second"]
    assert connection.closed is True
    assert control.stderr_task is None


def test_image_publication_initializes_modal_app(monkeypatch, capsys, tmp_path):
    events: list[str] = []

    class Lookup:
        def __call__(self, name, *, create_if_missing):
            assert name == MODAL_APP_NAME
            assert create_if_missing is True
            events.append("lookup")

    class Run:
        def __enter__(self):
            events.append("enter")

        def __exit__(self, *_args):
            events.append("exit")

    class App:
        @staticmethod
        def run():
            return Run()

    class Built:
        object_id = "im-test"

        @staticmethod
        def publish(name):
            assert events == ["lookup", "enter", "build"]
            events.append(f"publish:{name}")

    class Image:
        @staticmethod
        def build(_app):
            assert events == ["lookup", "enter"]
            events.append("build")
            return Built()

    monkeypatch.setattr(publish_image, "app", App())
    monkeypatch.setattr(publish_image, "image", Image())
    monkeypatch.setattr(
        publish_image, "with_executor_binary", lambda image, _path: image
    )
    monkeypatch.setattr(publish_image.subprocess, "run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        publish_image,
        "signed_release_manifest",
        lambda **_kwargs: {"signature": "signed"},
    )
    monkeypatch.setattr(publish_image.modal.App, "lookup", Lookup())
    monkeypatch.setenv("PWC_EXECUTOR_CARGO_TARGET_DIR", str(tmp_path))
    monkeypatch.setenv(
        "PWC_CHAT_EXECUTOR_MANIFEST_SIGNING_KEY_FILE", str(tmp_path / "key")
    )
    monkeypatch.setenv("PWC_CHAT_EXECUTOR_RELEASE_ID", "release-test")

    assert publish_image.main() == 0
    assert events == [
        "lookup",
        "enter",
        "build",
        f"publish:{IMAGE_PUBLISH_NAME}",
        "exit",
    ]
    assert capsys.readouterr().out == '{"signature":"signed"}\n'


def test_immutable_modal_image_uses_supported_constructor(monkeypatch):
    sentinel = object()

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.Image.from_id",
        lambda image_id: sentinel if image_id == "im-test" else None,
    )

    assert asyncio.run(resolve_modal_image("im-test")) is sentinel


def test_persistent_sandbox_uses_daemon_probe_and_request_limit_pairs(monkeypatch):
    captured: dict = {}

    async def lookup(*_args, **_kwargs):
        return object()

    async def image(_reference):
        return object()

    class Created:
        def __init__(self):
            self.exec = SimpleNamespace(aio=self._exec)
            self.poll = SimpleNamespace(aio=self._poll)

        async def _exec(self, *_args, **_kwargs):
            async def wait():
                return None

            return SimpleNamespace(
                returncode=0,
                wait=SimpleNamespace(aio=wait),
            )

        async def _poll(self):
            return None

    async def create(*command, **options):
        captured["command"] = command
        captured["options"] = options
        return Created()

    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.App.lookup",
        SimpleNamespace(aio=lookup),
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.resolve_modal_image",
        image,
    )
    monkeypatch.setattr(
        "backend.services.chat_sandbox_service.modal.Sandbox.create",
        SimpleNamespace(aio=create),
    )
    settings = Settings(
        _env_file=None,
        chat_gateway_url="https://gateway.example.test/api/internal/chat-gateway",
        chat_modal_image_version="im-test",
        chat_persistent_worker_enabled=True,
        chat_sandbox_cpu=0.125,
        chat_sandbox_cpu_limit=1,
        chat_sandbox_memory_mib=512,
        chat_sandbox_memory_limit_mib=2048,
    )

    asyncio.run(
        create_isolated_sandbox(settings, name="test", tags={"purpose": "test"})
    )

    assert captured["command"] == (
        "python",
        "-m",
        "backend.chat_sandbox_worker.control_daemon",
    )
    assert captured["options"]["cpu"] == (0.125, 1)
    assert captured["options"]["memory"] == (512, 2048)
    assert captured["options"]["region"] == "eu-west"
    assert captured["options"]["timeout"] == 86400
    assert captured["options"]["idle_timeout"] == 86400
    assert captured["options"]["inbound_cidr_allowlist"] is None
    assert captured["options"]["encrypted_ports"] == []
    assert captured["options"]["unencrypted_ports"] == []
    assert captured["options"]["env"]["PWC_CHAT_MAX_OUTPUT_TOKENS"] == "8000"
