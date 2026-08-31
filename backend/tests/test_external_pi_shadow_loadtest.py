from __future__ import annotations

import importlib
import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.loadtests.external_pi_shadow_core import (
    MAX_REPORT_COUNTER,
    MAX_REPORT_DURATION_MS,
    BaselineObservation,
    ExternalPiBaselineTracker,
    RunRefused,
    build_external_pi_baseline_request,
    classify_external_pi_baseline_response,
    finalize_external_pi_baseline,
    load_external_pi_baseline_config,
    validate_external_pi_baseline_topology,
)
from backend.services.chat_external_pi_shadow import ExternalPiWorkerStatus
from deploy.external_pi_slot_lifecycle import ExternalPiSlot


def _baseline_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, str]:
    app_root = tmp_path / "srv/paperswithcode"
    release = app_root / "releases/0123456789ab-staging"
    runtime = app_root / "runtimes/external-pi/runtime-id"
    slot_root = app_root / "environments/staging/slots/blue"
    release.mkdir(parents=True)
    runtime.joinpath("assets").mkdir(parents=True)
    runtime.joinpath("assets/pi-system-prompt.txt").write_text(
        "canonical-runtime-prompt", encoding="utf-8"
    )
    slot_root.mkdir(parents=True)
    slot_root.joinpath("release").symlink_to(release)
    staging = app_root / "environments/staging"
    staging.joinpath("current").symlink_to(release)
    staging.joinpath("active").symlink_to(slot_root)
    token_file = tmp_path / "external-pi-worker.env"
    token_file.write_text(
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN=secret-token-value\n", encoding="utf-8"
    )
    token_file.chmod(0o600)

    resolved = ExternalPiSlot(
        slot="blue",
        port=8766,
        worker_id="staging-blue",
        release=release,
        release_id=release.name,
        runtime=runtime,
        node=runtime / "node/bin/node",
        entry_point=runtime / "index.js",
        prompt=runtime / "assets/pi-system-prompt.txt",
        status_path=tmp_path / "status.json",
    )
    monkeypatch.setattr("backend.loadtests.external_pi_shadow_core.APP_ROOT", app_root)
    monkeypatch.setattr(
        "backend.loadtests.external_pi_shadow_core.SOURCE_ROOT", release
    )
    report_root = tmp_path / "var/lib/paperswithcode/staging"
    report_root.mkdir(parents=True)
    monkeypatch.setattr(
        "backend.loadtests.external_pi_shadow_core.REPORT_ROOT", report_root
    )
    monkeypatch.setattr(
        "backend.loadtests.external_pi_shadow_core.resolve_external_pi_slot",
        lambda environment, slot: resolved,
    )
    return {
        "PWC_EXTERNAL_PI_BASELINE_CONFIRM": "RUN_EXTERNAL_PI_SHADOW_BASELINE",
        "PWC_EXTERNAL_PI_BASELINE_PROFILE": "single-worker-overload-baseline",
        "PWC_EXTERNAL_PI_BASELINE_USERS": "100",
        "PWC_EXTERNAL_PI_BASELINE_SPAWN_RATE": "100",
        "PWC_EXTERNAL_PI_BASELINE_SLOT": "blue",
        "PWC_EXTERNAL_PI_BASELINE_WORKER_URL": "http://127.0.0.1:8766",
        "PWC_EXTERNAL_PI_BASELINE_TOKEN_FILE": str(token_file),
        "PWC_EXTERNAL_PI_BASELINE_REPORT": str(report_root / "baseline.json"),
    }


