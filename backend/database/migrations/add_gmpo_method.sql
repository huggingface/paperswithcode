-- Add GMPO, introduced in arXiv 2507.20673.
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
    'gmpo',
    'GMPO',
    'Geometric-Mean Policy Optimization (GMPO)',
    'Geometric-Mean Policy Optimization (GMPO) is a stabilized variant of [GRPO](/methods/grpo) for reinforcement learning of large language models. GRPO maximizes the arithmetic mean of token-level, importance-weighted rewards, so tokens with outlier importance-sampling ratios between the current and old policy can cause extreme, unstable policy updates. GMPO instead maximizes the geometric mean of the clipped token-level objectives, which is inherently less sensitive to outliers and keeps the importance-sampling ratio in a narrower range; this stability in turn allows a larger clipping range that promotes exploration. The authors back the design with theoretical and experimental analysis. GMPO-7B outperforms GRPO by an average of 4.1% on mathematical benchmarks (AIME24, AMC, MATH500, OlympiadBench, Minerva) and by 1.4% on the multimodal Geometry3K benchmark, while keeping higher entropy during training. It is a drop-in replacement for the GRPO objective in [RLVR](/methods/rlvr) pipelines and is related to sequence-level methods such as [GSPO](/methods/gspo).',
    'GMPO, geometric-mean policy optimization, geometric mean policy optimization',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2507.20673'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Geometric-Mean Policy Optimization',
    'https://github.com/callsys/GMPO',
    NULL,
    '[Geometric-Mean Policy Optimization](/paper/2507.20673)'
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
WHERE slug = 'gmpo' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'gmpo' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 56 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE gmpo_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gmpo'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        52630, 53013, 53040, 53105, 53167, 53376, 53462, 53831, 53877, 54715, 55001, 55044,
        55351, 55548, 56009, 56267, 56329, 56368, 56432, 56463, 56637, 56937, 57199, 57276,
        57452, 58088, 58667, 59594, 61360, 61552, 62862, 63704, 64360, 65346, 65817, 66056,
        66449, 66721, 83287, 83290, 83859, 93775, 95434, 98290, 98329, 98417, 98894, 99536,
        99559, 99725, 101445, 102716, 104486, 106387, 108747, 123137
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'gmpo citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM gmpo_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING gmpo_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 1 local citers name the method in title or abstract.
CREATE TEMP TABLE gmpo_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gmpo'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        83699
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gmpo_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM gmpo_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 1 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE gmpo_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gmpo'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        83699
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gmpo_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM gmpo_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
