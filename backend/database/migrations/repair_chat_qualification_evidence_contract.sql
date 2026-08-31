BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION 'repair_chat_qualification_evidence_contract.sql requires staging or public';
    END IF;
END $$;

-- Child references must be removed before repairing either parent identity.
ALTER TABLE IF EXISTS chat_qualification_evidence_events
    DROP CONSTRAINT IF EXISTS chat_qualification_evidence_scope_fkey;
ALTER TABLE IF EXISTS chat_turn_latency
    DROP CONSTRAINT IF EXISTS chat_turn_latency_qualification_scope_fkey;

ALTER TABLE chat_qualification_scopes
    ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS run_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS profile VARCHAR(32),
    ADD COLUMN IF NOT EXISTS app_release_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS window_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS window_ended_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE chat_qualification_evidence_events
    ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS qualification_scope_id UUID,
    ADD COLUMN IF NOT EXISTS turn_id UUID,
    ADD COLUMN IF NOT EXISTS chat_session_id UUID,
    ADD COLUMN IF NOT EXISTS event_type VARCHAR(32),
    ADD COLUMN IF NOT EXISTS operation_digest VARCHAR(64),
    ADD COLUMN IF NOT EXISTS operation_kind VARCHAR(8),
    ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ;
ALTER TABLE chat_turn_latency
    ADD COLUMN IF NOT EXISTS qualification_run_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS qualification_scope_id UUID,
    ADD COLUMN IF NOT EXISTS qualification_profile VARCHAR(32),
    ADD COLUMN IF NOT EXISTS qualification_workload VARCHAR(16),
    ADD COLUMN IF NOT EXISTS qualification_scenario VARCHAR(32);

-- Never coerce populated telemetry through an incompatible type or length.
DO $$
DECLARE
    mismatch RECORD;
BEGIN
    FOR mismatch IN
        SELECT expected.table_name, expected.column_name, expected.sql_type
        FROM (VALUES
          ('chat_qualification_scopes','id','uuid'::text,NULL::int,'UUID'),
          ('chat_qualification_scopes','run_id','character varying',64,'VARCHAR(64)'),
          ('chat_qualification_scopes','profile','character varying',32,'VARCHAR(32)'),
          ('chat_qualification_scopes','app_release_id','character varying',255,'VARCHAR(255)'),
          ('chat_qualification_scopes','window_started_at','timestamp with time zone',NULL,'TIMESTAMPTZ'),
          ('chat_qualification_scopes','window_ended_at','timestamp with time zone',NULL,'TIMESTAMPTZ'),
          ('chat_qualification_scopes','expires_at','timestamp with time zone',NULL,'TIMESTAMPTZ'),
          ('chat_qualification_scopes','created_at','timestamp with time zone',NULL,'TIMESTAMPTZ'),
          ('chat_qualification_evidence_events','id','uuid',NULL,'UUID'),
          ('chat_qualification_evidence_events','qualification_scope_id','uuid',NULL,'UUID'),
          ('chat_qualification_evidence_events','turn_id','uuid',NULL,'UUID'),
          ('chat_qualification_evidence_events','chat_session_id','uuid',NULL,'UUID'),
          ('chat_qualification_evidence_events','event_type','character varying',32,'VARCHAR(32)'),
          ('chat_qualification_evidence_events','operation_digest','character varying',64,'VARCHAR(64)'),
          ('chat_qualification_evidence_events','operation_kind','character varying',8,'VARCHAR(8)'),
          ('chat_qualification_evidence_events','occurred_at','timestamp with time zone',NULL,'TIMESTAMPTZ'),
          ('chat_turn_latency','qualification_run_id','character varying',64,'VARCHAR(64)'),
          ('chat_turn_latency','qualification_scope_id','uuid',NULL,'UUID'),
          ('chat_turn_latency','qualification_profile','character varying',32,'VARCHAR(32)'),
          ('chat_turn_latency','qualification_workload','character varying',16,'VARCHAR(16)'),
          ('chat_turn_latency','qualification_scenario','character varying',32,'VARCHAR(32)')
        ) AS expected(table_name,column_name,data_type,max_length,sql_type)
        JOIN information_schema.columns actual
          ON actual.table_schema = current_schema()
         AND actual.table_name = expected.table_name
         AND actual.column_name = expected.column_name
        WHERE actual.data_type <> expected.data_type
           OR actual.character_maximum_length IS DISTINCT FROM expected.max_length
    LOOP
        IF EXISTS (
            SELECT 1 FROM chat_qualification_scopes
            WHERE mismatch.table_name = 'chat_qualification_scopes'
            UNION ALL SELECT 1 FROM chat_qualification_evidence_events
            WHERE mismatch.table_name = 'chat_qualification_evidence_events'
            UNION ALL SELECT 1 FROM chat_turn_latency
            WHERE mismatch.table_name = 'chat_turn_latency'
            LIMIT 1
        ) THEN
            RAISE EXCEPTION 'refusing populated qualification column conversion %.%', mismatch.table_name, mismatch.column_name;
        END IF;
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN %I TYPE %s USING NULL::%s',
            mismatch.table_name, mismatch.column_name,
            mismatch.sql_type, mismatch.sql_type
        );
    END LOOP;
