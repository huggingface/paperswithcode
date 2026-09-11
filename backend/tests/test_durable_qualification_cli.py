from __future__ import annotations

import signal
import json
import grp
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_build_synthetic_transport_config_keeps_32_distinct_secrets_redacted():
    from backend.scripts.qualify_durable_external_turns import (
        build_synthetic_transport_config,
    )

    subjects: list[str] = []

    def encode(subject: str) -> str:
        subjects.append(subject)
        return f"secret-cookie-{subject}"

    config = build_synthetic_transport_config(
        run_id="run-123",
        admin_token="a" * 32,
        model="gpt-5.6-luna@openai",
        cookie_encoder=encode,
        max_spend_usd="1.25",
        required_spend_microusd=1_100_000,
        provider_spend_ceiling_microusd=1_000_000,
    )

    assert len(config.synthetic_cookies) == 32
    assert config.max_spend_microusd == 1_250_000
    assert config.provider_spend_ceiling_microusd == 1_000_000
    assert len(set(config.synthetic_cookies)) == 32
    assert subjects == [
        f"operator:pi-qualification:run-123:{ordinal}" for ordinal in range(32)
    ]
    rendered = repr(config)
    assert "secret-cookie" not in rendered
    assert "a" * 32 not in rendered


def test_synthetic_transport_rejects_declared_cap_below_live_cost_ceiling():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        build_synthetic_transport_config,
    )

    with pytest.raises(QualificationRefused, match="spend_envelope"):
        build_synthetic_transport_config(
            run_id="run-123",
            admin_token="a" * 32,
            model="gpt-5.6-luna@openai",
            cookie_encoder=lambda subject: f"cookie-{subject}",
            max_spend_usd="1",
            required_spend_microusd=1_000_001,
            provider_spend_ceiling_microusd=900_000,
        )


def test_live_spend_ceiling_uses_enforced_provider_and_lifecycle_limits():
    from backend.config import Settings
    from backend.services.chat_openai_budget_service import (
        MAX_REQUEST_BYTES,
        OpenAIRequestBounds,
        safe_maximum_microusd,
    )
    from backend.services.durable_external_qualification import (
        qualification_spend_ceiling_microusd,
    )
    from backend.services.durable_external_qualification_contract import (
        DURABLE_QUALIFICATION_EXPECTED_USERS,
        DURABLE_QUALIFICATION_PROVIDER_REQUESTS_PER_TURN,
        DURABLE_QUALIFICATION_RUN_TIMEOUT_SECONDS,
        DURABLE_QUALIFICATION_SANDBOX_LIFETIME_SECONDS,
        DURABLE_QUALIFICATION_TEARDOWN_TIMEOUT_SECONDS,
        DURABLE_QUALIFICATION_TOOL_TURNS,
    )

    settings = Settings(
        chat_openai_pricing_verified_at="2026-08-31",
        chat_openai_pricing_max_age_days=30,
    )
    provider, total = qualification_spend_ceiling_microusd(
        settings, modal_rate_microusd_per_second=53
    )
    per_call = safe_maximum_microusd(
        settings,
        OpenAIRequestBounds(
            request_bytes=MAX_REQUEST_BYTES,
            maximum_output_tokens=8_000,
        ),
    )

    assert provider == (
        DURABLE_QUALIFICATION_EXPECTED_USERS
        * DURABLE_QUALIFICATION_PROVIDER_REQUESTS_PER_TURN
        * per_call
    )
    assert DURABLE_QUALIFICATION_SANDBOX_LIFETIME_SECONDS >= (
        DURABLE_QUALIFICATION_RUN_TIMEOUT_SECONDS
        + DURABLE_QUALIFICATION_TEARDOWN_TIMEOUT_SECONDS
    )
    assert total == provider + round(
        DURABLE_QUALIFICATION_TOOL_TURNS
        * DURABLE_QUALIFICATION_SANDBOX_LIFETIME_SECONDS
        * 53
    )
    assert total < 10_000_000


@pytest.mark.parametrize("value", ("", "0", "10.01", "nan", "inf"))
def test_synthetic_transport_requires_a_bounded_spend_envelope(value: str):
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        build_synthetic_transport_config,
    )

    with pytest.raises(QualificationRefused, match="spend_envelope"):
        build_synthetic_transport_config(
            run_id="run-123",
            admin_token="a" * 32,
            model="gpt-5.6-luna@openai",
            cookie_encoder=lambda subject: subject,
            max_spend_usd=value,
        )


