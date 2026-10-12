"""Chat and qualification schema readiness probes."""

from __future__ import annotations


import pytest

from backend.config import Settings
from backend.services.runtime_validation import (
    validate_chat_schema,
    validate_qualification_evidence_schema,
)


class _ChatSchemaResult:
    def __init__(self, *, scalar=None, rows=None, first=None):
        self._scalar = scalar
        self._rows = rows
        self._first = first

    def scalar_one(self):
        return self._scalar

    def all(self):
        return self._rows

    def first(self):
        return self._first

    def scalars(self):
        return (row[0] for row in self._rows)


class _ChatSchemaDB:
    def __init__(
        self,
        transaction_read_only: str,
        *,
        include_edit_columns: bool = True,
        include_share_columns: bool = True,
        include_share_constraint: bool = True,
        include_pool_columns: bool = True,
        include_latency_columns: bool = True,
        include_qualification_columns: bool = True,
        include_mapped_qualification_columns: bool = True,
        include_reader_context_columns: bool = True,
        include_artifact_foundation: bool = True,
        include_durable_schema: bool = True,
        include_reservation_schema: bool = True,
    ):
        self.transaction_read_only = transaction_read_only
        self.include_edit_columns = include_edit_columns
        self.include_share_columns = include_share_columns
        self.include_share_constraint = include_share_constraint
        self.include_pool_columns = include_pool_columns
        self.include_latency_columns = include_latency_columns
        self.include_qualification_columns = include_qualification_columns
        self.include_mapped_qualification_columns = include_mapped_qualification_columns
        self.include_reader_context_columns = include_reader_context_columns
        self.include_artifact_foundation = include_artifact_foundation
        self.include_durable_schema = include_durable_schema
        self.include_reservation_schema = include_reservation_schema

    def execute(self, statement):
        sql = str(statement)
        if "SHOW transaction_read_only" in sql:
            return _ChatSchemaResult(scalar=self.transaction_read_only)
        if "to_regclass" in sql:
            names = (
                "chat_sessions",
                "chat_messages",
                "chat_shares",
                "chat_sandbox_leases",
                "chat_sandbox_pool",
                "chat_sandbox_compute_intervals",
                "chat_sandbox_budget_states",
                "chat_sandbox_circuit_events",
                "chat_title_budget_states",
                "chat_title_provider_calls",
                "chat_title_budget_events",
                "chat_turn_capabilities",
                "chat_turn_latency",
                "chat_openrouter_credentials",
                "chat_openrouter_monthly_usage",
                "chat_openrouter_provider_calls",
                "chat_openrouter_credential_audit",
            )
            if self.include_artifact_foundation:
                names += (
                    "chat_artifacts",
                    "chat_latex_paper_versions",
                    "chat_feedback",
                )
            if self.include_durable_schema:
                names += (
                    "chat_turn_jobs",
                    "chat_turn_event_chunks",
                    "chat_external_workers",
                )
            if self.include_reservation_schema:
                names += (
                    "chat_external_worker_reservations",
                    "chat_qualification_scopes",
                    "chat_qualification_evidence_events",
                )
            return _ChatSchemaResult(rows=[(name, name) for name in names])
        if (
            "character_maximum_length" in sql
            and "chat_external_worker_reservations" in sql
        ):
            rows = [
                ("request_id", "character varying", "NO", 200),
                ("turn_id", "uuid", "YES", None),
                ("endpoint_id", "character varying", "NO", 128),
                ("worker_id", "character varying", "NO", 128),
                ("instance_id", "uuid", "NO", None),
                ("worker_generation", "bigint", "NO", None),
                ("release_id", "character varying", "NO", 255),
                ("contract_version", "character varying", "NO", 128),
                ("maximum_sessions", "integer", "NO", None),
                ("reserved_at", "timestamp with time zone", "NO", None),
                ("expires_at", "timestamp with time zone", "NO", None),
            ]
            return _ChatSchemaResult(
                rows=rows if self.include_reservation_schema else []
            )
        if "qualification_evidence_exact_columns" in sql:
            rows = [
                ("chat_qualification_scopes", "id", "uuid", "NO", None),
                ("chat_qualification_scopes", "run_id", "character varying", "NO", 64),
                ("chat_qualification_scopes", "profile", "character varying", "NO", 32),
                (
                    "chat_qualification_scopes",
                    "app_release_id",
                    "character varying",
                    "NO",
                    255,
                ),
                (
                    "chat_qualification_scopes",
                    "window_started_at",
                    "timestamp with time zone",
                    "NO",
                    None,
                ),
                (
                    "chat_qualification_scopes",
                    "window_ended_at",
                    "timestamp with time zone",
                    "YES",
                    None,
                ),
                (
                    "chat_qualification_scopes",
                    "expires_at",
                    "timestamp with time zone",
                    "NO",
                    None,
                ),
                (
                    "chat_qualification_scopes",
                    "created_at",
                    "timestamp with time zone",
                    "NO",
                    None,
                ),
                ("chat_qualification_evidence_events", "id", "uuid", "NO", None),
                (
                    "chat_qualification_evidence_events",
                    "qualification_scope_id",
                    "uuid",
                    "NO",
                    None,
                ),
                ("chat_qualification_evidence_events", "turn_id", "uuid", "NO", None),
                (
                    "chat_qualification_evidence_events",
                    "chat_session_id",
                    "uuid",
                    "NO",
                    None,
                ),
                (
                    "chat_qualification_evidence_events",
                    "event_type",
                    "character varying",
                    "NO",
                    32,
                ),
                (
                    "chat_qualification_evidence_events",
                    "operation_digest",
                    "character varying",
                    "YES",
                    64,
                ),
                (
                    "chat_qualification_evidence_events",
                    "operation_kind",
                    "character varying",
                    "YES",
                    8,
                ),
                (
                    "chat_qualification_evidence_events",
                    "occurred_at",
                    "timestamp with time zone",
                    "NO",
                    None,
                ),
                ("chat_turn_latency", "qualification_scope_id", "uuid", "YES", None),
                (
                    "chat_turn_latency",
                    "qualification_run_id",
                    "character varying",
                    "YES",
                    64,
                ),
                (
                    "chat_turn_latency",
                    "qualification_profile",
                    "character varying",
                    "YES",
                    32,
                ),
                (
                    "chat_turn_latency",
                    "qualification_workload",
                    "character varying",
                    "YES",
                    16,
                ),
                (
                    "chat_turn_latency",
                    "qualification_scenario",
                    "character varying",
                    "YES",
                    32,
                ),
            ]
            rows = [
                (
                    *row,
                    "now()"
                    if row[:2] == ("chat_qualification_scopes", "created_at")
                    else None,
                )
                for row in rows
            ]
            return _ChatSchemaResult(
                rows=rows if self.include_reservation_schema else []
            )
        if "qualification_evidence_exact_constraints" in sql:
            fragments = {
                "chat_qualification_scopes_pkey": "PRIMARY KEY (id)",
                "chat_qualification_scopes_run_id_key": "UNIQUE (run_id)",
                "chat_qualification_scopes_profile_check": "CHECK (((profile)::text = ANY ((ARRAY['32-functional-turns'::character varying, '100-immediate-admission'::character varying])::text[])))",
                "chat_qualification_scopes_window_check": "CHECK (((window_ended_at IS NULL) OR (window_ended_at >= window_started_at)))",
                "chat_qualification_scopes_expiry_check": "CHECK ((expires_at > window_started_at))",
                "chat_qualification_evidence_events_pkey": "PRIMARY KEY (id)",
                "chat_qualification_evidence_scope_fkey": "FOREIGN KEY (qualification_scope_id) REFERENCES chat_qualification_scopes(id) ON DELETE CASCADE",
                "chat_qualification_evidence_turn_fkey": "FOREIGN KEY (turn_id) REFERENCES chat_turn_jobs(turn_id) ON DELETE CASCADE",
                "chat_qualification_evidence_session_fkey": "FOREIGN KEY (chat_session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE",
                "chat_qualification_evidence_event_type_check": "CHECK (((event_type)::text = ANY ((ARRAY['admitted_no_queue'::character varying, 'executor_started'::character varying, 'stale_fence'::character varying, 'queued'::character varying, 'workspace_created'::character varying, 'workspace_reused'::character varying, 'workspace_evicted'::character varying])::text[])))",
                "chat_qualification_evidence_operation_shape_check": "CHECK ((((event_type)::text = 'executor_started'::text) = ((operation_digest IS NOT NULL) AND (operation_kind IS NOT NULL) AND ((operation_kind)::text = ANY ((ARRAY['read'::character varying, 'bash'::character varying])::text[])))))",
                "chat_turn_latency_qualification_scope_fkey": "FOREIGN KEY (qualification_scope_id) REFERENCES chat_qualification_scopes(id) ON DELETE SET NULL",
                "chat_turn_latency_qualification_profile_check": "CHECK (((qualification_profile IS NULL) OR ((qualification_profile)::text = ANY ((ARRAY['32-functional-turns'::character varying, '100-immediate-admission'::character varying])::text[]))))",
                "chat_turn_latency_qualification_workload_check": "CHECK (((qualification_workload IS NULL) OR ((qualification_workload)::text = ANY ((ARRAY['no_tool'::character varying, 'read'::character varying, 'bash'::character varying])::text[]))))",
                "chat_turn_latency_qualification_scenario_check": "CHECK (((qualification_scenario IS NULL) OR ((qualification_scenario)::text = ANY ((ARRAY['focused_latency'::character varying, 'reliability'::character varying, 'clean_cancel'::character varying, 'forced_failure'::character varying])::text[]))))",
            }
            return _ChatSchemaResult(
                rows=list(fragments.items()) if self.include_reservation_schema else []
            )
        if "qualification_evidence_exact_indexes" in sql:
            columns = {
                "idx_chat_qualification_scopes_expiry": ["expires_at"],
                "idx_chat_qualification_scopes_release_profile": [
                    "app_release_id",
                    "profile",
                ],
                "idx_chat_qualification_evidence_scope_event_time": [
                    "qualification_scope_id",
                    "event_type",
                    "occurred_at",
                ],
                "idx_chat_qualification_evidence_session_time": [
                    "chat_session_id",
                    "occurred_at",
                ],
                "idx_chat_qualification_evidence_turn_event": ["turn_id", "event_type"],
                "uq_chat_qualification_evidence_stale_turn": [
                    "qualification_scope_id",
                    "turn_id",
                ],
                "uq_chat_qualification_evidence_eviction_turn": [
                    "qualification_scope_id",
                    "turn_id",
                ],
                "idx_chat_turn_latency_qualification_scope": [
                    "qualification_scope_id",
                    "admitted_at",
                ],
            }
            return _ChatSchemaResult(
                rows=[
                    (
                        name,
                        name.startswith("uq_"),
                        value,
                        (
                            "((event_type)::text = 'stale_fence'::text)"
                            if name.endswith("stale_turn")
                            else "((event_type)::text = 'workspace_evicted'::text)"
                            if name.endswith("eviction_turn")
                            else None
                        ),
                    )
                    for name, value in columns.items()
                ]
                if self.include_reservation_schema
                else []
            )
        if "information_schema.columns" in sql:
            rows = [
                ("chat_sessions", "execution_backend"),
                ("chat_sessions", "reasoning_effort"),
                ("chat_messages", "finish_reason"),
                ("chat_messages", "reasoning_effort"),
                ("chat_messages", "paper_mentions"),
                ("chat_messages", "effective_prompt"),
                ("chat_messages", "langfuse_trace_id"),
                ("chat_sandbox_compute_intervals", "accrued_microusd"),
                ("chat_sandbox_budget_states", "circuit_state"),
                ("chat_sandbox_budget_states", "provider_floor_microusd"),
                (
                    "chat_sandbox_budget_states",
                    "last_reconciliation_attempt_at",
                ),
                ("chat_sandbox_circuit_events", "fallback_delivery_state"),
                (
                    "chat_sandbox_circuit_events",
                    "fallback_next_delivery_attempt_at",
                ),
                ("chat_title_budget_states", "reserved_microusd"),
                ("chat_title_budget_states", "spent_microusd"),
                ("chat_title_provider_calls", "actual_microusd"),
                ("chat_title_provider_calls", "provider_generation_id"),
                ("chat_title_budget_events", "fallback_delivery_state"),
                ("chat_turn_capabilities", "provider_mode"),
                ("chat_turn_capabilities", "provider_credential_revision"),
                ("chat_turn_capabilities", "provider_error_code"),
                ("chat_turn_capabilities", "reasoning_effort"),
                ("chat_openrouter_credentials", "credential_revision"),
                ("chat_openrouter_monthly_usage", "reserved_microusd"),
                ("chat_openrouter_provider_calls", "actual_microusd"),
                ("chat_openrouter_provider_calls", "reasoning_effort"),
                ("chat_openrouter_provider_calls", "routing_policy"),
                ("chat_openrouter_provider_calls", "provider_ttft_ms"),
                ("chat_openrouter_provider_calls", "system_token_bucket"),
            ]
            if self.include_reader_context_columns:
                rows.extend(
                    [
                        ("chat_sessions", "primary_paper_id"),
                        ("chat_messages", "primary_paper_context"),
                        ("chat_messages", "viewer_context"),
                        ("chat_messages", "paper_selection"),
                    ]
                )
            if self.include_durable_schema:
                rows.extend(
                    [
                        ("chat_turn_jobs", name)
                        for name in (
                            "state",
                            "worker_id",
                            "worker_generation",
                            "lease_generation",
                            "lease_expires_at",
                            "terminal_at",
                            "failure_code",
                            "event_sequence",
                            "event_bytes",
                        )
                    ]
                    + [
                        ("chat_turn_event_chunks", name)
                        for name in (
                            "turn_id",
                            "first_sequence",
                            "last_sequence",
                            "events",
                            "payload_bytes",
                        )
                    ]
                    + [
                        ("chat_external_workers", name)
                        for name in (
                            "worker_id",
                            "instance_id",
                            "environment",
                            "release_id",
                            "contract_version",
                            "generation",
                            "state",
                            "maximum_sessions",
                            "active_sessions",
                            "lease_expires_at",
                        )
                    ]
                )
            if self.include_reservation_schema:
                rows.extend(
                    ("chat_external_worker_reservations", name)
                    for name in (
                        "request_id",
                        "turn_id",
                        "endpoint_id",
                        "worker_id",
                        "instance_id",
                        "worker_generation",
                        "release_id",
                        "contract_version",
                        "maximum_sessions",
                        "reserved_at",
                        "expires_at",
                    )
                )
                rows.extend(
                    ("chat_qualification_scopes", name)
                    for name in (
                        "id",
                        "run_id",
                        "profile",
                        "app_release_id",
                        "window_started_at",
                        "window_ended_at",
                        "expires_at",
                    )
                )
                rows.extend(
                    ("chat_qualification_evidence_events", name)
                    for name in (
                        "id",
                        "qualification_scope_id",
                        "turn_id",
                        "chat_session_id",
                        "event_type",
                        "operation_digest",
                        "operation_kind",
                        "occurred_at",
                    )
                )
            if self.include_artifact_foundation:
                rows.extend(
                    [
                        ("chat_artifacts", "source_head_version_id"),
                        ("chat_artifacts", "preview_head_version_id"),
                    ]
                )
            if self.include_edit_columns:
                rows.extend(
                    [
                        ("chat_messages", "prepared_fork_sdk_session_id"),
                        ("chat_messages", "prepared_fork_sdk_project_key"),
                    ]
                )
            if self.include_share_columns:
                rows.extend(
                    [
                        ("chat_shares", "snapshot_version"),
                        ("chat_shares", "messages"),
                    ]
                )
            if self.include_pool_columns:
                rows.extend(
                    [
                        ("chat_sandbox_leases", "worker_generation"),
                        ("chat_sandbox_leases", "egress_policy_digest"),
                        ("chat_sandbox_pool", "modal_sandbox_id"),
                        ("chat_sandbox_pool", "worker_generation"),
                        ("chat_sandbox_pool", "billing_month"),
                        ("chat_sandbox_pool", "estimated_blank_cost_usd"),
                        ("chat_sandbox_pool", "agent_harness"),
                        ("chat_sandbox_pool", "agent_harness_version"),
                        ("chat_sandbox_pool", "model_profile"),
                        ("chat_sandbox_pool", "reasoning_profile"),
                        ("chat_sandbox_pool", "prompt_digest"),
                        ("chat_sandbox_pool", "provider_adapter_contract"),
                        ("chat_sandbox_pool", "egress_policy_digest"),
                        ("chat_sandbox_pool", "provider_create_ms"),
                        ("chat_sandbox_pool", "backend_control_connect_ms"),
                        ("chat_sandbox_pool", "broker_ready_ms"),
                        ("chat_sandbox_pool", "control_ready_ms"),
                        ("chat_sandbox_pool", "agent_spawn_ms"),
                        ("chat_sandbox_pool", "agent_startup_ready_ms"),
                        ("chat_sandbox_pool", "health_check_token_hash"),
                        ("chat_sandbox_pool", "health_check_started_at"),
                    ]
                )
            if self.include_latency_columns:
                rows.extend(
                    [
                        ("chat_turn_latency", "request_id"),
                        ("chat_turn_latency", "terminal_status"),
                        ("chat_turn_latency", "browser_first_visible_delta_ms"),
                        ("chat_turn_latency", "browser_first_reasoning_delta_ms"),
                        ("chat_turn_latency", "first_semantic_event_ms"),
                        ("chat_turn_latency", "pool_miss_reason"),
                        ("chat_turn_latency", "session_reuse_cohort"),
                        ("chat_turn_latency", "estimated_active_cost_usd"),
                        ("chat_turn_latency", "failure_stage"),
                        ("chat_turn_latency", "failure_class"),
                        ("chat_turn_latency", "attempt_kind"),
                        ("chat_turn_latency", "retry_overhead_ms"),
                    ]
                )
            if self.include_mapped_qualification_columns:
                rows.extend(
                    [
                        ("chat_turn_latency", "qualification_scope_id"),
                        ("chat_turn_latency", "qualification_profile"),
                        ("chat_turn_latency", "qualification_workload"),
                    ]
                )
            if self.include_qualification_columns:
                rows.extend(
                    [
                        ("chat_turn_latency", "qualification_run_id"),
                        ("chat_turn_latency", "qualification_scenario"),
                    ]
                )
            return _ChatSchemaResult(rows=rows)
        if "FROM pg_indexes" in sql:
            if "idx_chat_external_worker_reservations_capacity" in sql:
                return _ChatSchemaResult(
                    rows=[
                        ("chat_external_worker_reservations_pkey",),
                        ("chat_external_worker_reservations_turn_id_key",),
                        ("idx_chat_external_worker_reservations_capacity",),
                        ("idx_chat_external_worker_reservations_unbound_expiry",),
                    ]
                    if self.include_reservation_schema
                    else []
                )
            if "tablename = 'chat_external_worker_reservations'" in sql:
                rows = [
                    (
                        "chat_external_worker_reservations_pkey",
                        "CREATE UNIQUE INDEX chat_external_worker_reservations_pkey "
                        "ON staging.chat_external_worker_reservations USING btree "
                        "(request_id)",
                    ),
                    (
                        "chat_external_worker_reservations_turn_id_key",
                        "CREATE UNIQUE INDEX chat_external_worker_reservations_turn_id_key "
                        "ON staging.chat_external_worker_reservations USING btree "
                        "(turn_id)",
                    ),
                    (
                        "idx_chat_external_worker_reservations_capacity",
                        "CREATE INDEX idx_chat_external_worker_reservations_capacity "
                        "ON staging.chat_external_worker_reservations USING btree "
                        "(worker_id, instance_id, worker_generation)",
                    ),
                    (
                        "idx_chat_external_worker_reservations_unbound_expiry",
                        "CREATE INDEX idx_chat_external_worker_reservations_unbound_expiry "
                        "ON staging.chat_external_worker_reservations USING btree "
                        "(expires_at) WHERE (turn_id IS NULL)",
                    ),
                ]
                return _ChatSchemaResult(
                    rows=rows if self.include_reservation_schema else []
                )
            if "idx_chat_external_workers_dispatch" in sql:
                return _ChatSchemaResult(
                    rows=[("idx_chat_external_workers_dispatch",)]
                    if self.include_durable_schema
                    else []
                )
            return _ChatSchemaResult(
                rows=[
                    (name,)
                    for name in (
                        "idx_chat_turn_jobs_expiry",
                        "idx_chat_turn_jobs_terminal_cleanup",
                        "idx_chat_turn_event_chunks_after",
                        "uq_chat_turn_event_chunk_start",
                    )
                ]
                if self.include_durable_schema
                else []
            )
        if "chat_turn_jobs_state_check" in sql:
            return _ChatSchemaResult(
                rows=[
                    (name,)
                    for name in (
                        "chat_turn_jobs_state_check",
                        "chat_turn_jobs_lease_fields_check",
                        "chat_turn_jobs_terminal_timestamp_check",
                        "ck_chat_turn_event_chunk_range",
                    )
                ]
                if self.include_durable_schema
                else []
            )
        if "chat_external_worker_reservations_worker_generation_check" in sql:
            return _ChatSchemaResult(
                rows=[
                    (
                        "chat_external_worker_reservations_pkey",
                        "PRIMARY KEY (request_id)",
                    ),
                    (
                        "chat_external_worker_reservations_turn_id_key",
                        "UNIQUE (turn_id)",
                    ),
                    (
                        "chat_external_worker_reservations_worker_generation_check",
                        "CHECK ((worker_generation > 0))",
                    ),
                    (
                        "chat_external_worker_reservations_maximum_sessions_check",
                        "CHECK ((maximum_sessions BETWEEN 1 AND 32))",
                    ),
                ]
                if self.include_reservation_schema
                else []
            )
        if "chat_shares_messages_array_check" in sql:
            return _ChatSchemaResult(
                first=(1,) if self.include_share_constraint else None
            )
        if "chat_artifacts_source_head_version_fkey" in sql:
            return _ChatSchemaResult(
                rows=[
                    ("chat_artifacts_preview_head_version_fkey",),
                    ("chat_artifacts_source_head_version_fkey",),
                ]
                if self.include_artifact_foundation
                else []
            )
        raise AssertionError(f"Unexpected schema validation query: {sql}")


