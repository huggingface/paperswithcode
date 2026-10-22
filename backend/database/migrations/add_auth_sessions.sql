-- Server-side browser sessions (see backend/services/auth_session_service.py).
-- Run as postgres against public. Production owns the table; staging may only
-- read it to verify the shared production session it receives.
BEGIN;

DO $$
BEGIN
    IF current_schema() <> 'public' THEN
        RAISE EXCEPTION 'auth_sessions belongs to the production authority in public';
    END IF;
    IF to_regrole('paperswithcode_user') IS NULL THEN
        RAISE EXCEPTION 'auth_sessions migration requires paperswithcode_user';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS auth_sessions (
    id VARCHAR(64) PRIMARY KEY,
    hf_subject VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_subject ON auth_sessions (hf_subject);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions (expires_at);

ALTER TABLE auth_sessions OWNER TO paperswithcode_user;

DO $$
BEGIN
    IF to_regrole('pwc_staging') IS NOT NULL THEN
        REVOKE ALL ON auth_sessions FROM pwc_staging;
        GRANT SELECT ON auth_sessions TO pwc_staging;
    END IF;
END $$;

COMMIT;
