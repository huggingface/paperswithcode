BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_external_worker_registry.sql must run with search_path staging,public or public';
    END IF;
    IF current_schema() = 'staging'
       AND (NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
            OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner')) THEN
        RAISE EXCEPTION
            'pwc_staging and pwc_staging_owner roles must exist before this migration';
    END IF;
    IF current_schema() = 'public'
       AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        RAISE EXCEPTION 'production chat migration requires paperswithcode_user';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_external_workers (
    worker_id VARCHAR(128) PRIMARY KEY,
    instance_id UUID NOT NULL UNIQUE,
    environment VARCHAR(16) NOT NULL
        CHECK (environment IN ('staging', 'production')),
    release_id VARCHAR(255) NOT NULL,
    contract_version VARCHAR(128) NOT NULL,
    generation BIGINT NOT NULL CHECK (generation > 0),
    state VARCHAR(16) NOT NULL
        CHECK (state IN ('ready', 'draining', 'offline')),
    maximum_sessions INTEGER NOT NULL
        CHECK (maximum_sessions BETWEEN 1 AND 32),
    active_sessions INTEGER NOT NULL
        CHECK (active_sessions BETWEEN 0 AND maximum_sessions),
    heartbeat_at TIMESTAMPTZ NOT NULL,
    lease_expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_external_workers_dispatch
    ON chat_external_workers (
        environment,
        state,
        contract_version,
        lease_expires_at
    );

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_external_workers OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_external_workers TO pwc_staging;
        REVOKE ALL ON chat_external_workers FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_external_workers OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_external_workers TO paperswithcode_user;
        REVOKE ALL ON chat_external_workers FROM pwc_staging;
    END IF;
END $$;

COMMIT;
