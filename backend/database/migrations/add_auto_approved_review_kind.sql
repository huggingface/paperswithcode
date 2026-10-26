-- Allow signed-in users' paper-page edits to be applied immediately and
-- reviewed afterwards: `reviewed_by_kind = 'auto'` marks those rows.
-- Apply as postgres for `public`, then again with `search_path=staging,public`,
-- before deploying. Idempotent: safe to re-run.
BEGIN;

ALTER TABLE pending_paper_edits
    DROP CONSTRAINT IF EXISTS pending_paper_edits_reviewed_by_kind_check;

ALTER TABLE pending_paper_edits
    ADD CONSTRAINT pending_paper_edits_reviewed_by_kind_check CHECK (
        reviewed_by_kind IS NULL OR reviewed_by_kind IN ('human', 'codex', 'auto')
    );

COMMIT;
