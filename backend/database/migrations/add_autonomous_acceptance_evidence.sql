BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_autonomous_acceptance_evidence.sql requires search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE autonomous_control_event
    DROP CONSTRAINT IF EXISTS autonomous_control_event_kind_check;
ALTER TABLE autonomous_control_event
    ADD CONSTRAINT autonomous_control_event_kind_check CHECK (
        event_kind IN (
            'manual_mode','operator_enabled','chat_baseline',
            'acceptance_evidence'
        )
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_autonomous_acceptance_evidence
    ON autonomous_control_event (target, after_digest)
    WHERE event_kind = 'acceptance_evidence';

COMMIT;
