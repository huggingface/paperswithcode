-- Directory-level task and method suggestions use the existing pending-edit
-- endpoint and review queue, but are not associated with a specific paper.
-- Idempotent: safe to re-run.
BEGIN;

ALTER TABLE pending_paper_edits
    ALTER COLUMN paper_id DROP NOT NULL;

COMMIT;
