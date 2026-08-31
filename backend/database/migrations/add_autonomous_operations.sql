BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_autonomous_operations.sql requires search_path staging,public or public';
    END IF;
    IF current_schema() = 'staging'
       AND (NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
            OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner')) THEN
        RAISE EXCEPTION
            'staging autonomous operations requires pwc_staging and pwc_staging_owner';
    END IF;
    IF current_schema() = 'public'
       AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        RAISE EXCEPTION
            'production autonomous operations requires paperswithcode_user';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS autonomous_operator_state (
    operator VARCHAR(32) PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT false,
    manual_mode BOOLEAN NOT NULL DEFAULT false,
    revision BIGINT NOT NULL DEFAULT 1,
    updated_by VARCHAR(255) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT autonomous_operator_state_operator_check CHECK (
        operator IN ('global','submissions','curation','cron_health','chat_reliability')
    ),
    CONSTRAINT autonomous_operator_state_manual_check CHECK (
        operator = 'global' OR NOT manual_mode
    ),
    CONSTRAINT autonomous_operator_state_global_check CHECK (
        operator <> 'global' OR NOT enabled
    ),
    CONSTRAINT autonomous_operator_state_revision_check CHECK (revision > 0)
);

INSERT INTO autonomous_operator_state (
    operator, enabled, manual_mode, revision, updated_by
) VALUES
    ('global', false, true, 1, 'system:migration'),
    ('submissions', false, false, 1, 'system:migration'),
    ('curation', false, false, 1, 'system:migration'),
    ('cron_health', false, false, 1, 'system:migration'),
    ('chat_reliability', false, false, 1, 'system:migration')
ON CONFLICT (operator) DO NOTHING;

CREATE TABLE IF NOT EXISTS autonomous_execution_intent (
    run_id UUID PRIMARY KEY,
    operator VARCHAR(32) NOT NULL,
    dry_run BOOLEAN NOT NULL,
    manifest_revision VARCHAR(128) NOT NULL,
    request_digest VARCHAR(64) NOT NULL,
    evidence_digests JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_alias VARCHAR(32) NOT NULL,
    budget_usd NUMERIC(18, 9) NOT NULL,
    pricing_policy_digest VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT autonomous_execution_intent_operator_check CHECK (
        operator IN ('submissions','curation','cron_health','chat_reliability')
    ),
    CONSTRAINT autonomous_execution_intent_model_alias_check CHECK (
        model_alias IN ('diagnosis','independent_review')
    ),
    CONSTRAINT autonomous_execution_intent_integrity_check CHECK (
        budget_usd > 0 AND length(request_digest) = 64
        AND length(pricing_policy_digest) = 64
    )
);

CREATE TABLE IF NOT EXISTS autonomous_run (
    id UUID PRIMARY KEY,
    operator VARCHAR(32) NOT NULL,
    dry_run BOOLEAN NOT NULL,
    manifest_revision VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    cost_usd NUMERIC(18, 9) NOT NULL DEFAULT 0,
    result_digest VARCHAR(64),
    exit_classification VARCHAR(32) NOT NULL DEFAULT 'unknown',
    capability_requests JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_digests JSONB NOT NULL DEFAULT '[]'::jsonb,
    pricing_revision VARCHAR(128) NOT NULL DEFAULT 'unknown',
    pricing_policy_digest VARCHAR(64) NOT NULL
        DEFAULT repeat('0', 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT autonomous_run_operator_check CHECK (
        operator IN ('submissions','curation','cron_health','chat_reliability')
    ),
    CONSTRAINT autonomous_run_status_check CHECK (
        status IN ('completed','rejected','failed','budget_exhausted','cancelled')
    ),
    CONSTRAINT autonomous_run_usage_check CHECK (
        input_tokens >= 0 AND output_tokens >= 0 AND cost_usd >= 0
    ),
    CONSTRAINT autonomous_run_digest_check CHECK (
        result_digest IS NULL OR length(result_digest) = 64
    ),
    CONSTRAINT autonomous_run_exit_classification_check CHECK (
        exit_classification IN (
            'unknown','completed','rejected','timeout','cancelled',
            'budget_exhausted','malformed_output','process_error',
            'output_limit','credential_missing','configuration_missing',
            'credential_revoke_failed','interrupted'
        )
    ),
    CONSTRAINT autonomous_run_capability_requests_check CHECK (
        jsonb_typeof(capability_requests) = 'array'
    ),
    CONSTRAINT autonomous_run_evidence_digests_check CHECK (
        jsonb_typeof(evidence_digests) = 'array'
    ),
    CONSTRAINT autonomous_run_pricing_policy_digest_check CHECK (
        length(pricing_policy_digest) = 64
    ),
    CONSTRAINT uq_autonomous_run_id_operator UNIQUE (id, operator)
);

ALTER TABLE autonomous_run
    ADD COLUMN IF NOT EXISTS exit_classification VARCHAR(32)
    NOT NULL DEFAULT 'unknown';
ALTER TABLE autonomous_run
    ADD COLUMN IF NOT EXISTS capability_requests JSONB
    NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE autonomous_run
    ADD COLUMN IF NOT EXISTS evidence_digests JSONB
    NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE autonomous_run
    ADD COLUMN IF NOT EXISTS pricing_revision VARCHAR(128)
    NOT NULL DEFAULT 'unknown';
ALTER TABLE autonomous_run
    ADD COLUMN IF NOT EXISTS pricing_policy_digest VARCHAR(64)
    NOT NULL DEFAULT repeat('0', 64);
ALTER TABLE autonomous_run
    ALTER COLUMN cost_usd TYPE NUMERIC(18, 9);

DO $$
BEGIN
    ALTER TABLE autonomous_run DROP CONSTRAINT IF EXISTS
        autonomous_run_exit_classification_check;
    ALTER TABLE autonomous_run ADD CONSTRAINT
        autonomous_run_exit_classification_check CHECK (
            exit_classification IN (
                'unknown','completed','rejected','timeout','cancelled',
                'budget_exhausted','malformed_output','process_error',
                'output_limit','credential_missing','configuration_missing',
                'credential_revoke_failed','interrupted'
            )
        );
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'autonomous_run_capability_requests_check'
          AND connamespace = current_schema()::regnamespace
    ) THEN
        ALTER TABLE autonomous_run ADD CONSTRAINT
            autonomous_run_capability_requests_check CHECK (
                jsonb_typeof(capability_requests) = 'array'
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'autonomous_run_evidence_digests_check'
          AND connamespace = current_schema()::regnamespace
    ) THEN
        ALTER TABLE autonomous_run ADD CONSTRAINT
            autonomous_run_evidence_digests_check CHECK (
                jsonb_typeof(evidence_digests) = 'array'
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'autonomous_run_pricing_policy_digest_check'
          AND connamespace = current_schema()::regnamespace
    ) THEN
        ALTER TABLE autonomous_run ADD CONSTRAINT
            autonomous_run_pricing_policy_digest_check CHECK (
                length(pricing_policy_digest) = 64
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_autonomous_run_operator_created
    ON autonomous_run (operator, created_at);

CREATE TABLE IF NOT EXISTS autonomous_budget_reservation (
    run_id UUID PRIMARY KEY,
    operator VARCHAR(32) NOT NULL,
    reservation_id VARCHAR(128) NOT NULL UNIQUE,
    provider VARCHAR(32) NOT NULL,
    model_alias VARCHAR(32) NOT NULL,
    limit_usd NUMERIC(18, 9) NOT NULL,
    attestation_digest VARCHAR(64) NOT NULL,
    request_digest VARCHAR(64) NOT NULL,
    endpoint_digest VARCHAR(64) NOT NULL,
    credential_scope VARCHAR(32) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    claim_id UUID NOT NULL,
    claim_expires_at TIMESTAMPTZ NOT NULL,
    state VARCHAR(32) NOT NULL DEFAULT 'claimed',
    authoritative_input_tokens BIGINT NOT NULL DEFAULT 0,
    authoritative_output_tokens BIGINT NOT NULL DEFAULT 0,
    authoritative_cost_usd NUMERIC(18, 9) NOT NULL DEFAULT 0,
    cost_upper_bound_usd NUMERIC(18, 9) NOT NULL DEFAULT 0,
    reconciliation_required BOOLEAN NOT NULL DEFAULT false,
    released_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT autonomous_budget_reservation_operator_check CHECK (
        operator IN ('submissions','curation','cron_health','chat_reliability')
    ),
    CONSTRAINT autonomous_budget_reservation_provider_check CHECK (
        provider = 'openai'
    ),
    CONSTRAINT autonomous_budget_reservation_model_alias_check CHECK (
        model_alias IN ('diagnosis','independent_review')
    ),
    CONSTRAINT autonomous_budget_reservation_integrity_check CHECK (
        limit_usd > 0 AND length(attestation_digest) = 64
    ),
    CONSTRAINT autonomous_budget_reservation_scope_check CHECK (
        length(request_digest) = 64 AND length(endpoint_digest) = 64
        AND credential_scope = 'responses'
    ),
    CONSTRAINT autonomous_budget_reservation_lifecycle_check CHECK (
        state IN ('claimed','released','release_failed','unknown')
        AND authoritative_input_tokens >= 0
        AND authoritative_output_tokens >= 0
        AND authoritative_cost_usd >= 0
        AND authoritative_cost_usd <= cost_upper_bound_usd
        AND cost_upper_bound_usd <= limit_usd
        AND (
            (state = 'released' AND reconciliation_required = false
                AND released_at IS NOT NULL)
            OR (state IN ('release_failed','unknown')
                AND reconciliation_required = true AND released_at IS NULL)
            OR (state = 'claimed' AND reconciliation_required = false
                AND released_at IS NULL)
        )
    )
);

ALTER TABLE autonomous_budget_reservation
    DROP CONSTRAINT IF EXISTS autonomous_budget_reservation_lifecycle_check;
ALTER TABLE autonomous_budget_reservation
    ADD CONSTRAINT autonomous_budget_reservation_lifecycle_check CHECK (
        state IN ('claimed','released','release_failed','unknown')
        AND authoritative_input_tokens >= 0
        AND authoritative_output_tokens >= 0
        AND authoritative_cost_usd >= 0
        AND authoritative_cost_usd <= cost_upper_bound_usd
        AND cost_upper_bound_usd <= limit_usd
        AND (
            (state = 'released' AND reconciliation_required = false
                AND released_at IS NOT NULL)
            OR (state IN ('release_failed','unknown')
                AND reconciliation_required = true AND released_at IS NULL)
            OR (state = 'claimed' AND reconciliation_required = false
                AND released_at IS NULL)
        )
    );

CREATE TABLE IF NOT EXISTS autonomous_action (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    operator VARCHAR(32) NOT NULL,
    capability VARCHAR(64) NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    resource_kind VARCHAR(64) NOT NULL,
    resource_identifier VARCHAR(255) NOT NULL,
    before_digest VARCHAR(64),
    after_digest VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT autonomous_action_operator_check CHECK (
        operator IN ('submissions','curation','cron_health','chat_reliability')
    ),
    CONSTRAINT autonomous_action_before_digest_check CHECK (
        before_digest IS NULL OR length(before_digest) = 64
    ),
    CONSTRAINT autonomous_action_after_digest_check CHECK (
        after_digest IS NULL OR length(after_digest) = 64
    ),
    CONSTRAINT fk_autonomous_action_run_operator
        FOREIGN KEY (run_id, operator)
        REFERENCES autonomous_run(id, operator) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_autonomous_action_run_created
    ON autonomous_action (run_id, created_at);

CREATE TABLE IF NOT EXISTS autonomous_control_event (
    id UUID PRIMARY KEY,
    actor VARCHAR(255) NOT NULL,
    event_kind VARCHAR(32) NOT NULL,
    target VARCHAR(64) NOT NULL,
    before_digest VARCHAR(64) NOT NULL,
    after_digest VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT autonomous_control_event_kind_check CHECK (
        event_kind IN ('manual_mode','operator_enabled','chat_baseline')
    ),
    CONSTRAINT autonomous_control_event_digest_check CHECK (
        length(before_digest) = 64 AND length(after_digest) = 64
    )
);

CREATE INDEX IF NOT EXISTS idx_autonomous_control_event_created
    ON autonomous_control_event (created_at);

CREATE TABLE IF NOT EXISTS autonomous_repair_lease (
    singleton_key VARCHAR(32) PRIMARY KEY,
    lease_id UUID NOT NULL UNIQUE,
    owner_run_id UUID NOT NULL,
    owner_operator VARCHAR(32) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT autonomous_repair_lease_singleton_check CHECK (
        singleton_key = 'source_repair'
    ),
    CONSTRAINT fk_autonomous_repair_lease_run_operator
        FOREIGN KEY (owner_run_id, owner_operator)
        REFERENCES autonomous_run(id, operator) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS autonomous_incident_attempt (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    operator VARCHAR(32) NOT NULL,
    signature VARCHAR(64) NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT autonomous_incident_attempt_operator_check CHECK (
        operator IN ('cron_health','chat_reliability')
    ),
    CONSTRAINT autonomous_incident_attempt_signature_check CHECK (
        length(signature) = 64
    ),
    CONSTRAINT fk_autonomous_incident_attempt_run_operator
        FOREIGN KEY (run_id, operator)
        REFERENCES autonomous_run(id, operator) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_autonomous_incident_attempt_window
    ON autonomous_incident_attempt (operator, signature, attempted_at);

CREATE TABLE IF NOT EXISTS chat_reliability_baseline (
    singleton BOOLEAN PRIMARY KEY,
    sha VARCHAR(40) NOT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    qualified_by VARCHAR(255) NOT NULL,
    qualified_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chat_reliability_baseline_singleton_check CHECK (singleton),
    CONSTRAINT chat_reliability_baseline_sha_check CHECK (length(sha) = 40),
    CONSTRAINT chat_reliability_baseline_revision_check CHECK (revision > 0)
);

CREATE TABLE IF NOT EXISTS chat_provider_runtime_state (
    environment VARCHAR(16) PRIMARY KEY,
    manifest_revision VARCHAR(128) NOT NULL,
    state_revision BIGINT NOT NULL DEFAULT 1,
    active_provider VARCHAR(64) NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chat_provider_runtime_state_environment_check CHECK (
        environment IN ('staging','production')
    ),
    CONSTRAINT chat_provider_runtime_state_revision_check CHECK (
        state_revision > 0
    )
);

CREATE OR REPLACE FUNCTION reject_autonomous_append_only_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS autonomous_run_no_update ON autonomous_run;
CREATE TRIGGER autonomous_run_no_update
    BEFORE UPDATE ON autonomous_run
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_run_no_delete ON autonomous_run;
CREATE TRIGGER autonomous_run_no_delete
    BEFORE DELETE ON autonomous_run
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_run_no_truncate ON autonomous_run;
CREATE TRIGGER autonomous_run_no_truncate
    BEFORE TRUNCATE ON autonomous_run
    FOR EACH STATEMENT EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_execution_intent_no_update
    ON autonomous_execution_intent;
CREATE TRIGGER autonomous_execution_intent_no_update
    BEFORE UPDATE ON autonomous_execution_intent
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_execution_intent_no_delete
    ON autonomous_execution_intent;
CREATE TRIGGER autonomous_execution_intent_no_delete
    BEFORE DELETE ON autonomous_execution_intent
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_execution_intent_no_truncate
    ON autonomous_execution_intent;
CREATE TRIGGER autonomous_execution_intent_no_truncate
    BEFORE TRUNCATE ON autonomous_execution_intent
    FOR EACH STATEMENT EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_action_no_update ON autonomous_action;
CREATE TRIGGER autonomous_action_no_update
    BEFORE UPDATE ON autonomous_action
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_action_no_delete ON autonomous_action;
CREATE TRIGGER autonomous_action_no_delete
    BEFORE DELETE ON autonomous_action
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_action_no_truncate ON autonomous_action;
CREATE TRIGGER autonomous_action_no_truncate
    BEFORE TRUNCATE ON autonomous_action
    FOR EACH STATEMENT EXECUTE FUNCTION reject_autonomous_append_only_mutation();

DROP TRIGGER IF EXISTS autonomous_budget_reservation_no_delete
    ON autonomous_budget_reservation;
CREATE TRIGGER autonomous_budget_reservation_no_delete
    BEFORE DELETE ON autonomous_budget_reservation
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_budget_reservation_no_truncate
    ON autonomous_budget_reservation;
CREATE TRIGGER autonomous_budget_reservation_no_truncate
    BEFORE TRUNCATE ON autonomous_budget_reservation
    FOR EACH STATEMENT EXECUTE FUNCTION reject_autonomous_append_only_mutation();

DROP TRIGGER IF EXISTS autonomous_control_no_update ON autonomous_control_event;
CREATE TRIGGER autonomous_control_no_update
    BEFORE UPDATE ON autonomous_control_event
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_control_no_delete ON autonomous_control_event;
CREATE TRIGGER autonomous_control_no_delete
    BEFORE DELETE ON autonomous_control_event
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_control_no_truncate ON autonomous_control_event;
CREATE TRIGGER autonomous_control_no_truncate
    BEFORE TRUNCATE ON autonomous_control_event
    FOR EACH STATEMENT EXECUTE FUNCTION reject_autonomous_append_only_mutation();

DROP TRIGGER IF EXISTS autonomous_attempt_no_update ON autonomous_incident_attempt;
CREATE TRIGGER autonomous_attempt_no_update
    BEFORE UPDATE ON autonomous_incident_attempt
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_attempt_no_delete ON autonomous_incident_attempt;
CREATE TRIGGER autonomous_attempt_no_delete
    BEFORE DELETE ON autonomous_incident_attempt
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_append_only_mutation();
DROP TRIGGER IF EXISTS autonomous_attempt_no_truncate ON autonomous_incident_attempt;
CREATE TRIGGER autonomous_attempt_no_truncate
    BEFORE TRUNCATE ON autonomous_incident_attempt
    FOR EACH STATEMENT EXECUTE FUNCTION reject_autonomous_append_only_mutation();

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'autonomous_operator_state',
        'autonomous_execution_intent',
        'autonomous_run',
        'autonomous_budget_reservation',
        'autonomous_action',
        'autonomous_control_event',
        'autonomous_repair_lease',
        'autonomous_incident_attempt',
        'chat_reliability_baseline',
        'chat_provider_runtime_state'
    ] LOOP
        IF current_schema() = 'staging' THEN
            EXECUTE format('ALTER TABLE %I OWNER TO pwc_staging_owner', table_name);
            EXECUTE format(
                'GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO pwc_staging',
                table_name
            );
            EXECUTE format('REVOKE ALL ON %I FROM paperswithcode_user', table_name);
        ELSE
            EXECUTE format('ALTER TABLE %I OWNER TO paperswithcode_user', table_name);
            EXECUTE format(
                'GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO paperswithcode_user',
                table_name
            );
            EXECUTE format('REVOKE ALL ON %I FROM pwc_staging', table_name);
        END IF;
    END LOOP;
END $$;

COMMIT;
