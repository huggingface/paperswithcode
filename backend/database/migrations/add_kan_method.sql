-- Add KAN, introduced in arXiv 2404.19756.
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
    'kan',
    'KAN',
    'Kolmogorov-Arnold Network (KAN)',
    'Kolmogorov-Arnold Networks (KANs) are neural networks inspired by the Kolmogorov-Arnold representation theorem and proposed as an alternative to multi-layer perceptrons ([MLP](/methods/feedforward-network)). Where an MLP applies fixed activation functions on nodes and learns linear weights on edges, a KAN has no linear weights at all: every edge carries a learnable univariate function parametrized as a spline, and nodes simply sum their inputs. Stacking such layers gives deep KANs whose spline grids can be refined after training (grid extension) and whose learned functions can be pruned and converted to symbolic formulas. The original paper reports that much smaller KANs match or beat much larger MLPs on data fitting and PDE solving, that KANs exhibit faster neural scaling laws, and that their visualizable activations helped (re)discover mathematical and physical laws. KANs have since been plugged into convolutional, graph, time-series and [Transformer](/methods/transformer) architectures, and were extended in [KAN 2.0](/paper/2408.10205).',
    'Kolmogorov-Arnold network, Kolmogorov-Arnold networks, kolmogorov-arnold network, KAN',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2024,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2404.19756'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'KAN: Kolmogorov-Arnold Networks',
    'https://github.com/KindXiaoming/pykan',
    NULL,
    '[KAN: Kolmogorov-Arnold Networks](/paper/2404.19756)'
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
WHERE slug = 'kan' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'kan' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 37 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE kan_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'kan'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        31273, 34503, 35988, 36963, 37269, 37784, 37902, 37906, 39014, 43277, 43559, 46878,
        53276, 58545, 63582, 63622, 64269, 68574, 70406, 71102, 75043, 84367, 84684, 85014,
        85722, 86008, 86037, 86442, 87332, 90791, 90904, 91361, 92690, 93660, 104463, 105664,
        122556
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'kan citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM kan_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING kan_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 53 local citers name the method in title or abstract.
CREATE TEMP TABLE kan_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'kan'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        31223, 33666, 36420, 36882, 36951, 37217, 37718, 37832, 45060, 45659, 46078, 49095,
        49828, 52127, 54593, 58407, 59092, 61492, 63900, 66067, 67039, 67595, 69634, 73106,
        73617, 74088, 76104, 76136, 76564, 76979, 82898, 89617, 90228, 90419, 90819, 91808,
        91883, 91894, 91957, 93043, 93186, 93501, 94933, 100398, 100546, 105136, 107125, 109006,
        109226, 109228, 112028, 112117, 117330
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM kan_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM kan_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 109 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE kan_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'kan'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        31223, 32241, 33053, 33179, 33306, 33666, 33939, 35123, 35809, 35878, 36420, 36882,
        36951, 37217, 37710, 37718, 37832, 38293, 43900, 43999, 44580, 45060, 45300, 45659,
        46078, 49095, 49828, 52127, 52848, 54593, 58407, 59092, 60229, 60330, 61492, 63900,
        64675, 66067, 67039, 67595, 69634, 70205, 73106, 73617, 73670, 74088, 75748, 76104,
        76136, 76564, 76684, 76761, 76979, 78969, 82898, 88697, 89361, 89617, 90228, 90419,
        90819, 91581, 91808, 91883, 91894, 91957, 92302, 93043, 93186, 93501, 94398, 94933,
        95188, 95588, 96155, 96258, 99100, 100398, 100546, 101036, 101593, 101703, 104087, 105083,
        105136, 105256, 105294, 105297, 105327, 105584, 105609, 105810, 106787, 106947, 107057, 107125,
        107814, 108010, 108767, 109006, 109226, 109228, 109696, 112028, 112117, 117330, 119985, 120054,
        120648
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM kan_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM kan_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
