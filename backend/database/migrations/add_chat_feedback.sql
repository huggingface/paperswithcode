BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION 'add_chat_feedback.sql requires staging or public';
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

-- One thumbs rating per completed assistant response. The database is the
-- record; the trace store (Trackio or Langfuse) only mirrors it best-effort.
CREATE TABLE IF NOT EXISTS chat_feedback (
    assistant_message_id UUID PRIMARY KEY
        REFERENCES chat_messages (id) ON DELETE CASCADE,
    session_id UUID NOT NULL
        REFERENCES chat_sessions (id) ON DELETE CASCADE,
    turn_id UUID NOT NULL,
    value BOOLEAN NOT NULL,
    comment VARCHAR(500),
    trace_id VARCHAR(64),
    exported_to VARCHAR(16),
    exported_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_feedback_created_at
    ON chat_feedback (created_at);
CREATE INDEX IF NOT EXISTS idx_chat_feedback_session_id
    ON chat_feedback (session_id);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_feedback OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_feedback TO pwc_staging;
        REVOKE ALL ON chat_feedback FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_feedback OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_feedback TO paperswithcode_user;
        REVOKE ALL ON chat_feedback FROM pwc_staging;
    END IF;
END $$;

COMMIT;
