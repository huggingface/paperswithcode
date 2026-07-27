-- Allow signed-in users to suggest conferences through the pending-edit queue.
-- Approval records the review decision; admins create the conference separately.
-- Idempotent: safe to re-run.
BEGIN;

ALTER TABLE pending_paper_edits
    DROP CONSTRAINT IF EXISTS pending_paper_edits_edit_type_check;

ALTER TABLE pending_paper_edits
    ADD CONSTRAINT pending_paper_edits_edit_type_check CHECK (
        edit_type IN (
            'tasks',
            'methods',
            'evaluations',
            'repositories',
            'project_pages',
            'source_url',
            'hf_artifacts',
            'new_task',
            'new_method',
            'new_benchmark',
            'new_metric',
            'new_conference'
        )
    );

COMMIT;
