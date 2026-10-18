-- Add DiffusionNFT, introduced in arXiv 2509.16117.
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
    'diffusionnft',
    'DiffusionNFT',
    'Diffusion Negative-aware FineTuning (DiffusionNFT)',
    'DiffusionNFT (Diffusion Negative-aware FineTuning) is an online reinforcement learning method for diffusion and flow models that optimizes on the forward process via [flow matching](/methods/flow-matching), instead of treating the reverse sampler as a policy. Earlier approaches such as Flow-GRPO discretize the reverse SDE to apply [GRPO](/methods/grpo)-style likelihood ratios. That restricts the solver, causes forward-reverse inconsistency and complicates [classifier-free guidance](/methods/classifier-free-guidance). DiffusionNFT splits the reward-weighted generations of the current model into implicit positive and negative policies. It trains both with ordinary flow-matching losses on clean images, which defines an implicit policy-improvement direction inside a supervised objective. As a result it works with arbitrary black-box samplers, needs no likelihood estimation or stored trajectories, and is CFG-free. It was up to 25× more efficient than Flow-GRPO head to head, raising GenEval from 0.24 to 0.98 within 1k steps, against 0.95 for Flow-GRPO after more than 5k steps with CFG. With multiple [reward models](/methods/reward-model) it improved SD3.5-Medium on every benchmark tested.',
    'DiffusionNFT, diffusion negative-aware finetuning, diffusion negative-aware fine-tuning',
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
        WHERE arxiv_id = '2509.16117'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'DiffusionNFT: Online Diffusion Reinforcement with Forward Process',
    'https://github.com/NVlabs/DiffusionNFT',
    NULL,
    '[DiffusionNFT: Online Diffusion Reinforcement with Forward Process](/paper/2509.16117)'
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
WHERE slug = 'diffusionnft' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'diffusionnft' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 114 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE diffusionnft_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'diffusionnft'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        47016, 52099, 53384, 53934, 54698, 55089, 55095, 55322, 55698, 55903, 55912, 56133,
        56451, 56517, 56548, 56651, 56653, 56704, 56971, 57105, 57308, 57489, 57537, 57626,
        57631, 57781, 57957, 58214, 58629, 58804, 58870, 59406, 59481, 60090, 60377, 60649,
        60765, 62730, 63755, 64171, 64691, 64906, 66721, 67398, 82847, 82850, 82908, 82967,
        82977, 83182, 83189, 83194, 83205, 83209, 83367, 83684, 83751, 83767, 83773, 83857,
        85536, 85676, 94496, 95076, 98133, 98194, 98420, 98681, 98812, 98913, 98914, 99208,
        99533, 101478, 101595, 102118, 102609, 103960, 104440, 104591, 104818, 105985, 106059, 108648,
        108694, 109520, 109758, 109776, 109817, 113801, 113933, 114019, 114212, 118366, 118372, 118401,
        118468, 119456, 122211, 122340, 122496, 122518, 122549, 122947, 122948, 122969, 123256, 123393,
        123437, 123477, 123498, 123558, 123559, 123594
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'diffusionnft citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM diffusionnft_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING diffusionnft_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 12 local citers name the method in title or abstract.
CREATE TEMP TABLE diffusionnft_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'diffusionnft'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        53683, 56134, 56904, 57779, 83524, 85644, 99559, 104043, 122555, 122815, 123056, 123137
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM diffusionnft_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM diffusionnft_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 14 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE diffusionnft_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'diffusionnft'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        53683, 56134, 56904, 57779, 82871, 83524, 85644, 99559, 104043, 109713, 122555, 122815,
        123056, 123137
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM diffusionnft_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM diffusionnft_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
