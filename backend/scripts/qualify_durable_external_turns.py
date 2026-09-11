"""Root-operated controller and CLI for durable external-turn qualification."""

from __future__ import annotations

import argparse
import os
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from backend.loadtests.external_pi_fleet_core import (
    DurableProfileReport,
    DurableQualificationReport,
    DurableQualificationProfile,
    HostResourceSnapshot,
    load_modal_rate_evidence,
    resolve_durable_profile,
)
from backend.loadtests.durable_chat_transport import DurableChatTransportConfig
from backend.services.durable_external_qualification import (
    CONFIRMATION,
    DURABLE_REPORT_PATH,
    DURABLE_REPORT_ROOT,
    CleanupProof,
    DurableQualificationInterrupted,
    DurableResourceSample,
    ImmutableFlagSnapshot,
    QualificationEnvironment,
    QualificationRefused,
    QualificationResult,
    ScopedCleanupState,
    StagingQualificationPrerequisites,
    WholeWindowResourceSampler,
    _FAILED_CLEANUP,
    _MAX_APPROVED_HOST_MEMORY_BYTES,
    _MIN_APPROVED_HOST_MEMORY_BYTES,
    _STAGING_RELEASE,
    build_synthetic_transport_config,
    qualification_signal_context,
    select_staging_pi_openai_model,
    qualification_spend_ceiling_microusd,
)
from backend.services.durable_external_qualification_system import (
    SystemDurableQualificationControlPlane,
    bind_active_staging_worker,
    build_system_control_plane,
    load_protected_staging_settings,
)


class DurableQualificationOperator(Protocol):
    def environment(self) -> QualificationEnvironment: ...

    def snapshot_flags(self) -> Mapping[str, bool]: ...

    def resource_snapshot(
        self, profile: DurableQualificationProfile
    ) -> HostResourceSnapshot: ...

    def setup_profile(self, profile: DurableQualificationProfile) -> None: ...

    def run_profile(
        self, profile: DurableQualificationProfile
    ) -> DurableProfileReport: ...

    def teardown_profile(
        self, profile: DurableQualificationProfile, scope_id: uuid.UUID | None
    ) -> None: ...

    def restore_flags(self, flags: Mapping[str, bool]) -> Mapping[str, bool]: ...

    def cleanup_transient_workers(self) -> CleanupProof: ...


class LiveQualificationControlPlane(Protocol):
    """Protected mutations and runtime evidence supplied by the live operation."""

    def environment(self) -> QualificationEnvironment: ...

    def snapshot_flags(self) -> Mapping[str, bool]: ...

    def resource_snapshot(
        self, profile: DurableQualificationProfile
    ) -> HostResourceSnapshot: ...

    def run_resources(self, profile: DurableQualificationProfile) -> object: ...

    def setup_profile(self, profile: DurableQualificationProfile) -> None: ...

    def restore_flags(self, flags: Mapping[str, bool]) -> Mapping[str, bool]: ...

    def cleanup_transient_workers(self) -> CleanupProof: ...

    def protected_runtime_evidence(
        self, profile: DurableQualificationProfile
    ) -> Mapping[str, str]: ...


