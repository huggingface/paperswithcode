"""Host evidence and safety gates for durable external-turn qualification."""

from __future__ import annotations

import contextlib
import math
import re
import signal
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from backend.loadtests.external_pi_fleet_core import (
    DurableQualificationReport,
)
from backend.loadtests.durable_chat_transport import DurableChatTransportConfig

_STAGING_RELEASE = re.compile(r"^[0-9a-f]{12}-staging$")
_MIN_APPROVED_HOST_MEMORY_BYTES = 15 * 1024**3
_MAX_APPROVED_HOST_MEMORY_BYTES = 17 * 1024**3
CONFIRMATION = "QUALIFY_STAGING_DURABLE_EXTERNAL_TURNS"
DURABLE_REPORT_ROOT = Path("/var/lib/paperswithcode/staging")
DURABLE_REPORT_PATH = DURABLE_REPORT_ROOT / "durable-external-turn-qualification.json"
MODAL_RATE_EVIDENCE_PATH = Path("/etc/paperswithcode/staging-modal-rate-evidence.json")


class QualificationRefused(RuntimeError):
    """The durable-turn qualification would violate an operator gate."""


class DurableQualificationInterrupted(QualificationRefused):
    """SIGINT or SIGTERM interrupted the qualification transaction."""

    def __init__(self, signal_number: int) -> None:
        super().__init__("durable_qualification_interrupted")
        self.signal_number = signal_number