def test_chat_schema_rejects_read_only_staging_connection():
    with pytest.raises(RuntimeError, match="database connection is read-only"):
        validate_chat_schema(
            _ChatSchemaDB("on"),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_accepts_writable_staging_connection():
    validate_chat_schema(
        _ChatSchemaDB("off"),
        Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
    )


def test_chat_schema_requires_real_durable_tables_when_dispatch_is_armed():
    settings = Settings(
        environment="staging",
        chat_durable_turn_dispatch_enabled=True,
    )
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_durable_schema=False), settings
        )
    validate_chat_schema(_ChatSchemaDB("off"), settings)


def test_chat_schema_requires_complete_reservation_contract_for_external_admission():
    settings = Settings(
        environment="staging",
        chat_external_pi_admission_enabled=True,
    )

    with pytest.raises(
        RuntimeError, match="required external worker schema is missing"
    ):
        validate_chat_schema(
            _ChatSchemaDB("off", include_reservation_schema=False), settings
        )

    validate_chat_schema(_ChatSchemaDB("off"), settings)


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        ("table", "chat_external_worker_reservations"),
        *(
            ("column", name)
            for name in (
                "request_id",
                "turn_id",
                "endpoint_id",
                "worker_id",
                "instance_id",
                "worker_generation",
                "release_id",
                "contract_version",
                "maximum_sessions",
                "reserved_at",
                "expires_at",
            )
        ),
        *(
            ("index", name)
            for name in (
                "chat_external_worker_reservations_pkey",
                "chat_external_worker_reservations_turn_id_key",
                "idx_chat_external_worker_reservations_capacity",
                "idx_chat_external_worker_reservations_unbound_expiry",
            )
        ),
        *(
            ("constraint", name)
            for name in (
                "chat_external_worker_reservations_pkey",
                "chat_external_worker_reservations_turn_id_key",
                "chat_external_worker_reservations_worker_generation_check",
                "chat_external_worker_reservations_maximum_sessions_check",
            )
        ),
    ],
)
def test_chat_schema_rejects_each_missing_reservation_contract_item(kind, name):
    db = _ChatSchemaDB("off")
    original_execute = db.execute

    def without_contract_item(statement):
        sql = str(statement)
        result = original_execute(statement)
        if kind == "table" and "to_regclass" in sql:
            result._rows = [row for row in result._rows if row[0] != name]
        elif kind == "column" and "information_schema.columns" in sql:
            result._rows = [
                row
                for row in result._rows
                if not (
                    row[0] == name or row == ("chat_external_worker_reservations", name)
                )
            ]
        elif kind == "index" and "FROM pg_indexes" in sql:
            result._rows = [row for row in result._rows if row[0] != name]
        elif kind == "constraint" and "pg_constraint AS constraint_row" in sql:
            result._rows = [row for row in result._rows if row[0] != name]
        return result

    db.execute = without_contract_item
    with pytest.raises(
        RuntimeError, match="required external worker schema is missing"
    ):
        validate_chat_schema(
            db,
            Settings(environment="staging", chat_external_pi_admission_enabled=True),
        )


