BEGIN;

-- Widen the production chat reasoning-effort checks to accept 'medium'. Apply
-- before deploying a backend that writes it; the old backend never does.
SET LOCAL search_path = public;

DO $$
BEGIN
    IF current_schema() <> 'public' THEN
        RAISE EXCEPTION
            'add_chat_medium_reasoning_effort_production.sql must run in public';
    END IF;
END $$;

ALTER TABLE chat_sessions
    DROP CONSTRAINT IF EXISTS chat_sessions_reasoning_effort_check,
    ADD CONSTRAINT chat_sessions_reasoning_effort_check
        CHECK (reasoning_effort IN ('low','medium','high','max')) NOT VALID;
ALTER TABLE chat_sessions VALIDATE CONSTRAINT chat_sessions_reasoning_effort_check;

ALTER TABLE chat_messages
    DROP CONSTRAINT IF EXISTS chat_messages_reasoning_effort_check,
    ADD CONSTRAINT chat_messages_reasoning_effort_check
        CHECK (reasoning_effort IN ('low','medium','high','max')) NOT VALID;
ALTER TABLE chat_messages VALIDATE CONSTRAINT chat_messages_reasoning_effort_check;

ALTER TABLE chat_turn_capabilities
    DROP CONSTRAINT IF EXISTS chat_turn_capabilities_reasoning_effort_check,
    ADD CONSTRAINT chat_turn_capabilities_reasoning_effort_check
        CHECK (reasoning_effort IN ('low','medium','high','max')) NOT VALID;
ALTER TABLE chat_turn_capabilities VALIDATE CONSTRAINT chat_turn_capabilities_reasoning_effort_check;

ALTER TABLE chat_openrouter_provider_calls
    DROP CONSTRAINT IF EXISTS chat_openrouter_provider_calls_reasoning_effort_check,
    ADD CONSTRAINT chat_openrouter_provider_calls_reasoning_effort_check
        CHECK (reasoning_effort IN ('low','medium','high','max')) NOT VALID;
ALTER TABLE chat_openrouter_provider_calls VALIDATE CONSTRAINT chat_openrouter_provider_calls_reasoning_effort_check;

ALTER TABLE chat_openai_provider_calls
    DROP CONSTRAINT IF EXISTS chat_openai_provider_calls_reasoning_effort_check,
    ADD CONSTRAINT chat_openai_provider_calls_reasoning_effort_check
        CHECK (reasoning_effort IN ('low','medium','high','max')) NOT VALID;
ALTER TABLE chat_openai_provider_calls VALIDATE CONSTRAINT chat_openai_provider_calls_reasoning_effort_check;

COMMIT;
