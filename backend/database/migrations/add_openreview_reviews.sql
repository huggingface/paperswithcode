-- Public OpenReview submissions and their replies (reviews, meta-reviews,
-- decisions, comments) for conferences such as ICLR 2027.
--
-- Filled by backend/scripts/import_openreview_reviews.py. Only notes whose
-- readers include 'everyone' are stored, so nothing an authenticated account
-- can see privately (reviewer identities, confidential comments) is kept.
--
-- Run as the schema owner (postgres). Idempotent — safe to re-run.

BEGIN;

SET LOCAL search_path = public;

CREATE TABLE IF NOT EXISTS openreview_submissions (
    -- OpenReview forum id, e.g. 'j6wn1MIOB5'.
    id VARCHAR(32) PRIMARY KEY,
    -- OpenReview venue group, e.g. 'ICLR.cc/2027/Conference'.
    venue_id VARCHAR(200) NOT NULL,
    conference_id BIGINT REFERENCES conferences(id) ON DELETE SET NULL,
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    abstract TEXT,
    keywords TEXT[] NOT NULL DEFAULT '{}',
    primary_area TEXT,
    -- Last segment of content.venueid: 'Submission', 'Withdrawn_Submission',
    -- 'Desk_Rejected_Submission', or the accepted venue after decisions.
    status VARCHAR(100) NOT NULL,
    -- Human venue label, e.g. 'ICLR 2027 Conference Submission'.
    venue TEXT,
    pdf_path TEXT,
    -- Matching PwC paper (normalized title match), if any.
    paper_id BIGINT REFERENCES papers(id) ON DELETE SET NULL,
    license VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL,
    modified_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (venue_id, number)
);

CREATE INDEX IF NOT EXISTS idx_openreview_submissions_paper_id
    ON openreview_submissions (paper_id) WHERE paper_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_openreview_submissions_conference_id
    ON openreview_submissions (conference_id);

CREATE TABLE IF NOT EXISTS openreview_notes (
    id VARCHAR(32) PRIMARY KEY,
    forum_id VARCHAR(32) NOT NULL
        REFERENCES openreview_submissions(id) ON DELETE CASCADE,
    reply_to VARCHAR(32),
    -- 'official_review', 'meta_review', 'decision', 'official_comment',
    -- 'public_comment', 'rebuttal', 'withdrawal', 'desk_rejection', 'other'.
    kind VARCHAR(40) NOT NULL,
    -- Last segment of the note's invitation, e.g. 'Official_Review'.
    invitation VARCHAR(100) NOT NULL,
    -- Anonymous signature, e.g. 'Reviewer_B3x7', 'Area_Chair_x1Yz', 'Authors'.
    signature VARCHAR(100) NOT NULL,
    -- Field name -> value, unwrapped from OpenReview's {"value": ...}.
    content JSONB NOT NULL,
    rating SMALLINT,
    confidence SMALLINT,
    license VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL,
    modified_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Set when a later import no longer sees the note publicly.
    removed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_openreview_notes_forum_id
    ON openreview_notes (forum_id);
CREATE INDEX IF NOT EXISTS idx_openreview_notes_kind
    ON openreview_notes (kind) WHERE removed_at IS NULL;

ALTER TABLE openreview_submissions OWNER TO paperswithcode_user;
ALTER TABLE openreview_notes OWNER TO paperswithcode_user;

DO $$
BEGIN
    IF to_regrole('pwc_staging') IS NOT NULL THEN
        GRANT SELECT ON openreview_submissions, openreview_notes TO pwc_staging;
    END IF;
END $$;

COMMIT;
