-- Add SentencePiece method, introduced in arXiv 1808.06226. The source paper
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
    'sentencepiece',
    'SentencePiece',
    'SentencePiece',
    'SentencePiece is a language-independent subword tokenizer and detokenizer for neural text processing. It trains subword models directly from raw sentences without language-specific pre-tokenization, treating the whitespace as an ordinary symbol (the meta symbol ▁), so tokenization is lossless and detokenization is a simple concatenation. It implements both [byte-pair encoding](/methods/bpe) and the unigram language model subword algorithm, provides a fast C++ implementation with Python bindings, and stores the full normalization rules and vocabulary in one self-contained model file for reproducible preprocessing. SentencePiece is the tokenizer library behind many multilingual and large language models, including [T5](/methods/t5) and [LLaMA](/methods/llama).',
    'SentencePiece',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2018,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1808.06226'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'SentencePiece: A simple and language independent subword tokenizer and detokenizer for Neural Text Processing',
    'https://github.com/google/sentencepiece',
    NULL,
    '[SentencePiece: A simple and language independent subword tokenizer and detokenizer for Neural Text Processing](/paper/1808.06226)'
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
WHERE slug = 'sentencepiece'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'sentencepiece'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 913 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention SentencePiece or subword tokenization are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE sentencepiece_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'sentencepiece'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        1587, 2239, 2286, 2326, 2341, 2376, 2434, 2566, 2579, 2600, 2639, 2715,
        2769, 2796, 2805, 2856, 2931, 2947, 3020, 3101, 3165, 3179, 3217, 3304,
        3309, 3311, 3332, 3337, 3345, 3408, 3459, 3462, 3475, 3476, 3620, 3623,
        3647, 3660, 3666, 3677, 3707, 3734, 3761, 3831, 3854, 3866, 3878, 3880,
        3894, 3918, 3943, 3961, 3969, 3988, 4010, 4046, 4073, 4078, 4131, 4177,
        4231, 4325, 4343, 4345, 4402, 4406, 4412, 4416, 4424, 4435, 4457, 4504,
        4645, 4662, 4714, 4819, 4843, 4917, 4978, 5084, 5102, 5116, 5124, 5146,
        5177, 5335, 5363, 5370, 5373, 5376, 5485, 5506, 5509, 5513, 5519, 5565,
        5619, 5622, 5640, 5661, 5674, 5751, 5896, 5902, 5925, 5935, 5946, 5977,
        6061, 6098, 6122, 6126, 6275, 6284, 6358, 6378, 6411, 6441, 6470, 6474,
        6476, 6505, 6542, 6547, 6558, 6561, 6562, 6574, 6589, 6611, 6648, 6650,
        6658, 6673, 6689, 6695, 6776, 6836, 6869, 6925, 7146, 7217, 7244, 7262,
        7283, 7448, 7488, 7490, 7505, 7514, 7559, 7574, 7596, 7657, 7675, 7689,
        7725, 7736, 7789, 7816, 7826, 7848, 7856, 7922, 7976, 8004, 8014, 8037,
        8243, 8266, 8269, 8275, 8300, 8339, 8367, 8369, 8472, 8574, 8575, 8580,
        8625, 8673, 8748, 8763, 8785, 8906, 8940, 8979, 8980, 9012, 9018, 9113,
        9114, 9120, 9151, 9160, 9162, 9180, 9190, 9322, 9331, 9382, 9456, 9493,
        9502, 9526, 9617, 9747, 9797, 9863, 9879, 9921, 9961, 10001, 10013, 10015,
        10029, 10103, 10140, 10233, 10296, 10350, 10359, 10365, 10373, 10405, 10435, 10534,
        10670, 10758, 10997, 11023, 11109, 11122, 11261, 11263, 11281, 11696, 11743, 11750,
        11775, 11798, 11950, 11976, 11978, 12040, 12069, 12084, 12112, 12119, 12125, 12165,
        12168, 12243, 12336, 12468, 12589, 12683, 12691, 12794, 12828, 13020, 13179, 13187,
        13212, 13311, 13341, 13349, 13351, 13394, 13414, 13426, 13906, 14052, 14138, 14181,
        14227, 14296, 14308, 14349, 14388, 14394, 14412, 14580, 14719, 14729, 14730, 14739,
        14744, 14762, 14780, 14799, 15015, 15175, 15213, 15245, 15287, 15355, 15457, 15608,
        15632, 15656, 15670, 15713, 15726, 15802, 15831, 15840, 15898, 15919, 15956, 16262,
        16315, 16384, 16389, 16474, 16580, 16618, 16879, 17011, 17072, 17273, 17584, 17690,
        17773, 17809, 17810, 17835, 17915, 17923, 17965, 17972, 18066, 18074, 18099, 18110,
        18133, 18189, 18199, 18203, 18221, 18230, 18369, 18491, 18526, 18584, 18868, 18958,
        18975, 19335, 19336, 19390, 19748, 19870, 19984, 20038, 20093, 20102, 20107, 20134,
        20235, 20289, 20318, 20412, 20440, 20444, 20498, 20548, 20549, 20598, 20641, 20645,
        20670, 20675, 20683, 20761, 20866, 20895, 20973, 20992, 21022, 21290, 21398, 21776,
        21781, 21814, 21816, 22087, 22106, 22107, 22186, 22193, 22388, 22477, 22704, 22730,
        22741, 22756, 22939, 22966, 23012, 23157, 23199, 23202, 23213, 23329, 23365, 23381,
        23384, 23490, 23627, 23776, 23804, 24190, 24298, 24370, 24578, 24622, 24687, 24723,
        24785, 25139, 25192, 25261, 25296, 25297, 25395, 25541, 25555, 25632, 25723, 25782,
        25980, 26106, 26153, 26155, 26226, 26303, 26306, 26455, 26928, 27042, 27364, 27393,
        27398, 27649, 27680, 27811, 27876, 27995, 28171, 28191, 28324, 28463, 28517, 28525,
        28592, 28641, 28778, 28942, 28946, 28959, 29063, 29236, 29455, 29558, 29821, 29948,
        29995, 30234, 30238, 30251, 30335, 30396, 30458, 30577, 30656, 30695, 30824, 30849,
        30877, 31154, 31185, 31310, 31339, 31352, 31456, 31542, 31553, 31695, 31738, 31825,
        31975, 32007, 32011, 32161, 32323, 32338, 32340, 32359, 32406, 32492, 32600, 32764,
        32787, 32905, 32924, 33023, 33062, 33140, 33301, 33405, 33430, 33517, 33575, 33673,
        33706, 33844, 33945, 34024, 34127, 34136, 34197, 34222, 34291, 34346, 34402, 34509,
        34545, 34814, 34828, 35187, 35296, 35361, 35408, 35538, 35619, 35992, 36358, 36563,
        36598, 36652, 36865, 37264, 37341, 37406, 37418, 37526, 37537, 37698, 37790, 37855,
        38246, 38373, 38522, 38741, 38762, 38862, 38980, 39112, 39129, 39279, 39542, 39596,
        39725, 39784, 39817, 39825, 39914, 39930, 40006, 40210, 40627, 40761, 40819, 41261,
        41564, 41628, 41797, 42525, 43030, 43519, 43590, 43853, 44010, 44474, 44562, 44809,
        45058, 45133, 45516, 46269, 46734, 47507, 47845, 47994, 48300, 48314, 48762, 49147,
        49174, 50038, 50481, 50615, 50720, 51217, 51289, 51351, 51538, 51650, 51729, 52331,
        52909, 53078, 53411, 53773, 53890, 54884, 55599, 56441, 57019, 58727, 59355, 59678,
        59940, 60406, 61894, 62620, 62744, 64880, 65389, 65705, 65716, 66103, 66339, 66967,
        68256, 68609, 68839, 69422, 69495, 69915, 71055, 71095, 71676, 71849, 72695, 73406,
        73699, 74941, 74947, 75825, 75974, 76206, 76321, 76394, 76641, 76893, 77264, 77473,
        77637, 77705, 77870, 77997, 78086, 78362, 78370, 78854, 78897, 78924, 79007, 79318,
        79444, 79890, 80098, 80628, 80640, 80859, 80894, 81039, 81512, 81614, 85034, 85915,
        88610, 88888, 89149, 90634, 91031, 91038, 91156, 91470, 92295, 92762, 93529, 93794,
        93900, 95865, 98926, 102601, 102800, 102922, 103369, 103382, 103400, 103658, 104080, 105871,
        110006, 110792, 110919, 111164, 111243, 111578, 111607, 111711, 111764, 115860, 116741, 122391,
        123150
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'sentencepiece citation review 2026-10-15: cites the source paper without using the method'
FROM sentencepiece_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING sentencepiece_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING sentencepiece_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
