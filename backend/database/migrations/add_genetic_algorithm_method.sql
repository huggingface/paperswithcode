-- Add Genetic Algorithm (no introducing paper in the catalog; external reference).
-- Added 2026-10-20 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

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
    'genetic-algorithm',
    'Genetic Algorithm',
    'Genetic Algorithm (GA)',
    'A genetic algorithm (GA) is an evolutionary optimization method that evolves a population of candidate solutions encoded as chromosomes. Each generation evaluates fitness, selects parents in proportion to fitness, and produces offspring through crossover and mutation, so good building blocks spread while diversity is maintained. Formalized by John Holland in the 1970s, GAs are used for combinatorial and black-box optimization, [neural architecture search](/methods/neural-architecture-search) and program search; [particle swarm optimization](/methods/particle-swarm-optimization) and LLM-driven evolutionary search such as [AlphaEvolve](/methods/alphaevolve) are related population-based approaches.',
    'genetic algorithm, genetic algorithms',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    1975,
    NULL,
    'https://mitpress.mit.edu/9780262581110/adaptation-in-natural-and-artificial-systems/',
    'Adaptation in Natural and Artificial Systems (Holland, 1975)',
    NULL,
    NULL,
    'Illustration by Papers with Code'
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

-- 103 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE genetic_algorithm_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'genetic-algorithm'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        1021, 1570, 2643, 2924, 3561, 3784, 3985, 4087, 4479, 5627, 5964, 6128,
        7425, 7720, 7925, 8064, 9095, 10088, 10395, 13540, 13643, 14903, 17009, 18205,
        19259, 20731, 21350, 21518, 23311, 23393, 25148, 25637, 31086, 31937, 35242, 37669,
        38839, 45068, 46843, 47422, 47486, 50941, 51272, 52621, 54210, 54921, 55081, 62446,
        62694, 64089, 64412, 66114, 66347, 67296, 68507, 72466, 73106, 73577, 74042, 74582,
        74601, 76391, 76864, 77246, 78138, 79542, 79748, 79787, 80218, 80320, 80497, 80996,
        81084, 81119, 81238, 81386, 81490, 81909, 86009, 86171, 86349, 88591, 89088, 89377,
        89756, 92763, 95627, 95699, 95757, 97674, 97779, 99361, 99511, 100329, 107716, 107798,
        108387, 109785, 110354, 110443, 110796, 115053, 121995
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM genetic_algorithm_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM genetic_algorithm_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