END $$;

UPDATE chat_qualification_scopes SET id = gen_random_uuid() WHERE id IS NULL;
UPDATE chat_qualification_evidence_events SET id = gen_random_uuid() WHERE id IS NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM chat_qualification_scopes WHERE
        run_id IS NULL OR profile IS NULL OR app_release_id IS NULL OR
        window_started_at IS NULL OR expires_at IS NULL OR created_at IS NULL OR
        profile NOT IN ('32-functional-turns','100-immediate-admission') OR
        expires_at <= window_started_at OR
        (window_ended_at IS NOT NULL AND window_ended_at < window_started_at))
       OR EXISTS (SELECT run_id FROM chat_qualification_scopes GROUP BY run_id HAVING count(*) > 1)
       OR EXISTS (SELECT id FROM chat_qualification_scopes GROUP BY id HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'refusing lossy qualification scope repair';
    END IF;
    IF EXISTS (SELECT 1 FROM chat_qualification_evidence_events evidence WHERE
        qualification_scope_id IS NULL OR turn_id IS NULL OR chat_session_id IS NULL OR
        event_type IS NULL OR occurred_at IS NULL OR
        event_type NOT IN ('admitted_no_queue','executor_started','stale_fence','queued','workspace_created','workspace_reused','workspace_evicted') OR
        ((event_type = 'executor_started') <> (operation_digest IS NOT NULL AND operation_kind IS NOT NULL AND operation_kind IN ('read','bash'))) OR
        NOT EXISTS (SELECT 1 FROM chat_qualification_scopes scope WHERE scope.id = evidence.qualification_scope_id) OR
        NOT EXISTS (SELECT 1 FROM chat_turn_jobs job WHERE job.turn_id = evidence.turn_id) OR
        NOT EXISTS (SELECT 1 FROM chat_sessions session WHERE session.id = evidence.chat_session_id))
       OR EXISTS (SELECT id FROM chat_qualification_evidence_events GROUP BY id HAVING count(*) > 1)
       OR EXISTS (
            SELECT qualification_scope_id, turn_id, event_type
            FROM chat_qualification_evidence_events
            WHERE event_type IN ('stale_fence','workspace_evicted')
            GROUP BY qualification_scope_id, turn_id, event_type
            HAVING count(*) > 1
       ) THEN
        RAISE EXCEPTION 'refusing lossy qualification evidence repair';
    END IF;
    IF EXISTS (SELECT 1 FROM chat_turn_latency WHERE
        qualification_profile IS NOT NULL AND qualification_profile NOT IN ('32-functional-turns','100-immediate-admission') OR
        qualification_workload IS NOT NULL AND qualification_workload NOT IN ('no_tool','read','bash') OR
        qualification_scenario IS NOT NULL AND qualification_scenario NOT IN ('focused_latency','reliability','clean_cancel','forced_failure') OR
        qualification_scope_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM chat_qualification_scopes scope WHERE scope.id = qualification_scope_id)) THEN
        RAISE EXCEPTION 'refusing lossy qualification latency repair';
    END IF;
END $$;

-- Remove differently named partial contracts as well as canonical names.
DO $$
DECLARE
    item RECORD;
BEGIN
    FOR item IN
        SELECT relation.relname AS table_name, constraint_row.conname
        FROM pg_constraint constraint_row
        JOIN pg_class relation ON relation.oid = constraint_row.conrelid
        WHERE relation.relnamespace = current_schema()::regnamespace
          AND (
            (relation.relname = 'chat_qualification_scopes' AND constraint_row.contype IN ('p','u','c'))
            OR (relation.relname = 'chat_qualification_evidence_events' AND constraint_row.contype IN ('p','f','c'))
            OR (relation.relname = 'chat_turn_latency' AND constraint_row.conname LIKE 'chat_turn_latency_qualification_%')
          )
    LOOP
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', item.table_name, item.conname);
    END LOOP;
