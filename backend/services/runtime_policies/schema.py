"""Fail-closed database schema validation for chat runtime tables."""

from __future__ import annotations

import re

from sqlalchemy import text

from backend.config import Settings


def validate_external_worker_reservation_schema(db) -> None:
    """Require model/migration parity for protected external-worker admission."""
    expected_columns = {
        "request_id": ("character varying", "NO", 200),
        "turn_id": ("uuid", "YES", None),
        "endpoint_id": ("character varying", "NO", 128),
        "worker_id": ("character varying", "NO", 128),
        "instance_id": ("uuid", "NO", None),
        "worker_generation": ("bigint", "NO", None),
        "release_id": ("character varying", "NO", 255),
        "contract_version": ("character varying", "NO", 128),
        "maximum_sessions": ("integer", "NO", None),
        "reserved_at": ("timestamp with time zone", "NO", None),
        "expires_at": ("timestamp with time zone", "NO", None),
    }
    columns = {
        name: (data_type, nullable, maximum_length)
        for name, data_type, nullable, maximum_length in db.execute(
            text("""
                SELECT column_name, data_type, is_nullable, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'chat_external_worker_reservations'
                """)
        ).all()
    }
    if columns != expected_columns:
        raise RuntimeError("required external worker schema is missing")

    index_rows = dict(
        db.execute(
            text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = 'chat_external_worker_reservations'
                """)
        ).all()
    )
    expected_index_names = {
        "chat_external_worker_reservations_pkey",
        "chat_external_worker_reservations_turn_id_key",
        "idx_chat_external_worker_reservations_capacity",
        "idx_chat_external_worker_reservations_unbound_expiry",
    }
    if set(index_rows) != expected_index_names:
        raise RuntimeError("required external worker schema is missing")
    normalized_indexes = {
        name: " ".join(definition.lower().replace('"', "").split())
        for name, definition in index_rows.items()
    }
    index_contracts = {
        "chat_external_worker_reservations_pkey": (
            True,
            "(request_id)",
            None,
        ),
        "chat_external_worker_reservations_turn_id_key": (
            True,
            "(turn_id)",
            None,
        ),
        "idx_chat_external_worker_reservations_capacity": (
            False,
            "(worker_id, instance_id, worker_generation)",
            None,
        ),
        "idx_chat_external_worker_reservations_unbound_expiry": (
            False,
            "(expires_at)",
            "where (turn_id is null)",
        ),
    }
    for name, (unique, columns_text, predicate) in index_contracts.items():
        definition = normalized_indexes[name]
        if (
            (definition.startswith("create unique index ") != unique)
            or f" using btree {columns_text}" not in definition
            or (predicate is None and " where " in definition)
            or (predicate is not None and not definition.endswith(predicate))
        ):
            raise RuntimeError("required external worker schema is missing")

    constraint_rows = dict(
        db.execute(
            text("""
                SELECT constraint_row.conname,
                       pg_get_constraintdef(constraint_row.oid, true)
                FROM pg_constraint AS constraint_row
                JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
                JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = current_schema()
                  AND relation.relname = 'chat_external_worker_reservations'
                  AND conname IN (
                      'chat_external_worker_reservations_pkey',
                      'chat_external_worker_reservations_turn_id_key',
                      'chat_external_worker_reservations_worker_generation_check',
                      'chat_external_worker_reservations_maximum_sessions_check'
                  )
                """)
        ).all()
    )
    expected_constraint_names = {
        "chat_external_worker_reservations_pkey",
        "chat_external_worker_reservations_turn_id_key",
        "chat_external_worker_reservations_worker_generation_check",
        "chat_external_worker_reservations_maximum_sessions_check",
    }
    if set(constraint_rows) != expected_constraint_names:
        raise RuntimeError("required external worker schema is missing")
    definitions = {
        name: " ".join(definition.lower().replace('"', "").split())
        for name, definition in constraint_rows.items()
    }
    generation_check = definitions[
        "chat_external_worker_reservations_worker_generation_check"
    ]
    maximum_check = definitions[
        "chat_external_worker_reservations_maximum_sessions_check"
    ]
    if (
        definitions["chat_external_worker_reservations_pkey"]
        != "primary key (request_id)"
        or definitions["chat_external_worker_reservations_turn_id_key"]
        != "unique (turn_id)"
        or not re.fullmatch(r"check \(\(*worker_generation > 0\)*\)", generation_check)
        or not (
            re.fullmatch(
                r"check \(\(*maximum_sessions between 1 and 32\)*\)", maximum_check
            )
            or re.fullmatch(
                r"check \(\(*maximum_sessions >= 1\)* and "
                r"\(*maximum_sessions <= 32\)*\)",
                maximum_check,
            )
        )
    ):
        raise RuntimeError("required external worker schema is missing")


def validate_qualification_evidence_schema(db) -> None:
    """Require the exact durable qualification storage contract."""
    columns = {
        (table, column): (data_type, nullable, maximum_length, default)
        for table, column, data_type, nullable, maximum_length, default in db.execute(
            text("""
                /* qualification_evidence_exact_columns */
                SELECT table_name, column_name, data_type, is_nullable,
                       character_maximum_length, column_default
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name IN (
                    'chat_qualification_scopes',
                    'chat_qualification_evidence_events',
                    'chat_turn_latency'
                  )
            """)
        ).all()
    }
    required_columns = {
        ("chat_qualification_scopes", "id"): ("uuid", "NO", None, None),
        ("chat_qualification_scopes", "run_id"): ("character varying", "NO", 64, None),
        ("chat_qualification_scopes", "profile"): ("character varying", "NO", 32, None),
        ("chat_qualification_scopes", "app_release_id"): (
            "character varying",
            "NO",
            255,
            None,
        ),
        ("chat_qualification_scopes", "window_started_at"): (
            "timestamp with time zone",
            "NO",
            None,
            None,
        ),
        ("chat_qualification_scopes", "window_ended_at"): (
            "timestamp with time zone",
            "YES",
            None,
            None,
        ),
        ("chat_qualification_scopes", "expires_at"): (
            "timestamp with time zone",
            "NO",
            None,
            None,
        ),
        ("chat_qualification_scopes", "created_at"): (
            "timestamp with time zone",
            "NO",
            None,
            "now()",
        ),
        ("chat_qualification_evidence_events", "id"): ("uuid", "NO", None, None),
        ("chat_qualification_evidence_events", "qualification_scope_id"): (
            "uuid",
            "NO",
            None,
            None,
        ),
        ("chat_qualification_evidence_events", "turn_id"): ("uuid", "NO", None, None),
        ("chat_qualification_evidence_events", "chat_session_id"): (
            "uuid",
            "NO",
            None,
            None,
        ),
        ("chat_qualification_evidence_events", "event_type"): (
            "character varying",
            "NO",
            32,
            None,
        ),
        ("chat_qualification_evidence_events", "operation_digest"): (
            "character varying",
            "YES",
            64,
            None,
        ),
        ("chat_qualification_evidence_events", "operation_kind"): (
            "character varying",
            "YES",
            8,
            None,
        ),
        ("chat_qualification_evidence_events", "occurred_at"): (
            "timestamp with time zone",
            "NO",
            None,
            None,
        ),
        ("chat_turn_latency", "qualification_run_id"): (
            "character varying",
            "YES",
            64,
            None,
        ),
        ("chat_turn_latency", "qualification_scope_id"): ("uuid", "YES", None, None),
        ("chat_turn_latency", "qualification_profile"): (
            "character varying",
            "YES",
            32,
            None,
        ),
        ("chat_turn_latency", "qualification_workload"): (
            "character varying",
            "YES",
            16,
            None,
        ),
        ("chat_turn_latency", "qualification_scenario"): (
            "character varying",
            "YES",
            32,
            None,
        ),
    }
    contract_columns = {
        key: value
        for key, value in columns.items()
        if key[0]
        in {
            "chat_qualification_scopes",
            "chat_qualification_evidence_events",
        }
        or key[1].startswith("qualification_")
    }
    if contract_columns != required_columns:
        raise RuntimeError("required qualification evidence schema is missing")

    constraints = {
        name: " ".join(definition.lower().replace('"', "").split())
        for name, definition in db.execute(
            text("""
                /* qualification_evidence_exact_constraints */
                SELECT conname, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE connamespace = current_schema()::regnamespace
                  AND (
                    conrelid = 'chat_qualification_scopes'::regclass
                    OR conrelid = 'chat_qualification_evidence_events'::regclass
                    OR (
                      conrelid = 'chat_turn_latency'::regclass
                      AND conname LIKE 'chat_turn_latency_qualification_%'
                    )
                  )
            """)
        ).all()
    }
    required_constraints = {
        "chat_qualification_scopes_pkey": "primary key (id)",
        "chat_qualification_scopes_run_id_key": "unique (run_id)",
        "chat_qualification_scopes_profile_check": "check (((profile)::text = any ((array['32-functional-turns'::character varying, '100-immediate-admission'::character varying])::text[])))",
        "chat_qualification_scopes_window_check": "check (((window_ended_at is null) or (window_ended_at >= window_started_at)))",
        "chat_qualification_scopes_expiry_check": "check ((expires_at > window_started_at))",
        "chat_qualification_evidence_events_pkey": "primary key (id)",
        "chat_qualification_evidence_scope_fkey": "foreign key (qualification_scope_id) references chat_qualification_scopes(id) on delete cascade",
        "chat_qualification_evidence_turn_fkey": "foreign key (turn_id) references chat_turn_jobs(turn_id) on delete cascade",
        "chat_qualification_evidence_session_fkey": "foreign key (chat_session_id) references chat_sessions(id) on delete cascade",
        "chat_qualification_evidence_event_type_check": "check (((event_type)::text = any ((array['admitted_no_queue'::character varying, 'executor_started'::character varying, 'stale_fence'::character varying, 'queued'::character varying, 'workspace_created'::character varying, 'workspace_reused'::character varying, 'workspace_evicted'::character varying])::text[])))",
        "chat_qualification_evidence_operation_shape_check": "check ((((event_type)::text = 'executor_started'::text) = ((operation_digest is not null) and (operation_kind is not null) and ((operation_kind)::text = any ((array['read'::character varying, 'bash'::character varying])::text[])))))",
        "chat_turn_latency_qualification_scope_fkey": "foreign key (qualification_scope_id) references chat_qualification_scopes(id) on delete set null",
        "chat_turn_latency_qualification_profile_check": "check (((qualification_profile is null) or ((qualification_profile)::text = any ((array['32-functional-turns'::character varying, '100-immediate-admission'::character varying])::text[]))))",
        "chat_turn_latency_qualification_workload_check": "check (((qualification_workload is null) or ((qualification_workload)::text = any ((array['no_tool'::character varying, 'read'::character varying, 'bash'::character varying])::text[]))))",
        "chat_turn_latency_qualification_scenario_check": "check (((qualification_scenario is null) or ((qualification_scenario)::text = any ((array['focused_latency'::character varying, 'reliability'::character varying, 'clean_cancel'::character varying, 'forced_failure'::character varying])::text[]))))",
    }
    if constraints != required_constraints:
        raise RuntimeError("required qualification evidence schema is missing")

    indexes = {
        name: (unique, list(index_columns), predicate)
        for name, unique, index_columns, predicate in db.execute(
            text("""
                /* qualification_evidence_exact_indexes */
                SELECT index_class.relname,
                       index_meta.indisunique,
                       ARRAY(
                         SELECT attribute.attname
                         FROM unnest(index_meta.indkey) WITH ORDINALITY AS key(attnum, position)
                         JOIN pg_attribute attribute
                           ON attribute.attrelid = table_class.oid
                          AND attribute.attnum = key.attnum
                         ORDER BY key.position
                       ),
                       pg_get_expr(index_meta.indpred, index_meta.indrelid)
                FROM pg_index index_meta
                JOIN pg_class index_class ON index_class.oid = index_meta.indexrelid
                JOIN pg_class table_class ON table_class.oid = index_meta.indrelid
                JOIN pg_namespace namespace ON namespace.oid = table_class.relnamespace
                WHERE namespace.nspname = current_schema()
                  AND index_class.relname IN (
                    'idx_chat_qualification_scopes_expiry',
                    'idx_chat_qualification_scopes_release_profile',
                    'idx_chat_qualification_evidence_scope_event_time',
                    'idx_chat_qualification_evidence_session_time',
                    'idx_chat_qualification_evidence_turn_event',
                    'uq_chat_qualification_evidence_stale_turn',
                    'uq_chat_qualification_evidence_eviction_turn',
                    'idx_chat_turn_latency_qualification_scope'
                  )
            """)
        ).all()
    }
    required_indexes = {
        "idx_chat_qualification_scopes_expiry": (False, ["expires_at"], None),
        "idx_chat_qualification_scopes_release_profile": (
            False,
            ["app_release_id", "profile"],
            None,
        ),
        "idx_chat_qualification_evidence_scope_event_time": (
            False,
            ["qualification_scope_id", "event_type", "occurred_at"],
            None,
        ),
        "idx_chat_qualification_evidence_session_time": (
            False,
            ["chat_session_id", "occurred_at"],
            None,
        ),
        "idx_chat_qualification_evidence_turn_event": (
            False,
            ["turn_id", "event_type"],
            None,
        ),
        "uq_chat_qualification_evidence_stale_turn": (
            True,
            ["qualification_scope_id", "turn_id"],
            "((event_type)::text = 'stale_fence'::text)",
        ),
        "uq_chat_qualification_evidence_eviction_turn": (
            True,
            ["qualification_scope_id", "turn_id"],
            "((event_type)::text = 'workspace_evicted'::text)",
        ),
        "idx_chat_turn_latency_qualification_scope": (
            False,
            ["qualification_scope_id", "admitted_at"],
            None,
        ),
    }
    if indexes != required_indexes:
        raise RuntimeError("required qualification evidence schema is missing")


def validate_chat_schema(db, settings: Settings) -> None:
    """Validate only the tables required by the enabled provider profile."""

    if db.execute(text("SHOW transaction_read_only")).scalar_one() != "off":
        raise RuntimeError("chat database connection is read-only")
    common_tables = {
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
        "chat_artifacts",
        "chat_latex_paper_versions",
        "chat_feedback",
    }
    pi_tables = {
        "chat_pi_sessions",
        "chat_pi_transcript_entries",
        "chat_pi_prepared_forks",
        "chat_harness_assignment_audit",
    }
    openrouter_tables = {
        "chat_openrouter_credentials",
        "chat_openrouter_monthly_usage",
        "chat_openrouter_provider_calls",
        "chat_openrouter_credential_audit",
    }
    web_search_tables = {
        "chat_web_search_budget_states",
        "chat_web_search_circuit_events",
        "chat_web_search_owner_usage",
    }
    durable_turn_tables = {"chat_turn_jobs", "chat_turn_event_chunks"}
    external_worker_tables = {
        "chat_external_workers",
        "chat_external_worker_reservations",
        "chat_qualification_scopes",
        "chat_qualification_evidence_events",
    }
    required_tables = (
        common_tables
        | (
            openrouter_tables
            if settings.chat_openrouter_server_funded_enabled
            else set()
        )
        | (web_search_tables if settings.chat_web_search_enabled else set())
        | (pi_tables if settings.chat_pi_runtime_enabled else set())
        | (
            durable_turn_tables
            if settings.chat_durable_turn_dispatch_enabled
            else set()
        )
        | (
            external_worker_tables
            if settings.chat_external_pi_admission_enabled
            else set()
        )
    )
    rows = dict(
        db.execute(
            text("""
                SELECT name, to_regclass(name)::text
                FROM (VALUES
                    ('chat_sessions'),
                    ('chat_messages'),
                    ('chat_shares'),
                    ('chat_sandbox_leases'),
                    ('chat_sandbox_pool'),
                    ('chat_sandbox_compute_intervals'),
                    ('chat_sandbox_budget_states'),
                    ('chat_sandbox_circuit_events'),
                    ('chat_title_budget_states'),
                    ('chat_title_provider_calls'),
                    ('chat_title_budget_events'),
                    ('chat_turn_capabilities'),
                    ('chat_turn_latency'),
                    ('chat_artifacts'),
                    ('chat_latex_paper_versions'),
                    ('chat_openrouter_credentials'),
                    ('chat_openrouter_monthly_usage'),
                    ('chat_openrouter_provider_calls'),
                    ('chat_openrouter_credential_audit')
                    ,('chat_web_search_budget_states')
                    ,('chat_web_search_circuit_events')
                    ,('chat_web_search_owner_usage')
                    ,('chat_pi_sessions')
                    ,('chat_pi_transcript_entries')
                    ,('chat_pi_prepared_forks')
                    ,('chat_harness_assignment_audit')
                    ,('chat_turn_jobs')
                    ,('chat_turn_event_chunks')
                    ,('chat_external_workers')
                    ,('chat_external_worker_reservations')
                    ,('chat_qualification_scopes')
                    ,('chat_qualification_evidence_events')
                    ,('chat_feedback')
                ) AS required(name)
                """)
        ).all()
    )
    missing = [name for name in required_tables if rows.get(name) is None]
    common_columns = {
        ("chat_sessions", "execution_backend"),
        ("chat_sessions", "reasoning_effort"),
        ("chat_sessions", "primary_paper_id"),
        ("chat_messages", "finish_reason"),
        ("chat_messages", "reasoning_effort"),
        ("chat_messages", "primary_paper_context"),
        ("chat_messages", "viewer_context"),
        ("chat_messages", "paper_selection"),
        ("chat_messages", "prepared_fork_sdk_session_id"),
        ("chat_messages", "prepared_fork_sdk_project_key"),
        ("chat_messages", "paper_mentions"),
        ("chat_messages", "effective_prompt"),
        ("chat_messages", "langfuse_trace_id"),
        ("chat_shares", "snapshot_version"),
        ("chat_shares", "messages"),
        ("chat_artifacts", "source_head_version_id"),
        ("chat_artifacts", "preview_head_version_id"),
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
        ("chat_sandbox_compute_intervals", "accrued_microusd"),
        ("chat_sandbox_budget_states", "circuit_state"),
        ("chat_sandbox_budget_states", "provider_floor_microusd"),
        ("chat_sandbox_budget_states", "last_reconciliation_attempt_at"),
        ("chat_sandbox_circuit_events", "fallback_delivery_state"),
        ("chat_sandbox_circuit_events", "fallback_next_delivery_attempt_at"),
        ("chat_title_budget_states", "reserved_microusd"),
        ("chat_title_budget_states", "spent_microusd"),
        ("chat_title_provider_calls", "actual_microusd"),
        ("chat_title_provider_calls", "provider_generation_id"),
        ("chat_title_budget_events", "fallback_delivery_state"),
        ("chat_turn_latency", "request_id"),
        ("chat_turn_latency", "terminal_status"),
        ("chat_turn_latency", "browser_first_visible_delta_ms"),
        ("chat_turn_latency", "browser_first_reasoning_delta_ms"),
        ("chat_turn_latency", "first_semantic_event_ms"),
        ("chat_turn_latency", "pool_miss_reason"),
        ("chat_turn_latency", "session_reuse_cohort"),
        ("chat_turn_latency", "estimated_active_cost_usd"),
        ("chat_turn_latency", "qualification_run_id"),
        ("chat_turn_latency", "qualification_scope_id"),
        ("chat_turn_latency", "qualification_profile"),
        ("chat_turn_latency", "qualification_workload"),
        ("chat_turn_latency", "qualification_scenario"),
        ("chat_turn_latency", "failure_stage"),
        ("chat_turn_latency", "failure_class"),
        ("chat_turn_latency", "attempt_kind"),
        ("chat_turn_latency", "retry_overhead_ms"),
        ("chat_turn_capabilities", "provider_mode"),
        ("chat_turn_capabilities", "provider_credential_revision"),
        ("chat_turn_capabilities", "provider_error_code"),
        ("chat_turn_capabilities", "reasoning_effort"),
    }
    pi_columns = {
        ("chat_sessions", "agent_harness"),
        ("chat_messages", "agent_harness"),
        ("chat_messages", "agent_resume_boundary_id"),
        ("chat_turn_latency", "agent_harness"),
        ("chat_turn_latency", "pi_version"),
        ("chat_turn_latency", "first_semantic_event_class"),
        ("chat_turn_capabilities", "agent_harness"),
    }
    openrouter_columns = {
        ("chat_openrouter_credentials", "credential_revision"),
        ("chat_openrouter_monthly_usage", "reserved_microusd"),
        ("chat_openrouter_provider_calls", "actual_microusd"),
        ("chat_openrouter_provider_calls", "reasoning_effort"),
        ("chat_openrouter_provider_calls", "routing_policy"),
        ("chat_openrouter_provider_calls", "provider_ttft_ms"),
        ("chat_openrouter_provider_calls", "system_token_bucket"),
    }
    web_search_columns = {
        ("chat_sessions", "web_search_enabled"),
        ("chat_messages", "web_search_enabled"),
        ("chat_turn_capabilities", "web_search_calls"),
        ("chat_turn_capabilities", "web_search_failed"),
    }
    hf_catalog_columns = {
        ("chat_turn_capabilities", "hf_catalog_calls"),
        ("chat_turn_capabilities", "hf_recursive_list_calls"),
    }
    durable_turn_columns = {
        ("chat_turn_jobs", "state"),
        ("chat_turn_jobs", "worker_id"),
        ("chat_turn_jobs", "worker_generation"),
        ("chat_turn_jobs", "lease_generation"),
        ("chat_turn_jobs", "lease_expires_at"),
        ("chat_turn_jobs", "terminal_at"),
        ("chat_turn_jobs", "failure_code"),
        ("chat_turn_jobs", "event_sequence"),
        ("chat_turn_jobs", "event_bytes"),
        ("chat_turn_event_chunks", "turn_id"),
        ("chat_turn_event_chunks", "first_sequence"),
        ("chat_turn_event_chunks", "last_sequence"),
        ("chat_turn_event_chunks", "events"),
        ("chat_turn_event_chunks", "payload_bytes"),
    }
    external_worker_columns = {
        ("chat_external_workers", "worker_id"),
        ("chat_external_workers", "instance_id"),
        ("chat_external_workers", "environment"),
        ("chat_external_workers", "release_id"),
        ("chat_external_workers", "contract_version"),
        ("chat_external_workers", "generation"),
        ("chat_external_workers", "state"),
        ("chat_external_workers", "maximum_sessions"),
        ("chat_external_workers", "active_sessions"),
        ("chat_external_workers", "lease_expires_at"),
        ("chat_external_worker_reservations", "request_id"),
        ("chat_external_worker_reservations", "turn_id"),
        ("chat_external_worker_reservations", "endpoint_id"),
        ("chat_external_worker_reservations", "worker_id"),
        ("chat_external_worker_reservations", "instance_id"),
        ("chat_external_worker_reservations", "worker_generation"),
        ("chat_external_worker_reservations", "release_id"),
        ("chat_external_worker_reservations", "contract_version"),
        ("chat_external_worker_reservations", "maximum_sessions"),
        ("chat_external_worker_reservations", "reserved_at"),
        ("chat_external_worker_reservations", "expires_at"),
        ("chat_qualification_evidence_events", "id"),
        ("chat_qualification_evidence_events", "qualification_scope_id"),
        ("chat_qualification_evidence_events", "turn_id"),
        ("chat_qualification_evidence_events", "chat_session_id"),
        ("chat_qualification_evidence_events", "event_type"),
        ("chat_qualification_evidence_events", "operation_digest"),
        ("chat_qualification_evidence_events", "operation_kind"),
        ("chat_qualification_evidence_events", "occurred_at"),
        ("chat_qualification_scopes", "id"),
        ("chat_qualification_scopes", "run_id"),
        ("chat_qualification_scopes", "profile"),
        ("chat_qualification_scopes", "app_release_id"),
        ("chat_qualification_scopes", "window_started_at"),
        ("chat_qualification_scopes", "window_ended_at"),
        ("chat_qualification_scopes", "expires_at"),
        ("chat_turn_latency", "qualification_scope_id"),
        ("chat_turn_latency", "qualification_profile"),
    }
    expected_columns = (
        common_columns
        | (
            openrouter_columns
            if settings.chat_openrouter_server_funded_enabled
            else set()
        )
        | (web_search_columns if settings.chat_web_search_enabled else set())
        | (hf_catalog_columns if settings.chat_hf_catalog_enabled else set())
        | (pi_columns if settings.chat_pi_runtime_enabled else set())
        | (
            durable_turn_columns
            if settings.chat_durable_turn_dispatch_enabled
            else set()
        )
        | (
            external_worker_columns
            if settings.chat_external_pi_admission_enabled
            else set()
        )
    )
    present_columns = set(
        db.execute(
            text("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE (table_name, column_name) IN (
                ('chat_sessions', 'execution_backend'),
                ('chat_sessions', 'reasoning_effort'),
                ('chat_sessions', 'primary_paper_id'),
                ('chat_sessions', 'agent_harness'),
                ('chat_messages', 'finish_reason'),
                ('chat_messages', 'reasoning_effort'),
                ('chat_messages', 'primary_paper_context'),
                ('chat_messages', 'viewer_context'),
                ('chat_messages', 'paper_selection'),
                ('chat_messages', 'prepared_fork_sdk_session_id'),
                ('chat_messages', 'prepared_fork_sdk_project_key'),
                ('chat_messages', 'paper_mentions'),
                ('chat_messages', 'effective_prompt'),
                ('chat_messages', 'langfuse_trace_id'),
                ('chat_messages', 'agent_harness'),
                ('chat_messages', 'agent_resume_boundary_id'),
                ('chat_shares', 'snapshot_version'),
                ('chat_shares', 'messages'),
                ('chat_artifacts', 'source_head_version_id'),
                ('chat_artifacts', 'preview_head_version_id'),
                ('chat_sandbox_leases', 'worker_generation'),
                ('chat_sandbox_leases', 'egress_policy_digest'),
                ('chat_sandbox_pool', 'modal_sandbox_id'),
                ('chat_sandbox_pool', 'worker_generation'),
                ('chat_sandbox_pool', 'billing_month'),
                ('chat_sandbox_pool', 'estimated_blank_cost_usd'),
                ('chat_sandbox_pool', 'agent_harness'),
                ('chat_sandbox_pool', 'agent_harness_version'),
                ('chat_sandbox_pool', 'model_profile'),
                ('chat_sandbox_pool', 'reasoning_profile'),
                ('chat_sandbox_pool', 'prompt_digest'),
                ('chat_sandbox_pool', 'provider_adapter_contract'),
                ('chat_sandbox_pool', 'egress_policy_digest'),
                ('chat_sandbox_pool', 'provider_create_ms'),
                ('chat_sandbox_pool', 'backend_control_connect_ms'),
                ('chat_sandbox_pool', 'broker_ready_ms'),
                ('chat_sandbox_pool', 'control_ready_ms'),
                ('chat_sandbox_pool', 'agent_spawn_ms'),
                ('chat_sandbox_pool', 'agent_startup_ready_ms'),
                ('chat_sandbox_pool', 'health_check_token_hash'),
                ('chat_sandbox_pool', 'health_check_started_at'),
                ('chat_sandbox_compute_intervals', 'accrued_microusd'),
                ('chat_sandbox_budget_states', 'circuit_state'),
                ('chat_sandbox_budget_states', 'provider_floor_microusd'),
                ('chat_sandbox_budget_states', 'last_reconciliation_attempt_at'),
                ('chat_sandbox_circuit_events', 'fallback_delivery_state'),
                ('chat_sandbox_circuit_events', 'fallback_next_delivery_attempt_at'),
                ('chat_title_budget_states', 'reserved_microusd'),
                ('chat_title_budget_states', 'spent_microusd'),
                ('chat_title_provider_calls', 'actual_microusd'),
                ('chat_title_provider_calls', 'provider_generation_id'),
                ('chat_title_budget_events', 'fallback_delivery_state'),
                ('chat_turn_latency', 'request_id'),
                ('chat_turn_latency', 'terminal_status'),
                ('chat_turn_latency', 'browser_first_visible_delta_ms'),
                ('chat_turn_latency', 'browser_first_reasoning_delta_ms'),
                ('chat_turn_latency', 'first_semantic_event_ms'),
                ('chat_turn_latency', 'pool_miss_reason'),
                ('chat_turn_latency', 'session_reuse_cohort'),
                ('chat_turn_latency', 'estimated_active_cost_usd'),
                ('chat_turn_latency', 'qualification_run_id'),
                ('chat_turn_latency', 'qualification_scenario'),
                ('chat_turn_latency', 'failure_stage'),
                ('chat_turn_latency', 'failure_class'),
                ('chat_turn_latency', 'attempt_kind'),
                ('chat_turn_latency', 'retry_overhead_ms'),
                ('chat_turn_latency', 'agent_harness'),
                ('chat_turn_latency', 'pi_version'),
                ('chat_turn_latency', 'first_semantic_event_class'),
                ('chat_turn_capabilities', 'provider_mode'),
                ('chat_turn_capabilities', 'provider_credential_revision'),
                ('chat_turn_capabilities', 'provider_error_code'),
                ('chat_turn_capabilities', 'reasoning_effort'),
                ('chat_turn_capabilities', 'agent_harness'),
                ('chat_openrouter_credentials', 'credential_revision'),
                ('chat_openrouter_monthly_usage', 'reserved_microusd'),
                ('chat_openrouter_provider_calls', 'actual_microusd')
                ,('chat_openrouter_provider_calls', 'reasoning_effort')
                ,('chat_openrouter_provider_calls', 'routing_policy')
                ,('chat_openrouter_provider_calls', 'provider_ttft_ms')
                ,('chat_openrouter_provider_calls', 'system_token_bucket')
                ,('chat_sessions', 'web_search_enabled')
                ,('chat_messages', 'web_search_enabled')
                ,('chat_turn_capabilities', 'web_search_calls')
                ,('chat_turn_capabilities', 'web_search_failed')
                ,('chat_turn_capabilities', 'hf_catalog_calls')
                ,('chat_turn_capabilities', 'hf_recursive_list_calls')
                ,('chat_turn_jobs', 'state')
                ,('chat_turn_jobs', 'worker_id')
                ,('chat_turn_jobs', 'worker_generation')
                ,('chat_turn_jobs', 'lease_generation')
                ,('chat_turn_jobs', 'lease_expires_at')
                ,('chat_turn_jobs', 'terminal_at')
                ,('chat_turn_jobs', 'failure_code')
                ,('chat_turn_jobs', 'event_sequence')
                ,('chat_turn_jobs', 'event_bytes')
                ,('chat_turn_event_chunks', 'turn_id')
                ,('chat_turn_event_chunks', 'first_sequence')
                ,('chat_turn_event_chunks', 'last_sequence')
                ,('chat_turn_event_chunks', 'events')
                ,('chat_turn_event_chunks', 'payload_bytes')
                ,('chat_external_workers', 'worker_id')
                ,('chat_external_workers', 'instance_id')
                ,('chat_external_workers', 'environment')
                ,('chat_external_workers', 'release_id')
                ,('chat_external_workers', 'contract_version')
                ,('chat_external_workers', 'generation')
                ,('chat_external_workers', 'state')
                ,('chat_external_workers', 'maximum_sessions')
                ,('chat_external_workers', 'active_sessions')
                ,('chat_external_workers', 'lease_expires_at')
                ,('chat_external_worker_reservations', 'request_id')
                ,('chat_external_worker_reservations', 'turn_id')
                ,('chat_external_worker_reservations', 'endpoint_id')
                ,('chat_external_worker_reservations', 'worker_id')
                ,('chat_external_worker_reservations', 'instance_id')
                ,('chat_external_worker_reservations', 'worker_generation')
                ,('chat_external_worker_reservations', 'release_id')
                ,('chat_external_worker_reservations', 'contract_version')
                ,('chat_external_worker_reservations', 'maximum_sessions')
                ,('chat_external_worker_reservations', 'reserved_at')
                ,('chat_external_worker_reservations', 'expires_at')
                ,('chat_qualification_evidence_events', 'id')
                ,('chat_qualification_evidence_events', 'qualification_scope_id')
                ,('chat_qualification_evidence_events', 'turn_id')
                ,('chat_qualification_evidence_events', 'chat_session_id')
                ,('chat_qualification_evidence_events', 'event_type')
                ,('chat_qualification_evidence_events', 'operation_digest')
                ,('chat_qualification_evidence_events', 'operation_kind')
                ,('chat_qualification_evidence_events', 'occurred_at')
                ,('chat_qualification_scopes', 'id')
                ,('chat_qualification_scopes', 'run_id')
                ,('chat_qualification_scopes', 'profile')
                ,('chat_qualification_scopes', 'app_release_id')
                ,('chat_qualification_scopes', 'window_started_at')
                ,('chat_qualification_scopes', 'window_ended_at')
                ,('chat_qualification_scopes', 'expires_at')
                ,('chat_turn_latency', 'qualification_scope_id')
                ,('chat_turn_latency', 'qualification_profile')
                ,('chat_turn_latency', 'qualification_workload')
            )
            """)
        ).all()
    )
    missing_columns = expected_columns - present_columns
    if settings.chat_external_pi_admission_enabled and (
        "chat_external_worker_reservations" in missing
        or any(
            table == "chat_external_worker_reservations"
            for table, _column in missing_columns
        )
    ):
        raise RuntimeError("required external worker schema is missing")
    if missing or missing_columns:
        raise RuntimeError("required chat sandbox schema is missing")
    if settings.chat_durable_turn_dispatch_enabled:
        durable_contract = set(
            db.execute(
                text("""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname IN (
                          'idx_chat_turn_jobs_expiry',
                          'idx_chat_turn_jobs_terminal_cleanup',
                          'idx_chat_turn_event_chunks_after',
                          'uq_chat_turn_event_chunk_start'
                      )
                    """)
            ).scalars()
        )
        if durable_contract != {
            "idx_chat_turn_jobs_expiry",
            "idx_chat_turn_jobs_terminal_cleanup",
            "idx_chat_turn_event_chunks_after",
            "uq_chat_turn_event_chunk_start",
        }:
            raise RuntimeError("required durable chat schema is missing")
        durable_constraints = set(
            db.execute(
                text("""
                    SELECT conname
                    FROM pg_constraint
                    WHERE conname IN (
                        'chat_turn_jobs_state_check',
                        'chat_turn_jobs_lease_fields_check',
                        'chat_turn_jobs_terminal_timestamp_check',
                        'ck_chat_turn_event_chunk_range'
                    )
                    """)
            ).scalars()
        )
        if durable_constraints != {
            "chat_turn_jobs_state_check",
            "chat_turn_jobs_lease_fields_check",
            "chat_turn_jobs_terminal_timestamp_check",
            "ck_chat_turn_event_chunk_range",
        }:
            raise RuntimeError("required durable chat schema is missing")
    if settings.chat_external_pi_admission_enabled:
        worker_indexes = set(
            db.execute(
                text("""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname = 'idx_chat_external_workers_dispatch'
                    """)
            ).scalars()
        )
        if worker_indexes != {"idx_chat_external_workers_dispatch"}:
            raise RuntimeError("required external worker schema is missing")
        validate_external_worker_reservation_schema(db)
        validate_qualification_evidence_schema(db)
    share_snapshot_constraint = db.execute(
        text("""
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = 'chat_shares'::regclass
              AND conname = 'chat_shares_messages_array_check'
            """)
    ).first()
    if share_snapshot_constraint is None:
        raise RuntimeError("required chat sandbox schema is missing")
    artifact_head_constraints = set(
        db.execute(
            text("""
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'chat_artifacts'::regclass
                  AND confrelid = 'chat_latex_paper_versions'::regclass
                  AND contype = 'f'
                  AND conname IN (
                      'chat_artifacts_source_head_version_fkey',
                      'chat_artifacts_preview_head_version_fkey'
                  )
                """)
        ).all()
    )
    if artifact_head_constraints != {
        ("chat_artifacts_source_head_version_fkey",),
        ("chat_artifacts_preview_head_version_fkey",),
    }:
        raise RuntimeError("required chat sandbox schema is missing")
