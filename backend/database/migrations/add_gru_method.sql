-- Add GRU, introduced in arXiv 1406.1078.
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
    'gru',
    'GRU',
    'Gated Recurrent Unit (GRU)',
    'The Gated Recurrent Unit (GRU) is a recurrent neural network cell with an update gate and a reset gate that control how much of the previous hidden state is kept and how much is replaced by a candidate state. It was proposed by Cho et al. (2014) for the RNN encoder-decoder in statistical machine translation as a simpler alternative to the [LSTM](/methods/lstm): it has no separate memory cell and fewer parameters, yet mitigates vanishing gradients similarly. GRUs remain a common choice for sequence modeling in speech, time series and recommendation, and appear as building blocks such as ConvGRU in optical flow models.',
    'GRU, gated recurrent unit, gated recurrent units, gated recurrent neural network',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2014,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1406.1078'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Learning Phrase Representations using RNN Encoder-Decoder for Statistical Machine Translation',
    'https://github.com/pytorch/pytorch/blob/main/torch/nn/modules/rnn.py',
    NULL,
    '[Learning Phrase Representations using RNN Encoder-Decoder for Statistical Machine Translation](/paper/1406.1078)'
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
WHERE slug = 'gru' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'gru' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 488 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE gru_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gru'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        10359, 10406, 10461, 10502, 10507, 10566, 10820, 10834, 10843, 10855, 10889, 10893,
        10942, 10947, 11060, 11187, 11230, 11245, 11505, 11733, 12090, 12146, 12215, 12307,
        12354, 12363, 12396, 12478, 12764, 13108, 13184, 13196, 13244, 13489, 13546, 13588,
        13665, 13731, 13855, 14085, 14355, 14512, 14547, 14628, 15079, 15122, 15379, 15477,
        15505, 15587, 15629, 15716, 15737, 16183, 16274, 16411, 16473, 16824, 16979, 17060,
        17209, 17286, 17379, 17880, 18051, 18236, 18241, 18415, 18456, 18463, 18507, 18551,
        18554, 18776, 18872, 18904, 19203, 19462, 19512, 19562, 19574, 19634, 19799, 19836,
        19902, 19924, 20033, 20276, 20354, 20362, 20397, 20474, 20727, 20833, 21025, 21371,
        21484, 21846, 22189, 22379, 22470, 22657, 22725, 22820, 22852, 22859, 22998, 23076,
        23082, 23173, 23174, 23260, 23550, 23591, 23593, 23761, 24382, 24544, 24607, 24642,
        24689, 24717, 24864, 24975, 24984, 25282, 25699, 25820, 25932, 26524, 26632, 27161,
        27163, 27510, 27914, 28062, 28073, 28183, 28313, 28314, 28327, 28502, 28809, 28841,
        28952, 28973, 29138, 29350, 29544, 29628, 29958, 30106, 30260, 30313, 30335, 30483,
        30967, 31223, 31412, 31427, 31467, 31545, 31553, 31557, 31656, 31680, 32311, 32423,
        32579, 32723, 33038, 33259, 33698, 33802, 33962, 33992, 33999, 34206, 34322, 34434,
        34483, 34725, 34787, 34878, 35076, 35146, 35158, 35444, 35784, 35977, 36223, 36546,
        36766, 36767, 36869, 37038, 37164, 37699, 37707, 38324, 38820, 39068, 39205, 39255,
        39354, 39386, 39546, 39678, 39987, 40151, 40461, 41134, 41264, 42270, 42370, 43042,
        43345, 43349, 43657, 43691, 44737, 44741, 44780, 45001, 45030, 45062, 45103, 45280,
        45340, 46010, 46383, 46393, 46964, 46980, 47844, 48332, 48606, 49046, 49145, 49226,
        49395, 49548, 49604, 50176, 51066, 51514, 51527, 51766, 51916, 52090, 52129, 52826,
        53320, 53340, 53343, 53525, 54855, 56585, 56613, 56993, 57461, 57633, 57893, 58864,
        59401, 59504, 60111, 60407, 60447, 60473, 60608, 60733, 61553, 63247, 64134, 64140,
        64188, 64584, 64629, 64665, 65922, 65989, 66026, 66134, 66154, 66921, 67329, 67462,
        67688, 67702, 68547, 68639, 68910, 69493, 70036, 70554, 70673, 71028, 71224, 71671,
        71818, 71899, 72179, 72284, 72405, 72432, 72903, 73053, 73486, 73518, 73691, 73732,
        73782, 74252, 74258, 74435, 74942, 74993, 75248, 75555, 76162, 76452, 76530, 76586,
        76728, 76934, 76939, 77025, 77179, 77375, 77564, 77602, 77625, 77887, 78045, 78083,
        78268, 78269, 78313, 78343, 78415, 78622, 78855, 78959, 79004, 79196, 79203, 79342,
        79371, 79519, 79585, 79659, 79743, 82918, 83256, 83514, 83518, 83714, 85722, 85952,
        85963, 86074, 86080, 86116, 86457, 86631, 86719, 86733, 86768, 86782, 86959, 87283,
        87489, 88227, 88383, 88397, 88412, 88569, 88879, 89122, 89128, 89544, 89626, 89732,
        89775, 89962, 90004, 90383, 90558, 90840, 90864, 90981, 91097, 91548, 91946, 92383,
        92791, 92981, 93153, 93679, 93965, 94025, 94033, 95024, 95239, 96370, 96530, 96564,
        96572, 97990, 98193, 98209, 98212, 98672, 98788, 98971, 99675, 99911, 99975, 100425,
        100687, 100877, 101311, 101646, 101660, 101687, 101765, 102539, 103436, 104224, 104430, 104821,
        106502, 106898, 107876, 108059, 108408, 108598, 108717, 108766, 109006, 109180, 109333, 109742,
        109939, 110282, 110333, 110808, 111125, 111689, 112701, 112722, 112986, 113145, 113257, 113708,
        113921, 114252, 115717, 115772, 115799, 115852, 115960, 116021, 116046, 116048, 116062, 116223,
        116459, 116641, 116953, 116976, 117256, 117979, 117981, 118667, 119668, 119763, 120299, 121102,
        121752, 122051, 122055, 122955, 123017, 123457, 123521, 123688
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'gru citation review 2026-10-20: cites the source without naming the method in title or abstract'
FROM gru_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING gru_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 34 local citers name the method in title or abstract.
CREATE TEMP TABLE gru_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gru'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        11224, 13681, 16655, 17854, 21085, 21211, 23952, 24792, 31329, 32237, 36028, 37628,
        39409, 41327, 44797, 58272, 62648, 65908, 69997, 73726, 76485, 78537, 78675, 79074,
        84702, 88675, 101529, 106287, 109309, 113961, 113972, 115866, 122675, 123065
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gru_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM gru_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 152 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE gru_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gru'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        133, 327, 783, 792, 876, 883, 975, 1035, 1134, 1232, 1420, 2141,
        2209, 2223, 2453, 2884, 3024, 3281, 4034, 4134, 4740, 4748, 4854, 5618,
        5673, 6046, 6371, 6863, 6910, 7459, 8094, 8467, 9588, 10531, 11224, 11229,
        12262, 13200, 13566, 13681, 13919, 14257, 16655, 17854, 18701, 20089, 20447, 20736,
        20775, 20884, 21085, 21211, 22884, 23170, 23952, 24554, 24792, 25769, 26411, 26824,
        29414, 31329, 32173, 32237, 34680, 35331, 35791, 36028, 36970, 37628, 39409, 39560,
        40983, 41327, 44797, 45661, 47015, 48581, 56004, 56219, 58272, 58655, 59218, 59407,
        61451, 62648, 63845, 65908, 66209, 68043, 69997, 71666, 73726, 76178, 76389, 76485,
        76546, 77078, 78268, 78537, 78675, 78969, 79046, 79074, 80024, 80360, 80516, 81900,
        81988, 82010, 82099, 84577, 84702, 85452, 86156, 87682, 88675, 89909, 91685, 95069,
        95112, 95702, 95745, 96659, 97402, 97769, 98905, 101529, 104070, 104076, 104338, 105363,
        106287, 106310, 107281, 107806, 109309, 109488, 109508, 111210, 111926, 112047, 113961, 113972,
        114249, 114861, 115534, 115866, 121531, 122675, 123016, 123065
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gru_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM gru_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