END $$;

ALTER TABLE chat_qualification_scopes
    ALTER COLUMN id DROP DEFAULT, ALTER COLUMN id SET NOT NULL,
    ALTER COLUMN run_id DROP DEFAULT, ALTER COLUMN profile DROP DEFAULT,
    ALTER COLUMN app_release_id DROP DEFAULT,
    ALTER COLUMN window_started_at DROP DEFAULT,
    ALTER COLUMN window_ended_at DROP DEFAULT,
    ALTER COLUMN expires_at DROP DEFAULT,
    ALTER COLUMN created_at SET DEFAULT now(),
    ALTER COLUMN run_id SET NOT NULL, ALTER COLUMN profile SET NOT NULL,
    ALTER COLUMN app_release_id SET NOT NULL,
    ALTER COLUMN window_started_at SET NOT NULL,
    ALTER COLUMN expires_at SET NOT NULL, ALTER COLUMN created_at SET NOT NULL,
    DROP CONSTRAINT IF EXISTS chat_qualification_scopes_pkey,
    DROP CONSTRAINT IF EXISTS chat_qualification_scopes_run_id_key,
    DROP CONSTRAINT IF EXISTS chat_qualification_scopes_profile_check,
    DROP CONSTRAINT IF EXISTS chat_qualification_scopes_window_check,
    DROP CONSTRAINT IF EXISTS chat_qualification_scopes_expiry_check,
    ADD CONSTRAINT chat_qualification_scopes_pkey PRIMARY KEY (id),
    ADD CONSTRAINT chat_qualification_scopes_run_id_key UNIQUE (run_id),
    ADD CONSTRAINT chat_qualification_scopes_profile_check CHECK (profile IN ('32-functional-turns','100-immediate-admission')),
    ADD CONSTRAINT chat_qualification_scopes_window_check CHECK (window_ended_at IS NULL OR window_ended_at >= window_started_at),
    ADD CONSTRAINT chat_qualification_scopes_expiry_check CHECK (expires_at > window_started_at);

