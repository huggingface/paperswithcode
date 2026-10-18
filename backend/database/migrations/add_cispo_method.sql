-- Add CISPO, introduced in arXiv 2506.13585.
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
    'cispo',
    'CISPO',
    'Clipped IS-weight Policy Optimization (CISPO)',
    'CISPO (Clipped IS-weight Policy Optimization) is a reinforcement learning algorithm for large language models introduced with the MiniMax-M1 reasoning model. In [PPO](/methods/ppo) and [GRPO](/methods/grpo), clipping the token-level update removes the gradient of tokens whose probability ratio moves too far; MiniMax found these were often rare, low-probability reflective tokens such as ''However'' or ''Wait'' that act as forks in reasoning, so they stopped contributing after the first on-policy update. CISPO instead starts from a [REINFORCE](/methods/reinforce) objective with off-policy correction and clips only the importance-sampling weight, which is detached with a stop-gradient, so every token keeps a bounded gradient contribution. It keeps GRPO''s group-relative advantage and a token-level loss. On Qwen2.5-32B-base, CISPO beats GRPO and [DAPO](/methods/dapo) on AIME 2024 at equal training steps and matches DAPO with 50% of the steps. Combined with hybrid lightning attention, it let MiniMax-M1''s full RL training run on 512 H800 GPUs finish in three weeks.',
    'CISPO, Clipped IS-weight Policy Optimization',
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
        WHERE arxiv_id = '2506.13585'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'MiniMax-M1: Scaling Test-Time Compute Efficiently with Lightning Attention',
    'https://github.com/MiniMax-AI/MiniMax-M1',
    NULL,
    '[MiniMax-M1: Scaling Test-Time Compute Efficiently with Lightning Attention](/paper/2506.13585)'
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
WHERE slug = 'cispo' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'cispo' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 139 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE cispo_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'cispo'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        46671, 52067, 52284, 52303, 52319, 52390, 52463, 52563, 52630, 52656, 52783, 53074,
        53167, 53231, 53272, 53369, 53744, 53831, 53992, 54141, 54225, 54330, 54444, 54687,
        54977, 55554, 55767, 55831, 55832, 55864, 55931, 56045, 56167, 56222, 56261, 56267,
        56282, 56301, 56336, 56469, 56597, 56745, 56825, 57469, 57506, 57722, 57796, 57855,
        58332, 58667, 58782, 58822, 59295, 59594, 59640, 59778, 60307, 60611, 60806, 61013,
        61074, 61263, 61403, 61687, 61711, 61838, 62022, 62242, 64360, 64495, 65346, 65817,
        66495, 66731, 66821, 66824, 67532, 69027, 69346, 69372, 69818, 70251, 70874, 71184,
        82877, 82909, 83021, 83120, 83134, 83138, 83206, 83248, 83405, 83726, 83934, 84105,
        93775, 94758, 94954, 98039, 98135, 98290, 98325, 98511, 98518, 98702, 99077, 99536,
        99559, 99725, 99967, 99984, 100134, 100646, 101618, 102353, 102716, 103204, 103832, 104387,
        104486, 104509, 104517, 106105, 106122, 106224, 106234, 106257, 108064, 108433, 109064, 109756,
        114225, 114236, 122131, 122139, 122246, 122347, 123137
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'cispo citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM cispo_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING cispo_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 1 local citers name the method in title or abstract.
CREATE TEMP TABLE cispo_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'cispo'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        55853
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM cispo_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM cispo_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 4 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE cispo_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'cispo'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        55853, 61566, 63984, 123410
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM cispo_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM cispo_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
