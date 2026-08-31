BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_qualification_evidence_events.sql requires staging or public';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_qualification_scopes (
    id UUID PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL UNIQUE,
    profile VARCHAR(32) NOT NULL,
    app_release_id VARCHAR(255) NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL,
    window_ended_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE chat_qualification_scopes
    ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS run_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS profile VARCHAR(32),
    ADD COLUMN IF NOT EXISTS app_release_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS window_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS window_ended_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

-- Partial/old same-name qualification tables contain disposable gate telemetry.
-- Remove those rows before installing strict non-null/FK contracts.
DELETE FROM chat_qualification_scopes
WHERE run_id IS NULL OR profile IS NULL OR app_release_id IS NULL
   OR window_started_at IS NULL OR expires_at IS NULL OR created_at IS NULL
   OR profile NOT IN ('32-functional-turns','100-immediate-admission')
   OR expires_at <= window_started_at
   OR (window_ended_at IS NOT NULL AND window_ended_at < window_started_at);

DELETE FROM chat_qualification_scopes duplicate
USING chat_qualification_scopes retained
WHERE duplicate.run_id = retained.run_id AND duplicate.ctid > retained.ctid;

ALTER TABLE chat_qualification_scopes
    ALTER COLUMN id SET NOT NULL,
    ALTER COLUMN run_id SET NOT NULL,
    ALTER COLUMN profile SET NOT NULL,
    ALTER COLUMN app_release_id SET NOT NULL,
    ALTER COLUMN window_started_at SET NOT NULL,
    ALTER COLUMN expires_at SET NOT NULL,
    ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE chat_qualification_scopes
    DROP CONSTRAINT IF EXISTS chat_qualification_scopes_run_id_key,
    DROP CONSTRAINT IF EXISTS chat_qualification_scopes_profile_check,
    DROP CONSTRAINT IF EXISTS chat_qualification_scopes_window_check,
    DROP CONSTRAINT IF EXISTS chat_qualification_scopes_expiry_check;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_qualification_scopes'::regclass AND conname = 'chat_qualification_scopes_run_id_key') THEN
        ALTER TABLE chat_qualification_scopes ADD CONSTRAINT chat_qualification_scopes_run_id_key UNIQUE (run_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_qualification_scopes'::regclass AND conname = 'chat_qualification_scopes_profile_check') THEN
        ALTER TABLE chat_qualification_scopes ADD CONSTRAINT chat_qualification_scopes_profile_check CHECK (profile IN ('32-functional-turns','100-immediate-admission')) NOT VALID;
        ALTER TABLE chat_qualification_scopes VALIDATE CONSTRAINT chat_qualification_scopes_profile_check;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_qualification_scopes'::regclass AND conname = 'chat_qualification_scopes_window_check') THEN
        ALTER TABLE chat_qualification_scopes ADD CONSTRAINT chat_qualification_scopes_window_check CHECK (window_ended_at IS NULL OR window_ended_at >= window_started_at) NOT VALID;
        ALTER TABLE chat_qualification_scopes VALIDATE CONSTRAINT chat_qualification_scopes_window_check;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_qualification_scopes'::regclass AND conname = 'chat_qualification_scopes_expiry_check') THEN
        ALTER TABLE chat_qualification_scopes ADD CONSTRAINT chat_qualification_scopes_expiry_check CHECK (expires_at > window_started_at) NOT VALID;
        ALTER TABLE chat_qualification_scopes VALIDATE CONSTRAINT chat_qualification_scopes_expiry_check;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS chat_qualification_evidence_events (
    id UUID PRIMARY KEY,
    qualification_scope_id UUID NOT NULL,
    turn_id UUID NOT NULL,
    chat_session_id UUID NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    operation_digest VARCHAR(64),
    operation_kind VARCHAR(8),
    occurred_at TIMESTAMPTZ NOT NULL
);

ALTER TABLE chat_qualification_evidence_events
    ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS qualification_scope_id UUID,
    ADD COLUMN IF NOT EXISTS turn_id UUID,
    ADD COLUMN IF NOT EXISTS chat_session_id UUID,
    ADD COLUMN IF NOT EXISTS event_type VARCHAR(32),
    ADD COLUMN IF NOT EXISTS operation_digest VARCHAR(64),
    ADD COLUMN IF NOT EXISTS operation_kind VARCHAR(8),
    ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ;

DELETE FROM chat_qualification_evidence_events evidence
WHERE qualification_scope_id IS NULL OR turn_id IS NULL OR chat_session_id IS NULL
   OR event_type IS NULL OR occurred_at IS NULL
   OR event_type NOT IN ('admitted_no_queue','executor_started','stale_fence','queued','workspace_created','workspace_reused','workspace_evicted')
   OR ((event_type = 'executor_started') <> (operation_digest IS NOT NULL AND operation_kind IS NOT NULL AND operation_kind IN ('read','bash')))
   OR NOT EXISTS (SELECT 1 FROM chat_qualification_scopes scope WHERE scope.id = evidence.qualification_scope_id)
   OR NOT EXISTS (SELECT 1 FROM chat_turn_jobs turn_job WHERE turn_job.turn_id = evidence.turn_id)
   OR NOT EXISTS (SELECT 1 FROM chat_sessions session WHERE session.id = evidence.chat_session_id);

DELETE FROM chat_qualification_evidence_events duplicate
USING chat_qualification_evidence_events retained
WHERE duplicate.qualification_scope_id = retained.qualification_scope_id
  AND duplicate.turn_id = retained.turn_id
  AND duplicate.event_type = retained.event_type
  AND duplicate.event_type IN ('stale_fence','workspace_evicted')
  AND duplicate.ctid > retained.ctid;

ALTER TABLE chat_qualification_evidence_events
    ALTER COLUMN id SET NOT NULL,
    ALTER COLUMN qualification_scope_id SET NOT NULL,
    ALTER COLUMN turn_id SET NOT NULL,
    ALTER COLUMN chat_session_id SET NOT NULL,
    ALTER COLUMN event_type SET NOT NULL,
    ALTER COLUMN occurred_at SET NOT NULL;

ALTER TABLE chat_qualification_evidence_events
    DROP CONSTRAINT IF EXISTS chat_qualification_evidence_scope_fkey,
    DROP CONSTRAINT IF EXISTS chat_qualification_evidence_turn_fkey,
    DROP CONSTRAINT IF EXISTS chat_qualification_evidence_session_fkey,
    DROP CONSTRAINT IF EXISTS chat_qualification_evidence_event_type_check,
    DROP CONSTRAINT IF EXISTS chat_qualification_evidence_operation_shape_check;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_qualification_evidence_events'::regclass AND conname = 'chat_qualification_evidence_scope_fkey') THEN
        ALTER TABLE chat_qualification_evidence_events ADD CONSTRAINT chat_qualification_evidence_scope_fkey FOREIGN KEY (qualification_scope_id) REFERENCES chat_qualification_scopes(id) ON DELETE CASCADE NOT VALID;
        ALTER TABLE chat_qualification_evidence_events VALIDATE CONSTRAINT chat_qualification_evidence_scope_fkey;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_qualification_evidence_events'::regclass AND conname = 'chat_qualification_evidence_turn_fkey') THEN
        ALTER TABLE chat_qualification_evidence_events ADD CONSTRAINT chat_qualification_evidence_turn_fkey FOREIGN KEY (turn_id) REFERENCES chat_turn_jobs(turn_id) ON DELETE CASCADE NOT VALID;
        ALTER TABLE chat_qualification_evidence_events VALIDATE CONSTRAINT chat_qualification_evidence_turn_fkey;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_qualification_evidence_events'::regclass AND conname = 'chat_qualification_evidence_session_fkey') THEN
        ALTER TABLE chat_qualification_evidence_events ADD CONSTRAINT chat_qualification_evidence_session_fkey FOREIGN KEY (chat_session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE NOT VALID;
        ALTER TABLE chat_qualification_evidence_events VALIDATE CONSTRAINT chat_qualification_evidence_session_fkey;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_qualification_evidence_events'::regclass AND conname = 'chat_qualification_evidence_event_type_check') THEN
        ALTER TABLE chat_qualification_evidence_events ADD CONSTRAINT chat_qualification_evidence_event_type_check CHECK (event_type IN ('admitted_no_queue','executor_started','stale_fence','queued','workspace_created','workspace_reused','workspace_evicted')) NOT VALID;
        ALTER TABLE chat_qualification_evidence_events VALIDATE CONSTRAINT chat_qualification_evidence_event_type_check;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'chat_qualification_evidence_events'::regclass AND conname = 'chat_qualification_evidence_operation_shape_check') THEN
        ALTER TABLE chat_qualification_evidence_events ADD CONSTRAINT chat_qualification_evidence_operation_shape_check CHECK ((event_type = 'executor_started') = (operation_digest IS NOT NULL AND operation_kind IS NOT NULL AND operation_kind IN ('read','bash'))) NOT VALID;
        ALTER TABLE chat_qualification_evidence_events VALIDATE CONSTRAINT chat_qualification_evidence_operation_shape_check;
    END IF;
END $$;

DROP INDEX IF EXISTS idx_chat_qualification_scopes_expiry;
DROP INDEX IF EXISTS idx_chat_qualification_scopes_release_profile;
DROP INDEX IF EXISTS idx_chat_qualification_evidence_scope_event_time;
DROP INDEX IF EXISTS idx_chat_qualification_evidence_session_time;
DROP INDEX IF EXISTS idx_chat_qualification_evidence_turn_event;
DROP INDEX IF EXISTS uq_chat_qualification_evidence_stale_turn;
DROP INDEX IF EXISTS uq_chat_qualification_evidence_eviction_turn;
CREATE INDEX idx_chat_qualification_scopes_expiry ON chat_qualification_scopes (expires_at);
CREATE INDEX idx_chat_qualification_scopes_release_profile ON chat_qualification_scopes (app_release_id, profile);
CREATE INDEX idx_chat_qualification_evidence_scope_event_time ON chat_qualification_evidence_events (qualification_scope_id, event_type, occurred_at);
CREATE INDEX idx_chat_qualification_evidence_session_time ON chat_qualification_evidence_events (chat_session_id, occurred_at);
CREATE INDEX idx_chat_qualification_evidence_turn_event ON chat_qualification_evidence_events (turn_id, event_type);
CREATE UNIQUE INDEX uq_chat_qualification_evidence_stale_turn ON chat_qualification_evidence_events (qualification_scope_id, turn_id) WHERE event_type = 'stale_fence';
CREATE UNIQUE INDEX uq_chat_qualification_evidence_eviction_turn ON chat_qualification_evidence_events (qualification_scope_id, turn_id) WHERE event_type = 'workspace_evicted';

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_qualification_scopes OWNER TO pwc_staging_owner;
        ALTER TABLE chat_qualification_evidence_events OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_qualification_scopes, chat_qualification_evidence_events TO pwc_staging;
        REVOKE ALL ON chat_qualification_scopes, chat_qualification_evidence_events FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_qualification_scopes OWNER TO paperswithcode_user;
        ALTER TABLE chat_qualification_evidence_events OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_qualification_scopes, chat_qualification_evidence_events TO paperswithcode_user;
        REVOKE ALL ON chat_qualification_scopes, chat_qualification_evidence_events FROM pwc_staging;
    END IF;
END $$;

COMMIT;
