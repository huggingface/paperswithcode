BEGIN;

DO $$
BEGIN
    IF current_schema() <> 'staging' THEN
        RAISE EXCEPTION
            'add_chat_sandbox_runtime.sql must run with search_path staging,public';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
       OR NOT EXISTS (
           SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner'
       ) THEN
        RAISE EXCEPTION
            'pwc_staging and pwc_staging_owner roles must exist before this migration';
    END IF;
END $$;

ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS execution_backend VARCHAR(24) NOT NULL DEFAULT 'local_mcp';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chat_sessions_execution_backend_check'
    ) THEN
        ALTER TABLE chat_sessions ADD CONSTRAINT chat_sessions_execution_backend_check
            CHECK (execution_backend IN ('local_mcp', 'modal_cli'));
    END IF;
END $$;

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS app_release_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS sandbox_image_version VARCHAR(255),
    ADD COLUMN IF NOT EXISTS worker_contract_version VARCHAR(64),
    ADD COLUMN IF NOT EXISTS pwc_cli_version VARCHAR(64),
    ADD COLUMN IF NOT EXISTS system_prompt_sha256 VARCHAR(64);

CREATE TABLE IF NOT EXISTS chat_sandbox_leases (
    chat_session_id UUID PRIMARY KEY REFERENCES chat_sessions(id) ON DELETE CASCADE,
    modal_sandbox_id VARCHAR(255) UNIQUE,
    app_release_id VARCHAR(255) NOT NULL,
    image_version VARCHAR(255) NOT NULL,
    worker_contract_version VARCHAR(64) NOT NULL,
    state VARCHAR(24) NOT NULL DEFAULT 'starting'
        CHECK (state IN ('starting','ready','busy','idle','terminating','terminated','failed')),
    lease_token_hash VARCHAR(64),
    lease_expires_at TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    workspace_snapshot_id VARCHAR(255),
    snapshot_image_version VARCHAR(255),
    snapshot_updated_at TIMESTAMPTZ,
    workspace_dirty BOOLEAN NOT NULL DEFAULT false,
    failure_code VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE chat_sandbox_leases
    ADD COLUMN IF NOT EXISTS workspace_dirty BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_chat_sandbox_leases_state_activity
    ON chat_sandbox_leases (state, last_activity_at);

CREATE TABLE IF NOT EXISTS chat_turn_capabilities (
    id UUID PRIMARY KEY,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    chat_session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    turn_id UUID NOT NULL,
    sdk_session_id UUID,
    owner_hash VARCHAR(64) NOT NULL,
    model VARCHAR(255) NOT NULL,
    scopes JSONB NOT NULL,
    nonce VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    provider_requests INTEGER NOT NULL DEFAULT 0,
    provider_tokens BIGINT NOT NULL DEFAULT 0,
    gateway_calls INTEGER NOT NULL DEFAULT 0,
    catalog_search_calls INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE chat_turn_capabilities
    ADD COLUMN IF NOT EXISTS sdk_session_id UUID,
    ADD COLUMN IF NOT EXISTS catalog_search_calls INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_chat_turn_capabilities_scope
    ON chat_turn_capabilities (chat_session_id, turn_id, expires_at);

ALTER TABLE chat_sandbox_leases OWNER TO pwc_staging_owner;
ALTER TABLE chat_turn_capabilities OWNER TO pwc_staging_owner;
GRANT SELECT, INSERT, UPDATE, DELETE ON chat_sandbox_leases,
    chat_turn_capabilities TO pwc_staging;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user'
    ) THEN
        REVOKE ALL ON chat_sandbox_leases, chat_turn_capabilities
            FROM paperswithcode_user;
    END IF;
END $$;

COMMIT;
