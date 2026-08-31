BEGIN;

ALTER TABLE autonomous_submission_claim
    ADD COLUMN IF NOT EXISTS remote_manifest_digest VARCHAR(64),
    ADD COLUMN IF NOT EXISTS remote_job_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS remote_review_run_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'autonomous_submission_claim_remote_manifest_digest_check'
          AND conrelid = 'autonomous_submission_claim'::regclass
    ) THEN
        ALTER TABLE autonomous_submission_claim
            ADD CONSTRAINT autonomous_submission_claim_remote_manifest_digest_check
            CHECK (
                remote_manifest_digest IS NULL
                OR length(remote_manifest_digest) = 64
            );
    END IF;
END $$;

REVOKE ALL ON autonomous_submission_claim FROM PUBLIC;

COMMIT;
