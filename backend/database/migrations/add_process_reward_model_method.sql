-- Add Process Reward Model (no single introducing paper).
-- Added 2026-10-18 from a scan of methods named by many recent papers but
-- missing from the catalog.

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
    'process-reward-model',
    'Process Reward Model',
    'Process Reward Model (PRM)',
    'A process reward model (PRM) is a [reward model](/methods/reward-model) that scores each intermediate step of a model''s reasoning, rather than only the final answer as an outcome reward model (ORM) does. Given a problem and a step-by-step solution, a PRM predicts whether each step is correct, and a solution-level score is typically the product or minimum of the step scores. [Uesato et al.](/paper/2211.14275) compared process- and outcome-based supervision on GSM8K and found that process supervision, or learned reward models that emulate it, was needed to reduce reasoning errors in solutions with correct final answers. [Lightman et al.](/paper/2305.20050) scaled the idea to MATH: their process-supervised model solved 78% of a representative MATH test subset, clearly ahead of outcome supervision, and they released PRM800K, 800,000 step-level human labels. [Math-Shepherd](/paper/2312.08935) replaced human step labels with automatically constructed ones. PRMs rerank samples in [Best-of-N](/methods/best-of-n), guide step-level search for [test-time scaling](/methods/test-time-scaling), and supply dense rewards for reinforcement learning.',
    'process reward model, process reward modeling, process-supervised reward model, process-based reward model, process-level reward model, step-level reward model',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2022,
    NULL,
    'https://openai.com/index/improving-mathematical-reasoning-with-process-supervision/',
    'Improving mathematical reasoning with process supervision',
    'https://github.com/openai/prm800k',
    NULL,
    '[Let''s Verify Step by Step](/paper/2305.20050)'
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

-- 193 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE process_reward_model_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'process-reward-model'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        22017, 23155, 24782, 32402, 32651, 38262, 38374, 38517, 38858, 39040, 40510, 40872,
        41236, 41375, 41593, 41896, 41985, 41989, 42419, 42535, 42615, 42793, 42819, 43088,
        43474, 43570, 43598, 43649, 43670, 43805, 43948, 44208, 44342, 44471, 44568, 44602,
        44640, 44939, 45082, 45552, 46033, 46196, 46275, 46778, 46840, 46918, 47093, 47124,
        47692, 48008, 48086, 48174, 48845, 49063, 49280, 49350, 49513, 49645, 49710, 49764,
        49837, 49871, 50591, 50725, 51071, 51084, 51393, 51630, 52170, 52451, 52538, 52640,
        52734, 52878, 52928, 53071, 53115, 53264, 53456, 53640, 53675, 53941, 54118, 54338,
        54638, 55026, 55393, 55403, 55610, 55759, 56244, 56427, 56821, 57388, 57418, 57448,
        57738, 57754, 58071, 58152, 58410, 58822, 59023, 59291, 60156, 60443, 61258, 61765,
        61793, 62018, 62909, 64409, 65066, 66024, 66488, 66641, 66887, 67176, 67554, 67661,
        67795, 67819, 67928, 67947, 68189, 68681, 69086, 69118, 70150, 70187, 70279, 70311,
        70336, 70494, 70810, 71355, 72088, 72299, 72541, 72762, 72912, 73274, 74764, 75013,
        82879, 82919, 83447, 83595, 84327, 84463, 88803, 89623, 92502, 92696, 93481, 93797,
        93827, 93894, 94927, 98887, 99603, 100256, 100661, 100733, 101250, 101536, 101975, 102114,
        102314, 102471, 103004, 103133, 103166, 103344, 103545, 103668, 106047, 106349, 106522, 107613,
        107710, 108262, 108410, 108553, 109288, 110244, 110551, 113885, 118738, 118755, 121624, 122408,
        123051
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM process_reward_model_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM process_reward_model_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
