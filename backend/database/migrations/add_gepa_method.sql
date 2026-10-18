-- Add GEPA, introduced in arXiv 2507.19457.
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
    'gepa',
    'GEPA',
    'Genetic-Pareto Prompt Optimizer (GEPA)',
    'GEPA (Genetic-Pareto) is a reflective prompt optimizer for compound AI systems built from one or more LLM prompts. Instead of learning from scalar rewards with policy gradients as in [GRPO](/methods/grpo), it uses natural-language reflection. GEPA samples system-level trajectories (reasoning, tool calls and tool outputs), has an LLM reflect on them to diagnose failures, and proposes updated prompts for individual modules. Candidates evolve genetically through reflective mutation and a system-aware merge of modules from different lineages. A Pareto-based selection keeps every candidate that is best on at least one training instance, which keeps the search diverse. Across four tasks GEPA outperforms GRPO by 10% on average and up to 20% while using up to 35× fewer rollouts. It also beats the MIPROv2 optimizer from [DSPy](/paper/2310.03714) by over 10% across two LLMs. GEPA automates [prompt engineering](/methods/prompt-engineering) and also shows promise as an inference-time search strategy for code optimization.',
    'gepa, Genetic-Pareto',
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
        WHERE arxiv_id = '2507.19457'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning',
    'https://github.com/gepa-ai/gepa',
    NULL,
    '[GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning](/paper/2507.19457)'
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
WHERE slug = 'gepa' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'gepa' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 157 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE gepa_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gepa'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        47737, 48871, 52979, 53224, 53493, 53658, 54128, 54139, 54246, 54319, 54408, 54470,
        54851, 54853, 55226, 56128, 56168, 56317, 56377, 56712, 56784, 56863, 56906, 56967,
        57004, 57132, 57178, 57252, 57569, 57680, 58085, 58142, 58330, 59971, 60362, 60545,
        60611, 60634, 60922, 61006, 61052, 61403, 61453, 61528, 61831, 63211, 63380, 63910,
        64389, 64512, 64805, 64990, 65509, 65515, 65715, 65947, 66860, 67775, 68582, 68983,
        69157, 70794, 82955, 83243, 83245, 83296, 83299, 83433, 83466, 83528, 83763, 83791,
        83817, 83846, 83850, 85661, 92557, 92736, 92769, 96617, 98172, 98683, 98808, 98974,
        98998, 99080, 101952, 102542, 102560, 102572, 102961, 104226, 104388, 104507, 105917, 106284,
        106340, 106373, 108697, 108742, 108770, 108921, 108953, 109021, 109057, 109128, 109135, 109531,
        109711, 109712, 109715, 109816, 113743, 113917, 114064, 114077, 114089, 114108, 114193, 114228,
        118712, 118822, 121953, 121971, 122011, 122112, 122137, 122190, 122250, 122260, 122264, 122465,
        122488, 122501, 122553, 122558, 122680, 122707, 122710, 122718, 122799, 122902, 122906, 122933,
        123004, 123049, 123059, 123136, 123196, 123218, 123240, 123254, 123385, 123523, 123554, 123566,
        123595
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'gepa citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM gepa_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING gepa_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 14 local citers name the method in title or abstract.
CREATE TEMP TABLE gepa_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gepa'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        57304, 58044, 58512, 59447, 60202, 60687, 63589, 83001, 83682, 97982, 98137, 98545,
        108809, 123008
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gepa_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM gepa_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 21 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE gepa_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gepa'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        57304, 57387, 57415, 58044, 58512, 59158, 59447, 59499, 60202, 60687, 63589, 83001,
        83494, 83682, 92481, 94413, 97982, 98137, 98545, 108809, 123008
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gepa_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM gepa_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
