-- Migration: Record saved-papers Bucket migrations on the account
--
-- The HF Bucket token is stored in a per-browser cookie, so a second device
-- (or the same device after the token expires) cannot tell that the user has
-- already migrated. `saved_papers_bucket_migrated_at` is set the first time a
-- request reads the user's Bucket, and /saved then offers a reconnect instead
-- of a fresh migration. Nullable with no default: a metadata-only change.
--
-- Created: 2026-10-29
-- Usage (as postgres, before deploying the backend that maps the column):
--   sudo -u postgres psql -d paperswithcode_hf -X -v ON_ERROR_STOP=1 \
--        < backend/database/migrations/add_saved_papers_bucket_migrated_at.sql

BEGIN;

SET LOCAL lock_timeout = '10s';

ALTER TABLE public.user_preferences
    ADD COLUMN IF NOT EXISTS saved_papers_bucket_migrated_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE IF EXISTS staging.user_preferences
    ADD COLUMN IF NOT EXISTS saved_papers_bucket_migrated_at TIMESTAMP WITH TIME ZONE;

COMMIT;
