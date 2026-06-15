-- Migration: HF-enhanced paper trending
-- Description: Adds normalized Hugging Face artifact metric storage, a paper<->artifact
--              junction, and paper-level composite trending score columns. The existing
--              repositories.trending_score (GitHub stars/hour EMA) is left untouched so the
--              current GitHub-only ranking remains the immediate rollback path.

-- =============================================================================
-- TABLE: hf_artifacts (normalized Hugging Face model/dataset/space rows)
-- =============================================================================

CREATE TABLE IF NOT EXISTS hf_artifacts (
    id BIGSERIAL PRIMARY KEY,
    kind VARCHAR(20) NOT NULL,
    repo_id TEXT NOT NULL,
    url TEXT NOT NULL,
    trending_score NUMERIC(12, 4) NULL,
    likes INTEGER NULL,
    downloads BIGINT NULL,
    fetched_at TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT hf_artifacts_kind_check CHECK (kind IN ('model', 'dataset', 'space')),
    CONSTRAINT uq_hf_artifacts_kind_repo UNIQUE (kind, repo_id)
);

COMMENT ON TABLE hf_artifacts IS
'Normalized Hugging Face artifacts (models/datasets/spaces) with Hub popularity metrics';
COMMENT ON COLUMN hf_artifacts.trending_score IS 'Hugging Face Hub trendingScore (expand[]=trendingScore)';

CREATE INDEX IF NOT EXISTS idx_hf_artifacts_trending_score
ON hf_artifacts(trending_score DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_hf_artifacts_fetched_at
ON hf_artifacts(fetched_at NULLS FIRST);

CREATE INDEX IF NOT EXISTS idx_hf_artifacts_kind
ON hf_artifacts(kind);

-- =============================================================================
-- TABLE: paper_hf_artifacts (paper <-> hf_artifact junction)
-- =============================================================================

CREATE TABLE IF NOT EXISTS paper_hf_artifacts (
    paper_id BIGINT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    hf_artifact_id BIGINT NOT NULL REFERENCES hf_artifacts(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (paper_id, hf_artifact_id)
);

COMMENT ON TABLE paper_hf_artifacts IS
'Links papers to the Hugging Face artifacts used for composite trending scores';

CREATE INDEX IF NOT EXISTS idx_paper_hf_artifacts_paper
ON paper_hf_artifacts(paper_id);

CREATE INDEX IF NOT EXISTS idx_paper_hf_artifacts_artifact
ON paper_hf_artifacts(hf_artifact_id);

-- =============================================================================
-- COLUMNS: papers composite trending score
-- =============================================================================

ALTER TABLE papers
ADD COLUMN IF NOT EXISTS trending_score NUMERIC(12, 4) NULL;

COMMENT ON COLUMN papers.trending_score IS
'Composite paper trending score (GitHub star velocity + Hugging Face artifact trending)';

ALTER TABLE papers
ADD COLUMN IF NOT EXISTS trending_score_updated_at TIMESTAMP WITH TIME ZONE NULL;

ALTER TABLE papers
ADD COLUMN IF NOT EXISTS github_trending_component NUMERIC(12, 4) NULL;

COMMENT ON COLUMN papers.github_trending_component IS
'Normalized GitHub component (0-1.5) of the composite paper trending score (debug)';

ALTER TABLE papers
ADD COLUMN IF NOT EXISTS hf_trending_component NUMERIC(12, 4) NULL;

COMMENT ON COLUMN papers.hf_trending_component IS
'Normalized Hugging Face component (0-1.5) of the composite paper trending score (debug)';

ALTER TABLE papers
ADD COLUMN IF NOT EXISTS hf_artifacts_scanned_at TIMESTAMP WITH TIME ZONE NULL;

COMMENT ON COLUMN papers.hf_artifacts_scanned_at IS
'When this paper was last scanned for linked Hugging Face artifacts (NULL = never)';

CREATE INDEX IF NOT EXISTS idx_papers_trending_score
ON papers(trending_score DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_papers_trending_score_updated_at
ON papers(trending_score_updated_at);

CREATE INDEX IF NOT EXISTS idx_papers_hf_artifacts_scanned_at
ON papers(hf_artifacts_scanned_at NULLS FIRST);

-- =============================================================================
-- VERIFICATION
-- =============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_name = 'hf_artifacts'
    ) THEN
        RAISE NOTICE 'Table hf_artifacts ready';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_name = 'paper_hf_artifacts'
    ) THEN
        RAISE NOTICE 'Table paper_hf_artifacts ready';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'papers' AND column_name = 'trending_score'
    ) THEN
        RAISE NOTICE 'Column papers.trending_score ready';
    END IF;
END $$;