def test_whole_window_sampler_aggregates_and_refuses_stall():
    from backend.scripts.qualify_durable_external_turns import (
        DurableResourceSample,
        QualificationRefused,
        WholeWindowResourceSampler,
    )

    now = [10.0]
    samples = iter(
        (
            DurableResourceSample(10, 20, 3_000, 10.0, 1, 1, 0),
            DurableResourceSample(30, 40, 2_000, 50.0, 32, 1, 16),
        )
    )
    sampler = WholeWindowResourceSampler(
        sample=lambda: next(samples),
        monotonic=lambda: now[0],
        interval_seconds=0.1,
        threaded=False,
    )
    sampler.start()
    now[0] = 10.1
    resources = sampler.stop()

    assert resources.peak_memory_bytes == 70
    assert resources.minimum_host_mem_available_bytes == 2_000
    assert resources.peak_cpu_percent == 50.0
    assert resources.peak_active_backend_turns == 32
    assert resources.peak_active_external_workers == 1
    assert resources.peak_active_sandboxes == 16

    stalled = WholeWindowResourceSampler(
        sample=lambda: DurableResourceSample(1, 1, 3_000, 1.0, 0, 1, 0),
        monotonic=lambda: now[0],
        interval_seconds=0.1,
        threaded=False,
    )
    stalled.start()
    now[0] += 0.6
    with pytest.raises(QualificationRefused, match="resource_sampling_stalled"):
        stalled.stop()


def test_live_runner_starts_and_stops_sampler_around_chat_window(monkeypatch):
    adapter = pytest.importorskip("backend.loadtests.external_pi_fleet_locustfile")
    from backend.loadtests.durable_chat_transport import DurableChatTransportConfig

    events = []
    sampled = adapter.DurableRunResources(70, 2_000, 50.0, 32, 1, 16)

    class Sampler:
        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")
            return sampled

    monkeypatch.setattr(
        adapter,
        "_run_durable_observations",
        lambda **_kwargs: events.append("run") or (),
    )
    result = adapter.run_live_durable_profile(
        profile_name="32-functional-turns",
        transport_config=DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("cookie",),
            initial_model="gpt-5.6-luna@openai",
            qualification_run_id="run-123",
            admin_token="a" * 32,
        ),
        resources=Sampler(),
        qualification_scope_id=__import__("uuid").uuid4(),
    )

    assert events == ["start", "run", "stop"]
    assert result.resources is sampled


def test_durable_signal_context_restores_handlers_and_raises_typed_interrupt(
    monkeypatch,
):
    from backend.scripts.qualify_durable_external_turns import (
        DurableQualificationInterrupted,
        qualification_signal_context,
    )

    handlers = {signal.SIGINT: object(), signal.SIGTERM: object()}
    installed = []
    monkeypatch.setattr(signal, "getsignal", lambda number: handlers[number])
    monkeypatch.setattr(
        signal, "signal", lambda number, handler: installed.append((number, handler))
    )
    monkeypatch.setattr(signal, "pthread_sigmask", lambda *_args: set())

    with pytest.raises(DurableQualificationInterrupted):
        with qualification_signal_context():
            active = dict(installed[-2:])
            active[signal.SIGTERM](signal.SIGTERM, None)

    assert installed[-2:] == [
        (signal.SIGTERM, handlers[signal.SIGTERM]),
        (signal.SIGINT, handlers[signal.SIGINT]),
    ] or installed[-2:] == [
        (signal.SIGINT, handlers[signal.SIGINT]),
        (signal.SIGTERM, handlers[signal.SIGTERM]),
    ]


def test_cli_parser_help_is_import_safe(capsys):
    from backend.scripts.qualify_durable_external_turns import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit) as stopped:
        parser.parse_args(["--help"])
    assert stopped.value.code == 0
    help_text = capsys.readouterr().out
    assert "QUALIFY_STAGING_DURABLE_EXTERNAL_TURNS" in help_text
    assert "32-functional-turns" in help_text


