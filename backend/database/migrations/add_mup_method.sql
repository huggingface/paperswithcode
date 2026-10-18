-- Add muP, introduced in arXiv 2011.14522.
-- Added 2026-10-18 from a scan of methods named by many recent papers but
-- missing from the catalog. The source paper gets the source evidence row (Introduced banner).

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'mup',
    'muP',
    'Maximal Update Parametrization (muP)',
    'Maximal Update Parametrization (muP, written μP) is a rule for scaling a network''s initialization variances, per-layer learning rates and output multipliers with width so that every layer keeps learning features as width grows. It was derived with the Tensor Programs technique in [Feature Learning in Infinite-Width Neural Networks](/paper/2011.14522), which showed that standard and NTK parametrizations lose feature learning in the infinite-width limit and that muP is the parametrization that maximizes it. [Tensor Programs V](/paper/2203.03466) found that many optimal hyperparameters stay stable across model sizes under muP, enabling muTransfer: tune a small proxy and copy the hyperparameters zero-shot to the full model. Transferring from a 13M-parameter proxy beat published BERT-large results, and transferring from 40M parameters beat the published 6.7B [GPT-3](/methods/gpt-3) at a tuning cost of 7% of pre-training. muP and its depth and [Muon](/methods/muon)-compatible extensions are widely used for LLM pre-training and studied alongside [scaling laws](/methods/scaling-laws) and [Adam](/methods/adam).',
    'μP, µP, muP, muTransfer, μTransfer, maximal update parametrization, maximal update parameterization, maximal-update parameterization, maximum update parameterization',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2020,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2011.14522'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Feature Learning in Infinite-Width Neural Networks',
    'https://github.com/microsoft/mup',
    NULL,
    '[Tensor Programs V: Tuning Large Neural Networks via Zero-Shot Hyperparameter Transfer](/paper/2203.03466)'
)
ON CONFLICT (slug) DO UPDATE
SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'mup' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'mup' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 60 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE mup_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mup'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        5945, 6036, 6509, 7972, 9141, 12694, 13890, 13926, 17917, 20568, 21822, 26241,
        27999, 28058, 28787, 28870, 29155, 34237, 38075, 44808, 45561, 48348, 49089, 51470,
        51820, 52347, 59049, 60060, 61892, 72988, 74315, 80398, 80701, 83269, 86391, 87271,
        87330, 88528, 88574, 88584, 88834, 88943, 89014, 91449, 91851, 92083, 92418, 92968,
        93039, 93117, 94702, 98317, 100490, 100701, 100881, 101295, 101990, 102079, 102256, 102981
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'mup citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM mup_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING mup_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 7 local citers name the method in title or abstract.
CREATE TEMP TABLE mup_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mup'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        8161, 32611, 36185, 53665, 78315, 91119, 102539
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mup_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM mup_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 40 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE mup_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mup'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        8161, 14502, 14695, 24980, 32161, 32611, 34298, 35165, 36185, 48381, 49279, 53665,
        54437, 55063, 55157, 55858, 56389, 58743, 62061, 62560, 62777, 63066, 63265, 64482,
        65467, 71679, 78315, 83362, 83512, 83668, 89714, 91119, 92565, 93047, 93632, 102062,
        102539, 109589, 121628, 123245
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mup_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM mup_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
