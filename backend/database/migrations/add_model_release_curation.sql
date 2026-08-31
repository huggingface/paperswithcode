BEGIN;

CREATE TABLE IF NOT EXISTS model_releases (
    id BIGSERIAL PRIMARY KEY,
    paper_id BIGINT REFERENCES papers(id) ON DELETE CASCADE,
    canonical_name VARCHAR(500) NOT NULL,
    publisher VARCHAR(255),
    canonical_source_url TEXT,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_open BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_model_release_paper_name UNIQUE (paper_id, canonical_name)
);
CREATE INDEX IF NOT EXISTS idx_model_releases_paper ON model_releases(paper_id);
CREATE INDEX IF NOT EXISTS idx_model_releases_publisher ON model_releases(publisher);

CREATE TABLE IF NOT EXISTS model_release_artifacts (
    id BIGSERIAL PRIMARY KEY,
    model_release_id BIGINT NOT NULL REFERENCES model_releases(id) ON DELETE CASCADE,
    hf_artifact_id BIGINT NOT NULL REFERENCES hf_artifacts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_model_release_artifact UNIQUE (model_release_id, hf_artifact_id)
);
CREATE INDEX IF NOT EXISTS idx_model_release_artifacts_hf
    ON model_release_artifacts(hf_artifact_id);

CREATE TABLE IF NOT EXISTS model_provider_aliases (
    id BIGSERIAL PRIMARY KEY,
    model_release_id BIGINT NOT NULL REFERENCES model_releases(id) ON DELETE CASCADE,
    provider VARCHAR(100) NOT NULL,
    alias VARCHAR(500) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_model_provider_alias UNIQUE (provider, alias)
);
CREATE INDEX IF NOT EXISTS idx_model_provider_alias_release
    ON model_provider_aliases(model_release_id);

CREATE TABLE IF NOT EXISTS trending_model_candidates (
    id UUID PRIMARY KEY,
    repo_id TEXT NOT NULL UNIQUE,
    author VARCHAR(255) NOT NULL,
    readme_sha VARCHAR(64),
    readme_revision VARCHAR(64),
    status VARCHAR(24) NOT NULL DEFAULT 'discovered',
    rejection_reason TEXT,
    featured_publisher BOOLEAN NOT NULL DEFAULT FALSE,
    trending_score NUMERIC(12, 4),
    model_release_id BIGINT REFERENCES model_releases(id) ON DELETE SET NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMPTZ,
    CONSTRAINT trending_model_candidates_status_check CHECK (
        status IN ('discovered', 'rejected', 'queued', 'resolving', 'resolved', 'failed')
    )
);
CREATE INDEX IF NOT EXISTS idx_trending_model_candidates_status
    ON trending_model_candidates(status, last_seen_at);
CREATE INDEX IF NOT EXISTS idx_trending_model_candidates_release
    ON trending_model_candidates(model_release_id);

CREATE TABLE IF NOT EXISTS trending_model_curation_state (
    id INTEGER PRIMARY KEY,
    discovery_dry_run_completed BOOLEAN NOT NULL DEFAULT FALSE,
    canary_started_at TIMESTAMPTZ,
    canary_candidate_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    canary_released_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE paper_curation_jobs ALTER COLUMN paper_id DROP NOT NULL;
ALTER TABLE paper_curation_jobs ALTER COLUMN paper_route DROP NOT NULL;
ALTER TABLE paper_curation_jobs ALTER COLUMN paper_title DROP NOT NULL;
ALTER TABLE paper_curation_jobs
    ADD COLUMN IF NOT EXISTS candidate_id UUID
    REFERENCES trending_model_candidates(id) ON DELETE CASCADE;
ALTER TABLE paper_curation_jobs DROP CONSTRAINT IF EXISTS paper_curation_jobs_kind_check;
ALTER TABLE paper_curation_jobs ADD CONSTRAINT paper_curation_jobs_kind_check
    CHECK (kind IN ('add-evals', 'enrich-paper', 'resolve-model-paper'));
ALTER TABLE paper_curation_jobs DROP CONSTRAINT IF EXISTS paper_curation_jobs_trigger_check;
ALTER TABLE paper_curation_jobs ADD CONSTRAINT paper_curation_jobs_trigger_check
    CHECK (trigger IN ('admin', 'hf-daily-cron', 'hf-trending-cron', 'benchmark-promotion'));
ALTER TABLE paper_curation_jobs DROP CONSTRAINT IF EXISTS paper_curation_jobs_scope_check;
ALTER TABLE paper_curation_jobs ADD CONSTRAINT paper_curation_jobs_scope_check
    CHECK (
        (kind = 'resolve-model-paper' AND candidate_id IS NOT NULL AND paper_id IS NULL)
        OR (kind <> 'resolve-model-paper' AND candidate_id IS NULL AND paper_id IS NOT NULL)
    );
CREATE INDEX IF NOT EXISTS idx_paper_curation_jobs_candidate
    ON paper_curation_jobs(candidate_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_trending_model_resolution
    ON paper_curation_jobs(candidate_id, policy_version)
    WHERE kind = 'resolve-model-paper'
      AND status IN ('queued', 'dispatching', 'running');

ALTER TABLE paper_curation_workflows
    ADD COLUMN IF NOT EXISTS source_candidate_id UUID
    REFERENCES trending_model_candidates(id) ON DELETE SET NULL;
ALTER TABLE paper_curation_workflows
    ADD COLUMN IF NOT EXISTS source_revision VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_curation_workflow_candidate_revision
    ON paper_curation_workflows(source_candidate_id, source_revision, policy_version)
    WHERE source_candidate_id IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            model_releases,
            model_release_artifacts,
            model_provider_aliases,
            trending_model_candidates,
            trending_model_curation_state TO paperswithcode_user;
        GRANT USAGE, SELECT ON SEQUENCE
            model_releases_id_seq,
            model_release_artifacts_id_seq,
            model_provider_aliases_id_seq TO paperswithcode_user;
    END IF;
END $$;

COMMIT;
