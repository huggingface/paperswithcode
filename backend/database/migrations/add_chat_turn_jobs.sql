BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_turn_jobs.sql must run with search_path staging,public or public';
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

CREATE TABLE IF NOT EXISTS chat_turn_jobs (
    turn_id UUID PRIMARY KEY,
    chat_session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    hf_user_id VARCHAR(255) NOT NULL,
    request_id VARCHAR(200) NOT NULL UNIQUE,
    revision INTEGER NOT NULL
        CONSTRAINT chat_turn_jobs_revision_check CHECK (revision > 0),
    dispatch_class VARCHAR(32) NOT NULL,
    dispatch_route VARCHAR(255) NOT NULL,
    state VARCHAR(24) NOT NULL,
    worker_id VARCHAR(128),
    worker_generation BIGINT,
    lease_generation BIGINT,
    app_release_id VARCHAR(255) NOT NULL,
    worker_contract_version VARCHAR(128) NOT NULL,
    admitted_at TIMESTAMPTZ NOT NULL,
    dispatched_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    terminal_at TIMESTAMPTZ,
    failure_code VARCHAR(64),
    last_agent_session_id UUID,
    last_resume_boundary_id TEXT,
    CONSTRAINT chat_turn_jobs_worker_generation_check
        CHECK (worker_generation IS NULL OR worker_generation > 0),
    CONSTRAINT chat_turn_jobs_lease_generation_check
        CHECK (lease_generation IS NULL OR lease_generation > 0),
    CONSTRAINT chat_turn_jobs_state_check CHECK (
        state IN (
            'admitted', 'leased', 'running', 'waiting_model', 'waiting_tool',
            'cancelling', 'completed', 'failed', 'interrupted'
        )
    ),
    CONSTRAINT chat_turn_jobs_lease_fields_check CHECK (
        (state = 'admitted'
         AND worker_id IS NULL
         AND worker_generation IS NULL
         AND lease_generation IS NULL
         AND lease_expires_at IS NULL)
        OR
        (state IN ('leased','running','waiting_model','waiting_tool','cancelling')
         AND worker_id IS NOT NULL
         AND worker_generation IS NOT NULL
         AND lease_generation IS NOT NULL
         AND lease_expires_at IS NOT NULL)
        OR
        (state IN ('completed','failed','interrupted')
         AND worker_id IS NOT NULL
         AND worker_generation IS NOT NULL
         AND lease_generation IS NOT NULL
         AND lease_expires_at IS NULL)
    ),
    CONSTRAINT chat_turn_jobs_terminal_timestamp_check CHECK (
        (state IN ('completed','failed','interrupted')) = (terminal_at IS NOT NULL)
    ),
    CONSTRAINT chat_turn_jobs_failure_code_check CHECK (
        failure_code IS NULL OR failure_code ~ '^[a-z0-9][a-z0-9_]{0,63}$'
    )
);

CREATE INDEX IF NOT EXISTS idx_chat_turn_jobs_claim
    ON chat_turn_jobs (state, admitted_at, turn_id);

CREATE INDEX IF NOT EXISTS idx_chat_turn_jobs_expiry
    ON chat_turn_jobs (state, lease_expires_at);

CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_turn_jobs_nonterminal_owner
    ON chat_turn_jobs (hf_user_id)
    WHERE state IN (
        'admitted','leased','running','waiting_model','waiting_tool','cancelling'
    );

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_turn_jobs OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_jobs TO pwc_staging;
        REVOKE ALL ON chat_turn_jobs FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_turn_jobs OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_jobs TO paperswithcode_user;
        REVOKE ALL ON chat_turn_jobs FROM pwc_staging;
    END IF;
END $$;

COMMIT;