@pytest.mark.parametrize(
    ("query_marker", "object_name", "replacement"),
    (
        (
            "character_maximum_length",
            "endpoint_id",
            ("endpoint_id", "text", "YES", None),
        ),
        (
            "tablename = 'chat_external_worker_reservations'",
            "chat_external_worker_reservations_turn_id_key",
            "CREATE INDEX chat_external_worker_reservations_turn_id_key "
            "ON staging.chat_external_worker_reservations USING btree (turn_id)",
        ),
        (
            "tablename = 'chat_external_worker_reservations'",
            "idx_chat_external_worker_reservations_capacity",
            "CREATE INDEX idx_chat_external_worker_reservations_capacity "
            "ON staging.chat_external_worker_reservations USING btree (worker_id)",
        ),
        (
            "tablename = 'chat_external_worker_reservations'",
            "idx_chat_external_worker_reservations_unbound_expiry",
            "CREATE INDEX idx_chat_external_worker_reservations_unbound_expiry "
            "ON staging.chat_external_worker_reservations USING btree (expires_at)",
        ),
        (
            "pg_get_constraintdef",
            "chat_external_worker_reservations_worker_generation_check",
            "CHECK ((worker_generation >= 0))",
        ),
        (
            "pg_get_constraintdef",
            "chat_external_worker_reservations_maximum_sessions_check",
            "CHECK ((maximum_sessions BETWEEN 1 AND 64))",
        ),
    ),
)
def test_chat_schema_rejects_malformed_same_name_reservation_objects(
    query_marker, object_name, replacement
):
    db = _ChatSchemaDB("off")
    original_execute = db.execute

    def malformed(statement):
        result = original_execute(statement)
        if query_marker in str(statement):
            result._rows = [
                (
                    replacement
                    if row[0] == object_name and isinstance(replacement, tuple)
                    else ((row[0], replacement) if row[0] == object_name else row)
                )
                for row in result._rows
            ]
        return result

    db.execute = malformed
    with pytest.raises(
        RuntimeError, match="required external worker schema is missing"
    ):
        validate_chat_schema(
            db,
            Settings(environment="staging", chat_external_pi_admission_enabled=True),
        )


