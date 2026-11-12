BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_uploaded_files.sql must run with search_path staging,public or public';
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

CREATE TABLE IF NOT EXISTS chat_uploaded_files (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    hf_user_id VARCHAR(255) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    media_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    page_count INTEGER,
    pdf_detail VARCHAR(8),
    token_estimate INTEGER NOT NULL,
    storage_key VARCHAR(300) NOT NULL,
    openai_file_id VARCHAR(100),
    state VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chat_uploaded_files_state_check CHECK (state IN ('pending', 'ready')),
    CONSTRAINT chat_uploaded_files_detail_check
        CHECK (pdf_detail IS NULL OR pdf_detail IN ('low', 'high')),
    CONSTRAINT chat_uploaded_files_size_check CHECK (size_bytes > 0)
);

CREATE INDEX IF NOT EXISTS idx_chat_uploaded_files_session
    ON chat_uploaded_files (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_uploaded_files_owner
    ON chat_uploaded_files (hf_user_id, state);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_uploaded_files OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_uploaded_files TO pwc_staging;
        REVOKE ALL ON chat_uploaded_files FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_uploaded_files OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_uploaded_files TO paperswithcode_user;
        REVOKE ALL ON chat_uploaded_files FROM pwc_staging;
    END IF;
END $$;

COMMIT;
