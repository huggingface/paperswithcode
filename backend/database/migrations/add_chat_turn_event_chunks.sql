BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_turn_event_chunks.sql must run with search_path staging,public or public';
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

ALTER TABLE chat_turn_jobs
    ADD COLUMN IF NOT EXISTS event_sequence INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS event_bytes INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS chat_turn_event_chunks (
    id BIGSERIAL PRIMARY KEY,
    turn_id UUID NOT NULL REFERENCES chat_turn_jobs(turn_id) ON DELETE CASCADE,
    first_sequence INTEGER NOT NULL,
    last_sequence INTEGER NOT NULL,
    events JSONB NOT NULL,
    payload_bytes INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_chat_turn_event_chunk_start UNIQUE (turn_id, first_sequence),
    CONSTRAINT ck_chat_turn_event_chunk_range CHECK (last_sequence >= first_sequence)
);

CREATE INDEX IF NOT EXISTS idx_chat_turn_event_chunks_after
    ON chat_turn_event_chunks (turn_id, last_sequence);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_turn_event_chunks OWNER TO pwc_staging_owner;
        ALTER SEQUENCE chat_turn_event_chunks_id_seq OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_event_chunks TO pwc_staging;
        GRANT USAGE, SELECT ON SEQUENCE chat_turn_event_chunks_id_seq TO pwc_staging;
        REVOKE ALL ON chat_turn_event_chunks FROM paperswithcode_user;
        REVOKE ALL ON SEQUENCE chat_turn_event_chunks_id_seq FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_turn_event_chunks OWNER TO paperswithcode_user;
        ALTER SEQUENCE chat_turn_event_chunks_id_seq OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_event_chunks
            TO paperswithcode_user;
        GRANT USAGE, SELECT ON SEQUENCE chat_turn_event_chunks_id_seq
            TO paperswithcode_user;
        REVOKE ALL ON chat_turn_event_chunks FROM pwc_staging;
        REVOKE ALL ON SEQUENCE chat_turn_event_chunks_id_seq FROM pwc_staging;
    END IF;
END $$;

COMMIT;
