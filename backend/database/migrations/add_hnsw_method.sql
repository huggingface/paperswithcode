-- Add HNSW, introduced in arXiv 1603.09320.
-- Added 2026-10-20 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.
-- The source paper gets the source evidence row (Introduced banner).

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
    'hnsw',
    'HNSW',
    'Hierarchical Navigable Small World (HNSW)',
    'Hierarchical Navigable Small World (HNSW) is a graph-based index for approximate nearest neighbor search. It builds a multi-layer proximity graph in which upper layers hold exponentially fewer nodes with long links, so a query greedily descends from coarse to fine layers and reaches its neighbors in roughly logarithmic time. HNSW offers a strong recall-latency trade-off and is the default index in vector databases and libraries such as hnswlib, FAISS, Milvus and pgvector, which makes it a core component of dense [retrieval](/tasks/retrieval) and retrieval-augmented generation systems.',
    'HNSW, hierarchical navigable small world',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2016,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1603.09320'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs',
    'https://github.com/nmslib/hnswlib',
    NULL,
    '[Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs](/paper/1603.09320)'
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
WHERE slug = 'hnsw' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'hnsw' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 242 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE hnsw_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'hnsw'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        2142, 2258, 3340, 3613, 4215, 4345, 4405, 5036, 5160, 5761, 5842, 6341,
        6880, 7028, 7230, 7696, 8789, 9013, 9064, 9149, 9204, 9380, 9698, 9721,
        9722, 9736, 10951, 10983, 11123, 11129, 11646, 11980, 12336, 12614, 13166, 13438,
        13871, 14022, 14451, 14454, 14590, 14687, 15038, 15605, 15843, 16394, 16630, 16899,
        17443, 17603, 18948, 19022, 19557, 20489, 20659, 20834, 21816, 21872, 22147, 22590,
        23069, 23787, 24021, 24434, 24532, 25235, 25803, 25851, 26148, 26271, 26545, 26613,
        26698, 26899, 27381, 28841, 30084, 30157, 30445, 30483, 30549, 30687, 30718, 30926,
        30999, 34238, 34871, 35234, 35361, 35391, 36944, 37190, 38317, 39325, 39505, 39708,
        39718, 40123, 40864, 41105, 41260, 41403, 41945, 43730, 43954, 44069, 44237, 45216,
        45534, 46090, 46743, 46923, 47097, 47660, 47759, 47849, 48072, 48424, 48449, 48875,
        49338, 49597, 50827, 50842, 52179, 52891, 52906, 53609, 54227, 54615, 54799, 55061,
        55673, 55815, 56177, 57723, 57986, 58273, 58890, 59018, 59478, 60551, 60572, 61203,
        61211, 61288, 61866, 62181, 62499, 62582, 62674, 62679, 63884, 64025, 64844, 64911,
        65254, 65489, 65858, 66264, 67079, 67379, 67850, 68365, 68806, 68938, 70283, 70573,
        70702, 70739, 71043, 71376, 72906, 74119, 74149, 74337, 74417, 74422, 74691, 74943,
        75187, 75950, 76027, 76272, 76279, 76378, 76951, 77243, 77352, 78128, 79528, 81241,
        82830, 82927, 83578, 83888, 85640, 87314, 88663, 88763, 88893, 90634, 91124, 91407,
        91964, 92050, 93335, 93790, 93855, 98155, 98156, 98655, 98970, 99101, 99346, 100197,
        100377, 100552, 100614, 100700, 100817, 101202, 101927, 102126, 102371, 102496, 102749, 103520,
        105858, 106572, 106671, 107912, 108705, 110795, 110899, 110920, 112465, 112797, 112869, 113955,
        117401, 120314
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'hnsw citation review 2026-10-20: cites the source without naming the method in title or abstract'
FROM hnsw_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING hnsw_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 14 local citers name the method in title or abstract.
CREATE TEMP TABLE hnsw_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'hnsw'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        19887, 31876, 48921, 58691, 62170, 63633, 65662, 67865, 71867, 87007, 92957, 93823,
        100181, 111591
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM hnsw_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM hnsw_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 14 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE hnsw_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'hnsw'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        19887, 31876, 48921, 58691, 62170, 63633, 65662, 67865, 71867, 87007, 92957, 93823,
        100181, 111591
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM hnsw_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM hnsw_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