def test_chat_schema_production_profile_does_not_require_openrouter_tables():
    db = _ChatSchemaDB("off")
    original_execute = db.execute

    def without_openrouter(statement):
        result = original_execute(statement)
        if "to_regclass" in str(statement):
            result._rows = [
                row for row in result._rows if not row[0].startswith("chat_openrouter_")
            ]
        elif "information_schema.columns" in str(statement):
            result._rows = [
                row for row in result._rows if not row[0].startswith("chat_openrouter_")
            ]
        return result

    db.execute = without_openrouter
    validate_chat_schema(
        db,
        Settings(environment="production", chat_openrouter_server_funded_enabled=False),
    )


def test_chat_schema_fails_closed_without_health_ownership_columns():
    db = _ChatSchemaDB("off")
    original_execute = db.execute

    def without_health_ownership(statement):
        result = original_execute(statement)
        if "information_schema.columns" in str(statement):
            result._rows = [
                row
                for row in result._rows
                if row
                not in {
                    ("chat_sandbox_pool", "health_check_token_hash"),
                    ("chat_sandbox_pool", "health_check_started_at"),
                }
            ]
        return result

    db.execute = without_health_ownership
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            db,
            Settings(
                environment="staging",
                chat_openrouter_server_funded_enabled=True,
            ),
        )


