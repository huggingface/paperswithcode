-- Voice dictation tickets and metering (see backend/services/dictation_service.py).
-- Each row is one single-use WebSocket ticket. Only a hash of the ticket is
-- stored; no audio or transcript is ever written. Run as postgres once with
-- search_path=staging,public and once for public.
BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_dictation_sessions.sql must run with search_path staging,public or public';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS dictation_sessions (
    id UUID PRIMARY KEY,
    hf_subject VARCHAR(255) NOT NULL,
    provider VARCHAR(16) NOT NULL,
    ticket_hash VARCHAR(64) NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    connected_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    max_seconds INTEGER NOT NULL,
    used_seconds INTEGER,
    CONSTRAINT uq_dictation_sessions_ticket UNIQUE (ticket_hash),
    CONSTRAINT dictation_sessions_provider_check CHECK (provider IN ('voxtral','openai')),
    CONSTRAINT dictation_sessions_seconds_check CHECK (
        max_seconds > 0 AND (used_seconds IS NULL OR used_seconds BETWEEN 0 AND max_seconds)
    )
);
CREATE INDEX IF NOT EXISTS idx_dictation_sessions_subject_issued
    ON dictation_sessions (hf_subject, issued_at);
CREATE INDEX IF NOT EXISTS idx_dictation_sessions_provider_connected
    ON dictation_sessions (provider, connected_at);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
           OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner') THEN
            RAISE EXCEPTION 'staging dictation migration requires staging roles';
        END IF;
        ALTER TABLE dictation_sessions OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON dictation_sessions TO pwc_staging;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
            REVOKE ALL ON dictation_sessions FROM paperswithcode_user;
        END IF;
    ELSE
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
            RAISE EXCEPTION 'production dictation migration requires paperswithcode_user';
        END IF;
        ALTER TABLE dictation_sessions OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON dictation_sessions TO paperswithcode_user;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
            REVOKE ALL ON dictation_sessions FROM pwc_staging;
        END IF;
    END IF;
END $$;

COMMIT;
