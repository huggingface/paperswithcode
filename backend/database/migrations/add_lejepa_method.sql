-- Add LeJEPA, introduced in arXiv 2511.08544.
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
    'lejepa',
    'LeJEPA',
    'Lean Joint-Embedding Predictive Architecture (LeJEPA)',
    'LeJEPA is a theoretically grounded self-supervised training objective for [Joint-Embedding Predictive Architectures](/methods/jepa) (JEPAs) introduced by Randall Balestriero and Yann LeCun. The paper shows that the isotropic Gaussian is the optimal distribution for JEPA embeddings to minimize downstream prediction risk, and introduces Sketched Isotropic Gaussian Regularization (SIGReg), which pushes embeddings toward that distribution by matching random one-dimensional projections to a standard Gaussian. Combining the JEPA predictive loss with SIGReg removes the usual [self-supervised learning](/methods/self-supervised-learning) heuristics such as stop-gradient, teacher-student networks and hyper-parameter schedulers, leaving a single trade-off hyperparameter, linear time and memory complexity, and an implementation of about 50 lines of code. It is stable across ResNets, [Vision Transformers](/methods/vision-transformer) and ConvNets and over 10+ datasets and 60+ architectures; with ImageNet-1k pretraining and frozen-backbone linear evaluation, a ViT-H/14 reaches 79%. It offers a heuristics-free alternative to [DINO](/methods/dino)-style distillation.',
    'LeJEPA, SIGReg, sketched isotropic gaussian regularization',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2511.08544'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'LeJEPA: Provable and Scalable Self-Supervised Learning Without the Heuristics',
    'https://github.com/rbalestr-lab/lejepa',
    NULL,
    '[LeJEPA: Provable and Scalable Self-Supervised Learning Without the Heuristics](/paper/2511.08544)'
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
WHERE slug = 'lejepa' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'lejepa' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 51 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE lejepa_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lejepa'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        55184, 56364, 56719, 56841, 56944, 58611, 59444, 59510, 61328, 61775, 62597, 63814,
        63874, 64731, 98453, 98852, 98956, 99043, 99067, 99639, 100026, 100475, 100641, 101669,
        101771, 102574, 102613, 102655, 104096, 105861, 105947, 106016, 106017, 106030, 108870, 109505,
        109539, 119106, 119568, 119609, 121987, 122247, 122415, 122522, 122616, 122704, 123120, 123138,
        123140, 123141, 123156
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'lejepa citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM lejepa_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING lejepa_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 10 local citers name the method in title or abstract.
CREATE TEMP TABLE lejepa_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lejepa'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        58970, 59168, 59812, 61611, 101702, 109304, 109848, 122929, 123158, 123383
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM lejepa_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM lejepa_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 14 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE lejepa_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lejepa'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        58970, 59168, 59812, 61611, 98562, 101702, 102205, 106058, 109304, 109848, 122822, 122929,
        123158, 123383
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM lejepa_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM lejepa_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