def test_cli_report_destination_is_fixed(tmp_path: Path):
    from backend.scripts.qualify_durable_external_turns import (
        DURABLE_REPORT_PATH,
        build_parser,
    )

    args = build_parser().parse_args(
        [
            "--environment",
            "staging",
            "--release-id",
            "0123456789ab-staging",
            "--confirm",
            "QUALIFY_STAGING_DURABLE_EXTERNAL_TURNS",
            "--max-spend-usd",
            "1",
        ]
    )
    assert not hasattr(args, "report")
    assert str(DURABLE_REPORT_PATH).endswith(
        "/staging/durable-external-turn-qualification.json"
    )


def test_protected_staging_settings_ignore_ambient_admin_credential(
    tmp_path, monkeypatch
):
    from backend.services.durable_external_qualification_system import (
        load_protected_staging_settings,
    )

    path = tmp_path / "staging.env"
    path.write_text(
        "PWC_ENVIRONMENT=staging\n"
        f"PWC_ADMIN_API_TOKEN={'p' * 40}\n"
        f"PWC_JWT_SECRET={'j' * 40}\n"
    )
    path.chmod(0o640)
    os.chown(path, 0, grp.getgrnam("pwc-staging").gr_gid)
    monkeypatch.setenv("PWC_ADMIN_API_TOKEN", "ambient-must-not-win")

    settings = load_protected_staging_settings(path)

    assert settings.admin_api_token == "p" * 40
    assert settings.jwt_secret == "j" * 40
    assert settings.release_id == "development"


def test_protected_staging_settings_ignore_unrelated_pwc_keys(tmp_path):
    from backend.services.durable_external_qualification_system import (
        load_protected_staging_settings,
    )

    path = tmp_path / "staging.env"
    path.write_text(
        "PWC_ENVIRONMENT=staging\n"
        f"PWC_ADMIN_API_TOKEN={'p' * 40}\n"
        f"PWC_JWT_SECRET={'j' * 40}\n"
        "PWC_TRENDING_PIN_ARXIV_IDS=2601.00001:72\n"
    )
    path.chmod(0o640)
    os.chown(path, 0, grp.getgrnam("pwc-staging").gr_gid)

    settings = load_protected_staging_settings(path)

    assert settings.environment == "staging"


def test_bind_active_staging_worker_uses_verified_slot(tmp_path):
    from backend.config import Settings
    from backend.services.durable_external_qualification_system import (
        bind_active_staging_worker,
        configured_worker_ids,
    )

    slot = tmp_path / "environments" / "staging" / "slots" / "green"
    slot.mkdir(parents=True)
    active = slot.parents[1] / "active"
    active.symlink_to(slot)
    settings = Settings(
        environment="staging",
        chat_external_pi_worker_token="t" * 64,
    )

    bound = bind_active_staging_worker(settings, app_root=tmp_path)

    assert bound.chat_external_pi_worker_id == ""
    assert bound.chat_external_pi_worker_url == ""
    assert bound.chat_external_pi_worker_token == ""
    assert configured_worker_ids(bound) == tuple(
        f"staging-green-{index:02d}" for index in range(8)
    )
    assert len(bound.chat_external_pi_worker_endpoints) == 8
    assert bound.chat_external_pi_worker_max_sessions == 4


def test_system_prerequisites_aggregate_all_configured_workers(monkeypatch):
    from backend.database import connection
    from backend.services import durable_external_qualification_system as system
    from backend.services import runtime_validation

    worker_ids = tuple(f"staging-blue-{index:02d}" for index in range(8))
    workers = tuple(
        SimpleNamespace(
            worker_id=worker_id,
            environment="staging",
            release_id="0123456789ab-staging",
            state="ready",
            contract_version="external-pi-v1",
            maximum_sessions=4,
            active_sessions=index % 2,
        )
        for index, worker_id in enumerate(worker_ids)
    )

    class FakeSession:
        def execute(self, _statement):
            return SimpleNamespace(one=lambda: ("pwc_staging", "staging"))

        def scalars(self, _statement):
            return workers

    class SessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        connection,
        "db_manager",
        SimpleNamespace(session_local=lambda: SessionContext()),
    )
    for name in (
        "validate_chat_schema",
        "validate_external_worker_reservation_schema",
        "validate_qualification_evidence_schema",
    ):
        monkeypatch.setattr(runtime_validation, name, lambda *_args: None)
    settings = SimpleNamespace(
        chat_external_pi_worker_endpoints=tuple(
            SimpleNamespace(worker_id=worker_id) for worker_id in worker_ids
        ),
        chat_pi_runtime_enabled=True,
        chat_external_pi_supervisor_enabled=True,
        chat_external_pi_ready_registry_enabled=True,
        chat_durable_turn_dispatch_enabled=True,
        chat_turn_event_journal_schema_enabled=True,
        chat_sandbox_executor_enabled=True,
        chat_remote_workspace_tools_enabled=True,
        chat_remote_bash_enabled=True,
        chat_remote_read_enabled=True,
        chat_lazy_workspace_enabled=True,
        chat_new_session_pi_percentage=100,
        chat_external_pi_worker_contract_version="external-pi-v1",
        chat_external_pi_runtime_contract_version="durable-external-pi-v1",
    )

    evidence = system._system_prerequisites(settings, "0123456789ab-staging")

    assert evidence.worker_id == ",".join(worker_ids)
    assert evidence.worker_environment == "staging"
    assert evidence.worker_release_id == "0123456789ab-staging"
    assert evidence.worker_state == "ready"
    assert evidence.maximum_sessions == 32
    assert evidence.active_sessions == 4
    assert evidence.runtime_ready is True
    assert evidence.migrations_ready is True


