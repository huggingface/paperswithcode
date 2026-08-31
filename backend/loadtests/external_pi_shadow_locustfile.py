"""Thin Locust adapter for the staging-only external Pi overload baseline."""

from __future__ import annotations

import itertools
import os
import time
import warnings

from gevent.monkey import MonkeyPatchWarning

with warnings.catch_warnings():
    # Pytest imports the dependency-free core (and therefore ssl/httpx) before
    # import-smoking this adapter. The real Locust process has already patched.
    warnings.simplefilter("ignore", MonkeyPatchWarning)
    from locust import HttpUser, between, events, task
    from locust.exception import StopUser
    from locust.runners import LocalRunner

import httpx
from requests.exceptions import RequestException

from backend.loadtests.external_pi_shadow_core import (
    EXPECTED_SPAWN_RATE,
    EXPECTED_USERS,
    BaselineObservation,
    ExternalPiBaselineConfig,
    ExternalPiBaselineTracker,
    RunRefused,
    build_external_pi_baseline_request,
    classify_external_pi_baseline_response,
    finalize_external_pi_baseline,
    load_external_pi_baseline_config,
    validate_external_pi_baseline_topology,
)
from backend.services.chat_external_pi_shadow import ExternalPiWorkerStatus

_ordinals = itertools.count()
_config: ExternalPiBaselineConfig | None = None
_before: ExternalPiWorkerStatus | None = None
_tracker = ExternalPiBaselineTracker()


def _read_status(config: ExternalPiBaselineConfig) -> ExternalPiWorkerStatus | None:
    try:
        response = httpx.get(
            f"{config.worker_url}/v1/status",
            headers={"Authorization": f"Bearer {config.token}"},
            timeout=5.0,
            follow_redirects=False,
            trust_env=False,
        )
        response.raise_for_status()
        return ExternalPiWorkerStatus.model_validate(response.json())
    except (httpx.HTTPError, ValueError):
        return None


def _status(config: ExternalPiBaselineConfig) -> ExternalPiWorkerStatus:
    status = _read_status(config)
    if status is None:
        raise RunRefused("external Pi baseline worker status is invalid")
    return status


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1_000))


@events.test_start.add_listener
def _start(environment, **_kwargs) -> None:
    global _config, _before, _tracker, _ordinals
    if not isinstance(environment.runner, LocalRunner):
        raise RunRefused("external Pi baseline requires one local Locust runner")
    options = environment.parsed_options
    if (
        getattr(options, "num_users", None) != EXPECTED_USERS
        or getattr(options, "spawn_rate", None) != EXPECTED_SPAWN_RATE
    ):
        raise RunRefused(
            "external Pi baseline requires exactly 100 users at spawn rate 100.0"
        )
    config = load_external_pi_baseline_config(os.environ)
    validate_external_pi_baseline_topology(config)
    if environment.host != config.worker_url:
        raise RunRefused(
            "external Pi baseline requires the active staging worker endpoint"
        )
    before = _status(config)
    if (
        before.protocol != "external-pi-v1"
        or before.state != "ready"
        or before.release_id != config.release_id
        or before.worker_id != config.worker_id
        or before.maximum_sessions != 8
        or before.active_sessions != 0
        or before.worker_generation is None
        or before.capability_evidence.provider_credentials_present
        or before.capability_evidence.modal_credentials_present
        or before.capability_evidence.registered_tool_count != 0
        or any(
            (
                before.operation_counters.model_calls,
                before.operation_counters.tool_calls,
                before.operation_counters.provider_calls,
                before.operation_counters.modal_calls,
                before.operation_counters.billing_events,
            )
        )
    ):
        raise RunRefused("external Pi baseline initial worker evidence is unsafe")
    _config = config
    _before = before
    _tracker = ExternalPiBaselineTracker()
    _ordinals = itertools.count()


class ExternalPiShadowBaselineUser(HttpUser):
    host = None
    wait_time = between(0, 0)

    def on_start(self) -> None:
        self.client.trust_env = False
        self.client.proxies.clear()

    @task
    def run_once(self) -> None:
        config = _config
        if config is None:
            raise StopUser()
        ordinal = next(_ordinals)
        if ordinal >= EXPECTED_USERS:
            raise StopUser()
        request = build_external_pi_baseline_request(ordinal, config.prompt)
        started = time.perf_counter()
        observation = BaselineObservation("error", 0)
        try:
            with self.client.post(
                "/v1/shadow",
                headers={"Authorization": f"Bearer {config.token}"},
                json=request.wire_payload(),
                name="external_pi.error",
                catch_response=True,
                timeout=10.0,
                allow_redirects=False,
            ) as response:
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                observation = classify_external_pi_baseline_response(
                    request=request,
                    status_code=response.status_code,
                    payload=payload,
                    latency_ms=_elapsed_ms(started),
                )
                response.request_meta["name"] = (
                    f"external_pi.{observation.classification}"
                )
                if observation.classification == "error":
                    response.failure("external_pi.error")
                else:
                    response.success()
        except RequestException:
            observation = BaselineObservation("error", _elapsed_ms(started))
        _tracker.record(observation)
        raise StopUser()


@events.test_stop.add_listener
def _stop(environment, **_kwargs) -> None:
    environment.process_exit_code = 1
    if _config is None or _before is None:
        return
    try:
        validate_external_pi_baseline_topology(_config)
        after = _status(_config)
        validate_external_pi_baseline_topology(_config)
        report = finalize_external_pi_baseline(
            config=_config,
            before=_before,
            after=after,
            tracker=_tracker,
        )
    except (OSError, RunRefused, ValueError):
        return
    if report.safety_passed:
        environment.process_exit_code = 0
