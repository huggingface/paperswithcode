-- Persistent executor v1 stores bounded routing/security metadata only.
-- Rollback audit rows remain in the normal PostgreSQL backup and restore path.
-- Privileged database administration is outside this v1 tamper-resistance boundary.

BEGIN;

CREATE TABLE IF NOT EXISTS chat_executor_manifests (
    digest varchar(64) PRIMARY KEY,
    parent_digest varchar(64) REFERENCES chat_executor_manifests(digest),
    image_digest varchar(64) NOT NULL,
    environment_binary_digest varchar(64) NOT NULL,
    daemon_digest varchar(64) NOT NULL,
    source_commit varchar(64) NOT NULL,
    release_id varchar(128) NOT NULL DEFAULT 'legacy'
        CHECK (length(release_id) BETWEEN 1 AND 128),
    protocol_version integer NOT NULL CHECK (protocol_version > 0),
    schema_digest varchar(64) NOT NULL,
    qualification_status varchar(16) NOT NULL
        CHECK (qualification_status IN ('pending','qualified','failed')),
    compatibility_state varchar(16) NOT NULL
        CHECK (compatibility_state IN ('current','compatible','incompatible')),
    qualification_evidence_ref varchar(255) NOT NULL,
    ready_capacity integer NOT NULL DEFAULT 0 CHECK (ready_capacity >= 0),
    compatibility_expires_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chat_executor_manifests_digest_check CHECK (
        length(digest)=64 AND length(image_digest)=64
        AND length(environment_binary_digest)=64 AND length(daemon_digest)=64
        AND length(source_commit)=64 AND length(schema_digest)=64
    )
);

