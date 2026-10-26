"""systemd templates, host routing, deployment status, and worker status polling."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

import deploy.cli as deploy_cli
import deploy.external_pi_slot_lifecycle as lifecycle
import deploy.install_host_layout as install_host_layout


@pytest.mark.parametrize("mcp_enabled", [None, "false", "true"])
def test_dedicated_worker_environment_contains_only_token_and_tool_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mcp_enabled: str | None
):
    (tmp_path / "staging.env").write_text(
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN=" + "t" * 32 + "\n"
        "PWC_DB_PASSWORD=must-not-leak\n"
        "PWC_OPENAI_API_KEY=must-not-leak\n"
        + (f"PWC_CHAT_PWC_MCP_ENABLED={mcp_enabled}\n" if mcp_enabled else "")
    )
    worker_environment = tmp_path / "external-pi-worker.env"
    monkeypatch.setattr(lifecycle, "CONFIG_ROOT", tmp_path)
    monkeypatch.setattr(lifecycle, "WORKER_CONFIG", worker_environment)
    monkeypatch.setattr(
        lifecycle.grp, "getgrnam", lambda _name: SimpleNamespace(gr_gid=1234)
    )
    ownership: list[tuple[int, int]] = []
    monkeypatch.setattr(
        lifecycle.os,
        "chown",
        lambda _path, user, group: ownership.append((user, group)),
    )

    lifecycle.sync_worker_environment("staging")

    assert worker_environment.read_text() == (
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN="
        + "t" * 32
        + "\n"
        + f"PWC_CHAT_PWC_MCP_ENABLED={mcp_enabled or 'false'}\n"
    )
    assert worker_environment.stat().st_mode & 0o777 == 0o640
    assert ownership == [(0, 1234)]


def test_systemd_templates_split_worker_and_supervisor_credentials():
    supervisor = (
        Path(__file__).parents[3]
        / "deploy/systemd/paperswithcode-staging-external-pi@.service"
    ).read_text()
    worker = (
        Path(__file__).parents[3]
        / "deploy/systemd/paperswithcode-staging-external-pi-worker@.service"
    ).read_text()

    assert "User=pwc-staging" in supervisor
    assert "EnvironmentFile=/etc/paperswithcode/staging.env" in supervisor
    assert "external_pi_slot_launcher.py staging %i" in supervisor
    assert "User=pwc-external-pi-staging" in worker
    assert "EnvironmentFile=/etc/paperswithcode/external-pi-worker.env" in worker
    assert (
        "BindReadOnlyPaths=/etc/paperswithcode/external-pi-hosts:/etc/hosts" in worker
    )
    assert "RuntimeDirectory=paperswithcode/external-pi-%i" in worker
    assert "PWC_EXTERNAL_PI_STATE_ROOT=/run/paperswithcode/external-pi-%i" in worker
    assert "external_pi_worker_launcher.py staging %i" in worker
    assert "staging.env" not in worker
    assert "ProtectProc=invisible" in worker
    assert "CPUQuota=400%" in worker
    assert "MemoryMax=6442450944" in worker
    assert "TasksMax=512" in worker
    assert "CPUQuota=200%" in supervisor
    assert "MemoryMax=2147483648" in supervisor
    assert "TasksMax=256" in supervisor
    timeout_line = next(
        line for line in supervisor.splitlines() if line.startswith("TimeoutStopSec=")
    )
    assert (
        int(timeout_line.partition("=")[2])
        > lifecycle.MAXIMUM_DRAIN_STOP_TIMEOUT_SECONDS
    )


def test_external_pi_hosts_bypasses_the_public_cdn_only_for_the_worker(
    tmp_path: Path,
):
    hosts = tmp_path / "external-pi-hosts"

    install_host_layout.install_external_pi_hosts(hosts)

    assert hosts.read_text() == (
        "127.0.0.1 localhost chat-gateway-staging.paperswithcode.co "
        "chat-gateway.paperswithcode.co\n"
        "::1 localhost ip6-localhost ip6-loopback "
        "chat-gateway-staging.paperswithcode.co chat-gateway.paperswithcode.co\n"
    )
    assert hosts.stat().st_mode & 0o777 == 0o644


def test_deployment_status_reports_shadow_unit_and_durable_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    environments = tmp_path / "environments"
    (environments / "staging").mkdir(parents=True)
    monkeypatch.setattr(deploy_cli, "APP_ROOT", tmp_path)
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS", ("staging",))
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)
    monkeypatch.setattr(deploy_cli, "RUNTIME_LOCK", tmp_path / "runtime-lock")
    monkeypatch.setattr(
        deploy_cli,
        "read_pointers",
        lambda _root: SimpleNamespace(current=None, previous=None),
    )
    monkeypatch.setattr(deploy_cli, "_active_slot", lambda _environment: "blue")
    monkeypatch.setattr(
        deploy_cli, "_nginx_uses_active_slot", lambda _environment: True
    )
    monkeypatch.setattr(deploy_cli, "_slot_release", lambda *_args: None)
    monkeypatch.setattr(deploy_cli, "_systemctl_state", lambda unit: "active")
    monkeypatch.setattr(deploy_cli, "_unix_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        deploy_cli,
        "external_pi_slot_status",
        lambda _environment, slot: {
            "worker_id": f"staging-{slot}",
            "generation": 7,
            "heartbeats": 2,
            "state": "ready",
        },
    )

    assert deploy_cli.status(Namespace()) == 0

    value = json.loads(capsys.readouterr().out)
    shadow = value["environments"]["staging"]["slots"]["blue"]["external_pi_shadow"]
    assert shadow == {
        "supervisor": "active",
        "worker": "active",
        "lifecycle": {
            "worker_id": "staging-blue",
            "generation": 7,
            "heartbeats": 2,
            "state": "ready",
        },
    }


def test_worker_status_tolerates_the_window_before_the_worker_binds(
    monkeypatch: pytest.MonkeyPatch,
):
    # systemd reports the Type=simple worker unit active as soon as it execs,
    # while the Node process is still loading the Pi runtime and has not bound
    # its port. A single attempt turned that into a refused connection that
    # failed the whole deployment.
    spec = lifecycle.replica_specs("staging", "blue", "x" * 32)[0]
    attempts = {"n": 0}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self, _size):
            return json.dumps({"worker_id": spec.worker_id, "state": "ready"}).encode()

    def urlopen(_request, timeout=None):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionRefusedError(111, "Connection refused")
        return _Response()

    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(lifecycle.time, "sleep", lambda _seconds: None)

    assert lifecycle._worker_status(spec)["worker_id"] == spec.worker_id
    assert attempts["n"] == 3


def test_worker_status_gives_up_after_the_bind_grace_expires(
    monkeypatch: pytest.MonkeyPatch,
):
    spec = lifecycle.replica_specs("staging", "blue", "x" * 32)[0]
    clock = {"now": 0.0}

    def urlopen(_request, timeout=None):
        raise ConnectionRefusedError(111, "Connection refused")

    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        lifecycle.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    with pytest.raises(ConnectionRefusedError):
        lifecycle._worker_status(spec)


def test_worker_status_never_retries_a_malformed_payload(
    monkeypatch: pytest.MonkeyPatch,
):
    spec = lifecycle.replica_specs("staging", "blue", "x" * 32)[0]
    attempts = {"n": 0}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self, _size):
            return b"x" * (lifecycle.MAXIMUM_WORKER_STATUS_BYTES + 1)

    def urlopen(_request, timeout=None):
        attempts["n"] += 1
        return _Response()

    monkeypatch.setattr(lifecycle.urllib.request, "urlopen", urlopen)

    with pytest.raises(ValueError, match="too large"):
        lifecycle._worker_status(spec)
    assert attempts["n"] == 1


@pytest.mark.parametrize(
    ("configured_tier", "drained_sessions"), [(64, 4), (32, 8), (64, 8)]
)
def test_drain_recognises_workers_of_either_capacity_tier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured_tier: int,
    drained_sessions: int,
):
    monkeypatch.setattr(lifecycle, "STATUS_ROOT", tmp_path)
    monkeypatch.setattr(
        lifecycle, "fleet_sessions", lambda _environment: configured_tier
    )
    workers = lifecycle.replica_specs("staging", "green", "x" * 32)
    for spec in workers:
        (tmp_path / f"{spec.worker_id}.json").write_text(
            json.dumps(
                {
                    "protocol": lifecycle.CONTRACT_VERSION,
                    "release_id": "old-release",
                    "worker_id": spec.worker_id,
                    "state": "ready",
                    "maximum_sessions": drained_sessions,
                }
            )
        )

    selected = lifecycle._draining_replica_specs(
        "staging", "green", "x" * 32, "old-release"
    )

    assert len(selected) == 8
    assert {spec.maximum_sessions for spec in selected} == {drained_sessions}
    assert [spec.worker_id for spec in selected] == [spec.worker_id for spec in workers]


def test_fleet_sessions_reads_the_protected_tier_and_defaults_when_unreadable(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda _environment: {"PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": "64"},
    )
    assert lifecycle.fleet_sessions("production") == 64

    def missing(_environment):
        raise FileNotFoundError

    monkeypatch.setattr(lifecycle, "_protected_environment_values", missing)
    assert lifecycle.fleet_sessions("production") == 32

    monkeypatch.setattr(
        lifecycle,
        "_protected_environment_values",
        lambda _environment: {"PWC_CHAT_EXTERNAL_PI_WORKER_MAX_SESSIONS": "40"},
    )
    with pytest.raises(ValueError, match="reviewed tier"):
        lifecycle.fleet_sessions("production")


def test_staging_and_production_workers_never_share_a_unix_user():
    root = Path(__file__).parents[3] / "deploy/systemd"
    staging = (root / "paperswithcode-staging-external-pi-worker@.service").read_text()
    production = (
        root / "paperswithcode-production-external-pi-worker@.service"
    ).read_text()

    assert "User=pwc-external-pi-staging" in staging
    assert "User=pwc-external-pi\n" in production
