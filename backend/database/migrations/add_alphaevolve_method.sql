-- Add AlphaEvolve, introduced in arXiv 2506.13131.
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
    'alphaevolve',
    'AlphaEvolve',
    'AlphaEvolve',
    'AlphaEvolve is an evolutionary coding [agent](/methods/agent) from Google DeepMind that uses [large language models](/methods/large-language-model-llm) to discover and improve algorithms by editing code directly. A user supplies an initial program with marked components to evolve and evaluation code that scores candidates. AlphaEvolve then runs an asynchronous loop: a prompt sampler builds rich prompts from a program database of past solutions, an ensemble of Gemini 2.0 Flash and Gemini 2.0 Pro proposes code diffs, and a pool of evaluators scores the children, which are added back to the database. It extends FunSearch from single functions to whole files and multiple objectives. AlphaEvolve found a procedure to multiply two 4×4 complex-valued matrices with 48 scalar multiplications, the first improvement over Strassen''s algorithm in this setting in 56 years. At Google it produced a data-center scheduling heuristic that recovers on average 0.7% of fleet-wide compute, simplified accelerator circuit designs and sped up Gemini training kernels.',
    'AlphaEvolve',
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
        WHERE arxiv_id = '2506.13131'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'AlphaEvolve: A coding agent for scientific and algorithmic discovery',
    NULL,
    NULL,
    '[AlphaEvolve: A coding agent for scientific and algorithmic discovery](/paper/2506.13131)'
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
WHERE slug = 'alphaevolve' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'alphaevolve' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 259 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE alphaevolve_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'alphaevolve'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        35242, 43393, 46193, 46836, 47334, 47910, 48002, 48944, 49560, 49615, 49702, 49784,
        50174, 50467, 50584, 50600, 50801, 51978, 52403, 52502, 52959, 53063, 53344, 53493,
        53531, 53637, 53658, 53742, 53771, 54074, 54111, 54307, 54496, 54573, 54614, 54851,
        55044, 55093, 55148, 55196, 55286, 55485, 55546, 55554, 55562, 55638, 55812, 55872,
        55895, 55896, 56001, 56181, 56253, 56442, 56459, 56470, 56483, 56597, 56633, 56752,
        56784, 56847, 57004, 57035, 57072, 57077, 57132, 57155, 57178, 57186, 57246, 57502,
        57518, 57530, 57569, 57649, 58226, 58330, 58460, 58512, 58671, 58823, 59503, 59564,
        59625, 59665, 60297, 60362, 60435, 60611, 60634, 60668, 60671, 60885, 60903, 60905,
        61484, 61528, 61551, 61831, 61846, 62276, 62339, 62826, 62916, 63872, 63910, 64203,
        64537, 64629, 65287, 65599, 65644, 66320, 66325, 66721, 67485, 67993, 68582, 69500,
        69638, 69647, 70423, 70500, 70677, 70794, 70989, 71008, 71098, 71642, 71798, 73526,
        74054, 82884, 82911, 82927, 82945, 82955, 83001, 83002, 83181, 83433, 83444, 83533,
        83545, 83745, 83846, 83852, 83881, 88556, 88610, 92497, 92554, 92557, 92633, 92744,
        92838, 93338, 93368, 93390, 93673, 93935, 94233, 94414, 94651, 97965, 98137, 98189,
        98203, 98222, 98240, 98241, 98508, 98537, 98683, 98700, 98715, 98998, 99042, 99049,
        99409, 99569, 99595, 99716, 100357, 100536, 100549, 100592, 100858, 101125, 101345, 101420,
        102169, 102192, 102530, 102568, 102572, 103330, 103439, 103956, 104017, 104226, 104305, 104398,
        104728, 105879, 106045, 106046, 106261, 106284, 106340, 107211, 107849, 108088, 108642, 108790,
        108921, 108953, 109021, 109055, 109057, 109109, 109135, 109145, 109711, 109712, 109715, 113728,
        113795, 113969, 114071, 114099, 114211, 121985, 121995, 122137, 122145, 122213, 122260, 122264,
        122277, 122331, 122354, 122497, 122591, 122707, 122724, 122743, 122906, 123000, 123008, 123049,
        123218, 123260, 123364, 123385, 123414, 123495, 123553
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'alphaevolve citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM alphaevolve_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING alphaevolve_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 18 local citers name the method in title or abstract.
CREATE TEMP TABLE alphaevolve_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'alphaevolve'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        53305, 54178, 54350, 55366, 55614, 56211, 56712, 60202, 63195, 64389, 66347, 68592,
        83494, 95091, 101327, 109382, 109747, 122680
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM alphaevolve_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM alphaevolve_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 25 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE alphaevolve_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'alphaevolve'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        53305, 54113, 54178, 54350, 55366, 55450, 55614, 56211, 56285, 56642, 56712, 60202,
        63195, 64389, 65470, 66347, 68592, 83494, 95091, 101041, 101327, 108809, 109382, 109747,
        122680
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM alphaevolve_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM alphaevolve_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