@pytest.mark.parametrize(
    ("name", "updates", "message"),
    [
        (
            "production target",
            {"PWC_EXTERNAL_PI_BASELINE_WORKER_URL": "https://paperswithcode.co"},
            "active staging worker endpoint",
        ),
        (
            "wrong slot port",
            {"PWC_EXTERNAL_PI_BASELINE_WORKER_URL": "http://127.0.0.1:8767"},
            "active staging worker endpoint",
        ),
        (
            "wrong user count",
            {"PWC_EXTERNAL_PI_BASELINE_USERS": "99"},
            "exactly 100 users at spawn rate 100.0",
        ),
        (
            "wrong spawn rate",
            {"PWC_EXTERNAL_PI_BASELINE_SPAWN_RATE": "99"},
            "exactly 100 users at spawn rate 100.0",
        ),
    ],
)
def test_external_pi_baseline_refuses_production_breaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    updates: dict[str, str],
    message: str,
):
    environ = _baseline_environment(tmp_path, monkeypatch)
    environ.update(updates)

    with pytest.raises(RunRefused, match=message):
        load_external_pi_baseline_config(environ)


def test_external_pi_baseline_refuses_mutable_or_inactive_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environ = _baseline_environment(tmp_path, monkeypatch)
    current = tmp_path / "srv/paperswithcode/environments/staging/current"
    current.unlink()
    mutable = tmp_path / "srv/paperswithcode/releases/mutable-staging"
    mutable.mkdir()
    current.symlink_to(mutable)

    with pytest.raises(RunRefused, match="exact active immutable staging release"):
        load_external_pi_baseline_config(environ)


def test_external_pi_baseline_config_repr_hides_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environ = _baseline_environment(tmp_path, monkeypatch)

    config = load_external_pi_baseline_config(environ)

    assert "secret-token-value" not in repr(config)
    assert config.prompt == "canonical-runtime-prompt"


@pytest.mark.parametrize(
    ("contents", "mode", "message"),
    [
        ("UNKNOWN=value\n", 0o600, "unexpected entries"),
        (
            (
                "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN=first\n"
                "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN=second\n"
            ),
            0o600,
            "exactly one token",
        ),
        ("PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN=value\n", 0o620, "not protected"),
    ],
)
def test_external_pi_baseline_refuses_ambiguous_or_mutable_token_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contents: str,
    mode: int,
    message: str,
):
    environ = _baseline_environment(tmp_path, monkeypatch)
    token_file = Path(environ["PWC_EXTERNAL_PI_BASELINE_TOKEN_FILE"])
    token_file.write_text(contents, encoding="utf-8")
    token_file.chmod(mode)

    with pytest.raises(RunRefused, match=message):
        load_external_pi_baseline_config(environ)


def _compatible_projection(request):
    return {
        "type": "shadow_projection",
        "protocol_version": 1,
        "request_id": request.request_id,
        "chat_session_id": str(request.chat_session_id),
        "agent_session_id": str(request.agent_session_id),
        "current_leaf_id": request.current_leaf_id,
        "entry_count": 2_000,
        "transcript_sha256": request.transcript_sha256,
        "prompt_sha256": request.prompt_sha256,
        "tool_names_sha256": request.tool_names_sha256,
    }


def test_external_pi_baseline_builds_unique_maximum_entry_requests():
    first = build_external_pi_baseline_request(0, "canonical-runtime-prompt")
    last = build_external_pi_baseline_request(99, "canonical-runtime-prompt")

    assert len(first.transcript_entries) == 2_000
    assert first.request_id != last.request_id
    assert first.chat_session_id != last.chat_session_id
    assert first.agent_session_id != last.agent_session_id
    assert first.tool_names == ()
    assert first.prompt == "canonical-runtime-prompt"
    assert uuid.UUID(first.request_id)
    assert first.current_leaf_id == first.transcript_entries[-1]["id"]
    assert all("message" not in entry for entry in first.transcript_entries)