def test_system_resource_sampler_uses_active_slot_backend_unit(tmp_path, monkeypatch):
    from backend.services import durable_external_qualification_system as system

    slot = tmp_path / "environments" / "staging" / "slots" / "blue"
    slot.mkdir(parents=True)
    (slot.parents[1] / "active").symlink_to(slot)
    control = SimpleNamespace(app_root=tmp_path)
    evidence = system._SystemResourceEvidence(control)
    monkeypatch.setattr(evidence, "_scope_counts", lambda: (3, 1, 2))
    monkeypatch.setattr(evidence, "_cpu_percent", lambda: 12.5)
    monkeypatch.setattr(system, "_proc_memory_value", lambda _name: 10_000)
    units = []
    monkeypatch.setattr(
        system, "_systemctl_memory", lambda unit: units.append(unit) or 1_000
    )

    sample = evidence.sample()

    assert sample.active_backend_turns == 3
    assert units == [
        "paperswithcode-staging-backend@blue.service",
        "paperswithcode-staging-external-pi-worker@blue.service",
    ]


def test_system_resource_scope_counts_accept_exact_eight_worker_topology(monkeypatch):
    import uuid

    from backend.database import connection
    from backend.services import durable_external_qualification_system as system

    class FakeSession:
        def execute(self, _statement, _parameters):
            return SimpleNamespace(scalar_one=lambda: 0)

    class SessionContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        connection,
        "db_manager",
        SimpleNamespace(session_local=lambda: SessionContext()),
    )
    control = SimpleNamespace(
        qualification_scope_id=uuid.uuid4(),
        release_id="0123456789ab-staging",
        settings=SimpleNamespace(
            chat_external_pi_worker_endpoints=tuple(
                SimpleNamespace(worker_id=f"staging-blue-{index:02d}")
                for index in range(8)
            )
        ),
    )

    assert system._SystemResourceEvidence(control)._scope_counts() == (0, 0, 0)


@pytest.mark.parametrize("worker_count", (0, 7, 9, 16))
def test_system_resource_scope_counts_reject_non_current_topology(worker_count):
    import uuid

    from backend.services import durable_external_qualification_system as system

    control = SimpleNamespace(
        qualification_scope_id=uuid.uuid4(),
        release_id="0123456789ab-staging",
        settings=SimpleNamespace(
            chat_external_pi_worker_endpoints=tuple(
                SimpleNamespace(worker_id=f"staging-blue-{index:02d}")
                for index in range(worker_count)
            )
        ),
    )

    with pytest.raises(system.QualificationRefused, match="staging_prerequisite"):
        system._SystemResourceEvidence(control)._scope_counts()


@pytest.mark.parametrize("mode", (0o600, 0o644, 0o660))
def test_protected_staging_settings_reject_wrong_mode(tmp_path, mode):
    from backend.services.durable_external_qualification_system import (
        QualificationRefused,
        load_protected_staging_settings,
    )

    path = tmp_path / "staging.env"
    path.write_text("PWC_ENVIRONMENT=staging\n")
    path.chmod(mode)
    os.chown(path, 0, grp.getgrnam("pwc-staging").gr_gid)

    with pytest.raises(QualificationRefused, match="protected_staging_settings"):
        load_protected_staging_settings(path)


