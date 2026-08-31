BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_curation_autonomous_operator.sql requires search_path staging,public or public';
    END IF;
END $$;

ALTER TABLE autonomous_operator_state
    DROP CONSTRAINT autonomous_operator_state_operator_check;
ALTER TABLE autonomous_operator_state
    ADD CONSTRAINT autonomous_operator_state_operator_check CHECK (
        operator IN (
            'global','submissions','curation','cron_health','chat_reliability'
        )
    );

ALTER TABLE autonomous_execution_intent
    DROP CONSTRAINT autonomous_execution_intent_operator_check;
ALTER TABLE autonomous_execution_intent
    ADD CONSTRAINT autonomous_execution_intent_operator_check CHECK (
        operator IN ('submissions','curation','cron_health','chat_reliability')
    );

ALTER TABLE autonomous_run
    DROP CONSTRAINT autonomous_run_operator_check;
ALTER TABLE autonomous_run
    ADD CONSTRAINT autonomous_run_operator_check CHECK (
        operator IN ('submissions','curation','cron_health','chat_reliability')
    );

ALTER TABLE autonomous_budget_reservation
    DROP CONSTRAINT autonomous_budget_reservation_operator_check;
ALTER TABLE autonomous_budget_reservation
    ADD CONSTRAINT autonomous_budget_reservation_operator_check CHECK (
        operator IN ('submissions','curation','cron_health','chat_reliability')
    );

ALTER TABLE autonomous_action
    DROP CONSTRAINT autonomous_action_operator_check;
ALTER TABLE autonomous_action
    ADD CONSTRAINT autonomous_action_operator_check CHECK (
        operator IN ('submissions','curation','cron_health','chat_reliability')
    );

INSERT INTO autonomous_operator_state (
    operator, enabled, manual_mode, revision, updated_by
) VALUES (
    'curation', false, false, 1, 'system:migration'
)
ON CONFLICT (operator) DO NOTHING;

COMMIT;
