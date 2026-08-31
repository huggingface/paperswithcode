"""Thin Locust adapter for the operator-only staging chat profiles."""

from __future__ import annotations

import hashlib
import itertools
import os
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from locust import HttpUser, User, between, events, task
from locust.exception import StopUser
from locust.runners import LocalRunner
from requests.exceptions import RequestException
from sqlalchemy.exc import SQLAlchemyError

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.loadtests.chat_core import (
    STAGING_RUNTIME_ENV_PATH,
    BoundedSSEStream,
    Metric,
    ProfileObservationTracker,
    RunRefused,
    SSEParseError,
    build_turn_request,
    classify_refusal_bytes,
    load_run_config,
    validate_runtime_shape,
)
from backend.loadtests.durable_bridge_probe import (
    TwoPartyOverlapGate,
    run_durable_bridge_probe,
)
from backend.scripts.qualify_chat_durable_dispatch import (
    CONFIRMATION as QUALIFICATION_CONFIRMATION,
)
from backend.scripts.qualify_chat_durable_dispatch import (
    QualificationRefused,
    SchemaAudit,
    inspect_postgresql_contract,
    validate_operator_context,
)
from deploy.release import validate_manifest

CONFIG = load_run_config(
    os.environ,
    budget_path=STAGING_RUNTIME_ENV_PATH,
    expected_budget_path=STAGING_RUNTIME_ENV_PATH,
    expected_budget_owner_uid=0,
)
ACTIVE_STAGING_RELEASE = Path("/srv/paperswithcode/environments/staging/current")
IMMUTABLE_RELEASE_ROOT = Path("/srv/paperswithcode/releases")
_credential_counter = itertools.count()
_identity_nonce = uuid.uuid4().hex
_bridge_overlap_gate = TwoPartyOverlapGate()


@dataclass(frozen=True, slots=True)
class BridgeRuntime:
    release_id: str
    worker_contract_version: str
    schema_audit: SchemaAudit


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _record(user: User, metric: Metric) -> None:
    user.environment.events.request.fire(
        request_type="CHAT",
        name=metric.name,
        response_time=metric.elapsed_ms,
        response_length=0,
        exception=None if metric.success else RuntimeError(metric.name),
    )


def _record_refusal(user: User, label: str, started: float) -> None:
    _record(user, Metric(f"chat.{label}", _elapsed_ms(started), False))


def _load_bridge_runtime() -> BridgeRuntime:
    """Bind the DB probe to the exact active, protected staging runtime."""

    try:
        metadata = STAGING_RUNTIME_ENV_PATH.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_mode & 0o022
        ):
            raise RunRefused("protected staging runtime metadata is invalid")
        active_release = ACTIVE_STAGING_RELEASE.resolve(strict=True)
        active_release.relative_to(IMMUTABLE_RELEASE_ROOT)
        source_release = Path(__file__).resolve().parents[2]
        if source_release != active_release:
            raise RunRefused(
                "load harness is not running from the active staging release"
            )
        manifest = validate_manifest(active_release, "staging")
        release_id = manifest.get("release_id")
        runtime = manifest.get("chat_runtime")
        worker_contract = (
            runtime.get("worker_contract_version")
            if isinstance(runtime, dict)
            else None
        )
        if not isinstance(release_id, str) or not isinstance(worker_contract, str):
            raise RunRefused("immutable staging bridge contract is missing")
        settings = get_settings()
        validate_operator_context(
            confirmation=QUALIFICATION_CONFIRMATION,
            environment=settings,
            release_id=release_id,
            worker_contract_version=worker_contract,
        )
        with db_manager.session_local() as db:
            audit = inspect_postgresql_contract(db)
        return BridgeRuntime(release_id, worker_contract, audit)
    except (OSError, ValueError, QualificationRefused, SQLAlchemyError) as error:
        raise RunRefused("durable bridge runtime validation failed") from error


@events.test_start.add_listener
def _validate_runtime(environment, **_kwargs) -> None:
    if environment.host != CONFIG.host:
        raise RunRefused("Locust host changed after the exact staging-origin gate")
    validate_runtime_shape(
        CONFIG.profile,
        users=getattr(environment.parsed_options, "num_users", None),
        spawn_rate=getattr(environment.parsed_options, "spawn_rate", None),
    )
    if CONFIG.profile.cohort == "durable-bridge" and not isinstance(
        environment.runner, LocalRunner
    ):
        raise RunRefused("durable bridge requires one process-local Locust runner")


