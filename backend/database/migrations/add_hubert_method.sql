-- Add HuBERT, introduced in arXiv 2106.07447.
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
    'hubert',
    'HuBERT',
    'Hidden-Unit BERT (HuBERT)',
    'HuBERT (Hidden-Unit [BERT](/methods/bert)) is a self-supervised speech representation learning method that applies BERT-style masked prediction to continuous audio. Because speech has no lexicon of input units, no explicit segmentation and multiple sound units per utterance, HuBERT first runs an offline clustering step to assign discrete hidden-unit targets to frames, then trains a CNN encoder plus [Transformer](/methods/transformer) to predict those cluster labels over masked regions only, forcing it to learn a combined acoustic and language model. Training starts from a simple k-means teacher with 100 clusters on MFCC features and iterates, re-clustering the model''s own features. With two clustering iterations, HuBERT matched or improved on [wav2vec 2.0](/methods/wav2vec) on LibriSpeech (960h) and Libri-Light (60,000h) with 10-minute to 960-hour fine-tuning subsets, and a 1B-parameter model gave up to 19% and 13% relative WER reduction on dev-other and test-other. HuBERT units and features underpin [WavLM](/methods/wavlm), speech tokenizers and spoken language models.',
    'HuBERT, hidden-unit BERT',
    (
        SELECT id
        FROM areas
        WHERE name = 'Audio'
        LIMIT 1
    ),
    2021,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2106.07447'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'HuBERT: Self-Supervised Speech Representation Learning by Masked Prediction of Hidden Units',
    'https://github.com/facebookresearch/fairseq/tree/main/examples/hubert',
    NULL,
    '[HuBERT: Self-Supervised Speech Representation Learning by Masked Prediction of Hidden Units](/paper/2106.07447)'
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
WHERE slug = 'hubert' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'hubert' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 903 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE hubert_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'hubert'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        5634, 6225, 6641, 6713, 6904, 6931, 7062, 7151, 7267, 7330, 7450, 7518,
        7689, 7849, 7904, 8056, 8152, 8193, 8508, 8553, 8596, 9009, 9036, 9099,
        9322, 9416, 9486, 9539, 9785, 9827, 10049, 10231, 10441, 10482, 10488, 10583,
        10745, 10747, 10822, 10977, 11027, 11163, 11186, 11313, 11610, 11642, 11869, 12047,
        12089, 12144, 12223, 12316, 12429, 12650, 12705, 13145, 13368, 13441, 13545, 13608,
        13624, 13904, 13956, 14023, 14113, 14577, 14691, 14776, 14953, 15033, 15355, 15475,
        15504, 15599, 15615, 15618, 15645, 15686, 15700, 15717, 15737, 15774, 15797, 15824,
        15876, 15899, 16026, 16100, 16224, 16250, 16524, 16587, 16619, 16707, 16752, 16774,
        16843, 16846, 16977, 17036, 17051, 17085, 17322, 17352, 17507, 17631, 17690, 17696,
        17748, 17762, 17801, 17818, 17819, 17893, 18069, 18230, 18238, 18280, 18483, 18771,
        18943, 19131, 19134, 19390, 19524, 19711, 19973, 20289, 20292, 20390, 20392, 20395,
        20415, 20421, 20440, 20550, 20616, 20648, 20713, 20718, 20764, 20765, 20866, 20916,
        20970, 21124, 21136, 21140, 21154, 21177, 21214, 21270, 21401, 21591, 21608, 21667,
        21768, 21772, 21790, 21920, 22004, 22322, 22521, 22547, 22614, 22850, 22868, 22897,
        22922, 22932, 22968, 23081, 23202, 23278, 23549, 23807, 23854, 23959, 24187, 24370,
        24707, 24823, 24844, 24940, 25123, 25162, 25199, 25344, 25357, 25420, 25470, 25514,
        25528, 25553, 25554, 25619, 25634, 25687, 25870, 26074, 26134, 26238, 26244, 26684,
        26834, 26850, 26913, 27147, 27179, 27292, 27327, 27588, 27671, 27689, 27699, 27881,
        27954, 28432, 28650, 28934, 28964, 28965, 29157, 29429, 29710, 29731, 29817, 29819,
        29890, 29920, 30082, 30142, 30327, 30680, 30690, 30710, 30955, 30994, 31076, 31137,
        31388, 31429, 31442, 31667, 31966, 32203, 32207, 32291, 32345, 32407, 32480, 32549,
        32554, 32560, 32695, 32698, 32762, 32766, 32883, 32884, 32950, 33009, 33012, 33062,
        33103, 33114, 33210, 33217, 33244, 33269, 33333, 33390, 33433, 33540, 33566, 33628,
        33635, 33702, 33730, 33731, 33808, 33921, 33950, 34127, 34165, 34202, 34215, 34423,
        34431, 34496, 34551, 34645, 34796, 34828, 34834, 34867, 35039, 35069, 35071, 35189,
        35373, 35380, 35420, 35456, 35489, 35546, 35636, 35684, 35739, 35825, 35828, 36272,
        36293, 36300, 36379, 36382, 36413, 36415, 36422, 36470, 36562, 36624, 36676, 36690,
        36716, 36740, 36743, 36779, 36849, 36895, 36911, 36960, 36973, 37029, 37062, 37113,
        37182, 37194, 37210, 37248, 37267, 37368, 37389, 37446, 37559, 37566, 37786, 37900,
        38154, 38191, 38247, 38398, 38732, 38794, 38850, 38917, 39023, 39450, 39490, 39552,
        39575, 39580, 39596, 40019, 40022, 40688, 40715, 40807, 40948, 41328, 41463, 41506,
        41564, 41628, 41644, 41769, 41825, 41978, 41992, 42181, 42380, 42401, 42423, 42572,
        42648, 42708, 43035, 43234, 43689, 43720, 43739, 43793, 43884, 43945, 44145, 44284,
        44396, 44486, 44789, 44806, 44833, 44871, 44889, 44925, 44996, 45053, 45175, 45258,
        46034, 46070, 46140, 46569, 46772, 46848, 46982, 47219, 47237, 47266, 47456, 47516,
        47635, 47664, 48305, 48313, 48388, 48407, 48408, 48486, 48522, 48732, 49032, 49080,
        49176, 49184, 49209, 49239, 49304, 49349, 49433, 49520, 49533, 49795, 49804, 49825,
        49960, 50295, 50429, 50626, 50947, 51113, 51133, 51159, 51240, 51346, 51354, 51385,
        51493, 51941, 51980, 52010, 52028, 52077, 52227, 52371, 52392, 52482, 52732, 52767,
        52886, 52998, 53249, 53269, 53800, 53852, 53921, 53926, 54884, 55333, 55426, 55590,
        55847, 55849, 56048, 56228, 56768, 56807, 56872, 57214, 57911, 58048, 58100, 58107,
        58197, 58280, 58326, 58633, 58887, 59027, 59286, 59303, 59308, 59320, 59399, 59434,
        59485, 59551, 59582, 59651, 59691, 59819, 59836, 59851, 60144, 60171, 60206, 60217,
        60245, 60365, 60406, 60856, 60898, 60962, 61002, 61130, 61168, 61244, 61374, 61379,
        61477, 61706, 61953, 62001, 62393, 62419, 62508, 62720, 63208, 63391, 63407, 63423,
        63635, 63706, 63714, 63899, 63991, 64136, 64242, 64326, 64364, 64379, 64544, 64671,
        64763, 64915, 65025, 65152, 65497, 65630, 65659, 65672, 65736, 65837, 65839, 65973,
        66150, 66191, 66663, 66780, 66811, 66942, 67034, 67192, 67304, 67454, 67609, 67610,
        67700, 67718, 67803, 67905, 68029, 68131, 68145, 68159, 68160, 68204, 68271, 68312,
        68317, 68481, 68502, 69314, 69320, 69326, 69577, 69602, 69801, 69915, 70139, 70248,
        70374, 70741, 70991, 71297, 71528, 71530, 71604, 71637, 71732, 71856, 71923, 71984,
        71992, 72087, 72124, 72358, 72397, 72429, 72560, 72650, 72675, 72770, 72865, 72927,
        72961, 72972, 72975, 72990, 73096, 73103, 73229, 73262, 73291, 73300, 73579, 73589,
        73592, 73652, 73773, 73850, 73904, 74246, 74371, 74439, 74814, 74832, 74847, 74948,
        75056, 75060, 75084, 75239, 75394, 75550, 75554, 75594, 75628, 75677, 75810, 75823,
        75856, 75865, 75997, 76052, 76082, 76115, 76141, 76364, 76401, 76411, 76419, 76456,
        76497, 76503, 76513, 76533, 76545, 76930, 76985, 76999, 77008, 77031, 77040, 77093,
        77179, 77294, 77338, 77640, 77669, 77858, 77867, 77947, 77948, 77999, 78051, 78366,
        78393, 78526, 78543, 78613, 78709, 78845, 78859, 78927, 79084, 79139, 79289, 79309,
        79350, 79458, 79626, 79870, 80081, 80225, 83505, 83649, 84199, 84401, 86825, 87394,
        87573, 87956, 88134, 89472, 89798, 89899, 89989, 90094, 90457, 90463, 91125, 91512,
        91622, 91781, 91824, 92109, 92762, 93130, 93727, 93794, 94115, 94458, 97988, 98838,
        98966, 99020, 99390, 99446, 99624, 100305, 100325, 100709, 101100, 101212, 101463, 101541,
        102108, 102595, 102603, 102640, 102772, 102789, 102827, 102850, 103081, 103245, 103295, 103355,
        103407, 103533, 103559, 103823, 104280, 104289, 104291, 104412, 105917, 106803, 107680, 108306,
        108349, 108548, 108555, 108909, 109193, 109196, 109197, 109240, 109253, 109254, 109269, 109434,
        110020, 110464, 110471, 110555, 110751, 111136, 111137, 111154, 111155, 111156, 111166, 111170,
        111174, 111183, 111188, 111198, 111200, 111203, 111204, 111219, 111233, 111309, 111330, 111347,
        111349, 111350, 111371, 111373, 111393, 111413, 111425, 111441, 111445, 111472, 111476, 111477,
        111482, 111498, 111500, 111502, 111503, 111513, 111515, 111520, 111538, 111550, 111552, 111601,
        111612, 111617, 111629, 111641, 111679, 111680, 111696, 111705, 111707, 111708, 111740, 111756,
        111767, 111809, 111842, 111860, 111892, 111903, 111911, 111917, 111918, 111928, 111933, 111934,
        111935, 111936, 111940, 111942, 111947, 111948, 111949, 111951, 111953, 111956, 111959, 111960,
        111962, 111979, 111987, 111992, 112007, 112011, 112014, 112021, 112023, 112025, 112073, 112077,
        112125, 112132, 112135, 112150, 112315, 114073, 115470, 116506, 117257, 119168, 119244, 121972,
        123158, 123252, 123268
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'hubert citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM hubert_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING hubert_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 81 local citers name the method in title or abstract.
CREATE TEMP TABLE hubert_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'hubert'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        6421, 6792, 6878, 7198, 7655, 7890, 8249, 8475, 8512, 8786, 10515, 12357,
        15532, 15785, 15805, 16425, 16450, 20865, 20874, 20961, 22102, 24755, 27061, 29821,
        30565, 32487, 32559, 32622, 32979, 36925, 36958, 37537, 40486, 42193, 50380, 51304,
        55856, 58291, 59151, 59787, 61665, 61927, 63395, 63425, 65071, 65238, 67885, 68178,
        68196, 72160, 75933, 76916, 77012, 78423, 78936, 80271, 80412, 80461, 102569, 102940,
        103783, 104411, 108003, 108613, 108858, 111171, 111173, 111348, 111475, 111478, 111479, 111486,
        111504, 111608, 111732, 111750, 111863, 111938, 111943, 112075, 112134
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM hubert_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM hubert_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 97 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE hubert_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'hubert'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        4971, 6421, 6792, 6878, 7198, 7655, 7890, 8249, 8475, 8512, 8786, 10515,
        12357, 15532, 15785, 15805, 16425, 16450, 20446, 20865, 20874, 20961, 21490, 22102,
        24755, 27061, 29821, 30565, 31119, 32487, 32559, 32622, 32979, 36925, 36958, 37537,
        40486, 42193, 43574, 44007, 50380, 51304, 55856, 58291, 59151, 59787, 61138, 61665,
        61927, 63057, 63395, 63425, 65071, 65238, 67885, 68178, 68196, 68594, 72160, 75933,
        76265, 76916, 77012, 78240, 78423, 78936, 80271, 80412, 80461, 102569, 102940, 103783,
        104411, 108003, 108613, 108858, 111171, 111173, 111196, 111348, 111475, 111478, 111479, 111486,
        111504, 111608, 111732, 111750, 111863, 111924, 111938, 111943, 112047, 112055, 112075, 112116,
        112134
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM hubert_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM hubert_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
