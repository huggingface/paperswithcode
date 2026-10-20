-- Add Particle Swarm Optimization (no introducing paper in the catalog; external reference).
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
    'particle-swarm-optimization',
    'Particle Swarm Optimization',
    'Particle Swarm Optimization (PSO)',
    'Particle Swarm Optimization (PSO) is a population-based, derivative-free optimizer inspired by bird flocking. Each particle has a position and a velocity in the search space; at every step its velocity is pulled toward its own best position so far and the best position found by the swarm (or its neighbourhood), with an inertia term balancing exploration and exploitation. Proposed by Kennedy and Eberhart (1995), PSO is widely used for black-box and hyperparameter optimization, feature selection, and engineering design, often alongside the [genetic algorithm](/methods/genetic-algorithm).',
    'particle swarm optimization, particle swarm optimisation, particle swarm optimizer',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    1995,
    NULL,
    'https://doi.org/10.1109/ICNN.1995.488968',
    'Particle swarm optimization (Kennedy & Eberhart, ICNN 1995)',
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

-- 23 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE particle_swarm_optimization_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'particle-swarm-optimization'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        2731, 3575, 4087, 6661, 24774, 26806, 41177, 50737, 51265, 64412, 72974, 73432,
        78726, 87151, 95500, 95627, 96950, 97446, 97805, 106943, 111737, 113211, 121215
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM particle_swarm_optimization_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM particle_swarm_optimization_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
