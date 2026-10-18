-- Add Tool-Integrated Reasoning, introduced in arXiv 2309.17452.
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
    'tool-integrated-reasoning',
    'Tool-Integrated Reasoning',
    'Tool-Integrated Reasoning (TIR)',
    'Tool-integrated reasoning (TIR) is a reasoning format in which a language model interleaves natural-language rationales with calls to external tools, typically code executed in an interpreter or a symbolic solver, and reads the tool output before continuing to reason. It combines the semantic and planning strengths of [chain-of-thought](/methods/chain-of-thought-cot) reasoning with the exact computation of program-based approaches such as [PAL](/paper/2211.10435) and [Program of Thoughts](/paper/2211.12588). The term was coined by ToRA, a series of Tool-integrated Reasoning Agents for mathematical problem solving, trained by imitation learning on GPT-4-generated interactive tool-use trajectories and refined with output space shaping. ToRA models outperformed open-source models on 10 mathematical reasoning datasets by 13-19% absolute on average; ToRA-7B reached 44.6% on MATH and ToRA-Code-34B was the first open-source model above 50%. TIR has become a standard mode for reasoning models and is increasingly learned with reinforcement learning, as in [ToRL](/paper/2503.23383), building on [function calling](/methods/function-calling) and agent loops such as [ReAct](/methods/react).',
    'tool-integrated reasoning, tool integrated reasoning, tool-integrated reinforcement learning, tool-integrated rl',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2309.17452'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'ToRA: A Tool-Integrated Reasoning Agent for Mathematical Problem Solving',
    'https://github.com/microsoft/ToRA',
    NULL,
    '[ToRA: A Tool-Integrated Reasoning Agent for Mathematical Problem Solving](/paper/2309.17452)'
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
WHERE slug = 'tool-integrated-reasoning' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'tool-integrated-reasoning' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 175 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE tool_integrated_reasoning_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'tool-integrated-reasoning'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        19046, 22061, 23400, 23530, 23551, 24704, 24782, 24808, 25271, 25518, 25663, 25809,
        25848, 25919, 26114, 26841, 27063, 27369, 27377, 27673, 27846, 27966, 28165, 28194,
        28383, 28420, 28530, 28861, 29126, 29583, 29982, 30244, 30409, 30523, 30787, 31091,
        31577, 32015, 32280, 32401, 32634, 33028, 33147, 33232, 33354, 33379, 33757, 33780,
        33914, 34519, 34658, 34923, 35310, 36134, 36564, 37068, 37141, 37665, 37680, 37683,
        38028, 38125, 38238, 38274, 38275, 38325, 38452, 38716, 38860, 39041, 39123, 40327,
        40640, 41593, 42048, 42272, 42611, 42615, 42695, 43007, 43103, 43158, 43181, 44224,
        44342, 45104, 45566, 46952, 46956, 47045, 47057, 47071, 47252, 47349, 47733, 47914,
        47917, 48336, 48491, 48845, 48882, 48896, 48898, 48965, 49434, 49537, 49820, 49858,
        50026, 50174, 50280, 50284, 50946, 51070, 51161, 51485, 51831, 52073, 52602, 52635,
        52980, 53270, 53348, 53462, 53733, 54106, 54149, 54706, 55872, 56403, 58137, 58238,
        60072, 61582, 62242, 62259, 62339, 62446, 63157, 63379, 63981, 65986, 66047, 66453,
        66520, 66792, 69520, 69541, 69806, 71474, 71742, 71845, 72804, 75156, 77169, 77399,
        83572, 83844, 86493, 86668, 86831, 88642, 89278, 91683, 92113, 98325, 100246, 101581,
        104527, 107487, 109802, 110071, 110228, 122328, 123381
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'tool-integrated-reasoning citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM tool_integrated_reasoning_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING tool_integrated_reasoning_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 14 local citers name the method in title or abstract.
CREATE TEMP TABLE tool_integrated_reasoning_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'tool-integrated-reasoning'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        47974, 49404, 52020, 52840, 53028, 54352, 54897, 61540, 61630, 63201, 67484, 67603,
        83239, 102427
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM tool_integrated_reasoning_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM tool_integrated_reasoning_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 62 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE tool_integrated_reasoning_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'tool-integrated-reasoning'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        37042, 44398, 47011, 47974, 48088, 49404, 50960, 51962, 52020, 52202, 52460, 52533,
        52630, 52840, 53028, 53265, 53978, 54279, 54352, 54368, 54470, 54897, 55124, 55234,
        55324, 55469, 56331, 56918, 56925, 57277, 58299, 60846, 60946, 61109, 61442, 61540,
        61630, 61925, 62277, 62647, 62734, 62876, 63201, 63657, 63984, 64860, 64975, 65816,
        66506, 67484, 67603, 68237, 70587, 83239, 86232, 97953, 102427, 103019, 108651, 118690,
        119432, 122937
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM tool_integrated_reasoning_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM tool_integrated_reasoning_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
