BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_chat_turn_terminal_cleanup_index.sql must run with search_path staging,public or public';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_chat_turn_jobs_terminal_cleanup
    ON chat_turn_jobs (terminal_at, turn_id)
    WHERE state IN ('completed','failed','interrupted');

COMMIT;