def test_protected_staging_settings_reject_symlink_wrong_group_and_oversize(tmp_path):
    from backend.services.durable_external_qualification_system import (
        QualificationRefused,
        load_protected_staging_settings,
    )

    path = tmp_path / "staging.env"
    path.write_text("x" * (256 * 1024 + 1))
    path.chmod(0o640)
    os.chown(path, 0, grp.getgrnam("pwc-staging").gr_gid)
    with pytest.raises(QualificationRefused):
        load_protected_staging_settings(path)

    path.write_text("PWC_ENVIRONMENT=staging\n")
    os.chown(path, 0, 0)
    with pytest.raises(QualificationRefused):
        load_protected_staging_settings(path)

    os.chown(path, 1, grp.getgrnam("pwc-staging").gr_gid)
    with pytest.raises(QualificationRefused):
        load_protected_staging_settings(path)

    os.chown(path, 0, grp.getgrnam("pwc-staging").gr_gid)
    link = tmp_path / "linked.env"
    link.symlink_to(path)
    with pytest.raises(QualificationRefused):
        load_protected_staging_settings(link)


def test_cli_release_identity_must_match_validated_active_manifest():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        validated_active_release_id,
    )

    active = SimpleNamespace(release_id="0123456789ab-staging")
    assert (
        validated_active_release_id("0123456789ab-staging", active) == active.release_id
    )
    with pytest.raises(QualificationRefused, match="exact_staging_release"):
        validated_active_release_id("fedcba987654-staging", active)


def _release_tree(tmp_path: Path):
    app_root = tmp_path / "paperswithcode"
    releases = app_root / "releases"
    releases.mkdir(parents=True)
    staging = releases / "0123456789ab-staging"
    production = releases / "fedcba987654-production"
    staging.mkdir()
    production.mkdir()
    for environment, release in (("staging", staging), ("production", production)):
        directory = app_root / "environments" / environment
        directory.mkdir(parents=True)
        (directory / "current").symlink_to(release)
    return app_root


