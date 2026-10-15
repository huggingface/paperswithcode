-- Add PatchTST method, introduced in arXiv 2211.14730. The source paper
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
    'patchtst',
    'PatchTST',
    'PatchTST (Patch Time Series Transformer)',
    'PatchTST is a [Transformer](/methods/transformer)-based model for multivariate long-term time series forecasting built on two ideas. Patching segments each series into subseries-level patches that serve as input tokens, which keeps local semantic information, cuts the attention cost quadratically for a given look-back window, and lets the model attend to a much longer history. Channel independence treats every channel as a separate univariate series that shares the same embedding and Transformer weights. PatchTST improved long-term forecasting accuracy over earlier Transformer forecasters, and a masked-patch self-supervised pre-training variant transfers well across datasets. Its "a time series is worth 64 words" patch design was adopted by many later forecasting and time series foundation models.',
    'PatchTST',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2022,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2211.14730'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'A Time Series is Worth 64 Words: Long-term Forecasting with Transformers',
    'https://github.com/yuqinie98/PatchTST',
    NULL,
    '[A Time Series is Worth 64 Words: Long-term Forecasting with Transformers](/paper/2211.14730)'
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
WHERE slug = 'patchtst'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'patchtst'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 452 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention PatchTST are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE patchtst_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'patchtst'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        7965, 8908, 14038, 15824, 16899, 17149, 17502, 17509, 17559, 17655, 18090, 18848,
        19122, 19314, 19329, 20461, 20760, 21282, 21287, 21454, 21559, 21575, 21721, 21789,
        21869, 21977, 22075, 23040, 24143, 24226, 24747, 24986, 25240, 25241, 25305, 25578,
        26014, 26513, 26728, 26761, 26762, 26781, 26906, 27066, 27382, 27401, 27660, 27968,
        27976, 28157, 28392, 28607, 28705, 29333, 29486, 29645, 29699, 29799, 30284, 30753,
        31078, 31193, 31283, 31329, 31602, 31603, 32274, 32451, 32470, 32823, 32975, 32987,
        33180, 33782, 34359, 34408, 34445, 34544, 34628, 35470, 36415, 37003, 37271, 37369,
        37510, 37732, 37981, 38434, 38441, 38598, 39118, 39453, 42371, 42569, 42735, 42767,
        42772, 43456, 43484, 43520, 43521, 43571, 43615, 43783, 43902, 43936, 44125, 44832,
        44903, 44998, 45044, 45492, 45523, 46109, 47323, 48110, 48298, 48372, 48687, 49022,
        49090, 49230, 49284, 49559, 49892, 50141, 50176, 50390, 50691, 50726, 50870, 50890,
        51129, 51165, 51446, 51751, 51789, 52129, 52958, 52994, 53176, 53195, 53355, 53687,
        54620, 54703, 56494, 56536, 58945, 59246, 60180, 60250, 60473, 60555, 60556, 60639,
        60690, 61076, 61798, 61823, 61888, 63112, 63415, 63771, 63824, 63892, 64065, 64332,
        64574, 64576, 65112, 65366, 65613, 65911, 65989, 66134, 66219, 66426, 66613, 66629,
        66693, 66849, 67180, 67292, 67313, 67345, 67584, 67622, 67690, 67707, 67792, 68050,
        68190, 68253, 68269, 68494, 68656, 68943, 69752, 69921, 70046, 70081, 70123, 70259,
        70280, 70361, 70471, 70901, 70994, 71025, 71595, 71633, 72048, 72049, 72078, 72094,
        72138, 72205, 72239, 72478, 72611, 72903, 72930, 73345, 73473, 73603, 74390, 74552,
        75386, 75493, 75520, 75680, 76018, 76039, 76076, 76078, 76131, 76187, 76188, 76329,
        76728, 76920, 76939, 76995, 77095, 77179, 77193, 77391, 77545, 77852, 78144, 78171,
        78263, 78622, 78957, 78959, 79126, 79266, 79508, 82951, 82990, 83410, 83512, 83656,
        85717, 85722, 85846, 86083, 86098, 86257, 86359, 86699, 86709, 86805, 86874, 87213,
        87266, 87280, 87330, 87394, 87459, 88570, 88623, 88639, 88647, 88691, 88821, 89047,
        89177, 89268, 89383, 89469, 89621, 89649, 89656, 89730, 89760, 89773, 89826, 89887,
        90041, 90063, 91043, 91064, 91178, 91347, 91537, 91548, 91582, 91618, 91696, 91894,
        91952, 92049, 92053, 92177, 92393, 92411, 92584, 92588, 92655, 93152, 93207, 93248,
        93274, 93395, 93404, 93413, 93428, 93480, 93587, 93657, 93773, 93962, 93964, 94083,
        94105, 94121, 94188, 94189, 94215, 94245, 94291, 94300, 94310, 94334, 94341, 94345,
        94388, 94422, 94508, 94565, 94621, 94840, 94888, 94951, 94977, 95000, 96805, 98209,
        98220, 98226, 98588, 98746, 98787, 98788, 98948, 99308, 99331, 99455, 99475, 99483,
        99485, 99531, 99802, 99838, 99850, 99907, 99911, 100014, 100039, 100096, 100114, 100118,
        100147, 100166, 100167, 100192, 100274, 100289, 100597, 100729, 100803, 100847, 100877, 100892,
        101072, 101088, 101134, 101200, 101219, 101243, 101298, 101299, 101439, 101502, 101504, 101506,
        101563, 101633, 101722, 101755, 101759, 101997, 102100, 102186, 102479, 102758, 103051, 103303,
        103807, 103842, 104066, 104083, 104093, 104099, 104122, 104581, 105991, 106222, 106748, 107098,
        107908, 108122, 108382, 108447, 108626, 108627, 108692, 108810, 108837, 109293, 110422, 116228,
        120397, 122786, 123362
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'patchtst citation review 2026-10-15: cites the source paper without using the method'
FROM patchtst_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING patchtst_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING patchtst_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