def test_chat_schema_requires_qualification_metadata_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_qualification_columns=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_production_requires_mapped_qualification_metadata_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_mapped_qualification_columns=False),
            Settings(environment="production"),
        )


def test_chat_schema_requires_reader_context_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_reader_context_columns=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_requires_artifact_foundation():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_artifact_foundation=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_requires_typed_edit_preparation_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_edit_columns=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_requires_self_contained_share_snapshot_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_share_columns=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_requires_share_snapshot_array_constraint():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_share_constraint=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_requires_blank_pool_accounting_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_pool_columns=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


def test_chat_schema_requires_latency_telemetry_columns():
    with pytest.raises(RuntimeError, match="required chat sandbox schema is missing"):
        validate_chat_schema(
            _ChatSchemaDB("off", include_latency_columns=False),
            Settings(environment="staging", chat_openrouter_server_funded_enabled=True),
        )


_QUALIFICATION_SCHEMA_OBJECTS = (
    *(
        ("columns", name)
        for name in (
            "id",
            "run_id",
            "profile",
            "app_release_id",
            "window_started_at",
            "window_ended_at",
            "expires_at",
            "created_at",
            "qualification_scope_id",
            "turn_id",
            "chat_session_id",
            "event_type",
            "operation_digest",
            "operation_kind",
            "occurred_at",
            "qualification_profile",
        )
    ),
    *(
        ("constraints", name)
        for name in (
            "chat_qualification_scopes_run_id_key",
            "chat_qualification_scopes_profile_check",
            "chat_qualification_scopes_window_check",
            "chat_qualification_scopes_expiry_check",
            "chat_qualification_evidence_scope_fkey",
            "chat_qualification_evidence_turn_fkey",
            "chat_qualification_evidence_session_fkey",
            "chat_qualification_evidence_event_type_check",
            "chat_qualification_evidence_operation_shape_check",
            "chat_turn_latency_qualification_scope_fkey",
            "chat_turn_latency_qualification_profile_check",
        )
    ),
    *(
        ("indexes", name)
        for name in (
            "idx_chat_qualification_scopes_expiry",
            "idx_chat_qualification_scopes_release_profile",
            "idx_chat_qualification_evidence_scope_event_time",
            "idx_chat_qualification_evidence_session_time",
            "idx_chat_qualification_evidence_turn_event",
            "uq_chat_qualification_evidence_stale_turn",
            "uq_chat_qualification_evidence_eviction_turn",
            "idx_chat_turn_latency_qualification_scope",
        )
    ),
)


