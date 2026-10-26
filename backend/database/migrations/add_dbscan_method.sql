-- Add DBSCAN (no introducing paper in the catalog; external reference).
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url, image_url, image_credit
)
VALUES (
    'dbscan',
    'DBSCAN',
    'Density-Based Spatial Clustering of Applications with Noise (DBSCAN)',
    'DBSCAN is a density-based clustering algorithm that groups points lying in dense regions and marks points in sparse regions as noise. Two parameters define density: a neighborhood radius eps and a minimum number of points minPts. A point with at least minPts neighbors within eps is a core point, clusters grow by chaining core points whose neighborhoods overlap, and everything left over is labeled an outlier. Unlike [k-means clustering](/methods/k-means-clustering) it needs no preset number of clusters and finds clusters of arbitrary shape, but it struggles when cluster densities differ.',
    'DBSCAN, density-based spatial clustering of applications with noise',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    1996,
    NULL,
    'https://www.aaai.org/Papers/KDD/1996/KDD96-037.pdf',
    'A Density-Based Algorithm for Discovering Clusters in Large Spatial Databases with Noise (Ester et al., KDD 1996)',
    NULL,
    NULL,
    'Illustration by Papers with Code'
)
ON CONFLICT (slug) DO UPDATE SET
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

-- 22 papers match the method keywords (same matcher as the daily keyword backfill).
CREATE TEMP TABLE dbscan_keyword ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dbscan'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        720, 4886, 6382, 15016, 39344, 56579, 64473, 70928, 73751, 73799, 76166, 77840,
        79144, 83201, 87801, 91697, 94456, 96953, 104311, 107442, 117721, 118942
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dbscan_keyword x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM dbscan_keyword x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