class StagingBridgeUser(User):
    abstract = CONFIG.profile.cohort != "durable-bridge"
    wait_time = between(1, 2)

    def on_start(self) -> None:
        index = next(_credential_counter)
        cookie = CONFIG.synthetic_cookies[index % len(CONFIG.synthetic_cookies)]
        digest = hashlib.sha256(
            f"{_identity_nonce}:{index}:{cookie}".encode()
        ).hexdigest()
        self.opaque_identity = f"loadtest-{digest}"

    @task
    def run_profile_once(self) -> None:
        started = time.perf_counter()
        try:
            runtime = _load_bridge_runtime()
            result = run_durable_bridge_probe(
                session_factory=db_manager.session_local,
                settings=get_settings(),
                release_id=runtime.release_id,
                worker_contract_version=runtime.worker_contract_version,
                schema_audit=runtime.schema_audit,
                opaque_identity=self.opaque_identity,
                overlap_gate=_bridge_overlap_gate,
            )
            for metric in result.metrics:
                _record(self, metric)
        except RunRefused:
            for name in ("admission", "ownership", "overlap", "terminal"):
                _record(self, Metric(f"bridge.{name}", _elapsed_ms(started), False))
            _record(self, Metric("bridge.cleanup", _elapsed_ms(started), True))
        raise StopUser()


class StagingChatUser(HttpUser):
    abstract = CONFIG.profile.cohort == "durable-bridge"
    host = CONFIG.host
    wait_time = between(1, 2)

    def on_start(self) -> None:
        index = next(_credential_counter)
        cookie_index = 0 if CONFIG.profile.same_account else index
        self.client.cookies.set(
            "pwc_staging_session",
            CONFIG.synthetic_cookies[cookie_index % len(CONFIG.synthetic_cookies)],
            domain="staging.paperswithcode.co",
            secure=True,
        )

    @task
    def run_profile_once(self) -> None:
        if CONFIG.profile.cohort == "availability":
            self._availability_connectivity()
        else:
            self._stream_turn()
        raise StopUser()

    def _availability_connectivity(self) -> None:
        with self.client.get(
            "/api/v1/chat/availability",
            name=f"{CONFIG.profile.metric_label}/availability",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure("availability check failed")

    def _stream_turn(self) -> None:
        started = time.perf_counter()
        body = build_turn_request(
            CONFIG.profile,
            client_message_id=f"load-{uuid.uuid4()}",
            max_prompt_chars=CONFIG.max_prompt_chars,
            initial_model=CONFIG.initial_model,
        )
        with self.client.post(
            "/api/v1/chat/stream",
            json=body,
            headers={"Accept": "text/event-stream"},
            stream=True,
            name=f"{CONFIG.profile.metric_label}/response_headers",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                label = classify_refusal_bytes(response.raw.read(4097))
                _record_refusal(self, label, started)
                response.failure(f"typed refusal: {label}")
                return
            response.success()
            session_id = self._drain_sse_response(
                response,
                started,
                stop_after_admission=CONFIG.profile.cohort == "reconnect",
            )
            if CONFIG.profile.cohort == "reconnect":
                response.close()
                self._resume(session_id)

    def _drain_sse_response(
        self,
        response,
        started: float,
        *,
        replay: bool = False,
        stop_after_admission: bool = False,
    ) -> str | None:
        stream = BoundedSSEStream(
            max_output_chars=CONFIG.max_output_chars,
            replay=replay,
        )
        observations = ProfileObservationTracker(CONFIG.profile)
        try:
            for chunk in response.iter_content(
                chunk_size=1 if stop_after_admission else 4096
            ):
                batch = stream.feed(chunk, elapsed_ms=_elapsed_ms(started))
                for metric in batch.metrics:
                    _record(self, metric)
                for event in batch.events:
                    if not replay:
                        for metric in observations.observe(
                            event, elapsed_ms=_elapsed_ms(started)
                        ):
                            _record(self, metric)
                    if stop_after_admission and event.get("type") == "stream_start":
                        value = event.get("session_id")
                        return value if isinstance(value, str) else None
                if stream.finished:
                    return None
            batch = stream.close(elapsed_ms=_elapsed_ms(started))
            for metric in batch.metrics:
                _record(self, metric)
            for event in batch.events:
                if not replay:
                    for metric in observations.observe(
                        event, elapsed_ms=_elapsed_ms(started)
                    ):
                        _record(self, metric)
        except (SSEParseError, RequestException):
            _record_refusal(self, "stream_error", started)
            return None
        if not stream.finished:
            _record_refusal(self, "stream_error", started)
        return None

    def _resume(self, session_id: str | None) -> None:
        started = time.perf_counter()
        if not session_id:
            _record(self, Metric("chat.reconnect", 0, False))
            _record_refusal(self, "stream_error", started)
            return
        with self.client.get(
            f"/api/v1/chat/sessions/{quote(session_id, safe='')}/stream",
            headers={"Accept": "text/event-stream"},
            stream=True,
            name=f"{CONFIG.profile.metric_label}/reconnect_headers",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure("reconnect failed")
                _record(self, Metric("chat.reconnect", _elapsed_ms(started), False))
                _record_refusal(self, "stream_error", started)
                return
            response.success()
            _record(self, Metric("chat.reconnect", _elapsed_ms(started), True))
            self._drain_sse_response(response, started, replay=True)