@pytest.mark.parametrize(
    ("status_code", "payload", "expected"),
    [
        (200, "compatible", "compatible"),
        (503, {"code": "shadow_capacity"}, "capacity"),
        (503, {"code": "worker_unavailable"}, "error"),
        (200, "malformed", "error"),
        (200, "mismatch", "error"),
    ],
)
def test_external_pi_baseline_classifies_only_fixed_safe_outcomes(
    status_code: int, payload: object, expected: str
):
    request = build_external_pi_baseline_request(0, "canonical-runtime-prompt")
    if payload == "compatible":
        payload = _compatible_projection(request)
    elif payload == "malformed":
        payload = {"type": "shadow_projection"}
    elif payload == "mismatch":
        payload = {**_compatible_projection(request), "request_id": str(uuid.uuid4())}

    observation = classify_external_pi_baseline_response(
        request=request,
        status_code=status_code,
        payload=payload,
        latency_ms=17,
    )

    assert observation.classification == expected
    assert observation.latency_ms == 17
    assert set(observation.__dataclass_fields__) == {"classification", "latency_ms"}


def _worker_status(**updates) -> ExternalPiWorkerStatus:
    values = {
        "protocol": "external-pi-v1",
        "worker_id": "staging-blue",
        "instance_id": "10000000-0000-4000-8000-000000000001",
        "release_id": "0123456789ab-staging",
        "state": "ready",
        "active_sessions": 0,
        "maximum_sessions": 8,
        "worker_generation": 7,
        "operation_counters": {
            "shadow_requests": 20,
            "model_calls": 0,
            "tool_calls": 0,
            "provider_calls": 0,
            "modal_calls": 0,
            "billing_events": 0,
        },
        "capability_evidence": {
            "provider_credentials_present": False,
            "modal_credentials_present": False,
            "registered_tool_count": 0,
        },
    }
    values.update(updates)
    return ExternalPiWorkerStatus.model_validate(values)


def _tracker(*, compatible: int, capacity: int, error: int = 0, capacity_ms=41):
    tracker = ExternalPiBaselineTracker()
    for index in range(compatible):
        tracker.record(BaselineObservation("compatible", index + 1))
    for _ in range(capacity):
        tracker.record(BaselineObservation("capacity", capacity_ms))
    for _ in range(error):
        tracker.record(BaselineObservation("error", 3))
    return tracker


def test_external_pi_baseline_reports_safe_fail_fast_overload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = load_external_pi_baseline_config(
        _baseline_environment(tmp_path, monkeypatch)
    )
    after = _worker_status(
        operation_counters={
            **_worker_status().operation_counters.model_dump(),
            "shadow_requests": 120,
        }
    )

    report = finalize_external_pi_baseline(
        config=config,
        before=_worker_status(),
        after=after,
        tracker=_tracker(compatible=8, capacity=92),
    )

    assert report.safety_passed is True
    assert report.capacity_target_passed is False
    assert report.compatible == 8
    assert report.capacity == 92
    assert report.error == 0
    assert report.capacity_max_ms == 41


def test_external_pi_baseline_reports_true_hundred_user_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = load_external_pi_baseline_config(
        _baseline_environment(tmp_path, monkeypatch)
    )
    after = _worker_status(
        operation_counters={
            **_worker_status().operation_counters.model_dump(),
            "shadow_requests": 120,
        }
    )

    report = finalize_external_pi_baseline(
        config=config,
        before=_worker_status(),
        after=after,
        tracker=_tracker(compatible=100, capacity=0),
    )

    assert report.safety_passed is True
    assert report.capacity_target_passed is True
    assert report.latency_p50_ms == 50
    assert report.latency_p95_ms == 95
    assert report.latency_p99_ms == 99


