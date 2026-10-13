"""Fail-closed authorization for every autonomous mutation capability."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.services.autonomous_capabilities import (
    CAPABILITY_MANIFESTS,
    CAPABILITY_RESOURCE_KINDS,
    AuthorizationDecision,
    Capability,
    ResourceKind,
    ResourceRef,
)
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    DryRunMutation,
    ManualModeEnabled,
    Operator,
    OperatorDisabled,
    RunContext,
)


_EXISTING_ONLY = frozenset(
    {
        ResourceKind.PENDING_EDIT,
        ResourceKind.TASK,
        ResourceKind.METHOD,
        ResourceKind.BENCHMARK,
        ResourceKind.METRIC,
        ResourceKind.PAPER,
        ResourceKind.EVALUATION,
        ResourceKind.TRENDING_MODEL_CANDIDATE,
        ResourceKind.BENCHMARK_CANDIDATE,
        ResourceKind.DECLARED_CRON,
    }
)
_REPAIR_CAPABILITIES = frozenset(
    {Capability.REPAIR_DECLARED_CRON_SOURCE, Capability.REPAIR_CHAT_SOURCE}
)


class AutonomousPolicy:
    def __init__(self, repository: AutonomousOperationsRepository | None = None):
        self.repository = repository or AutonomousOperationsRepository()

    def authorize(
        self,
        db: Session,
        context: RunContext,
        capability: Capability,
        resource: ResourceRef,
        *,
        incident_signature: str | None = None,
        incident_attempt_id: uuid.UUID | None = None,
    ) -> AuthorizationDecision:
        return self._authorize(
            db,
            context,
            capability,
            resource,
            incident_signature=incident_signature,
            incident_attempt_id=incident_attempt_id,
            require_durable_run=True,
        )

    def authorize_admission(
        self,
        db: Session,
        context: RunContext,
        capability: Capability,
        resource: ResourceRef,
    ) -> AuthorizationDecision:
        """Validate a prospective run without recording terminal run state."""
        return self._authorize(
            db,
            context,
            capability,
            resource,
            require_durable_run=False,
        )

    def _authorize(
        self,
        db: Session,
        context: RunContext,
        capability: Capability,
        resource: ResourceRef,
        *,
        incident_signature: str | None = None,
        incident_attempt_id: uuid.UUID | None = None,
        require_durable_run: bool,
    ) -> AuthorizationDecision:
        if not isinstance(context, RunContext) or not isinstance(
            context.operator, Operator
        ):
            return AuthorizationDecision(False, "invalid_run_context")
        if not isinstance(capability, Capability):
            return AuthorizationDecision(False, "unknown_capability")
        if not isinstance(resource, ResourceRef):
            return AuthorizationDecision(False, "unknown_resource")
        if capability not in CAPABILITY_MANIFESTS.get(context.operator, frozenset()):
            return AuthorizationDecision(False, "capability_not_in_manifest")
        if resource.kind not in CAPABILITY_RESOURCE_KINDS[capability]:
            return AuthorizationDecision(False, "resource_kind_not_allowed")
        try:
            self.repository.assert_mutation_allowed(db, context)
        except ManualModeEnabled:
            return AuthorizationDecision(False, "manual_mode")
        except OperatorDisabled:
            return AuthorizationDecision(False, "operator_disabled")
        except DryRunMutation:
            return AuthorizationDecision(False, "dry_run")
        if require_durable_run:
            try:
                self.repository.assert_run_context(db, context)
            except (TypeError, ValueError):
                return AuthorizationDecision(False, "invalid_run_context")
        if resource.kind in _EXISTING_ONLY and not resource.exists:
            return AuthorizationDecision(False, "resource_not_found")
        if capability in _REPAIR_CAPABILITIES:
            if not self.repository.owns_repair_lease(db, context=context):
                return AuthorizationDecision(False, "repair_lease_not_owned")
        if capability == Capability.REPAIR_CHAT_SOURCE:
            if incident_signature is None or incident_attempt_id is None:
                return AuthorizationDecision(False, "incident_attempt_required")
            try:
                owns_attempt = self.repository.owns_chat_repair_attempt(
                    db,
                    context=context,
                    signature=incident_signature,
                    attempt_id=incident_attempt_id,
                )
            except ValueError:
                return AuthorizationDecision(False, "invalid_incident_signature")
            if not owns_attempt:
                return AuthorizationDecision(False, "incident_attempt_not_owned")
        return AuthorizationDecision(True, "authorized")


def authorize(
    db: Session,
    context: RunContext,
    capability: Capability,
    resource: ResourceRef,
    **kwargs,
) -> AuthorizationDecision:
    return AutonomousPolicy().authorize(db, context, capability, resource, **kwargs)
