BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_external_worker_reservations.sql requires staging or public';
    END IF;
    IF current_schema() = 'staging'
       AND (NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
            OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner')) THEN
        RAISE EXCEPTION 'staging chat roles must exist before this migration';
    END IF;
    IF current_schema() = 'public'
       AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        RAISE EXCEPTION 'production chat migration requires paperswithcode_user';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_external_worker_reservations (
    request_id VARCHAR(200) PRIMARY KEY,
    turn_id UUID UNIQUE,
    endpoint_id VARCHAR(128) NOT NULL,
    worker_id VARCHAR(128) NOT NULL,
    instance_id UUID NOT NULL,
    worker_generation BIGINT NOT NULL
        CONSTRAINT chat_external_worker_reservations_worker_generation_check
        CHECK (worker_generation > 0),
    release_id VARCHAR(255) NOT NULL,
    contract_version VARCHAR(128) NOT NULL,
    maximum_sessions INTEGER NOT NULL
        CONSTRAINT chat_external_worker_reservations_maximum_sessions_check
        CHECK (maximum_sessions BETWEEN 1 AND 32),
    reserved_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

-- Forward repair for environments that applied the earlier additive table shape.
-- PostgreSQL may already have equivalent automatically named checks; these blocks
-- install the canonical names only when they are absent and validate existing rows.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_external_worker_reservations'::regclass
          AND conname = 'chat_external_worker_reservations_worker_generation_check'
    ) THEN
        ALTER TABLE chat_external_worker_reservations
            ADD CONSTRAINT chat_external_worker_reservations_worker_generation_check
            CHECK (worker_generation > 0) NOT VALID;
        ALTER TABLE chat_external_worker_reservations
            VALIDATE CONSTRAINT
                chat_external_worker_reservations_worker_generation_check;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'chat_external_worker_reservations'::regclass
          AND conname = 'chat_external_worker_reservations_maximum_sessions_check'
    ) THEN
        ALTER TABLE chat_external_worker_reservations
            ADD CONSTRAINT
                chat_external_worker_reservations_maximum_sessions_check
            CHECK (maximum_sessions BETWEEN 1 AND 32) NOT VALID;
        ALTER TABLE chat_external_worker_reservations
            VALIDATE CONSTRAINT
                chat_external_worker_reservations_maximum_sessions_check;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_chat_external_worker_reservations_capacity
    ON chat_external_worker_reservations (
        worker_id,
        instance_id,
        worker_generation
    );

CREATE INDEX IF NOT EXISTS idx_chat_external_worker_reservations_unbound_expiry
    ON chat_external_worker_reservations (expires_at)
    WHERE turn_id IS NULL;

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_external_worker_reservations OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON chat_external_worker_reservations TO pwc_staging;
        REVOKE ALL ON chat_external_worker_reservations FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_external_worker_reservations OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON chat_external_worker_reservations TO paperswithcode_user;
        REVOKE ALL ON chat_external_worker_reservations FROM pwc_staging;
    END IF;
END $$;

COMMIT;