@pytest.mark.parametrize(
    ("tracker", "after_updates"),
    [
        (_tracker(compatible=7, capacity=92, error=1), {}),
        (_tracker(compatible=8, capacity=92, capacity_ms=5_001), {}),
        (_tracker(compatible=8, capacity=92), {"worker_generation": 8}),
        (_tracker(compatible=8, capacity=92), {"active_sessions": 1}),
        (
            _tracker(compatible=8, capacity=92),
            {
                "operation_counters": {
                    **_worker_status().operation_counters.model_dump(),
                    "shadow_requests": 119,
                }
            },
        ),
        (
            _tracker(compatible=8, capacity=92),
            {
                "operation_counters": {
                    **_worker_status().operation_counters.model_dump(),
                    "shadow_requests": 120,
                    "tool_calls": 1,
                }
            },
        ),
        (
            _tracker(compatible=8, capacity=92),
            {
                "capability_evidence": {
                    "provider_credentials_present": True,
                    "modal_credentials_present": False,
                    "registered_tool_count": 0,
                }
            },
        ),
        (
            _tracker(compatible=8, capacity=92),
            {
                "capability_evidence": {
                    "provider_credentials_present": False,
                    "modal_credentials_present": False,
                    "registered_tool_count": 1,
                }
            },
        ),
    ],
)
def test_external_pi_baseline_fails_closed_on_unsafe_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tracker: ExternalPiBaselineTracker,
    after_updates: dict[str, object],
):
    config = load_external_pi_baseline_config(
        _baseline_environment(tmp_path, monkeypatch)
    )
    counter_values = {
        **_worker_status().operation_counters.model_dump(),
        "shadow_requests": 120,
    }
    after_updates = {"operation_counters": counter_values, **after_updates}
    after = _worker_status(**after_updates)

    report = finalize_external_pi_baseline(
        config=config, before=_worker_status(), after=after, tracker=tracker
    )

    assert report.safety_passed is False


def test_external_pi_baseline_report_is_content_free_and_atomically_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environ = _baseline_environment(tmp_path, monkeypatch)
    config = load_external_pi_baseline_config(environ)
    config.report_path.parent.mkdir(parents=True, exist_ok=True)
    config.report_path.write_text('{"complete":"previous"}', encoding="utf-8")
    after = _worker_status(
        operation_counters={
            **_worker_status().operation_counters.model_dump(),
            "shadow_requests": 120,
        }
    )
    report = finalize_external_pi_baseline(
        config=config,
        before=_worker_status(),
        after=after,
        tracker=_tracker(compatible=8, capacity=92),
    )
    serialized = config.report_path.read_text(encoding="utf-8")

    assert report.safety_passed is True
    assert config.report_path.stat().st_mode & 0o777 == 0o600
    for secret in (
        "secret-token-value",
        "request-id-sensitive",
        "entry-id-sensitive",
        "canonical-runtime-prompt",
        "response-body-sensitive",
        "exception-text-sensitive",
    ):
        assert secret not in serialized


def test_external_pi_baseline_rejects_report_outside_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environ = _baseline_environment(tmp_path, monkeypatch)
    environ["PWC_EXTERNAL_PI_BASELINE_REPORT"] = str(tmp_path / "outside.json")

    with pytest.raises(RunRefused, match="retained under staging"):
        load_external_pi_baseline_config(environ)


def test_external_pi_baseline_atomic_failure_preserves_previous_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environ = _baseline_environment(tmp_path, monkeypatch)
    config = load_external_pi_baseline_config(environ)
    previous = '{"complete":"previous"}\n'
    config.report_path.write_text(previous, encoding="utf-8")
    after = _worker_status(
        operation_counters={
            **_worker_status().operation_counters.model_dump(),
            "shadow_requests": 120,
        }
    )

    def fail_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(
        "backend.loadtests.external_pi_shadow_core.os.replace", fail_replace
    )
    with pytest.raises(OSError, match="simulated replace failure"):
        finalize_external_pi_baseline(
            config=config,
            before=_worker_status(),
            after=after,
            tracker=_tracker(compatible=8, capacity=92),
        )

    assert config.report_path.read_text(encoding="utf-8") == previous


def test_external_pi_baseline_locust_adapter_import_is_quiet(capsys, recwarn):
    if importlib.util.find_spec("locust") is None:
        return

    importlib.import_module("backend.loadtests.external_pi_shadow_locustfile")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert not recwarn, [str(warning.message) for warning in recwarn]


