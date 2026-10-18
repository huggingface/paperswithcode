-- Add HRM, introduced in arXiv 2506.21734.
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
    'hrm',
    'HRM',
    'Hierarchical Reasoning Model (HRM)',
    'The Hierarchical Reasoning Model (HRM) is a brain-inspired recurrent architecture from Sapient Intelligence that performs deep reasoning in a single forward pass, without [chain-of-thought](/methods/chain-of-thought-cot) supervision or pre-training. It couples two interdependent recurrent [Transformer](/methods/transformer) modules running at different timescales: a slow high-level module for abstract planning and a fast low-level module that performs several detailed computation steps per high-level update. This hierarchical convergence gives HRM large effective computational depth. It is trained with a one-step gradient approximation inspired by deep equilibrium models, which avoids backpropagation through time, plus deep supervision and adaptive computation time to decide when to stop. With only 27 million parameters and about 1,000 training examples, HRM achieves nearly perfect accuracy on hard Sudoku and large-maze path finding and outperforms much larger LLMs on ARC-AGI. It is a precursor of the simpler [Tiny Recursive Model](/methods/tiny-recursive-model) and is related to [looped transformers](/methods/looped-transformer) and [latent reasoning](/methods/latent-reasoning).',
    'hierarchical reasoning model',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2506.21734'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Hierarchical Reasoning Model',
    'https://github.com/sapientinc/HRM',
    NULL,
    '[Hierarchical Reasoning Model](/paper/2506.21734)'
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
WHERE slug = 'hrm' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'hrm' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 52 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE hrm_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'hrm'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        44949, 51934, 52643, 53344, 54120, 54371, 54807, 54836, 55689, 55900, 56032, 56613,
        56979, 57473, 57766, 60456, 60553, 61828, 62239, 62445, 64056, 64395, 64755, 68573,
        68722, 69552, 69651, 70745, 82976, 82990, 83256, 83262, 83514, 83518, 87164, 94156,
        94668, 99757, 101313, 101988, 104048, 104301, 105956, 105960, 106053, 109050, 114095, 122266,
        122516, 122715, 122750, 122955
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'hrm citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM hrm_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING hrm_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 4 local citers name the method in title or abstract.
CREATE TEMP TABLE hrm_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'hrm'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        62450, 67250, 94101, 101877
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM hrm_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM hrm_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 6 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE hrm_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'hrm'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        53263, 62450, 67250, 94101, 101877, 109348
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM hrm_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM hrm_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
