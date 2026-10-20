-- Add Iterative Closest Point (no introducing paper in the catalog; external reference).
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
    'iterative-closest-point',
    'Iterative Closest Point',
    'Iterative Closest Point (ICP)',
    'Iterative Closest Point (ICP) is the classic algorithm for rigidly aligning two point clouds or shapes. Starting from an initial pose, it alternates between matching each source point to its closest target point and solving in closed form for the rotation and translation that minimize the distance between the matched pairs, until the error converges. Introduced by Besl and McKay (1992) and concurrently by Chen and Medioni (point-to-plane), ICP is fast but needs a good initialization, so learned and [RANSAC](/methods/ransac)-based global registration is often used to initialize it in point cloud registration, SLAM and 3D reconstruction.',
    'iterative closest point, iterative closest points',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    1992,
    NULL,
    'https://doi.org/10.1109/34.121791',
    'A Method for Registration of 3-D Shapes (Besl & McKay, TPAMI 1992)',
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

-- 19 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE iterative_closest_point_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'iterative-closest-point'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        3893, 19413, 71504, 71735, 73047, 73228, 74449, 74750, 76666, 77748, 95925, 96686,
        96876, 96954, 97542, 97759, 105379, 112857, 121098
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM iterative_closest_point_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM iterative_closest_point_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
