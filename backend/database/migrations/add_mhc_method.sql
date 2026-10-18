-- Add mHC, introduced in arXiv 2512.24880.
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
    'mhc',
    'mHC',
    'Manifold-Constrained Hyper-Connections (mHC)',
    'Manifold-Constrained Hyper-Connections (mHC) is a residual connection design from DeepSeek that stabilizes [Hyper-Connections](/methods/hyper-connections) (HC) at scale. HC widens the residual stream into n parallel streams mixed by learnable matrices, which improves performance but breaks the identity mapping of the standard [residual connection](/methods/residual-block), causing training instability, poor scalability and memory access overhead. mHC projects each residual mixing matrix onto the Birkhoff polytope of doubly stochastic matrices with the Sinkhorn-Knopp algorithm, so rows and columns sum to one, signal norms are preserved and the composite mapping across layers stays doubly stochastic. Together with kernel fusion, recomputation and communication overlapping, this keeps the extra cost low: in-house training reports only a 6.7% time overhead at expansion rate n = 4. Experiments on [Mixture-of-Experts](/methods/mixture-of-experts) models up to 27B parameters show stable training and better scalability than HC. mHC is used in DeepSeek-V4 and has inspired variants such as mHC-lite and KromHC.',
    'mHC, manifold-constrained hyper-connection, manifold constrained hyper-connection',
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
        WHERE arxiv_id = '2512.24880'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'mHC: Manifold-Constrained Hyper-Connections',
    NULL,
    NULL,
    '[mHC: Manifold-Constrained Hyper-Connections](/paper/2512.24880)'
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
WHERE slug = 'mhc' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'mhc' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 24 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE mhc_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mhc'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        43136, 55075, 55748, 55884, 56513, 56730, 56731, 57644, 59564, 61013, 61197, 83683,
        99239, 100461, 100740, 101490, 102638, 105937, 106325, 113806, 117884, 122351, 122399, 122660
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'mhc citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM mhc_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING mhc_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 10 local citers name the method in title or abstract.
CREATE TEMP TABLE mhc_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mhc'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        55597, 55893, 59068, 60456, 62199, 63085, 83400, 104300, 122333, 123187
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mhc_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM mhc_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 16 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE mhc_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'mhc'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        55597, 55893, 57889, 59068, 59340, 60456, 62199, 62729, 63085, 83400, 98780, 104300,
        109015, 109745, 122333, 123187
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mhc_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM mhc_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
