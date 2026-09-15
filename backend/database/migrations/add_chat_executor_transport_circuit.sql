BEGIN;

ALTER TABLE chat_turn_reservations
    ADD COLUMN IF NOT EXISTS transport VARCHAR(16) NOT NULL DEFAULT 'legacy'
    CHECK (transport IN ('legacy','persistent'));

CREATE TABLE IF NOT EXISTS chat_executor_transport_circuits (
    environment VARCHAR(16) PRIMARY KEY CHECK (environment IN ('staging','production')),
    state VARCHAR(24) NOT NULL DEFAULT 'closed' CHECK (state IN ('closed','open','half_open','security_hold')),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    epoch INTEGER NOT NULL DEFAULT 0 CHECK (epoch >= 0),
    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    failure_window_started_at TIMESTAMPTZ,
    opened_at TIMESTAMPTZ,
    open_until TIMESTAMPTZ,
    canary_owner VARCHAR(128),
    canary_expires_at TIMESTAMPTZ,
    half_open_successes INTEGER NOT NULL DEFAULT 0 CHECK (half_open_successes >= 0),
    security_reason VARCHAR(64),
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_executor_transport_alerts (
    event_id VARCHAR(160) PRIMARY KEY,
    environment VARCHAR(16) NOT NULL REFERENCES chat_executor_transport_circuits(environment) ON DELETE CASCADE,
    epoch INTEGER NOT NULL CHECK (epoch > 0),
    transition VARCHAR(24) NOT NULL CHECK (transition IN ('open','security_hold','recovered')),
    delivery_state VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (delivery_state IN ('pending','claimed','acknowledged')),
    claim_owner VARCHAR(128),
    claim_expires_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL,
    acknowledged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (environment, epoch, transition),
    CHECK ((delivery_state = 'claimed') = (claim_owner IS NOT NULL AND claim_expires_at IS NOT NULL))
);

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        IF to_regrole('pwc_staging') IS NULL OR to_regrole('pwc_staging_owner') IS NULL THEN
            RAISE EXCEPTION 'staging transport circuit migration requires pwc_staging roles';
        END IF;
        ALTER TABLE chat_executor_transport_circuits OWNER TO pwc_staging_owner;
        ALTER TABLE chat_executor_transport_alerts OWNER TO pwc_staging_owner;
        GRANT SELECT,INSERT,UPDATE,DELETE ON
            chat_executor_transport_circuits,chat_executor_transport_alerts
            TO pwc_staging;
        IF to_regrole('paperswithcode_user') IS NOT NULL THEN
            REVOKE ALL ON
                chat_executor_transport_circuits,chat_executor_transport_alerts
                FROM paperswithcode_user;
        END IF;
    ELSIF current_schema() = 'public' THEN
        IF to_regrole('paperswithcode_user') IS NULL THEN
            RAISE EXCEPTION 'production transport circuit migration requires paperswithcode_user';
        END IF;
        ALTER TABLE chat_executor_transport_circuits OWNER TO paperswithcode_user;
        ALTER TABLE chat_executor_transport_alerts OWNER TO paperswithcode_user;
        GRANT SELECT,INSERT,UPDATE,DELETE ON
            chat_executor_transport_circuits,chat_executor_transport_alerts
            TO paperswithcode_user;
        IF to_regrole('pwc_staging') IS NOT NULL THEN
            REVOKE ALL ON
                chat_executor_transport_circuits,chat_executor_transport_alerts
                FROM pwc_staging;
        END IF;
    ELSE
        RAISE EXCEPTION 'transport circuit migration requires staging or public schema';
    END IF;
END;
$$;

COMMIT;