def test_external_pi_baseline_status_failure_drops_protected_http_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    if importlib.util.find_spec("locust") is None:
        return
    import httpx

    adapter = importlib.import_module("backend.loadtests.external_pi_shadow_locustfile")
    config = load_external_pi_baseline_config(
        _baseline_environment(tmp_path, monkeypatch)
    )
    request = httpx.Request(
        "GET",
        f"{config.worker_url}/v1/status",
        headers={"Authorization": f"Bearer {config.token}"},
    )
    response = httpx.Response(503, request=request)
    protected_error = httpx.HTTPStatusError(
        "protected transport failure", request=request, response=response
    )

    def fail_status(*_args, **_kwargs):
        raise protected_error

    monkeypatch.setattr(adapter.httpx, "get", fail_status)
    with pytest.raises(RunRefused, match="worker status is invalid") as captured:
        adapter._status(config)

    chain: list[BaseException] = []
    pending: list[BaseException] = [captured.value]
    while pending:
        error = pending.pop()
        chain.append(error)
        if error.__cause__ is not None:
            pending.append(error.__cause__)
        if error.__context__ is not None and error.__context__ not in pending:
            pending.append(error.__context__)
    assert chain == [captured.value]
    assert all(not isinstance(error, httpx.HTTPError) for error in chain)
    assert config.token not in " ".join(repr(error) for error in chain)


def test_external_pi_baseline_duration_has_a_literal_report_bound():
    assert BaselineObservation("compatible", MAX_REPORT_DURATION_MS).latency_ms == (
        MAX_REPORT_DURATION_MS
    )

    with pytest.raises(ValueError, match="bounded report range"):
        BaselineObservation("compatible", MAX_REPORT_DURATION_MS + 1)


@pytest.mark.parametrize(
    ("after_updates", "field"),
    [
        ({"worker_generation": MAX_REPORT_COUNTER + 1}, "worker_generation"),
        (
            {
                "operation_counters": {
                    **_worker_status().operation_counters.model_dump(),
                    "shadow_requests": MAX_REPORT_COUNTER + 1,
                }
            },
            "shadow_requests",
        ),
        (
            {
                "operation_counters": {
                    **_worker_status().operation_counters.model_dump(),
                    "shadow_requests": 120,
                    "provider_calls": MAX_REPORT_COUNTER + 1,
                }
            },
            "provider_calls",
        ),
    ],
)
def test_external_pi_baseline_refuses_unbounded_worker_report_counters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_updates: dict[str, object],
    field: str,
):
    config = load_external_pi_baseline_config(
        _baseline_environment(tmp_path, monkeypatch)
    )
    after = _worker_status(**after_updates)

    with pytest.raises(RunRefused, match="bounded report values"):
        finalize_external_pi_baseline(
            config=config,
            before=_worker_status(),
            after=after,
            tracker=_tracker(compatible=8, capacity=92),
        )

    assert not config.report_path.exists(), field


def test_external_pi_baseline_accepts_literal_maximum_worker_report_counter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = load_external_pi_baseline_config(
        _baseline_environment(tmp_path, monkeypatch)
    )
    before = _worker_status(
        worker_generation=MAX_REPORT_COUNTER,
        operation_counters={
            **_worker_status().operation_counters.model_dump(),
            "shadow_requests": MAX_REPORT_COUNTER - 100,
        },
    )
    after = _worker_status(
        worker_generation=MAX_REPORT_COUNTER,
        operation_counters={
            **_worker_status().operation_counters.model_dump(),
            "shadow_requests": MAX_REPORT_COUNTER,
        },
    )

    report = finalize_external_pi_baseline(
        config=config,
        before=before,
        after=after,
        tracker=_tracker(compatible=8, capacity=92),
    )

    assert report.worker_generation == MAX_REPORT_COUNTER
    assert report.shadow_requests_delta == 100
    assert report.safety_passed is True


def test_external_pi_baseline_status_bypasses_proxies_and_redirects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_shadow_locustfile")
    config = load_external_pi_baseline_config(
        _baseline_environment(tmp_path, monkeypatch)
    )
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return _worker_status().model_dump(mode="json")

    def get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr(adapter.httpx, "get", get)

    assert adapter._status(config) == _worker_status()
    assert captured["trust_env"] is False
    assert captured["follow_redirects"] is False


