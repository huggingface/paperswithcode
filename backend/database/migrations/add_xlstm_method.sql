-- Add xLSTM, introduced in arXiv 2405.04517.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url, image_url, image_credit
)
VALUES (
    'xlstm',
    'xLSTM',
    'Extended Long Short-Term Memory (xLSTM)',
    'xLSTM revisits the [LSTM](/methods/lstm) with two changes to scale it to billions of parameters and compete with Transformers and state-space models in language modeling. Exponential gating with normalization and stabilization replaces the sigmoid gates, and two new cells extend memory: sLSTM keeps a scalar memory with new memory mixing, while mLSTM uses a matrix memory with a covariance update rule that can be trained in parallel. Residually stacked blocks of these cells form xLSTM architectures with linear-time inference and constant memory per token.',
    'xLSTM, extended LSTM, extended long short-term memory',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2024,
    (SELECT id FROM papers WHERE arxiv_id = '2405.04517' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'xLSTM: Extended Long Short-Term Memory',
    'https://github.com/NX-AI/xlstm',
    NULL,
    '[xLSTM: Extended Long Short-Term Memory](/paper/2405.04517)'
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

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'xlstm' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'xlstm' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 133 local citers cite the source without naming the method in title or abstract; exclude them so the hourly reference backfill does not link them.
CREATE TEMP TABLE xlstm_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'xlstm'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        24607, 29214, 30160, 30239, 31150, 31715, 32129, 32636, 33410, 33575, 34212, 34500,
        34801, 34961, 35424, 35979, 36289, 36546, 37185, 37628, 37947, 38095, 38171, 38180,
        38420, 38684, 40166, 40378, 40674, 41231, 41327, 41397, 41864, 41900, 42370, 42371,
        43031, 43345, 44057, 44201, 44207, 44474, 44579, 44772, 45205, 45362, 45389, 45566,
        46964, 46980, 47404, 47844, 48060, 49453, 49974, 50609, 50715, 50884, 51066, 51777,
        51934, 53079, 53320, 53451, 55076, 55712, 56264, 56612, 56613, 58259, 59401, 60473,
        60841, 60971, 61076, 61818, 62375, 63858, 64727, 65462, 65536, 65613, 65676, 65989,
        69838, 70046, 70259, 70471, 70710, 70874, 71326, 71405, 71476, 72432, 72802, 73298,
        74102, 74524, 75122, 75778, 76078, 76757, 76791, 82940, 82990, 83013, 83256, 83512,
        83730, 86000, 86599, 87188, 87413, 87429, 89805, 91472, 91548, 92473, 93679, 94245,
        95916, 98588, 98699, 101148, 101265, 101529, 102544, 102587, 106012, 109187, 122661, 123362,
        123521
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'xlstm citation review 2026-10-22: cites the source without naming the method in title or abstract'
FROM xlstm_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING xlstm_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 23 local citers name the method in title or abstract.
CREATE TEMP TABLE xlstm_cited ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'xlstm'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        33988, 34628, 35210, 39354, 39705, 44737, 45992, 46266, 50141, 51089, 51612, 56732,
        58579, 67096, 68462, 73996, 76497, 76537, 85722, 93153, 93252, 98212, 103807
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM xlstm_cited x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM xlstm_cited x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 33 papers match the method keywords (same matcher as the daily keyword backfill).
CREATE TEMP TABLE xlstm_keyword ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'xlstm'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        32445, 33988, 34628, 35210, 39354, 39705, 41991, 42716, 43493, 44737, 45992, 46266,
        46683, 50141, 51089, 51612, 56732, 58038, 58579, 67096, 67334, 67467, 68462, 73996,
        76497, 76537, 85722, 85799, 93153, 93252, 98212, 103807, 123808
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM xlstm_keyword x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM xlstm_keyword x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
