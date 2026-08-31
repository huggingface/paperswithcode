BEGIN;

DO $$
BEGIN
    IF current_schema() <> 'public' OR session_user <> 'postgres' THEN
        RAISE EXCEPTION
            'autonomous release broker migration requires postgres in public';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS autonomous_release_consumption (
    authorization_action_id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    action VARCHAR(16) NOT NULL,
    environment VARCHAR(16) NOT NULL,
    sha VARCHAR(40) NOT NULL,
    consumed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT fk_autonomous_release_consumption_action
        FOREIGN KEY (authorization_action_id)
        REFERENCES autonomous_action(id) ON DELETE RESTRICT,
    CONSTRAINT autonomous_release_consumption_action_check
        CHECK (action IN ('deploy','rollback')),
    CONSTRAINT autonomous_release_consumption_environment_check
        CHECK (environment IN ('staging','production')),
    CONSTRAINT autonomous_release_consumption_sha_check
        CHECK (length(sha) = 40)
);

ALTER TABLE autonomous_release_consumption OWNER TO postgres;
REVOKE ALL ON autonomous_release_consumption FROM PUBLIC;
REVOKE ALL ON autonomous_release_consumption FROM paperswithcode_user;
REVOKE ALL ON autonomous_release_consumption FROM pwc_staging;

COMMIT;
