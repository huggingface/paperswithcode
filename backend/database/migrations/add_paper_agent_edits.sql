-- Apply before deploying paper-agent edits. No catalog data is changed.
BEGIN;
ALTER TABLE catalog_mutation_events ADD COLUMN IF NOT EXISTS paper_id bigint;
CREATE INDEX IF NOT EXISTS ix_catalog_mutation_events_paper_id ON catalog_mutation_events (paper_id);
-- The schema owner disables only the rewrite trigger during this transaction
-- to populate the new indexing column. Snapshots and attribution are untouched.
ALTER TABLE catalog_mutation_events DISABLE TRIGGER catalog_mutation_events_append_only;
-- Attach existing audit events to their paper without changing their snapshots.
UPDATE catalog_mutation_events SET paper_id = CASE
    WHEN entity_type LIKE 'paper_%' AND entity_id ~ '^[0-9]+$' THEN entity_id::bigint
    WHEN entity_type = 'evaluation' AND entity_id ~ '^paper:[0-9]+$' THEN split_part(entity_id, ':', 2)::bigint
    WHEN entity_type = 'evaluation' THEN COALESCE(after_snapshot->>'paper_id', before_snapshot->>'paper_id')::bigint
END WHERE paper_id IS NULL AND (entity_type LIKE 'paper_%' OR entity_type = 'evaluation');
ALTER TABLE catalog_mutation_events ENABLE TRIGGER catalog_mutation_events_append_only;
CREATE TABLE IF NOT EXISTS paper_edit_accounts (
    hf_subject varchar(255) PRIMARY KEY,
    suspended boolean NOT NULL DEFAULT false,
    updated_by varchar(255),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS paper_edit_authorizations (
    id uuid PRIMARY KEY,
    paper_id bigint NOT NULL,
    client_key varchar(64),
    device_hash varchar(64) NOT NULL UNIQUE,
    token_hash varchar(64) UNIQUE,
    hf_subject varchar(255),
    username varchar(255),
    created_at timestamptz NOT NULL DEFAULT now(),
    approved_at timestamptz,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_paper_edit_authorizations_hf_subject ON paper_edit_authorizations (hf_subject);
CREATE INDEX IF NOT EXISTS ix_paper_edit_authorizations_expires_at ON paper_edit_authorizations (expires_at);
COMMIT;