@pytest.mark.parametrize(("kind", "missing_name"), _QUALIFICATION_SCHEMA_OBJECTS)
def test_qualification_schema_readiness_refuses_each_missing_contract_object(
    kind, missing_name
):
    class BrokenQualificationSchemaDB(_ChatSchemaDB):
        def execute(self, statement):
            result = super().execute(statement)
            if f"qualification_evidence_exact_{kind}" not in str(statement):
                return result
            identifier_index = 1 if kind == "columns" else 0
            return _ChatSchemaResult(
                rows=[
                    row for row in result.all() if row[identifier_index] != missing_name
                ]
            )

    with pytest.raises(
        RuntimeError, match="required qualification evidence schema is missing"
    ):
        validate_qualification_evidence_schema(BrokenQualificationSchemaDB("off"))


def test_chat_schema_probe_lists_every_required_table():
    # The required-table sets decide what must exist; the VALUES list is what
    # actually asks PostgreSQL. A table declared in one but not the other is
    # reported missing forever, so keep them in lockstep.
    import inspect
    import re

    from backend.services import runtime_validation

    source = inspect.getsource(runtime_validation.validate_chat_schema)
    declared_section, probe_section = source.split("rows = dict(", 1)
    declared = set(re.findall(r'"(chat_[a-z_]+)"', declared_section))
    probed = set(re.findall(r"\('(chat_[a-z_]+)'\)", probe_section))

    assert declared, "no required chat tables declared"
    assert declared <= probed, sorted(declared - probed)
