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

COMMIT;
