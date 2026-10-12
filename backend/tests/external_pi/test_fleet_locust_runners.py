"""Locust adapters and local and live fleet runners."""

from __future__ import annotations

import importlib
import importlib.util
import json
import threading
import uuid
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from backend.loadtests.external_pi_fleet_core import (
    FleetRunRefused,
    resolve_fleet_shape,
    resolve_durable_profile,
)
from backend.tests.external_pi.fleet_harness import (
    _FUNCTIONAL_MODAL,
    _LifecycleSource,
    _MODAL_RATE,
    _NO_MODAL,
)


def test_fleet_locust_adapter_import_is_quiet(capsys, recwarn):
    if importlib.util.find_spec("locust") is None:
        return

    importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert not recwarn, [str(warning.message) for warning in recwarn]


def test_durable_locust_specs_start_every_user_immediately_without_queue():
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    functional = adapter.build_durable_user_specs("32-functional-turns")
    admission = adapter.build_durable_user_specs("100-immediate-admission")

    assert [item.ordinal for item in functional] == list(range(32))
    assert Counter(item.workload for item in functional) == Counter(
        {"no_tool": 16, "read": 8, "bash": 8}
    )
    assert [item.ordinal for item in admission] == list(range(100))
    assert {item.workload for item in admission} == {"admission_stream"}
    assert all(item.arrival_delay_ms == 0 for item in functional + admission)
    assert all(item.application_queue is False for item in functional + admission)


def test_durable_locust_measurement_requires_content_free_typed_outcomes():
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    observation = adapter.build_durable_observation(
        workload="bash",
        outcome="completed",
        ttft_ms=125,
        completion_ms=2_500,
        reconnects=1,
        reconnect_successes=1,
        model_starts=1,
        operation_start_ids=("op-0001", "op-0002"),
        queued_states=0,
        stale_mutations=0,
        duplicate_turns=0,
        terminal_cause="completed",
        failure_code=None,
    )

    assert observation.ttft_ms == 125
    assert observation.terminal_cause == "completed"
    assert observation.operation_start_count == 2
    assert observation.duplicate_operation_start_count == 0
    secret = "TOP_SECRET_PROMPT"
    with pytest.raises(FleetRunRefused) as exc:
        adapter.build_durable_observation(
            workload="bash",
            outcome="completed",
            ttft_ms=125,
            completion_ms=2_500,
            reconnects=0,
            reconnect_successes=0,
            model_starts=1,
            operation_start_ids=(),
            queued_states=0,
            stale_mutations=0,
            duplicate_turns=0,
            terminal_cause="completed",
            failure_code=None,
            prompt=secret,
        )
    assert secret not in str(exc.value)
    invalid = {
        "workload": "bash",
        "outcome": "completed",
        "ttft_ms": 125,
        "completion_ms": 2_500,
        "reconnects": 0,
        "reconnect_successes": 0,
        "model_starts": 1,
        "operation_start_ids": (),
        "queued_states": 0,
        "stale_mutations": 0,
        "duplicate_turns": 0,
        "terminal_cause": "completed",
        "failure_code": secret,
    }
    with pytest.raises(FleetRunRefused) as exc:
        adapter.build_durable_observation(**invalid)
    assert secret not in str(exc.value)


def test_durable_locust_measurement_accepts_typed_refusal_without_milestones():
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    observation = adapter.build_durable_observation(
        workload="admission_stream",
        outcome="refused",
        ttft_ms=125,
        completion_ms=125,
        reconnects=0,
        reconnect_successes=0,
        model_starts=0,
        duplicate_turns=0,
        terminal_cause="refused",
        failure_code="chat_overload",
    )

    assert observation.outcome == "refused"
    assert observation.admission_ms is None
    assert observation.reconnect_ready_ms is None