def _safe_settings(**updates):
    values = {
        "environment": "staging",
        "release_id": "0123456789ab-staging",
        "chat_external_pi_admission_enabled": False,
        "chat_new_session_pi_percentage": 100,
        "chat_sandbox_executor_enabled": True,
        "chat_remote_workspace_tools_enabled": True,
        "chat_remote_bash_enabled": True,
        "chat_remote_read_enabled": True,
        "chat_lazy_workspace_enabled": True,
        "chat_external_pi_worker_endpoints": (
            SimpleNamespace(worker_id="staging-worker"),
        ),
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _ready_prerequisites(**updates):
    from backend.scripts.qualify_durable_external_turns import (
        StagingQualificationPrerequisites,
    )

    values = {
        "migrations_ready": True,
        "runtime_ready": True,
        "worker_environment": "staging",
        "worker_id": "staging-worker",
        "configured_worker_id": "staging-worker",
        "worker_release_id": "0123456789ab-staging",
        "worker_state": "ready",
        "worker_contract_version": "external-pi-v1",
        "maximum_sessions": 32,
        "active_sessions": 0,
    }
    values.update(updates)
    return StagingQualificationPrerequisites(**values)


def test_system_control_plane_independently_resolves_exact_release_and_flags(tmp_path):
    from backend.scripts.qualify_durable_external_turns import (
        SystemDurableQualificationControlPlane,
    )

    control = SystemDurableQualificationControlPlane(
        release_id="0123456789ab-staging",
        settings=_safe_settings(),
        app_root=_release_tree(tmp_path),
        environ={"PWC_RELEASE_ID": "0123456789ab-staging"},
        mem_total=lambda: 16 * 1024**3,
        prerequisites=_ready_prerequisites,
        resource_preflight=lambda _profile: None,
        sampler_factory=lambda _profile: object(),
        cleanup_probe=lambda: None,
        modal_rate_path=tmp_path / "rate.json",
    )

    environment = control.environment()
    assert environment.staging_release == "0123456789ab-staging"
    assert environment.production_release == "fedcba987654-production"
    assert control.snapshot_flags() == {"external_pi_admission": False}

    staging_current = tmp_path / "paperswithcode/environments/staging/current"
    staging_current.unlink()
    staging_current.symlink_to(
        tmp_path / "paperswithcode/releases/fedcba987654-production"
    )
    with pytest.raises(Exception, match="exact_staging_release"):
        control.environment()


@pytest.mark.parametrize(
    "updates",
    (
        {"migrations_ready": False},
        {"runtime_ready": False},
        {"worker_environment": "production"},
        {"worker_release_id": "fedcba987654-production"},
        {"worker_state": "draining"},
        {"worker_contract_version": "old"},
        {"maximum_sessions": 31},
        {"maximum_sessions": 33},
        {"active_sessions": 1},
        {"configured_worker_id": "some-other-worker"},
    ),
)
def test_system_control_plane_refuses_missing_staging_prerequisite(tmp_path, updates):
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        SystemDurableQualificationControlPlane,
    )
    from backend.loadtests.external_pi_fleet_core import resolve_durable_profile

    control = SystemDurableQualificationControlPlane(
        release_id="0123456789ab-staging",
        settings=_safe_settings(),
        app_root=_release_tree(tmp_path),
        environ={"PWC_RELEASE_ID": "0123456789ab-staging"},
        mem_total=lambda: 16 * 1024**3,
        prerequisites=lambda: _ready_prerequisites(**updates),
        resource_preflight=lambda _profile: None,
        sampler_factory=lambda _profile: object(),
        cleanup_probe=lambda: None,
        modal_rate_path=tmp_path / "rate.json",
    )

    with pytest.raises(QualificationRefused, match="staging_prerequisite"):
        control.setup_profile(resolve_durable_profile("32-functional-turns"))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("chat_new_session_pi_percentage", 0),
        ("chat_new_session_pi_percentage", 99),
        ("chat_sandbox_executor_enabled", False),
        ("chat_remote_workspace_tools_enabled", False),
        ("chat_remote_bash_enabled", False),
        ("chat_remote_read_enabled", False),
        ("chat_lazy_workspace_enabled", False),
    ),
)
def test_system_control_plane_requires_qualification_runtime_flags(
    tmp_path, field, value
):
    from backend.loadtests.external_pi_fleet_core import resolve_durable_profile
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        SystemDurableQualificationControlPlane,
    )

    control = SystemDurableQualificationControlPlane(
        release_id="0123456789ab-staging",
        settings=_safe_settings(**{field: value}),
        app_root=_release_tree(tmp_path),
        environ={"PWC_RELEASE_ID": "0123456789ab-staging"},
        mem_total=lambda: 16 * 1024**3,
        prerequisites=_ready_prerequisites,
        resource_preflight=lambda _profile: None,
        sampler_factory=lambda _profile: object(),
        cleanup_probe=lambda: None,
        modal_rate_path=tmp_path / "rate.json",
    )

    with pytest.raises(QualificationRefused, match="staging_prerequisite"):
        control.setup_profile(resolve_durable_profile("32-functional-turns"))


def test_system_control_plane_requires_prerequisite_worker_in_configured_topology(
    tmp_path,
):
    from backend.loadtests.external_pi_fleet_core import resolve_durable_profile
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        SystemDurableQualificationControlPlane,
    )

    control = SystemDurableQualificationControlPlane(
        release_id="0123456789ab-staging",
        settings=_safe_settings(
            chat_external_pi_worker_endpoints=(
                SimpleNamespace(worker_id="different-worker"),
            )
        ),
        app_root=_release_tree(tmp_path),
        environ={"PWC_RELEASE_ID": "0123456789ab-staging"},
        mem_total=lambda: 16 * 1024**3,
        prerequisites=_ready_prerequisites,
        resource_preflight=lambda _profile: None,
        sampler_factory=lambda _profile: object(),
        cleanup_probe=lambda: None,
        modal_rate_path=tmp_path / "rate.json",
    )

    with pytest.raises(QualificationRefused, match="staging_prerequisite"):
        control.setup_profile(resolve_durable_profile("32-functional-turns"))


