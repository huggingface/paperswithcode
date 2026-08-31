BEGIN;

CREATE TABLE IF NOT EXISTS autonomous_submission_claim (
    claim_id UUID PRIMARY KEY,
    pending_edit_id BIGINT NOT NULL REFERENCES pending_paper_edits(id) ON DELETE RESTRICT,
    run_id UUID NOT NULL REFERENCES autonomous_run(id) ON DELETE RESTRICT,
    review_run_id UUID REFERENCES autonomous_run(id) ON DELETE RESTRICT,
    attested_decision_digest VARCHAR(64),
    snapshot_digest VARCHAR(64) NOT NULL,
    callback_token_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    state VARCHAR(16) NOT NULL DEFAULT 'claimed',
    decision VARCHAR(16),
    decision_digest VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT autonomous_submission_claim_state_check
        CHECK (state IN ('claimed','completed')),
    CONSTRAINT autonomous_submission_claim_decision_check
        CHECK (decision IS NULL OR decision IN ('approve','reject','defer')),
    CONSTRAINT autonomous_submission_claim_digest_check
        CHECK (length(snapshot_digest) = 64 AND length(callback_token_hash) = 64),
    CONSTRAINT autonomous_submission_claim_decision_digest_check
        CHECK (decision_digest IS NULL OR length(decision_digest) = 64),
    CONSTRAINT autonomous_submission_claim_attested_digest_check
        CHECK (attested_decision_digest IS NULL OR length(attested_decision_digest) = 64),
    CONSTRAINT uq_autonomous_submission_claim_edit_run UNIQUE (pending_edit_id, run_id)
);

ALTER TABLE autonomous_submission_claim
    ADD COLUMN IF NOT EXISTS review_run_id UUID
    REFERENCES autonomous_run(id) ON DELETE RESTRICT;

ALTER TABLE autonomous_submission_claim
    ADD COLUMN IF NOT EXISTS attested_decision_digest VARCHAR(64);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'autonomous_submission_claim_attested_digest_check'
          AND conrelid = 'autonomous_submission_claim'::regclass
    ) THEN
        ALTER TABLE autonomous_submission_claim
            ADD CONSTRAINT autonomous_submission_claim_attested_digest_check
            CHECK (
                attested_decision_digest IS NULL
                OR length(attested_decision_digest) = 64
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_autonomous_submission_claim_pending_state
    ON autonomous_submission_claim (pending_edit_id, state, expires_at);

REVOKE ALL ON autonomous_submission_claim FROM PUBLIC;

DO $$
BEGIN
    IF current_schema() = 'staging' THEN
        ALTER TABLE autonomous_submission_claim OWNER TO pwc_staging_owner;
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON autonomous_submission_claim TO pwc_staging;
        REVOKE ALL ON autonomous_submission_claim FROM paperswithcode_user;
    ELSE
        ALTER TABLE autonomous_submission_claim OWNER TO paperswithcode_user;
        GRANT SELECT, INSERT, UPDATE, DELETE
            ON autonomous_submission_claim TO paperswithcode_user;
        REVOKE ALL ON autonomous_submission_claim FROM pwc_staging;
    END IF;
END $$;

COMMIT;