def test_durable_locust_observation_counts_duplicate_operation_identity():
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    observation = adapter.build_durable_observation(
        workload="bash",
        outcome="completed",
        ttft_ms=100,
        completion_ms=1_000,
        reconnects=0,
        reconnect_successes=0,
        model_starts=1,
        operation_start_ids=("op-0001", "op-0002", "op-0001"),
        queued_states=0,
        stale_mutations=0,
        duplicate_turns=0,
        terminal_cause="completed",
        failure_code=None,
    )

    assert observation.operation_start_count == 2
    assert observation.duplicate_operation_start_count == 1


@pytest.mark.parametrize(
    ("profile_name", "expected_users", "expected_mix", "sandboxes"),
    (
        (
            "32-functional-turns",
            32,
            Counter({"no_tool": 16, "read": 8, "bash": 8}),
            16,
        ),
        (
            "100-immediate-admission",
            100,
            Counter({"admission_stream": 100}),
            0,
        ),
    ),
)
def test_executable_durable_locust_runner_releases_exact_simultaneous_profile(
    profile_name, expected_users, expected_mix, sandboxes
):
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    calls = []

    class Transport:
        def open_durable_stream(self, spec):
            calls.append(
                (
                    spec.ordinal,
                    spec.workload,
                    adapter._durable_barrier_arrivals,
                    spec.arrival_delay_ms,
                    spec.application_queue,
                )
            )
            operation_ids = (
                (f"op-{spec.ordinal:04d}-1", f"op-{spec.ordinal:04d}-2")
                if spec.workload == "bash"
                else ((f"op-{spec.ordinal:04d}-1",) if spec.workload == "read" else ())
            )
            return {
                "workload": spec.workload,
                "outcome": "completed",
                "ttft_ms": 100,
                "completion_ms": 1_000,
                "reconnects": 0,
                "reconnect_successes": 0,
                "model_starts": 1,
                "operation_start_ids": operation_ids,
                "queued_states": 0,
                "stale_mutations": 0,
                "duplicate_turns": 0,
                "terminal_cause": "completed",
                "failure_code": None,
            }

    report = adapter.run_local_durable_profile(
        profile_name=profile_name,
        transport=Transport(),
        resources=adapter.DurableRunResources(
            peak_memory_bytes=1024**3,
            minimum_host_mem_available_bytes=2 * 1024**3,
            peak_cpu_percent=20.0,
            peak_active_backend_turns=expected_users,
            peak_active_external_workers=4,
            peak_active_sandboxes=sandboxes,
        ),
        lifecycle_source=_LifecycleSource(
            _FUNCTIONAL_MODAL if profile_name == "32-functional-turns" else _NO_MODAL
        ),
        modal_rate=_MODAL_RATE,
        timeout_seconds=10.0,
    )

    assert report.passed is True
    assert len(calls) == expected_users
    assert Counter(workload for _, workload, *_ in calls) == expected_mix
    assert {arrivals for _, _, arrivals, _, _ in calls} == {expected_users}
    assert all(delay == 0 and queued is False for *_, delay, queued in calls)
    assert report.operation_start_count == (24 if expected_users == 32 else 0)
    assert report.duplicate_operation_start_count == 0


def test_live_durable_runner_constructs_real_transport_and_accepts_no_fake(monkeypatch):
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    from backend.loadtests.durable_chat_transport import (
        DurableChatTransportConfig,
        HttpSSEDurableChatTransport,
    )

    captured = {}

    def run_observations(**kwargs):
        captured.update(kwargs)
        return ()

    monkeypatch.setattr(adapter, "_run_durable_observations", run_observations)
    config = DurableChatTransportConfig(
        base_url="https://staging.paperswithcode.co",
        synthetic_cookies=("signed-cookie",),
        initial_model="gpt-5.6-luna@openai",
        qualification_run_id="run",
        admin_token="a" * 32,
    )

    scope_id = uuid.uuid4()
    result = adapter.run_live_durable_profile(
        profile_name="32-functional-turns",
        transport_config=config,
        resources=adapter.DurableRunResources(1, 2 * 1024**3, 1.0, 32, 4, 0),
        qualification_scope_id=scope_id,
    )

    assert result.profile_name == "32-functional-turns"
    assert type(captured["transport"]) is HttpSSEDurableChatTransport
    assert "/v1/shadow" not in repr(captured)


