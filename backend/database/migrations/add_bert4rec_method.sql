-- Add BERT4Rec, introduced in arXiv 1904.06690.
-- Added 2026-10-21 because production chat users looked it up with
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
    'bert4rec',
    'BERT4Rec',
    'BERT4Rec: Sequential Recommendation with Bidirectional Encoder Representations from Transformer',
    'BERT4Rec is a sequential recommendation model that applies a bidirectional Transformer, as in [BERT](/methods/bert), to user behavior sequences. Instead of predicting the next item left to right, it is trained with a Cloze objective that masks random items in the sequence and predicts them from context on both sides. This lets each item representation use the full history and outperformed unidirectional models such as SASRec on several recommendation datasets.',
    'BERT4Rec',
    (
        SELECT id
        FROM areas
        WHERE name = 'Other'
        LIMIT 1
    ),
    2019,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1904.06690'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'BERT4Rec: Sequential Recommendation with Bidirectional Encoder Representations from Transformer',
    'https://github.com/FeiSun/BERT4Rec',
    NULL,
    '[BERT4Rec: Sequential Recommendation with Bidirectional Encoder Representations from Transformer](/paper/1904.06690)'
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
WHERE slug = 'bert4rec' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'bert4rec' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 148 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE bert4rec_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bert4rec'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        33924, 34500, 35481, 35956, 36381, 36467, 36873, 36938, 37081, 37206, 37301, 37526,
        39138, 39397, 40316, 40398, 41035, 41397, 42021, 42270, 43919, 44134, 44569, 44581,
        44595, 44659, 44671, 45056, 45066, 45526, 46948, 47689, 48236, 50006, 50716, 51945,
        52812, 52891, 53340, 54204, 55129, 55676, 56002, 56039, 56105, 56121, 56147, 56243,
        56297, 56900, 58148, 59208, 59363, 59973, 60764, 60785, 60807, 60942, 61317, 61962,
        61998, 62098, 62132, 62145, 62902, 63163, 63315, 63665, 63850, 64493, 64566, 65648,
        65950, 66264, 66472, 66481, 66517, 66678, 67747, 69378, 69380, 69463, 70508, 70667,
        71043, 71346, 71375, 71892, 71968, 72110, 72327, 72590, 73072, 73221, 73548, 74082,
        74229, 74507, 74691, 75260, 75861, 75886, 76132, 76219, 76294, 76546, 76582, 76886,
        83843, 85738, 86787, 89121, 91318, 91363, 93373, 94547, 98434, 99346, 99793, 102887,
        102942, 106081, 106583, 106660, 106962, 107064, 107431, 107616, 107772, 107911, 107938, 107972,
        107979, 107980, 108033, 108180, 108266, 108428, 109088, 109694, 110303, 111031, 114180, 120239,
        122485, 123280, 123354, 123364
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'bert4rec citation review 2026-10-21: cites the source without naming the method in title or abstract'
FROM bert4rec_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING bert4rec_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 1 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE bert4rec_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bert4rec'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        95112
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM bert4rec_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM bert4rec_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