def test_cleanup_counts_only_transient_workers_and_exact_scope(tmp_path):
    from backend.scripts.qualify_durable_external_turns import (
        ScopedCleanupState,
        SystemDurableQualificationControlPlane,
    )

    # The configured baseline worker remains active outside this scoped state.
    control = SystemDurableQualificationControlPlane(
        release_id="0123456789ab-staging",
        settings=_safe_settings(),
        app_root=_release_tree(tmp_path),
        environ={"PWC_RELEASE_ID": "0123456789ab-staging"},
        mem_total=lambda: 16 * 1024**3,
        prerequisites=_ready_prerequisites,
        resource_preflight=lambda _profile: None,
        sampler_factory=lambda _profile: object(),
        cleanup_probe=lambda: ScopedCleanupState(True, 0, 0, 0, 0, 0, 0, 0),
        modal_rate_path=tmp_path / "rate.json",
    )

    proof = control.cleanup_transient_workers()
    assert proof.passed is True
    assert proof.final_active_external_workers == 0


def test_cleanup_fails_if_scope_creation_was_attempted_but_never_bound(tmp_path):
    from backend.scripts.qualify_durable_external_turns import (
        SystemDurableQualificationControlPlane,
    )
    from backend.services.durable_external_qualification_system import (
        system_cleanup_state,
    )

    control = SystemDurableQualificationControlPlane(
        release_id="0123456789ab-staging",
        settings=_safe_settings(),
        app_root=_release_tree(tmp_path),
        environ={"PWC_RELEASE_ID": "0123456789ab-staging"},
        mem_total=lambda: 16 * 1024**3,
        prerequisites=_ready_prerequisites,
        resource_preflight=lambda _profile: None,
        sampler_factory=lambda _profile: object(),
        cleanup_probe=lambda: system_cleanup_state(control),
        modal_rate_path=tmp_path / "rate.json",
    )
    control.mark_scope_attempted()

    assert control.cleanup_transient_workers().passed is False


def test_modal_rate_evidence_requires_root_owned_mode_0600_bounded_file(tmp_path):
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        SystemDurableQualificationControlPlane,
    )
    from backend.loadtests.external_pi_fleet_core import resolve_durable_profile

    path = tmp_path / "rate.json"
    path.write_text(
        json.dumps(
            {
                "PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND": "25",
                "PWC_MODAL_EXECUTOR_RATE_SOURCE_ID": "modal-staging-price-v1",
                "PWC_RELEASE_ID": "0123456789ab-staging",
            }
        )
    )
    path.chmod(0o600)
    control = SystemDurableQualificationControlPlane(
        release_id="0123456789ab-staging",
        settings=_safe_settings(),
        app_root=_release_tree(tmp_path),
        environ={"PWC_RELEASE_ID": "0123456789ab-staging"},
        mem_total=lambda: 16 * 1024**3,
        prerequisites=_ready_prerequisites,
        resource_preflight=lambda _profile: None,
        sampler_factory=lambda _profile: object(),
        cleanup_probe=lambda: None,
        modal_rate_path=path,
    )
    profile = resolve_durable_profile("32-functional-turns")

    assert control.protected_runtime_evidence(profile)["PWC_RELEASE_ID"].endswith(
        "-staging"
    )
    assert "PWC_MODAL_EXECUTOR_RATE_ATTESTED_AT_MS" not in (
        control.protected_runtime_evidence(profile)
    )
    path.chmod(0o644)
    with pytest.raises(QualificationRefused, match="modal_rate"):
        control.protected_runtime_evidence(profile)
    path.chmod(0o600)
    path.write_text(
        json.dumps(
            {
                "PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND": "not-a-rate",
                "PWC_MODAL_EXECUTOR_RATE_SOURCE_ID": "modal-staging-price-v1",
                "PWC_RELEASE_ID": "0123456789ab-staging",
            }
        )
    )
    with pytest.raises(QualificationRefused, match="modal_rate"):
        control.protected_runtime_evidence(profile)


def test_model_selection_requires_one_discovered_direct_openai_route():
    from backend.scripts.qualify_durable_external_turns import (
        QualificationRefused,
        select_staging_pi_openai_model,
    )

    direct = {
        "id": "gpt-5.6-luna@openai",
        "provider": "openai",
        "protocol": "openai-responses",
        "route": "gpt-5.6-luna",
    }
    assert (
        select_staging_pi_openai_model(SimpleNamespace(chat_model_choices=(direct,)))
        == direct["id"]
    )
    for choices in ((), (direct, direct)):
        with pytest.raises(QualificationRefused, match="pi_openai_model"):
            select_staging_pi_openai_model(SimpleNamespace(chat_model_choices=choices))
