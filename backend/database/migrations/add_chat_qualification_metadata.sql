BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_qualification_metadata.sql must run with search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE chat_turn_latency
    ADD COLUMN IF NOT EXISTS qualification_run_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS qualification_scenario VARCHAR(32),
    ADD COLUMN IF NOT EXISTS qualification_scope_id UUID,
    ADD COLUMN IF NOT EXISTS qualification_profile VARCHAR(32);

UPDATE chat_turn_latency latency
SET qualification_scope_id = NULL,
    qualification_profile = NULL
WHERE (qualification_scope_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM chat_qualification_scopes scope
        WHERE scope.id = latency.qualification_scope_id
    ))
   OR qualification_profile NOT IN (
        '32-functional-turns', '100-immediate-admission'
   );

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chat_turn_latency_qualification_scenario_check'
          AND conrelid = 'chat_turn_latency'::regclass
    ) THEN
        ALTER TABLE chat_turn_latency
            ADD CONSTRAINT chat_turn_latency_qualification_scenario_check
            CHECK (
                qualification_scenario IS NULL
                OR qualification_scenario IN (
                    'focused_latency',
                    'reliability',
                    'clean_cancel',
                    'forced_failure'
                )
            );
    END IF;
END $$;

DROP INDEX IF EXISTS idx_chat_turn_latency_qualification_scope;
CREATE INDEX idx_chat_turn_latency_qualification_scope
    ON chat_turn_latency (qualification_scope_id, admitted_at);

ALTER TABLE chat_turn_latency
    DROP CONSTRAINT IF EXISTS chat_turn_latency_qualification_scope_fkey,
    DROP CONSTRAINT IF EXISTS chat_turn_latency_qualification_profile_check;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chat_turn_latency_qualification_scope_fkey'
          AND conrelid = 'chat_turn_latency'::regclass
    ) THEN
        ALTER TABLE chat_turn_latency
            ADD CONSTRAINT chat_turn_latency_qualification_scope_fkey
            FOREIGN KEY (qualification_scope_id)
            REFERENCES chat_qualification_scopes(id) ON DELETE SET NULL NOT VALID;
        ALTER TABLE chat_turn_latency
            VALIDATE CONSTRAINT chat_turn_latency_qualification_scope_fkey;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chat_turn_latency_qualification_profile_check'
          AND conrelid = 'chat_turn_latency'::regclass
    ) THEN
        ALTER TABLE chat_turn_latency
            ADD CONSTRAINT chat_turn_latency_qualification_profile_check
            CHECK (
                qualification_profile IS NULL OR qualification_profile IN (
                    '32-functional-turns', '100-immediate-admission'
                )
            ) NOT VALID;
        ALTER TABLE chat_turn_latency
            VALIDATE CONSTRAINT chat_turn_latency_qualification_profile_check;
    END IF;
END $$;

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE chat_turn_latency OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_latency TO pwc_staging;
        REVOKE ALL ON chat_turn_latency FROM paperswithcode_user;
    ELSE
        ALTER TABLE chat_turn_latency OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE ON chat_turn_latency TO paperswithcode_user;
        REVOKE ALL ON chat_turn_latency FROM pwc_staging;
    END IF;
END $$;

COMMIT;
