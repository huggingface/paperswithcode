-- Add LightGCN method, introduced in arXiv 2002.02126. The source paper
-- gets the source evidence row (Introduced banner); citers are linked by
-- link_papers_by_source_citations.py and the hourly reference backfill.

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
    'lightgcn',
    'LightGCN',
    'LightGCN',
    'LightGCN is a simplified graph convolution network for collaborative filtering. Ablating NGCF, the authors found that the feature transformation and nonlinear activation inherited from [GCN](/methods/gcn) contribute little to recommendation and make training harder, so LightGCN keeps only neighborhood aggregation: user and item ID embeddings are propagated over the user-item interaction graph with symmetric degree normalization, and the final representation is a weighted sum of the embeddings from every layer. Trained with the Bayesian personalized ranking (BPR) loss and with the ID embeddings as its only parameters, LightGCN is easy to train and reported about 16% average relative improvement over NGCF. It is a standard strong baseline for graph-based recommendation.',
    'LightGCN',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2020,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2002.02126'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'LightGCN: Simplifying and Powering Graph Convolution Network for Recommendation',
    'https://github.com/kuandeng/LightGCN',
    NULL,
    '[LightGCN: Simplifying and Powering Graph Convolution Network for Recommendation](/paper/2002.02126)'
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
SELECT source_paper_id, id
FROM methods
WHERE slug = 'lightgcn'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'lightgcn'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 214 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention LightGCN are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE lightgcn_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lightgcn'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        4130, 4931, 5150, 5764, 5777, 6345, 8425, 8948, 9060, 9406, 9774, 10729,
        10830, 11182, 11323, 11850, 11873, 12537, 13142, 13735, 14522, 14607, 14774, 15084,
        15219, 15330, 15411, 15527, 16562, 16681, 16929, 16933, 16943, 18012, 18916, 19129,
        19596, 19850, 20185, 21188, 21530, 22169, 22249, 22442, 22485, 22544, 22710, 22849,
        22896, 24298, 24766, 24938, 25213, 25262, 25328, 26491, 26802, 27756, 27952, 28293,
        28945, 30465, 31220, 31658, 31681, 31888, 33499, 33924, 34262, 34508, 35908, 37351,
        37526, 38785, 39138, 39374, 39481, 39831, 42069, 42216, 42475, 43496, 44307, 44659,
        45342, 45360, 45526, 47206, 47835, 48082, 48517, 49525, 51685, 52159, 52427, 52730,
        52910, 54346, 54347, 55754, 56105, 60132, 60324, 60353, 60764, 60807, 60972, 61492,
        61595, 61962, 62132, 62145, 62545, 63117, 63183, 63315, 63711, 64757, 67815, 68539,
        69199, 69990, 70023, 70060, 70253, 71043, 71215, 71892, 71968, 72110, 72327, 72566,
        73646, 74620, 74699, 74792, 74802, 75284, 75595, 75861, 76170, 76386, 77146, 77201,
        77366, 77567, 78466, 78930, 79268, 79756, 79877, 80209, 80311, 80620, 80668, 80689,
        80724, 84608, 85738, 86756, 87156, 88664, 88889, 88962, 89882, 91318, 91326, 91363,
        92437, 92610, 93456, 93508, 93677, 93848, 94333, 94366, 95112, 99346, 99833, 100183,
        100344, 100833, 101175, 102253, 103023, 103187, 103680, 103739, 103934, 103935, 106081, 106523,
        106553, 106694, 107064, 107302, 107508, 107792, 107979, 107980, 108266, 108428, 108600, 108601,
        108655, 109477, 110544, 119611, 122485, 123280
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'lightgcn citation review 2026-10-15: cites the source paper without using the method'
FROM lightgcn_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING lightgcn_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING lightgcn_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