class GuardedLiveDurableOperator:
    """Bind the controller to the concrete chat transport and exact Locust profile."""

    def __init__(
        self,
        *,
        control_plane: LiveQualificationControlPlane,
        transport_config: DurableChatTransportConfig,
    ) -> None:
        self.control_plane = control_plane
        self.transport_config = transport_config
        from backend.loadtests.durable_chat_transport import (
            HttpDurableQualificationEvidenceSource,
        )

        self.evidence_source = HttpDurableQualificationEvidenceSource(transport_config)
        self._scopes: dict[str, uuid.UUID] = {}

    def environment(self) -> QualificationEnvironment:
        return self.control_plane.environment()

    def snapshot_flags(self) -> Mapping[str, bool]:
        return self.control_plane.snapshot_flags()

    def resource_snapshot(
        self, profile: DurableQualificationProfile
    ) -> HostResourceSnapshot:
        return self.control_plane.resource_snapshot(profile)

    def setup_profile(self, profile: DurableQualificationProfile) -> None:
        self.control_plane.setup_profile(profile)

    def run_profile(self, profile: DurableQualificationProfile):
        from backend.loadtests.external_pi_fleet_locustfile import (
            run_live_durable_profile,
        )

        mark_scope_attempted = getattr(self.control_plane, "mark_scope_attempted", None)
        if callable(mark_scope_attempted):
            mark_scope_attempted()
        scope = self.evidence_source.begin_scope(profile.name)
        scope_id = scope["scope_id"]
        if not isinstance(scope_id, uuid.UUID):
            raise QualificationRefused("qualification_scope_invalid")
        self._scopes[profile.name] = scope_id
        if scope.get("app_release_id") != self.environment().target_release:
            raise QualificationRefused("exact_staging_release_required")
        bind_scope = getattr(self.control_plane, "bind_scope", None)
        if callable(bind_scope):
            bind_scope(scope_id)
        return run_live_durable_profile(
            profile_name=profile.name,
            transport_config=self.transport_config,
            resources=self.control_plane.run_resources(profile),
            qualification_scope_id=scope_id,
        )

    def finalize_profile(self, profile: DurableQualificationProfile, measurement):
        from datetime import UTC, datetime
        from backend.loadtests.external_pi_fleet_locustfile import (
            finalize_live_durable_profile,
        )

        environment = self.environment()
        evidence = self.evidence_source.collect(measurement.qualification_scope_id)
        protected_rate = dict(self.control_plane.protected_runtime_evidence(profile))
        protected_rate["PWC_MODAL_EXECUTOR_RATE_ATTESTED_AT_MS"] = str(
            evidence.window_ended_at_ms
        )
        rate = load_modal_rate_evidence(
            protected_rate,
            expected_release=environment.target_release,
            window_started_at_ms=evidence.window_started_at_ms,
            window_ended_at_ms=evidence.window_ended_at_ms,
            now_ms=round(datetime.now(UTC).timestamp() * 1_000),
        )
        report = finalize_live_durable_profile(
            measurement,
            qualification_evidence=evidence,
            modal_rate=rate,
        )
        if report.modal_estimated_cost_microusd > self.spend_envelope_microusd:
            raise QualificationRefused("spend_envelope_exceeded")
        return report

    @property
    def spend_envelope_microusd(self) -> int:
        return self.transport_config.max_spend_microusd

    @property
    def provider_spend_ceiling_microusd(self) -> int:
        return self.transport_config.provider_spend_ceiling_microusd

    def cleanup_profile_evidence(self, profile: DurableQualificationProfile) -> None:
        scope_id = self._scopes.get(profile.name)
        if scope_id is not None:
            self.evidence_source.cleanup(scope_id)
            self._scopes.pop(profile.name, None)

    def qualification_scope_id(
        self, profile: DurableQualificationProfile
    ) -> uuid.UUID | None:
        return self._scopes.get(profile.name)

    def teardown_profile(
        self, profile: DurableQualificationProfile, scope_id: uuid.UUID | None
    ) -> None:
        expected_scope_id = self._scopes.get(profile.name)
        if scope_id is None or scope_id != expected_scope_id:
            raise QualificationRefused("qualification_scope_invalid")
        self.evidence_source.teardown(scope_id)

    def restore_flags(self, flags: Mapping[str, bool]) -> Mapping[str, bool]:
        return self.control_plane.restore_flags(flags)

    def cleanup_transient_workers(self) -> CleanupProof:
        return self.control_plane.cleanup_transient_workers()


def run_live_durable_qualification(
    *,
    control_plane: LiveQualificationControlPlane,
    transport_config: DurableChatTransportConfig,
) -> DurableQualificationReport:
    return run_durable_qualification(
        GuardedLiveDurableOperator(
            control_plane=control_plane,
            transport_config=transport_config,
        ),
        profiles=("32-functional-turns",),
    )


def validate_qualification_environment(environment: QualificationEnvironment) -> None:
    """Require an isolated exact staging release on the approved 16 GiB class."""
    if (
        environment.name != "staging"
        or environment.production_release == environment.target_release
        or environment.production_release.partition("-")[0]
        == environment.target_release.partition("-")[0]
    ):
        raise QualificationRefused("staging_isolation_required")
    if (
        environment.target_release != environment.staging_release
        or not _STAGING_RELEASE.fullmatch(environment.target_release)
    ):
        raise QualificationRefused("exact_staging_release_required")
    if (
        type(environment.host_mem_total_bytes) is not int
        or not _MIN_APPROVED_HOST_MEMORY_BYTES
        <= environment.host_mem_total_bytes
        <= _MAX_APPROVED_HOST_MEMORY_BYTES
    ):
        raise QualificationRefused("approved_16_gib_host_required")
    if not environment.public_external_admission_flags or any(
        type(flag) is not bool or flag
        for flag in environment.public_external_admission_flags
    ):
        raise QualificationRefused("public_external_admission_flags_must_be_off")