def test_external_pi_baseline_user_posts_once_without_proxy_or_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_shadow_locustfile")
    config = load_external_pi_baseline_config(
        _baseline_environment(tmp_path, monkeypatch)
    )

    class Response:
        status_code = 503

        def __init__(self):
            self.request_meta = {"name": "external_pi.error"}
            self.succeeded = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def json(self):
            return {"code": "shadow_capacity"}

        def success(self):
            self.succeeded = True

        def failure(self, _message):
            self.succeeded = False

    class Client:
        def __init__(self):
            self.trust_env = True
            self.proxies = {"http": "http://proxy.invalid"}
            self.calls: list[dict[str, object]] = []
            self.response = Response()

        def post(self, path, **kwargs):
            self.calls.append({"path": path, **kwargs})
            return self.response

    client = Client()
    user = object.__new__(adapter.ExternalPiShadowBaselineUser)
    user.client = client
    monkeypatch.setattr(adapter, "_config", config)
    monkeypatch.setattr(adapter, "_tracker", ExternalPiBaselineTracker())
    monkeypatch.setattr(adapter, "_ordinals", iter(range(100)))

    user.on_start()
    with pytest.raises(adapter.StopUser):
        user.run_once()

    assert client.trust_env is False
    assert client.proxies == {}
    assert len(client.calls) == 1
    assert client.calls[0]["allow_redirects"] is False
    assert client.response.request_meta["name"] == "external_pi.capacity"
    assert client.response.succeeded is True
    assert len(adapter._tracker.observations) == 1
    assert adapter._tracker.observations[0].classification == "capacity"


@pytest.mark.parametrize("changed_pointer", ["current", "active"])
def test_external_pi_baseline_topology_revalidation_refuses_pointer_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_pointer: str,
):
    config = load_external_pi_baseline_config(
        _baseline_environment(tmp_path, monkeypatch)
    )
    staging = tmp_path / "srv/paperswithcode/environments/staging"
    pointer = staging / changed_pointer
    pointer.unlink()
    if changed_pointer == "current":
        replacement = tmp_path / "srv/paperswithcode/releases/fedcba987654-staging"
        replacement.mkdir()
    else:
        replacement = staging / "slots/green"
        replacement.mkdir()
        replacement.joinpath("release").symlink_to(config.release)
    pointer.symlink_to(replacement)

    with pytest.raises(RunRefused, match="exact active immutable staging topology"):
        validate_external_pi_baseline_topology(config)


def test_external_pi_baseline_adapter_stop_revalidates_before_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_shadow_locustfile")
    config = load_external_pi_baseline_config(
        _baseline_environment(tmp_path, monkeypatch)
    )
    before = _worker_status()
    events: list[str] = []
    monkeypatch.setattr(adapter, "_config", config)
    monkeypatch.setattr(adapter, "_before", before)
    monkeypatch.setattr(
        adapter,
        "validate_external_pi_baseline_topology",
        lambda _config: events.append("topology"),
    )
    monkeypatch.setattr(
        adapter, "_status", lambda _config: events.append("status") or before
    )
    monkeypatch.setattr(
        adapter,
        "finalize_external_pi_baseline",
        lambda **_kwargs: (
            events.append("report") or SimpleNamespace(safety_passed=True)
        ),
    )
    environment = SimpleNamespace(process_exit_code=None)

    adapter._stop(environment)

    assert events == ["topology", "status", "topology", "report"]
    assert environment.process_exit_code == 0

    events.clear()

    def changed_topology(_config):
        events.append("topology")
        raise RunRefused("topology changed")

    monkeypatch.setattr(
        adapter, "validate_external_pi_baseline_topology", changed_topology
    )
    adapter._stop(environment)

    assert events == ["topology"]
    assert environment.process_exit_code == 1