@contextlib.contextmanager
def qualification_signal_context():
    """Turn normal operator signals into cleanup-preserving exceptions."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("qualification signal handlers require the main thread")
    watched = (signal.SIGINT, signal.SIGTERM)
    previous = {number: signal.getsignal(number) for number in watched}
    original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    interrupted = False

    def interrupt(signal_number, _frame):
        nonlocal interrupted
        if interrupted:
            return
        interrupted = True
        signal.pthread_sigmask(signal.SIG_BLOCK, watched)
        raise DurableQualificationInterrupted(signal_number)

    try:
        for number in watched:
            signal.signal(number, interrupt)
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, watched)
        try:
            for number, handler in previous.items():
                signal.signal(number, handler)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)


@dataclass(frozen=True, slots=True)
class DurableResourceSample:
    process_memory_bytes: int
    worker_memory_bytes: int
    host_mem_available_bytes: int
    host_cpu_percent: float
    active_backend_turns: int
    active_external_workers: int
    active_sandboxes: int

    def __post_init__(self) -> None:
        counts = (
            self.process_memory_bytes,
            self.worker_memory_bytes,
            self.host_mem_available_bytes,
            self.active_backend_turns,
            self.active_external_workers,
            self.active_sandboxes,
        )
        if (
            any(type(value) is not int or value < 0 for value in counts)
            or not isinstance(self.host_cpu_percent, (int, float))
            or not math.isfinite(self.host_cpu_percent)
            or not 0 <= self.host_cpu_percent <= 100
        ):
            raise ValueError("durable resource sample is invalid")


class WholeWindowResourceSampler:
    """Sample resources concurrently across the complete live profile window."""

    def __init__(
        self,
        *,
        sample: Callable[[], DurableResourceSample],
        interval_seconds: float = 0.25,
        monotonic: Callable[[], float] = time.monotonic,
        threaded: bool = True,
    ) -> None:
        if not 0.05 <= interval_seconds <= 5:
            raise ValueError("durable resource sample interval is invalid")
        self._sample = sample
        self._interval = interval_seconds
        self._monotonic = monotonic
        self._threaded = threaded
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._samples: list[tuple[float, DurableResourceSample]] = []
        self._failure = False
        self._started_at: float | None = None

    def _capture(self) -> None:
        try:
            value = self._sample()
            if not isinstance(value, DurableResourceSample):
                raise TypeError
            self._samples.append((self._monotonic(), value))
        except BaseException:
            self._failure = True

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._capture()
            if self._failure:
                return

    def start(self) -> None:
        if self._started_at is not None:
            raise QualificationRefused("resource_sampling_lifecycle_invalid")
        self._started_at = self._monotonic()
        self._capture()
        if self._failure:
            raise QualificationRefused("resource_sampling_failed")
        if self._threaded:
            self._thread = threading.Thread(
                target=self._run,
                name="durable-qualification-resource-sampler",
                daemon=True,
            )
            self._thread.start()

    def stop(self):
        if self._started_at is None:
            raise QualificationRefused("resource_sampling_lifecycle_invalid")
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval * 4))
            if self._thread.is_alive():
                self._failure = True
        ended_at = self._monotonic()
        last_at = self._samples[-1][0] if self._samples else self._started_at
        if ended_at - last_at > self._interval * 4:
            raise QualificationRefused("resource_sampling_stalled")
        self._capture()
        if self._failure or len(self._samples) < 2:
            raise QualificationRefused("resource_sampling_failed")
        from backend.loadtests.external_pi_fleet_locustfile import DurableRunResources

        values = tuple(sample for _, sample in self._samples)
        return DurableRunResources(
            peak_memory_bytes=max(
                sample.process_memory_bytes + sample.worker_memory_bytes
                for sample in values
            ),
            minimum_host_mem_available_bytes=min(
                sample.host_mem_available_bytes for sample in values
            ),
            peak_cpu_percent=max(sample.host_cpu_percent for sample in values),
            peak_active_backend_turns=max(
                sample.active_backend_turns for sample in values
            ),
            peak_active_external_workers=max(
                sample.active_external_workers for sample in values
            ),
            peak_active_sandboxes=max(sample.active_sandboxes for sample in values),
        )


def build_synthetic_transport_config(
    *,
    run_id: str,
    admin_token: str,
    model: str,
    cookie_encoder: Callable[[str], str],
    max_spend_usd: str,
    required_spend_microusd: int = 0,
    provider_spend_ceiling_microusd: int = 0,
) -> DurableChatTransportConfig:
    """Build the exact in-memory 32-user cohort after validating spend authority."""
    try:
        spend = Decimal(max_spend_usd)
    except (InvalidOperation, TypeError):
        raise QualificationRefused("spend_envelope_invalid") from None
    if not spend.is_finite() or not Decimal("0") < spend <= Decimal("10"):
        raise QualificationRefused("spend_envelope_invalid")
    max_spend_microusd = int(spend * Decimal("1000000"))
    if (
        not 0 <= provider_spend_ceiling_microusd <= required_spend_microusd
        or required_spend_microusd > max_spend_microusd
    ):
        raise QualificationRefused("spend_envelope_invalid")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", run_id):
        raise QualificationRefused("qualification_run_id_invalid")
    cookies = tuple(
        cookie_encoder(f"operator:pi-qualification:{run_id}:{ordinal}")
        for ordinal in range(32)
    )
    return DurableChatTransportConfig(
        base_url="https://staging.paperswithcode.co",
        synthetic_cookies=cookies,
        initial_model=model,
        qualification_run_id=run_id,
        admin_token=admin_token,
        max_spend_microusd=max_spend_microusd,
        provider_spend_ceiling_microusd=provider_spend_ceiling_microusd,
    )


def qualification_spend_ceiling_microusd(
    settings: object, *, modal_rate_microusd_per_second: int
) -> tuple[int, int]:
    """Return provider and total worst-case costs for the fixed live profile."""
    from backend.services.chat_openai_budget_service import (
        MAX_REQUEST_BYTES,
        OpenAIRequestBounds,
        safe_maximum_microusd,
    )
    from backend.chat_sandbox_worker.contract import PROVIDER_OUTPUT_TOKEN_LIMIT
    from backend.services.durable_external_qualification_contract import (
        DURABLE_QUALIFICATION_EXPECTED_USERS,
        DURABLE_QUALIFICATION_PROVIDER_REQUESTS_PER_TURN,
        DURABLE_QUALIFICATION_SANDBOX_LIFETIME_SECONDS,
        DURABLE_QUALIFICATION_TOOL_TURNS,
    )

    provider = (
        DURABLE_QUALIFICATION_EXPECTED_USERS
        * DURABLE_QUALIFICATION_PROVIDER_REQUESTS_PER_TURN
        * safe_maximum_microusd(
            settings,
            OpenAIRequestBounds(
                request_bytes=MAX_REQUEST_BYTES,
                maximum_output_tokens=PROVIDER_OUTPUT_TOKEN_LIMIT,
            ),
        )
    )
    modal = round(
        DURABLE_QUALIFICATION_TOOL_TURNS
        * DURABLE_QUALIFICATION_SANDBOX_LIFETIME_SECONDS
        * modal_rate_microusd_per_second
    )
    return provider, provider + modal


@dataclass(frozen=True, slots=True)
class QualificationEnvironment:
    name: str
    target_release: str
    staging_release: str
    production_release: str
    host_mem_total_bytes: int
    public_external_admission_flags: tuple[bool, ...]


@dataclass(frozen=True, slots=True)
class ImmutableFlagSnapshot:
    entries: tuple[tuple[str, bool], ...]

    @classmethod
    def capture(cls, value: Mapping[str, bool]) -> ImmutableFlagSnapshot:
        if not isinstance(value, Mapping) or not 1 <= len(value) <= 32:
            raise QualificationRefused("public_external_admission_flags_are_invalid")
        entries = tuple(sorted(value.items()))
        if any(
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name)
            or type(enabled) is not bool
            for name, enabled in entries
        ):
            raise QualificationRefused("public_external_admission_flags_are_invalid")
        return cls(entries)

    @property
    def any_enabled(self) -> bool:
        return any(enabled for _, enabled in self.entries)

    def as_dict(self) -> dict[str, bool]:
        return dict(self.entries)


@dataclass(frozen=True, slots=True)
class CleanupProof:
    exact_workers_drained: bool
    transient_workers_removed: bool
    listeners_gone: bool
    status_files_gone: bool
    processes_gone: bool
    final_active_backend_turns: int
    final_active_external_workers: int
    final_active_sandboxes: int

    def __post_init__(self) -> None:
        values = (
            self.exact_workers_drained,
            self.transient_workers_removed,
            self.listeners_gone,
            self.status_files_gone,
            self.processes_gone,
        )
        counts = (
            self.final_active_backend_turns,
            self.final_active_external_workers,
            self.final_active_sandboxes,
        )
        if any(type(value) is not bool for value in values) or any(
            type(count) is not int or count < 0 or count > 1_000_000 for count in counts
        ):
            raise ValueError("durable cleanup proof is invalid")

    @property
    def passed(self) -> bool:
        return (
            self.exact_workers_drained
            and self.transient_workers_removed
            and self.listeners_gone
            and self.status_files_gone
            and self.processes_gone
            and self.final_active_backend_turns == 0
            and self.final_active_external_workers == 0
            and self.final_active_sandboxes == 0
        )


_FAILED_CLEANUP = CleanupProof(False, False, False, False, False, 0, 0, 0)
QualificationResult = DurableQualificationReport


@dataclass(frozen=True, slots=True)
class StagingQualificationPrerequisites:
    migrations_ready: bool
    runtime_ready: bool
    worker_environment: str
    worker_id: str
    configured_worker_id: str
    worker_release_id: str
    worker_state: str
    worker_contract_version: str
    maximum_sessions: int
    active_sessions: int


@dataclass(frozen=True, slots=True)
class ScopedCleanupState:
    exact_workers_drained: bool
    transient_workers: int
    listeners: int
    status_files: int
    processes: int
    active_backend_turns: int
    active_external_workers: int
    active_sandboxes: int


def select_staging_pi_openai_model(settings: object) -> str:
    choices = getattr(settings, "chat_model_choices", ())
    compatible = tuple(
        choice.get("id")
        for choice in choices
        if isinstance(choice, Mapping)
        and choice.get("provider") == "openai"
        and choice.get("protocol") == "openai-responses"
        and isinstance(choice.get("route"), str)
        and choice.get("route")
    )
    if len(compatible) != 1 or not isinstance(compatible[0], str):
        raise QualificationRefused("staging_pi_openai_model_required")
    return compatible[0]
