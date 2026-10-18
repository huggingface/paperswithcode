-- Add GPTQ, introduced in arXiv 2210.17323.
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
    'gptq',
    'GPTQ',
    'GPTQ',
    'GPTQ is a one-shot, post-training weight [quantization](/methods/quantization) method for large generative [Transformer](/methods/transformer) models that uses approximate second-order information. Building on Optimal Brain Quantization, it quantizes the weight matrix of each layer column by column, in blocks, and after each step updates the not-yet-quantized weights using the inverse of the layer Hessian, computed once in Cholesky form, to compensate for the quantization error on a small calibration set. This makes it fast enough for the largest models: GPTQ quantizes 175-billion-parameter GPT and OPT models in about four GPU hours to 3 or 4 bits per weight with negligible accuracy loss, doubling the compression of earlier one-shot methods and fitting a 175B model on a single GPU for generative inference, with end-to-end speedups over FP16 of about 3.25x on A100 and 4.5x on A6000 GPUs. GPTQ became a standard format for sharing quantized open-weight LLMs and a common baseline for later methods.',
    'GPTQ, OPTQ',
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
        WHERE arxiv_id = '2210.17323'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers',
    'https://github.com/IST-DASLab/gptq',
    NULL,
    '[GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers](/paper/2210.17323)'
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
WHERE slug = 'gptq' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'gptq' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 774 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE gptq_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gptq'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        11437, 12087, 12150, 12604, 12851, 12949, 13693, 14720, 14778, 14957, 15396, 15741,
        15782, 15928, 16063, 16279, 16398, 16465, 16516, 16618, 16701, 16746, 16806, 16910,
        16988, 17347, 17401, 17691, 17739, 17912, 18201, 18401, 18794, 19063, 19256, 19440,
        19502, 19734, 19766, 19836, 19856, 19888, 19938, 19957, 20040, 20070, 20085, 20219,
        20273, 20291, 20400, 20411, 20597, 20828, 21039, 21086, 21196, 21237, 21247, 21525,
        21545, 21578, 21695, 21748, 21761, 21917, 21963, 22096, 22451, 22590, 22696, 22731,
        22856, 22919, 22994, 22996, 23097, 23117, 23213, 23413, 23414, 23593, 23836, 23851,
        24127, 24191, 24390, 24511, 24528, 24561, 24658, 24720, 24977, 25025, 25082, 25165,
        25261, 25279, 25286, 25354, 25356, 25573, 25581, 25719, 26039, 26051, 26142, 26280,
        26346, 26365, 26598, 26627, 26704, 26748, 26767, 26792, 26892, 26940, 26995, 26998,
        27018, 27035, 27052, 27085, 27116, 27209, 27301, 27370, 27380, 27422, 27437, 27463,
        27475, 27486, 27496, 27548, 27575, 27608, 27837, 27840, 27855, 27861, 27897, 27917,
        27967, 27989, 28004, 28010, 28108, 28112, 28129, 28244, 28270, 28369, 28381, 28415,
        28524, 28596, 28694, 28698, 28712, 28767, 28840, 29100, 29124, 29184, 29346, 29458,
        29494, 29658, 29662, 29701, 29896, 29981, 30032, 30079, 30088, 30143, 30148, 30152,
        30302, 30308, 30372, 30503, 30639, 30647, 30670, 30701, 30716, 31092, 31094, 31101,
        31152, 31387, 31500, 31516, 31570, 31629, 31630, 31642, 31761, 31772, 31852, 31916,
        31937, 31941, 32040, 32071, 32126, 32163, 32261, 32312, 32347, 32349, 32404, 32480,
        32607, 32624, 32689, 32941, 32973, 32977, 33133, 33222, 33233, 33373, 33394, 33561,
        33567, 33651, 33767, 33874, 33901, 33926, 33950, 34090, 34223, 34286, 34296, 34355,
        34455, 34547, 34550, 34576, 34609, 34671, 34692, 34701, 34752, 34878, 34897, 34951,
        35154, 35350, 35357, 35585, 35721, 35743, 35786, 35891, 35926, 35951, 36043, 36088,
        36294, 36410, 36427, 36503, 36535, 36585, 36669, 36986, 37046, 37110, 37309, 37314,
        37377, 37546, 37678, 37695, 37982, 38019, 38112, 38116, 38146, 38162, 38212, 38259,
        38290, 38450, 38583, 38613, 38673, 38684, 38819, 38830, 38991, 39001, 39058, 39082,
        39086, 39161, 39210, 39289, 39478, 39611, 39713, 39782, 39817, 39874, 40066, 40276,
        40512, 40524, 40540, 40691, 40999, 41002, 41003, 41085, 41286, 41504, 41583, 41605,
        41636, 41861, 41867, 41883, 42093, 42202, 42224, 42497, 42529, 43110, 43130, 43143,
        43180, 43249, 43309, 43348, 43390, 43418, 43474, 43480, 43522, 43542, 43628, 43673,
        43746, 43833, 43961, 44053, 44133, 44229, 44380, 44383, 44435, 44436, 44532, 44533,
        44564, 44696, 44731, 44785, 44881, 45130, 45316, 45328, 45376, 45646, 45761, 45840,
        45865, 46098, 46399, 46489, 46704, 46963, 47069, 47229, 47375, 47616, 47711, 47762,
        47804, 47846, 47951, 48029, 48049, 48149, 48241, 48380, 48392, 48463, 48550, 48615,
        48672, 48690, 48721, 48874, 49154, 49206, 49535, 49540, 49595, 49619, 49688, 49691,
        49746, 50166, 50409, 50504, 50653, 50822, 50980, 50987, 51174, 51216, 51337, 52044,
        52448, 52625, 52658, 52809, 52831, 52903, 52967, 53102, 53133, 53302, 53442, 53452,
        53601, 53641, 53988, 54138, 54526, 54577, 54617, 54619, 54662, 54741, 55475, 55492,
        55599, 55725, 55854, 55870, 55873, 55888, 55921, 56068, 56091, 56098, 56114, 56218,
        56274, 56493, 56690, 56788, 57150, 57299, 57308, 57397, 57914, 58017, 58022, 58089,
        58263, 58265, 58351, 58594, 58735, 58755, 58830, 58903, 58919, 59167, 59273, 59284,
        59363, 59379, 59627, 59868, 60159, 60479, 61025, 61047, 61051, 61053, 61185, 61209,
        61259, 61311, 61369, 61389, 61440, 61520, 61659, 61712, 61723, 61910, 61948, 61983,
        62210, 62617, 62626, 62649, 62669, 63194, 63246, 63247, 63529, 64042, 64210, 64248,
        64397, 64499, 64715, 64738, 64767, 64903, 65048, 65190, 65246, 65361, 65457, 65535,
        65920, 65943, 65963, 66081, 66195, 66249, 66348, 66524, 66525, 66559, 66574, 67017,
        67018, 67263, 67363, 67422, 67545, 67564, 67593, 67624, 67639, 67861, 68248, 68331,
        68350, 68370, 68437, 68504, 68652, 68761, 68833, 69203, 69245, 69338, 69356, 69390,
        69496, 69546, 69633, 69717, 69826, 69837, 70030, 70120, 70278, 70463, 70498, 71130,
        71264, 71316, 71467, 72281, 72586, 72760, 73217, 73241, 73245, 73277, 73288, 73508,
        73522, 73554, 73712, 73753, 73910, 74059, 74068, 74128, 74130, 74206, 74208, 74237,
        74397, 74398, 74509, 74531, 74633, 74747, 74868, 75015, 75350, 75366, 75540, 75778,
        75882, 75908, 75923, 76302, 76501, 77103, 77108, 77267, 77300, 77321, 77718, 78971,
        82878, 83141, 83308, 83366, 83376, 83401, 83509, 83513, 83521, 83694, 83744, 83936,
        84192, 84931, 84960, 85570, 85840, 85889, 86169, 86222, 86411, 86872, 87102, 87258,
        87325, 87784, 87943, 88696, 88720, 89151, 89161, 89335, 89558, 89765, 89824, 89906,
        90328, 90917, 91004, 91236, 91868, 91915, 92304, 92436, 92652, 92705, 92727, 93025,
        93052, 93095, 93283, 93329, 93576, 93841, 94517, 94541, 94784, 94808, 94852, 94864,
        94918, 94995, 95009, 95130, 97932, 98105, 99075, 99309, 99687, 100097, 100141, 100378,
        100432, 100437, 100479, 100644, 100658, 100674, 100814, 100904, 101107, 101204, 101255, 101309,
        101402, 101404, 101431, 101510, 101539, 101624, 101640, 101836, 101961, 102219, 102292, 102313,
        102550, 102684, 103142, 103212, 103233, 103378, 103555, 103591, 103597, 104064, 105950, 106428,
        106928, 107025, 107028, 107085, 107236, 107571, 107748, 107970, 108157, 108212, 108712, 108786,
        108853, 109088, 109583, 109699, 109799, 110193, 110800, 110949, 113922, 114153, 118022, 118026,
        118212, 118913, 119138, 119392, 120216, 120320, 121957, 122000, 122011, 122087, 122240, 122303,
        122423, 122691, 122700, 122887, 123037, 123136
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'gptq citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM gptq_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING gptq_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 40 local citers name the method in title or abstract.
CREATE TEMP TABLE gptq_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gptq'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        9543, 13772, 16925, 18087, 20145, 21116, 22930, 24750, 30980, 34220, 43402, 45361,
        47242, 49733, 53187, 53982, 56844, 57981, 58032, 58393, 61332, 62225, 62248, 62491,
        65041, 68185, 73130, 77024, 83402, 83655, 92850, 99600, 100970, 102401, 103828, 105982,
        106330, 106368, 110229, 122447
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gptq_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM gptq_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 57 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE gptq_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gptq'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        9543, 13772, 16925, 18087, 18608, 19262, 20097, 20145, 20971, 21004, 21116, 22930,
        23568, 24750, 30980, 34220, 36976, 43402, 45361, 47242, 49733, 51706, 52061, 53187,
        53982, 56844, 57981, 58032, 58393, 58902, 61255, 61332, 62225, 62248, 62491, 65041,
        68185, 70207, 72221, 73130, 75226, 77024, 83402, 83655, 92850, 99600, 100970, 102401,
        103828, 105982, 106078, 106330, 106368, 110229, 121496, 122393, 122447
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gptq_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM gptq_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
