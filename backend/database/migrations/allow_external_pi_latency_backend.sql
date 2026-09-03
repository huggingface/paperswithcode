BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'allow_external_pi_latency_backend.sql must run with search_path staging,public or public';
    END IF;
END $$;

-- Turns routed to the external Pi worker fleet never allocate a Modal sandbox.
-- Recording them as 'modal_cli' made finalize() bill the requested sandbox
-- shape for the whole turn and feed that phantom figure to the Modal spend
-- circuits. Allow the fleet to be recorded as its own execution backend.
ALTER TABLE chat_turn_latency
    DROP CONSTRAINT IF EXISTS chat_turn_latency_backend_check;

ALTER TABLE chat_turn_latency
    ADD CONSTRAINT chat_turn_latency_backend_check
    CHECK (execution_backend IN ('local_mcp', 'modal_cli', 'external_pi'));

COMMIT;