def test_guarded_live_operator_delegates_run_only_to_live_runner(monkeypatch):
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    from backend.loadtests.durable_chat_transport import DurableChatTransportConfig
    from backend.scripts.qualify_durable_external_turns import (
        GuardedLiveDurableOperator,
    )

    profile = resolve_durable_profile("32-functional-turns")
    resources = adapter.DurableRunResources(1, 2 * 1024**3, 1.0, 32, 4, 0)
    control = SimpleNamespace(
        run_resources=lambda selected: resources,
        environment=lambda: SimpleNamespace(target_release="0123456789ab-staging"),
    )
    captured = {}

    def run_live(**kwargs):
        captured.update(kwargs)
        return "profile-report"

    monkeypatch.setattr(adapter, "run_live_durable_profile", run_live)
    operator = GuardedLiveDurableOperator(
        control_plane=control,
        transport_config=DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("signed-cookie",),
            initial_model="gpt-5.6-luna@openai",
            qualification_run_id="run",
            admin_token="a" * 32,
        ),
    )
    scope_id = uuid.uuid4()
    operator.evidence_source = SimpleNamespace(
        begin_scope=lambda _profile: {
            "scope_id": scope_id,
            "app_release_id": "0123456789ab-staging",
        }
    )

    assert operator.run_profile(profile) == "profile-report"
    assert captured["profile_name"] == profile.name
    assert captured["resources"] is resources
    assert captured["qualification_scope_id"] == scope_id


def test_guarded_live_teardown_requires_and_evicts_only_the_exact_scope():
    from backend.loadtests.durable_chat_transport import DurableChatTransportConfig
    from backend.scripts.qualify_durable_external_turns import (
        GuardedLiveDurableOperator,
        QualificationRefused,
    )

    profile = resolve_durable_profile("32-functional-turns")
    operator = GuardedLiveDurableOperator(
        control_plane=SimpleNamespace(),
        transport_config=DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("signed-cookie",),
            initial_model="gpt-5.6-luna@openai",
            qualification_run_id="run",
            admin_token="a" * 32,
        ),
    )
    exact_scope = uuid.uuid4()
    calls = []
    operator._scopes[profile.name] = exact_scope
    operator.evidence_source = SimpleNamespace(
        teardown=lambda scope_id: calls.append(scope_id)
    )

    with pytest.raises(QualificationRefused, match="qualification_scope_invalid"):
        operator.teardown_profile(profile, uuid.uuid4())
    operator.teardown_profile(profile, exact_scope)
    assert calls == [exact_scope]


def test_guarded_live_finalization_attests_static_rate_inside_closed_scope_window(
    monkeypatch,
):
    pytest.importorskip("locust")
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    from backend.loadtests.durable_chat_transport import DurableChatTransportConfig
    from backend.scripts.qualify_durable_external_turns import (
        GuardedLiveDurableOperator,
    )

    scope_id = uuid.uuid4()
    captured = {}
    monkeypatch.setattr(
        adapter,
        "finalize_live_durable_profile",
        lambda measurement, **kwargs: captured.update(kwargs)
        or SimpleNamespace(modal_estimated_cost_microusd=1),
    )
    operator = GuardedLiveDurableOperator(
        control_plane=SimpleNamespace(
            environment=lambda: SimpleNamespace(target_release="0123456789ab-staging"),
            protected_runtime_evidence=lambda _profile: {
                "PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND": "25",
                "PWC_MODAL_EXECUTOR_RATE_SOURCE_ID": "modal-staging-price-v1",
                "PWC_RELEASE_ID": "0123456789ab-staging",
            },
        ),
        transport_config=DurableChatTransportConfig(
            base_url="https://staging.paperswithcode.co",
            synthetic_cookies=("cookie",),
            initial_model="gpt-5.6-luna@openai",
            qualification_run_id="run",
            admin_token="a" * 32,
        ),
    )
    operator.evidence_source = SimpleNamespace(
        collect=lambda _scope_id: SimpleNamespace(
            window_started_at_ms=10,
            window_ended_at_ms=20,
        )
    )

    result = operator.finalize_profile(
        resolve_durable_profile("32-functional-turns"),
        SimpleNamespace(qualification_scope_id=scope_id),
    )

    assert result.modal_estimated_cost_microusd == 1
    assert captured["modal_rate"].attested_at_ms == 20