ALTER TABLE chat_qualification_evidence_events
    ALTER COLUMN id DROP DEFAULT, ALTER COLUMN id SET NOT NULL,
    ALTER COLUMN qualification_scope_id DROP DEFAULT,
    ALTER COLUMN turn_id DROP DEFAULT, ALTER COLUMN chat_session_id DROP DEFAULT,
    ALTER COLUMN event_type DROP DEFAULT,
    ALTER COLUMN operation_digest DROP DEFAULT,
    ALTER COLUMN operation_kind DROP DEFAULT,
    ALTER COLUMN occurred_at DROP DEFAULT,
    ALTER COLUMN qualification_scope_id SET NOT NULL,
    ALTER COLUMN turn_id SET NOT NULL, ALTER COLUMN chat_session_id SET NOT NULL,
    ALTER COLUMN event_type SET NOT NULL, ALTER COLUMN occurred_at SET NOT NULL,
    DROP CONSTRAINT IF EXISTS chat_qualification_evidence_events_pkey,
    DROP CONSTRAINT IF EXISTS chat_qualification_evidence_turn_fkey,
    DROP CONSTRAINT IF EXISTS chat_qualification_evidence_session_fkey,
    DROP CONSTRAINT IF EXISTS chat_qualification_evidence_event_type_check,
    DROP CONSTRAINT IF EXISTS chat_qualification_evidence_operation_shape_check,
    ADD CONSTRAINT chat_qualification_evidence_events_pkey PRIMARY KEY (id),
    ADD CONSTRAINT chat_qualification_evidence_scope_fkey FOREIGN KEY (qualification_scope_id) REFERENCES chat_qualification_scopes(id) ON DELETE CASCADE,
    ADD CONSTRAINT chat_qualification_evidence_turn_fkey FOREIGN KEY (turn_id) REFERENCES chat_turn_jobs(turn_id) ON DELETE CASCADE,
    ADD CONSTRAINT chat_qualification_evidence_session_fkey FOREIGN KEY (chat_session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
    ADD CONSTRAINT chat_qualification_evidence_event_type_check CHECK (event_type IN ('admitted_no_queue','executor_started','stale_fence','queued','workspace_created','workspace_reused','workspace_evicted')),
    ADD CONSTRAINT chat_qualification_evidence_operation_shape_check CHECK ((event_type = 'executor_started') = (operation_digest IS NOT NULL AND operation_kind IS NOT NULL AND operation_kind IN ('read','bash')));

ALTER TABLE chat_turn_latency
    ALTER COLUMN qualification_run_id DROP DEFAULT,
    ALTER COLUMN qualification_scope_id DROP DEFAULT,
    ALTER COLUMN qualification_profile DROP DEFAULT,
    ALTER COLUMN qualification_workload DROP DEFAULT,
    ALTER COLUMN qualification_scenario DROP DEFAULT,
    DROP CONSTRAINT IF EXISTS chat_turn_latency_qualification_profile_check,
    DROP CONSTRAINT IF EXISTS chat_turn_latency_qualification_workload_check,
    DROP CONSTRAINT IF EXISTS chat_turn_latency_qualification_scenario_check,
    ADD CONSTRAINT chat_turn_latency_qualification_scope_fkey FOREIGN KEY (qualification_scope_id) REFERENCES chat_qualification_scopes(id) ON DELETE SET NULL,
    ADD CONSTRAINT chat_turn_latency_qualification_profile_check CHECK (qualification_profile IS NULL OR qualification_profile IN ('32-functional-turns','100-immediate-admission')),
    ADD CONSTRAINT chat_turn_latency_qualification_workload_check CHECK (qualification_workload IS NULL OR qualification_workload IN ('no_tool','read','bash')),
    ADD CONSTRAINT chat_turn_latency_qualification_scenario_check CHECK (qualification_scenario IS NULL OR qualification_scenario IN ('focused_latency','reliability','clean_cancel','forced_failure'));

DROP INDEX IF EXISTS idx_chat_qualification_scopes_expiry;
DROP INDEX IF EXISTS idx_chat_qualification_scopes_release_profile;
DROP INDEX IF EXISTS idx_chat_qualification_evidence_scope_event_time;
DROP INDEX IF EXISTS idx_chat_qualification_evidence_session_time;
DROP INDEX IF EXISTS idx_chat_qualification_evidence_turn_event;
DROP INDEX IF EXISTS uq_chat_qualification_evidence_stale_turn;
DROP INDEX IF EXISTS uq_chat_qualification_evidence_eviction_turn;
DROP INDEX IF EXISTS idx_chat_turn_latency_qualification_scope;
CREATE INDEX idx_chat_qualification_scopes_expiry ON chat_qualification_scopes (expires_at);
CREATE INDEX idx_chat_qualification_scopes_release_profile ON chat_qualification_scopes (app_release_id, profile);
CREATE INDEX idx_chat_qualification_evidence_scope_event_time ON chat_qualification_evidence_events (qualification_scope_id, event_type, occurred_at);
CREATE INDEX idx_chat_qualification_evidence_session_time ON chat_qualification_evidence_events (chat_session_id, occurred_at);
CREATE INDEX idx_chat_qualification_evidence_turn_event ON chat_qualification_evidence_events (turn_id, event_type);
CREATE UNIQUE INDEX uq_chat_qualification_evidence_stale_turn ON chat_qualification_evidence_events (qualification_scope_id, turn_id) WHERE event_type = 'stale_fence';
CREATE UNIQUE INDEX uq_chat_qualification_evidence_eviction_turn ON chat_qualification_evidence_events (qualification_scope_id, turn_id) WHERE event_type = 'workspace_evicted';
CREATE INDEX idx_chat_turn_latency_qualification_scope ON chat_turn_latency (qualification_scope_id, admitted_at);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_qualification_scopes OWNER TO pwc_staging_owner;
        ALTER TABLE chat_qualification_evidence_events OWNER TO pwc_staging_owner;
        ALTER TABLE chat_turn_latency OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_qualification_scopes, chat_qualification_evidence_events, chat_turn_latency TO pwc_staging;
        REVOKE ALL ON chat_qualification_scopes, chat_qualification_evidence_events, chat_turn_latency FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_qualification_scopes OWNER TO paperswithcode_user;
        ALTER TABLE chat_qualification_evidence_events OWNER TO paperswithcode_user;
        ALTER TABLE chat_turn_latency OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_qualification_scopes, chat_qualification_evidence_events, chat_turn_latency TO paperswithcode_user;
        REVOKE ALL ON chat_qualification_scopes, chat_qualification_evidence_events, chat_turn_latency FROM pwc_staging;
    END IF;
END $$;

COMMIT;
