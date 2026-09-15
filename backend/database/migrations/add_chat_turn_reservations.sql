BEGIN;

CREATE TABLE IF NOT EXISTS chat_turn_admission_budgets (
    environment VARCHAR(16) PRIMARY KEY CHECK (environment IN ('staging','production')),
    turn_limit INTEGER NOT NULL CHECK (turn_limit = 32),
    environment_limit INTEGER NOT NULL CHECK (environment_limit = 32),
    operation_limit INTEGER NOT NULL CHECK (operation_limit = 128),
    spend_limit_microusd BIGINT NOT NULL CHECK (spend_limit_microusd > 0),
    active_turns INTEGER NOT NULL DEFAULT 0 CHECK (active_turns >= 0),
    reserved_environments INTEGER NOT NULL DEFAULT 0 CHECK (reserved_environments >= 0),
    reserved_operations INTEGER NOT NULL DEFAULT 0 CHECK (reserved_operations >= 0),
    reserved_microusd BIGINT NOT NULL DEFAULT 0 CHECK (reserved_microusd >= 0),
    spent_microusd BIGINT NOT NULL DEFAULT 0 CHECK (spent_microusd >= 0),
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_turn_reservations (
    turn_id UUID PRIMARY KEY,
    request_id VARCHAR(200) NOT NULL UNIQUE,
    owner_id VARCHAR(255) NOT NULL,
    environment VARCHAR(16) NOT NULL REFERENCES chat_turn_admission_budgets(environment),
    state VARCHAR(24) NOT NULL CHECK (state IN ('reserved','dispatched','completed','failed','cancelled','cost_unknown')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    reserved_turns INTEGER NOT NULL DEFAULT 1 CHECK (reserved_turns = 1),
    reserved_environments INTEGER NOT NULL DEFAULT 1 CHECK (reserved_environments = 1),
    reserved_operations INTEGER NOT NULL DEFAULT 4 CHECK (reserved_operations = 4),
    reserved_microusd BIGINT NOT NULL CHECK (reserved_microusd >= 0),
    actual_microusd BIGINT CHECK (actual_microusd IS NULL OR actual_microusd >= 0),
    terminal_outcome VARCHAR(16) CONSTRAINT chat_turn_reservations_outcome_check CHECK (
        terminal_outcome IS NULL OR terminal_outcome IN ('completed','failed','cancelled')
    ),
    resource_started_at TIMESTAMPTZ,
    resource_ended_at TIMESTAMPTZ
        CONSTRAINT chat_turn_reservations_resource_window_check CHECK (
        resource_ended_at IS NULL OR (
            resource_started_at IS NOT NULL AND resource_ended_at >= resource_started_at
        )
    ),
    reserved_at TIMESTAMPTZ NOT NULL,
    dispatched_at TIMESTAMPTZ,
    settled_at TIMESTAMPTZ
);

ALTER TABLE chat_turn_reservations
    ADD COLUMN IF NOT EXISTS terminal_outcome VARCHAR(16),
    ADD COLUMN IF NOT EXISTS resource_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS resource_ended_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chat_turn_reservations_outcome_check'
          AND conrelid = 'chat_turn_reservations'::regclass
    ) THEN
        ALTER TABLE chat_turn_reservations
            ADD CONSTRAINT chat_turn_reservations_outcome_check CHECK (
                terminal_outcome IS NULL OR
                terminal_outcome IN ('completed','failed','cancelled')
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chat_turn_reservations_resource_window_check'
          AND conrelid = 'chat_turn_reservations'::regclass
    ) THEN
        ALTER TABLE chat_turn_reservations
            ADD CONSTRAINT chat_turn_reservations_resource_window_check CHECK (
                resource_ended_at IS NULL OR (
                    resource_started_at IS NOT NULL AND
                    resource_ended_at >= resource_started_at
                )
            );
    END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_turn_reservations_active_owner
    ON chat_turn_reservations(environment, owner_id)
    WHERE state IN ('reserved','dispatched');
CREATE INDEX IF NOT EXISTS idx_chat_turn_reservations_state
    ON chat_turn_reservations(environment, state);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        IF to_regrole('pwc_staging') IS NULL OR to_regrole('pwc_staging_owner') IS NULL THEN
            RAISE EXCEPTION 'staging turn reservation migration requires pwc_staging roles';
        END IF;
        ALTER TABLE chat_turn_admission_budgets OWNER TO pwc_staging_owner;
        ALTER TABLE chat_turn_reservations OWNER TO pwc_staging_owner;
        GRANT SELECT,INSERT,UPDATE,DELETE ON
            chat_turn_admission_budgets,chat_turn_reservations TO pwc_staging;
        IF to_regrole('paperswithcode_user') IS NOT NULL THEN
            REVOKE ALL ON
                chat_turn_admission_budgets,chat_turn_reservations
                FROM paperswithcode_user;
        END IF;
    ELSIF current_schema() = 'public' THEN
        IF to_regrole('paperswithcode_user') IS NULL THEN
            RAISE EXCEPTION 'production turn reservation migration requires paperswithcode_user';
        END IF;
        ALTER TABLE chat_turn_admission_budgets OWNER TO paperswithcode_user;
        ALTER TABLE chat_turn_reservations OWNER TO paperswithcode_user;
        GRANT SELECT,INSERT,UPDATE,DELETE ON
            chat_turn_admission_budgets,chat_turn_reservations TO paperswithcode_user;
        IF to_regrole('pwc_staging') IS NOT NULL THEN
            REVOKE ALL ON
                chat_turn_admission_budgets,chat_turn_reservations
                FROM pwc_staging;
        END IF;
    ELSE
        RAISE EXCEPTION 'turn reservation migration requires staging or public schema';
    END IF;
END;
$$;

COMMIT;
