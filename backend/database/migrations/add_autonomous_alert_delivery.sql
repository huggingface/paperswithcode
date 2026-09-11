BEGIN;

DO $$
BEGIN
    IF current_schema() NOT IN ('staging', 'public') THEN
        RAISE EXCEPTION
            'add_autonomous_alert_delivery.sql requires search_path staging,public or public';
    END IF;
    IF current_schema() = 'staging'
       AND (NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging')
            OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging_owner')) THEN
        RAISE EXCEPTION
            'staging autonomous alerts require pwc_staging and pwc_staging_owner';
    END IF;
    IF current_schema() = 'public'
       AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        RAISE EXCEPTION
            'production autonomous alerts require paperswithcode_user';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS autonomous_alert_delivery (
    id UUID PRIMARY KEY,
    dedup_key VARCHAR(64) NOT NULL UNIQUE,
    event_kind VARCHAR(64) NOT NULL CHECK (
        event_kind IN (
            'operator_failure','site_impact','lease_timeout','repair_started',
            'review_rejected','deploy_succeeded','rollback','provider_switch',
            'budget_threshold','both_provider_outage','daily_digest'
        )
    ),
    severity VARCHAR(16) NOT NULL CHECK (
        severity IN ('info','high','critical')
    ),
    operator VARCHAR(32) CHECK (
        operator IS NULL OR operator IN (
            'submissions','curation','cron_health','chat_reliability'
        )
    ),
    resource_digest VARCHAR(64) NOT NULL CHECK (
        length(resource_digest) = 64
    ),
    environment VARCHAR(16) NOT NULL CHECK (
        environment IN ('staging','production')
    ),
    release_digest VARCHAR(64) NOT NULL CHECK (length(release_digest) = 64),
    primary_state VARCHAR(16) NOT NULL CHECK (
        primary_state IN (
            'acknowledged','failed','not_configured','suppressed'
        )
    ),
    primary_status_code INTEGER CHECK (
        primary_status_code IS NULL OR primary_status_code BETWEEN 100 AND 599
    ),
    fallback_state VARCHAR(16) NOT NULL CHECK (
        fallback_state IN (
            'acknowledged','failed','not_configured','not_needed','suppressed'
        )
    ),
    fallback_status_code INTEGER CHECK (
        fallback_status_code IS NULL OR fallback_status_code BETWEEN 100 AND 599
    ),
    delivered_route VARCHAR(16) NOT NULL CHECK (
        delivered_route IN ('primary','fallback','none','suppressed')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_autonomous_alert_delivery_created
    ON autonomous_alert_delivery (created_at);

CREATE OR REPLACE FUNCTION reject_autonomous_alert_delivery_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'autonomous_alert_delivery is append-only';
END;
$$;

DROP TRIGGER IF EXISTS autonomous_alert_delivery_no_update
    ON autonomous_alert_delivery;
CREATE TRIGGER autonomous_alert_delivery_no_update
    BEFORE UPDATE ON autonomous_alert_delivery
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_alert_delivery_mutation();
DROP TRIGGER IF EXISTS autonomous_alert_delivery_no_delete
    ON autonomous_alert_delivery;
CREATE TRIGGER autonomous_alert_delivery_no_delete
    BEFORE DELETE ON autonomous_alert_delivery
    FOR EACH ROW EXECUTE FUNCTION reject_autonomous_alert_delivery_mutation();
DROP TRIGGER IF EXISTS autonomous_alert_delivery_no_truncate
    ON autonomous_alert_delivery;
CREATE TRIGGER autonomous_alert_delivery_no_truncate
    BEFORE TRUNCATE ON autonomous_alert_delivery
    FOR EACH STATEMENT EXECUTE FUNCTION reject_autonomous_alert_delivery_mutation();

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE autonomous_alert_delivery OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT ON autonomous_alert_delivery TO pwc_staging;
    ELSE
        ALTER TABLE autonomous_alert_delivery OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT ON autonomous_alert_delivery TO paperswithcode_user;
    END IF;
END $$;

COMMIT;
