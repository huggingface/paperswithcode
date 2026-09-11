BEGIN;

DO $$
DECLARE
    target_schema TEXT := current_schema();
    required_relation TEXT;
BEGIN
    IF target_schema NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_curation_autonomous_operator.sql requires search_path staging,public or public';
    END IF;

    FOREACH required_relation IN ARRAY ARRAY[
        'autonomous_operator_state',
        'autonomous_execution_intent',
        'autonomous_run',
        'autonomous_budget_reservation',
        'autonomous_action',
        'autonomous_alert_delivery'
    ] LOOP
        IF to_regclass(format('%I.%I', target_schema, required_relation)) IS NULL THEN
            RAISE EXCEPTION
                'add_curation_autonomous_operator.sql missing %.% prerequisite',
                target_schema,
                required_relation;
        END IF;
    END LOOP;

    EXECUTE format(
        'ALTER TABLE %I.autonomous_operator_state '
        'DROP CONSTRAINT autonomous_operator_state_operator_check',
        target_schema
    );
    EXECUTE format(
        'ALTER TABLE %I.autonomous_operator_state '
        'ADD CONSTRAINT autonomous_operator_state_operator_check CHECK ('
        'operator IN ('
        '''global'',''submissions'',''curation'',''cron_health'',''chat_reliability'''
        '))',
        target_schema
    );

    EXECUTE format(
        'ALTER TABLE %I.autonomous_execution_intent '
        'DROP CONSTRAINT autonomous_execution_intent_operator_check',
        target_schema
    );
    EXECUTE format(
        'ALTER TABLE %I.autonomous_execution_intent '
        'ADD CONSTRAINT autonomous_execution_intent_operator_check CHECK ('
        'operator IN ('
        '''submissions'',''curation'',''cron_health'',''chat_reliability'''
        '))',
        target_schema
    );

    EXECUTE format(
        'ALTER TABLE %I.autonomous_run '
        'DROP CONSTRAINT autonomous_run_operator_check',
        target_schema
    );
    EXECUTE format(
        'ALTER TABLE %I.autonomous_run '
        'ADD CONSTRAINT autonomous_run_operator_check CHECK ('
        'operator IN ('
        '''submissions'',''curation'',''cron_health'',''chat_reliability'''
        '))',
        target_schema
    );

    EXECUTE format(
        'ALTER TABLE %I.autonomous_budget_reservation '
        'DROP CONSTRAINT autonomous_budget_reservation_operator_check',
        target_schema
    );
    EXECUTE format(
        'ALTER TABLE %I.autonomous_budget_reservation '
        'ADD CONSTRAINT autonomous_budget_reservation_operator_check CHECK ('
        'operator IN ('
        '''submissions'',''curation'',''cron_health'',''chat_reliability'''
        '))',
        target_schema
    );

    EXECUTE format(
        'ALTER TABLE %I.autonomous_action '
        'DROP CONSTRAINT autonomous_action_operator_check',
        target_schema
    );
    EXECUTE format(
        'ALTER TABLE %I.autonomous_action '
        'ADD CONSTRAINT autonomous_action_operator_check CHECK ('
        'operator IN ('
        '''submissions'',''curation'',''cron_health'',''chat_reliability'''
        '))',
        target_schema
    );

    EXECUTE format(
        'ALTER TABLE %I.autonomous_alert_delivery '
        'DROP CONSTRAINT autonomous_alert_delivery_operator_check',
        target_schema
    );
    EXECUTE format(
        'ALTER TABLE %I.autonomous_alert_delivery '
        'ADD CONSTRAINT autonomous_alert_delivery_operator_check CHECK ('
        'operator IS NULL OR operator IN ('
        '''submissions'',''curation'',''cron_health'',''chat_reliability'''
        '))',
        target_schema
    );

    EXECUTE format(
        'INSERT INTO %I.autonomous_operator_state ('
        'operator, enabled, manual_mode, revision, updated_by'
        ') VALUES ('
        '''curation'', false, false, 1, ''system:migration'''
        ') ON CONFLICT (operator) DO NOTHING',
        target_schema
    );
END $$;

COMMIT;
