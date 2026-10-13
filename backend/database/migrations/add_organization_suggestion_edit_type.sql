-- Allow signed-in users to suggest new organizations (name, Hugging Face
-- handle, website, logo) through the pending-edit queue. Approval creates the
-- organization and, for suggestions made from a paper page, tags that paper.
-- Apply as postgres for `public`, then again with `search_path=staging,public`.
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
            'organizations',
            'x_threads',
            'new_task',
            'new_method',
            'new_benchmark',
            'new_metric',
            'new_conference',
            'new_organization',
            'new_external_paper'
        )
    );

COMMIT;