def _resource_refusal(
    profile: DurableQualificationProfile, snapshot: HostResourceSnapshot
) -> str | None:
    projected = max(
        0, snapshot.mem_available_bytes - snapshot.projected_additional_bytes
    )
    if (
        snapshot.mem_available_bytes < snapshot.projected_additional_bytes
        or projected < profile.minimum_available_bytes
    ):
        return "memory_headroom"
    if snapshot.cpu_guard_percent != 80.0 or snapshot.cpu_percent >= 80.0:
        return "cpu_headroom"
    return None


def run_durable_qualification(
    operator: DurableQualificationOperator,
    *,
    profiles: Sequence[str] = ("32-functional-turns",),
) -> DurableQualificationReport:
    """Run the fixed profiles and return directly publishable fail-closed evidence."""
    environment: QualificationEnvironment | None = None
    environment_valid = False
    previous_flags: ImmutableFlagSnapshot | None = None
    reports: list[DurableProfileReport] = []
    pending_evidence_cleanup: list[DurableQualificationProfile] = []
    status = "failed"
    reason: str | None = "durable_qualification_failed"
    flags_restored = False
    cleanup = _FAILED_CLEANUP
    unreportable_refusal: str | None = None
    try:
        profile_names = tuple(profiles)
        if profile_names != ("32-functional-turns",):
            raise QualificationRefused("binding_profile_order_required")
        environment = operator.environment()
        validate_qualification_environment(environment)
        environment_valid = True
        previous_flags = ImmutableFlagSnapshot.capture(operator.snapshot_flags())
        if previous_flags.any_enabled:
            raise QualificationRefused("public_external_admission_flags_must_be_off")
        for profile_name in profile_names:
            profile = resolve_durable_profile(profile_name)
            validate_qualification_environment(operator.environment())
            snapshot = operator.resource_snapshot(profile)
            refusal = _resource_refusal(profile, snapshot)
            if refusal is not None:
                status = "resource_refused"
                reason = refusal
                break
            result = None
            primary_error: BaseException | None = None
            profile_cleanup_failed = False
            teardown_succeeded = False
            try:
                operator.setup_profile(profile)
                result = operator.run_profile(profile)
            except BaseException as error:
                primary_error = error
            try:
                scope_id = getattr(result, "qualification_scope_id", None)
                scope_source = getattr(operator, "qualification_scope_id", None)
                if scope_id is None:
                    if callable(scope_source):
                        scope_id = scope_source(profile)
                if scope_id is not None or not callable(scope_source):
                    operator.teardown_profile(profile, scope_id)
                    teardown_succeeded = True
            except BaseException:
                profile_cleanup_failed = True

            report = None
            if primary_error is None and not profile_cleanup_failed:
                try:
                    finalize = getattr(operator, "finalize_profile", None)
                    report = finalize(profile, result) if callable(finalize) else result
                except BaseException as error:
                    primary_error = error
            if teardown_succeeded:
                pending_evidence_cleanup.append(profile)
            if profile_cleanup_failed:
                raise QualificationRefused("cleanup_failed")
            if primary_error is not None:
                raise primary_error
            if report.profile != profile.name:
                raise QualificationRefused("durable_profile_failed")
            reports.append(report)
            if not report.passed:
                raise QualificationRefused("durable_profile_failed")
        else:
            status = "completed"
            reason = None
    except QualificationRefused as error:
        reason = str(error)
        if not environment_valid:
            unreportable_refusal = reason
    except BaseException:
        reason = "durable_qualification_failed"
    finally:
        if previous_flags is not None:
            try:
                restored = ImmutableFlagSnapshot.capture(
                    operator.restore_flags(previous_flags.as_dict())
                )
                flags_restored = restored == previous_flags
            except BaseException:
                flags_restored = False
        try:
            candidate = operator.cleanup_transient_workers()
            if isinstance(candidate, CleanupProof):
                cleanup = candidate
        except BaseException:
            cleanup = _FAILED_CLEANUP

    if unreportable_refusal is not None or environment is None:
        raise QualificationRefused(
            unreportable_refusal or "durable_qualification_failed"
        ) from None
    if not cleanup.passed or (previous_flags is not None and not flags_restored):
        status = "failed"
        reason = "cleanup_failed"
    else:
        cleanup_evidence = getattr(operator, "cleanup_profile_evidence", None)
        if callable(cleanup_evidence):
            try:
                for profile in pending_evidence_cleanup:
                    cleanup_evidence(profile)
            except BaseException:
                status = "failed"
                reason = "cleanup_failed"
    return DurableQualificationReport(
        release_id=environment.target_release,
        status=status,
        reason=reason,
        profiles=tuple(reports),
        max_spend_microusd=getattr(operator, "spend_envelope_microusd", 0),
        provider_spend_ceiling_microusd=getattr(
            operator, "provider_spend_ceiling_microusd", 0
        ),
        flags_restored=flags_restored,
        exact_workers_drained=cleanup.exact_workers_drained,
        transient_workers_removed=cleanup.transient_workers_removed,
        listeners_gone=cleanup.listeners_gone,
        status_files_gone=cleanup.status_files_gone,
        processes_gone=cleanup.processes_gone,
        final_active_backend_turns=cleanup.final_active_backend_turns,
        final_active_external_workers=cleanup.final_active_external_workers,
        final_active_sandboxes=cleanup.final_active_sandboxes,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the root-only staging durable external-turn qualification; "
            f"confirmation must be {CONFIRMATION}."
        )
    )
    parser.add_argument("--environment", choices=("staging",), required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--max-spend-usd", required=True)
    parser.add_argument(
        "--profile",
        choices=("32-functional-turns",),
        default="32-functional-turns",
    )
    return parser


def validated_active_release_id(
    requested_release_id: str, release_settings: object
) -> str:
    """Bind CLI identity to the already validated active immutable manifest."""
    active_release_id = getattr(release_settings, "release_id", None)
    if (
        not isinstance(active_release_id, str)
        or _STAGING_RELEASE.fullmatch(active_release_id) is None
        or active_release_id != requested_release_id
    ):
        raise QualificationRefused("exact_staging_release_required")
    return active_release_id


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("run through sudo as the root operator")
    if args.confirm != CONFIRMATION:
        parser.error("exact durable qualification confirmation is required")
    if _STAGING_RELEASE.fullmatch(args.release_id) is None:
        parser.error("exact immutable staging release is required")
    try:
        from backend.loadtests.external_pi_fleet_core import publish_durable_report
        from backend.routers.auth import encode_qualification_session
        from backend.scripts.qualify_chat_sandbox import (
            merge_release_settings,
            settings_for_release,
        )

        current = Path("/srv/paperswithcode/environments/staging/current")
        release_settings = settings_for_release(current)
        active_release_id = validated_active_release_id(
            args.release_id, release_settings
        )
        protected_settings = bind_active_staging_worker(
            load_protected_staging_settings()
        )
        settings = merge_release_settings(protected_settings, release_settings)
        control_plane = build_system_control_plane(
            release_id=args.release_id,
            settings=settings,
            environ={"PWC_RELEASE_ID": active_release_id},
        )
        model = select_staging_pi_openai_model(settings)
        run_id = uuid.uuid4().hex[:24]
        static_rate = control_plane.protected_runtime_evidence(
            resolve_durable_profile("32-functional-turns")
        )
        provider_ceiling, required_ceiling = qualification_spend_ceiling_microusd(
            settings,
            modal_rate_microusd_per_second=int(
                static_rate["PWC_MODAL_EXECUTOR_RATE_MICROUSD_PER_SECOND"]
            ),
        )

        def encode(subject: str) -> str:
            return encode_qualification_session(
                {
                    "sub": subject,
                    "username": subject,
                    "chat_qualification_owner": subject,
                },
                settings,
            )

        transport = build_synthetic_transport_config(
            run_id=run_id,
            admin_token=settings.admin_api_token,
            model=model,
            cookie_encoder=encode,
            max_spend_usd=args.max_spend_usd,
            required_spend_microusd=required_ceiling,
            provider_spend_ceiling_microusd=provider_ceiling,
        )
        with qualification_signal_context():
            report = run_live_durable_qualification(
                control_plane=control_plane,
                transport_config=transport,
            )
        publish_durable_report(report, DURABLE_REPORT_PATH, DURABLE_REPORT_ROOT)
    except BaseException:  # noqa: BLE001 - never disclose protected live details
        print("durable external-turn qualification failed closed", file=os.sys.stderr)
        return 1
    return 0 if report.passed else 1


__all__ = (
    "CONFIRMATION",
    "DURABLE_REPORT_PATH",
    "DURABLE_REPORT_ROOT",
    "DurableQualificationOperator",
    "DurableQualificationInterrupted",
    "DurableResourceSample",
    "GuardedLiveDurableOperator",
    "LiveQualificationControlPlane",
    "WholeWindowResourceSampler",
    "CleanupProof",
    "ImmutableFlagSnapshot",
    "QualificationEnvironment",
    "QualificationRefused",
    "QualificationResult",
    "ScopedCleanupState",
    "StagingQualificationPrerequisites",
    "SystemDurableQualificationControlPlane",
    "build_parser",
    "build_system_control_plane",
    "build_synthetic_transport_config",
    "main",
    "qualification_signal_context",
    "run_durable_qualification",
    "run_live_durable_qualification",
    "select_staging_pi_openai_model",
    "validate_qualification_environment",
)


if __name__ == "__main__":
    raise SystemExit(main())