def test_fleet_locust_requires_one_local_exact_configured_user_runner(monkeypatch):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    shape = resolve_fleet_shape("5x32")
    adapter.configure_fleet_round(
        replicas=shape.replicas,
        prompt="canonical-runtime-prompt",
        token="protected-worker-token",
    )
    environment = SimpleNamespace(
        runner=object(),
        parsed_options=SimpleNamespace(num_users=100, spawn_rate=100.0),
        host=None,
    )
    with pytest.raises(FleetRunRefused, match="one local Locust runner"):
        adapter._start(environment)

    environment.runner = object.__new__(adapter.LocalRunner)
    environment.runner.greenlet = None
    for users, spawn_rate, host in (
        (99, 100.0, None),
        (100, 99.0, None),
        (100, 100.0, "https://staging.paperswithcode.co"),
    ):
        environment.parsed_options = SimpleNamespace(
            num_users=users, spawn_rate=spawn_rate
        )
        environment.host = host
        with pytest.raises(FleetRunRefused, match="exact configured|must not accept"):
            adapter._start(environment)


def test_fleet_locust_routes_each_one_shot_user_directly_without_proxy_or_redirect(
    monkeypatch,
):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    shape = resolve_fleet_shape("5x32")

    class Response:
        status_code = 503

        def __init__(self):
            self.request_meta = {"name": "external_pi.error"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def json(self):
            return {"code": "shadow_capacity"}

        def success(self):
            return None

        def failure(self, _message):
            return None

    class Client:
        def __init__(self):
            self.trust_env = True
            self.proxies = {"http": "http://proxy.invalid"}
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append({"url": url, **kwargs})
            return Response()

    adapter.configure_fleet_round(
        replicas=shape.replicas,
        prompt="canonical-runtime-prompt",
        token="protected-worker-token",
    )
    adapter._barrier_arrivals = 98
    adapter._arrival_gate.set()
    monkeypatch.setattr(adapter, "_ordinals", iter((0, 5)))
    client = Client()
    for _ in range(2):
        user = object.__new__(adapter.ExternalPiFleetUser)
        user.client = client
        user.on_start()
        with pytest.raises(adapter.StopUser):
            user.run_once()

    assert client.trust_env is False
    assert client.proxies == {}
    assert [call["url"] for call in client.calls] == [
        "http://127.0.0.1:8780/v1/shadow",
        "http://127.0.0.1:8780/v1/shadow",
    ]
    assert all(call["allow_redirects"] is False for call in client.calls)
    assert all("response" not in call and "body" not in call for call in client.calls)
    assert len(adapter.fleet_round_result().observations) == 2


@pytest.mark.parametrize(
    ("shape_name", "expected_users", "expected_per_worker"),
    (("5x32", 100, 20), ("2x32", 32, 16)),
)
def test_fleet_local_runner_completes_exact_balanced_profile_over_loopback(
    shape_name: str, expected_users: int, expected_per_worker: int
):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    counts = Counter()
    state = {"in_flight": 0, "peak": 0}
    arrivals_at_request = []
    aggregate_gate = threading.Event()
    aggregate_lock = threading.Lock()
    servers = []
    threads = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            with aggregate_lock:
                state["in_flight"] += 1
                state["peak"] = max(state["peak"], state["in_flight"])
                arrivals_at_request.append(adapter._barrier_arrivals)
                if state["in_flight"] == expected_users:
                    aggregate_gate.set()
            try:
                if not aggregate_gate.wait(timeout=10):
                    self.send_error(503)
                    return
                length = int(self.headers["Content-Length"])
                request = json.loads(self.rfile.read(length))
                with aggregate_lock:
                    counts[self.server.server_port] += 1
                response = {
                    "type": "shadow_projection",
                    "protocol_version": 1,
                    "request_id": request["request_id"],
                    "chat_session_id": request["chat_session_id"],
                    "agent_session_id": request["agent_session_id"],
                    "current_leaf_id": request["current_leaf_id"],
                    "entry_count": len(request["transcript_entries"]),
                    "transcript_sha256": request["expected_transcript_sha256"],
                    "prompt_sha256": request["expected_prompt_sha256"],
                    "tool_names_sha256": request["expected_tool_names_sha256"],
                }
                body = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            finally:
                with aggregate_lock:
                    state["in_flight"] -= 1

        def log_message(self, *_args):
            return None

    class HighBacklogServer(ThreadingHTTPServer):
        request_queue_size = 128

    try:
        shape = resolve_fleet_shape(shape_name)
        for replica in shape.replicas:
            port = replica.port
            server = HighBacklogServer(("127.0.0.1", port), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            servers.append(server)
            threads.append(thread)
        result = adapter.run_local_fleet_round(
            replicas=shape.replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
            expected_users=expected_users,
            timeout_seconds=20,
        )
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)

    assert len(result.observations) == expected_users
    assert all(item.classification == "compatible" for item in result.observations)
    assert result.protocol_errors == result.transport_errors == 0
    assert state["peak"] == expected_users
    assert set(arrivals_at_request) == {expected_users}
    assert counts == Counter(
        {replica.port: expected_per_worker for replica in shape.replicas}
    )


def test_fleet_local_runner_validates_before_start(monkeypatch):
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    started = False

    def reject(_environment):
        raise FleetRunRefused("runner invariant")

    def start(*_args, **_kwargs):
        nonlocal started
        started = True

    monkeypatch.setattr(adapter, "_validate_runner", reject)
    monkeypatch.setattr(adapter.LocalRunner, "start", start)
    with pytest.raises(FleetRunRefused, match="runner invariant"):
        adapter.run_local_fleet_round(
            replicas=resolve_fleet_shape("5x32").replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
        )
    assert started is False


def test_fleet_local_runner_timeout_refuses_incomplete_real_round():
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")
    timestamps = iter((0.0, 31.0))

    with pytest.raises(FleetRunRefused, match="round timed out"):
        adapter.run_local_fleet_round(
            replicas=resolve_fleet_shape("5x32").replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
            timeout_seconds=30,
            monotonic=lambda: next(timestamps),
        )


def test_fleet_local_runner_barrier_timeout_releases_without_requests():
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    with pytest.raises(FleetRunRefused, match="barrier.*timed out"):
        adapter.run_local_fleet_round(
            replicas=resolve_fleet_shape("5x32").replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
            timeout_seconds=5,
            barrier_timeout_seconds=0.001,
        )

    assert adapter._arrival_gate.is_set()
    assert adapter.fleet_round_result().observations == ()


def test_fleet_local_runner_abort_releases_barrier_and_cannot_pass():
    if importlib.util.find_spec("locust") is None:
        return
    adapter = importlib.import_module("backend.loadtests.external_pi_fleet_locustfile")

    with pytest.raises(FleetRunRefused, match="aborted"):
        adapter.run_local_fleet_round(
            replicas=resolve_fleet_shape("5x32").replicas,
            prompt="canonical-runtime-prompt",
            token="protected-worker-token",
            timeout_seconds=5,
            abort_requested=lambda: True,
        )

    assert adapter._arrival_gate.is_set()
    assert len(adapter.fleet_round_result().observations) < 100