CREATE TABLE IF NOT EXISTS chat_executor_cells (
    cell_id varchar(64) PRIMARY KEY,
    active_shard_id uuid,
    selected_manifest_digest varchar(64) REFERENCES chat_executor_manifests(digest),
    circuit_state varchar(16) NOT NULL DEFAULT 'closed'
        CHECK (circuit_state IN ('closed','open','half_open','security_hold')),
    circuit_revision bigint NOT NULL DEFAULT 1 CHECK (circuit_revision > 0),
    opened_at timestamptz,
    failure_window_started_at timestamptz,
    consecutive_attach_failures integer NOT NULL DEFAULT 0
        CHECK (consecutive_attach_failures >= 0),
    canary_lease_id uuid,
    canary_lease_expires_at timestamptz,
    canary_successes integer NOT NULL DEFAULT 0 CHECK (canary_successes BETWEEN 0 AND 3),
    key_epoch bigint NOT NULL DEFAULT 1 CHECK (key_epoch > 0),
    rollback_epoch bigint NOT NULL DEFAULT 0 CHECK (rollback_epoch >= 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chat_executor_cells_canary_pair_check CHECK (
        (canary_lease_id IS NULL) = (canary_lease_expires_at IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS chat_executor_shards (
    id uuid PRIMARY KEY,
    cell_id varchar(64) NOT NULL REFERENCES chat_executor_cells(cell_id),
    shard_id varchar(64) NOT NULL,
    generation bigint NOT NULL CHECK (generation > 0),
    state varchar(16) NOT NULL CHECK (state IN ('preparing','ready','draining','fenced')),
    ready_capacity integer NOT NULL DEFAULT 0 CHECK (ready_capacity >= 0),
    drain_started_at timestamptz,
    drain_deadline_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_chat_executor_shard_generation UNIQUE (cell_id,shard_id,generation),
    CONSTRAINT chat_executor_shards_drain_check CHECK (
        (drain_started_at IS NULL AND drain_deadline_at IS NULL)
        OR (drain_started_at IS NOT NULL AND drain_deadline_at >= drain_started_at)
    )
);

CREATE INDEX IF NOT EXISTS idx_chat_executor_shards_route
    ON chat_executor_shards(cell_id,state,generation);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_chat_executor_cells_active_shard'
          AND conrelid = 'chat_executor_cells'::regclass
    ) THEN
        ALTER TABLE chat_executor_cells
            ADD CONSTRAINT fk_chat_executor_cells_active_shard
            FOREIGN KEY (active_shard_id) REFERENCES chat_executor_shards(id);
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS chat_executor_registrations (
    id uuid PRIMARY KEY,
    environment_id varchar(64) NOT NULL,
    environment_generation bigint NOT NULL CHECK (environment_generation > 0),
    cell_id varchar(64) NOT NULL REFERENCES chat_executor_cells(cell_id),
    shard_id uuid NOT NULL REFERENCES chat_executor_shards(id),
    shard_generation bigint NOT NULL CHECK (shard_generation > 0),
    public_key_id varchar(64) NOT NULL CHECK (length(public_key_id)=64),
    public_noise_key jsonb NOT NULL,
    authorization_key_id varchar(128) NOT NULL,
    key_epoch bigint NOT NULL CHECK (key_epoch > 0),
    manifest_digest varchar(64) NOT NULL REFERENCES chat_executor_manifests(digest),
    state varchar(24) NOT NULL CHECK (
        state IN ('pending','ready','assigned_idle','claimed','suspect','draining','fenced','terminated')
    ),
    recovery_attempts integer NOT NULL DEFAULT 0,
    assigned_session_id uuid,
    last_seen_at timestamptz,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_chat_executor_environment_generation
        UNIQUE (environment_id,environment_generation),
    CONSTRAINT chat_executor_registrations_public_key_size_check
        CHECK (pg_column_size(public_noise_key) <= 4096),
    CONSTRAINT chat_executor_registrations_recovery_attempts_check
        CHECK (recovery_attempts BETWEEN 0 AND 3)
);

ALTER TABLE chat_executor_registrations
    ADD COLUMN IF NOT EXISTS recovery_attempts integer NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chat_executor_registrations_recovery_attempts_check'
          AND conrelid = 'chat_executor_registrations'::regclass
    ) THEN
        ALTER TABLE chat_executor_registrations
            ADD CONSTRAINT chat_executor_registrations_recovery_attempts_check
            CHECK (recovery_attempts BETWEEN 0 AND 3);
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_chat_executor_registrations_ready
    ON chat_executor_registrations(cell_id,shard_id,state,expires_at);

CREATE TABLE IF NOT EXISTS chat_executor_nonces (
    nonce_digest varchar(64) PRIMARY KEY CHECK (length(nonce_digest)=64),
    purpose varchar(16) NOT NULL CHECK (purpose IN ('launch','reconnect','liveness','recovery')),
    environment_id varchar(64) NOT NULL,
    environment_generation bigint NOT NULL CHECK (environment_generation > 0),
    shard_id uuid NOT NULL,
    shard_generation bigint NOT NULL CHECK (shard_generation > 0),
    key_epoch bigint NOT NULL CHECK (key_epoch > 0),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    invalidated_at timestamptz,
    retention_expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chat_executor_nonces_retention_check
        CHECK (retention_expires_at >= expires_at)
);

CREATE INDEX IF NOT EXISTS idx_chat_executor_nonces_cleanup
    ON chat_executor_nonces(retention_expires_at);

CREATE TABLE IF NOT EXISTS chat_executor_claims (
    turn_id uuid PRIMARY KEY,
    registration_id uuid NOT NULL REFERENCES chat_executor_registrations(id),
    claim_generation bigint NOT NULL CHECK (claim_generation > 0),
    cell_id varchar(64) NOT NULL,
    shard_id uuid NOT NULL,
    shard_generation bigint NOT NULL CHECK (shard_generation > 0),
    environment_generation bigint NOT NULL CHECK (environment_generation > 0),
    state varchar(16) NOT NULL CHECK (state IN ('active','settled','invalidated')),
    authorized_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    settled_at timestamptz,
    settlement_request_id uuid,
    terminal_code varchar(64),
    CONSTRAINT chat_executor_claims_settlement_check CHECK (
        (state='active' AND settled_at IS NULL AND settlement_request_id IS NULL)
        OR (state<>'active' AND settled_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_executor_claims_active_registration
    ON chat_executor_claims(registration_id) WHERE state='active';
CREATE INDEX IF NOT EXISTS idx_chat_executor_claims_expiry
    ON chat_executor_claims(state,expires_at);

CREATE TABLE IF NOT EXISTS chat_executor_key_revocations (
    id uuid PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE,
    cell_id varchar(64) NOT NULL,
    key_id varchar(128) NOT NULL,
    previous_epoch bigint NOT NULL CHECK (previous_epoch > 0),
    new_epoch bigint NOT NULL,
    actor varchar(128) NOT NULL,
    reason_class varchar(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_chat_executor_key_revocation_epoch UNIQUE (cell_id,new_epoch),
    CONSTRAINT chat_executor_key_revocations_epoch_check
        CHECK (new_epoch = previous_epoch + 1)
);

CREATE TABLE IF NOT EXISTS chat_executor_rollback_audits (
    request_id uuid PRIMARY KEY,
    cell_id varchar(64) NOT NULL,
    actor varchar(128) NOT NULL,
    reason_class varchar(64) NOT NULL,
    source_digest varchar(64) NOT NULL,
    target_digest varchar(64) NOT NULL,
    qualification_evidence_ref varchar(255) NOT NULL,
    outcome varchar(16) NOT NULL CHECK (outcome IN ('applied')),
    epoch bigint NOT NULL CHECK (epoch > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_chat_executor_rollback_epoch UNIQUE (cell_id,epoch),
    CONSTRAINT chat_executor_rollback_digest_check CHECK (
        source_digest <> target_digest
        AND length(source_digest)=64 AND length(target_digest)=64
    )
);

CREATE OR REPLACE FUNCTION reject_chat_executor_rollback_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'chat executor rollback audit rows are append-only';
END;
$$;

DROP TRIGGER IF EXISTS chat_executor_rollback_audit_immutable
    ON chat_executor_rollback_audits;
CREATE TRIGGER chat_executor_rollback_audit_immutable
BEFORE UPDATE OR DELETE ON chat_executor_rollback_audits
FOR EACH ROW EXECUTE FUNCTION reject_chat_executor_rollback_audit_mutation();

CREATE OR REPLACE FUNCTION reject_chat_executor_manifest_lineage_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.digest IS DISTINCT FROM OLD.digest
       OR NEW.parent_digest IS DISTINCT FROM OLD.parent_digest
       OR NEW.image_digest IS DISTINCT FROM OLD.image_digest
       OR NEW.environment_binary_digest IS DISTINCT FROM OLD.environment_binary_digest
       OR NEW.daemon_digest IS DISTINCT FROM OLD.daemon_digest
       OR NEW.source_commit IS DISTINCT FROM OLD.source_commit
       OR NEW.release_id IS DISTINCT FROM OLD.release_id
       OR NEW.protocol_version IS DISTINCT FROM OLD.protocol_version
       OR NEW.schema_digest IS DISTINCT FROM OLD.schema_digest THEN
        RAISE EXCEPTION 'chat executor manifest lineage is immutable';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS chat_executor_manifest_lineage_immutable
    ON chat_executor_manifests;
CREATE TRIGGER chat_executor_manifest_lineage_immutable
BEFORE UPDATE ON chat_executor_manifests
FOR EACH ROW EXECUTE FUNCTION reject_chat_executor_manifest_lineage_mutation();

DO $$
DECLARE
    mutable_tables text[] := ARRAY[
        'chat_executor_manifests',
        'chat_executor_cells',
        'chat_executor_shards',
        'chat_executor_registrations',
        'chat_executor_nonces',
        'chat_executor_claims',
        'chat_executor_key_revocations'
    ];
    table_name text;
BEGIN
    IF current_schema() = 'staging' THEN
        IF to_regrole('pwc_staging') IS NULL OR to_regrole('pwc_staging_owner') IS NULL THEN
            RAISE EXCEPTION 'staging executor migration requires pwc_staging roles';
        END IF;
        FOREACH table_name IN ARRAY mutable_tables LOOP
            EXECUTE format('ALTER TABLE %I OWNER TO pwc_staging_owner', table_name);
            EXECUTE format(
                'GRANT SELECT,INSERT,UPDATE,DELETE ON %I TO pwc_staging',
                table_name
            );
        END LOOP;
        ALTER TABLE chat_executor_rollback_audits OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT ON chat_executor_rollback_audits TO pwc_staging;
        REVOKE UPDATE, DELETE ON chat_executor_rollback_audits FROM pwc_staging;
        IF to_regrole('paperswithcode_user') IS NOT NULL THEN
            REVOKE ALL ON chat_executor_manifests,chat_executor_cells,chat_executor_shards,
                chat_executor_registrations,chat_executor_nonces,chat_executor_claims,
                chat_executor_key_revocations,chat_executor_rollback_audits
                FROM paperswithcode_user;
        END IF;
    ELSIF current_schema() = 'public' THEN
        IF to_regrole('paperswithcode_user') IS NULL THEN
            RAISE EXCEPTION 'production executor migration requires paperswithcode_user';
        END IF;
        FOREACH table_name IN ARRAY mutable_tables LOOP
            EXECUTE format('ALTER TABLE %I OWNER TO paperswithcode_user', table_name);
            EXECUTE format(
                'GRANT SELECT,INSERT,UPDATE,DELETE ON %I TO paperswithcode_user',
                table_name
            );
        END LOOP;
        -- The application role must not own the append-only audit table: PostgreSQL
        -- owners retain implicit mutation rights even after an explicit REVOKE.
        GRANT SELECT, INSERT ON chat_executor_rollback_audits TO paperswithcode_user;
        REVOKE UPDATE, DELETE ON chat_executor_rollback_audits FROM paperswithcode_user;
        IF to_regrole('pwc_staging') IS NOT NULL THEN
            REVOKE ALL ON chat_executor_manifests,chat_executor_cells,chat_executor_shards,
                chat_executor_registrations,chat_executor_nonces,chat_executor_claims,
                chat_executor_key_revocations,chat_executor_rollback_audits
                FROM pwc_staging;
        END IF;
    ELSE
        RAISE EXCEPTION 'executor registry migration requires staging or public schema';
    END IF;
END;
$$;

COMMIT;
