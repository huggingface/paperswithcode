-- Add DAgger, introduced in arXiv 1011.0686.
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
    'dagger',
    'DAgger',
    'Dataset Aggregation (DAgger)',
    'DAgger (Dataset Aggregation) is an iterative [imitation learning](/methods/imitation-learning) algorithm by Ross, Gordon and Bagnell that addresses the compounding errors of behavior cloning, where a learned policy drifts into states the expert never demonstrated because future observations depend on its own previous actions. At each iteration DAgger runs the current policy, optionally mixed with the expert, to collect trajectories, asks the expert to label the visited states with the correct actions, aggregates these with all previously collected data, and trains the next policy on the aggregate dataset. The paper shows that the procedure can be seen as a no-regret online learning algorithm and that it finds a single stationary deterministic policy that performs well under the distribution of states it induces, with guarantees that avoid the quadratic-in-horizon error growth of supervised imitation. It outperformed previous approaches on Super Tux Kart and Super Mario Bros imitation tasks and a sequence labeling benchmark, and DAgger-style interactive data collection remains common for training robot and [VLA](/methods/vla) policies.',
    'DAgger',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2011,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1011.0686'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning',
    NULL,
    NULL,
    '[A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning](/paper/1011.0686)'
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
WHERE slug = 'dagger' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'dagger' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 632 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE dagger_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dagger'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        242, 328, 397, 412, 417, 533, 830, 1124, 1201, 1508, 1619, 1764,
        1982, 2142, 2259, 2381, 2500, 2578, 2894, 2930, 2984, 3518, 3526, 3946,
        4028, 4099, 4304, 4770, 4775, 5321, 5406, 5480, 5868, 5992, 6379, 6435,
        6440, 6491, 6531, 6585, 7013, 7015, 7163, 7201, 7206, 7336, 7385, 7769,
        7804, 8384, 8402, 8934, 9111, 9303, 9577, 9653, 9781, 10424, 10531, 10691,
        10825, 10843, 11110, 11200, 11255, 11310, 11318, 11369, 11505, 11662, 11918, 12187,
        12456, 12521, 12727, 12827, 12870, 12883, 12910, 13010, 13396, 13429, 13556, 14141,
        14373, 14576, 14758, 14810, 14986, 15073, 15223, 15747, 15869, 16148, 16219, 16538,
        16824, 16939, 17016, 17189, 17248, 17379, 17381, 17431, 17640, 17673, 17721, 17764,
        17882, 18078, 18105, 18190, 18269, 18345, 18585, 18599, 18747, 18759, 18832, 18839,
        19074, 19202, 19854, 19949, 20341, 20900, 21033, 21261, 21289, 21320, 21386, 21527,
        21662, 21686, 21687, 21793, 21834, 21904, 21919, 22667, 23323, 23693, 24763, 24864,
        25582, 26199, 26632, 26899, 26941, 26959, 27217, 27244, 27403, 27606, 27932, 28106,
        28170, 28249, 28283, 28389, 28406, 28440, 28684, 29061, 29452, 29968, 30286, 30784,
        30898, 31704, 31744, 32372, 32408, 33423, 33539, 34434, 34446, 34669, 34725, 34807,
        35124, 35208, 35245, 35772, 35866, 36157, 36504, 36969, 37179, 37414, 37622, 37764,
        37765, 37766, 37830, 37966, 38036, 38094, 38236, 38407, 38520, 38541, 38820, 38861,
        39065, 39347, 40211, 40444, 41128, 41171, 41214, 41379, 41766, 41791, 41905, 42015,
        43576, 43663, 44861, 44988, 45110, 45183, 45278, 45295, 45558, 45610, 45631, 45887,
        46682, 47464, 47732, 48126, 48340, 48658, 48765, 49163, 49799, 49910, 50642, 50969,
        51121, 51241, 51276, 51585, 51650, 51724, 51953, 52131, 52330, 52488, 52826, 53177,
        53356, 53403, 53414, 53569, 53619, 53698, 53966, 54147, 54848, 54988, 55013, 55021,
        55159, 55172, 55180, 55403, 55542, 55554, 55618, 55667, 55752, 55762, 55775, 55818,
        55915, 55959, 56050, 56055, 56095, 56179, 56554, 56583, 56603, 56851, 56939, 56959,
        57474, 57950, 58263, 58379, 58411, 59189, 59495, 59805, 59890, 59916, 59943, 60015,
        60282, 60507, 60528, 60714, 60719, 60760, 60768, 60921, 60985, 61399, 61403, 61409,
        61788, 61954, 62028, 62190, 62359, 62416, 62640, 63030, 63357, 63597, 63712, 63874,
        64098, 64263, 64596, 64747, 64863, 65212, 65627, 65930, 66630, 66943, 66970, 67181,
        67290, 67558, 67662, 67921, 68084, 68381, 68445, 68454, 68557, 68730, 68998, 69475,
        69918, 70013, 70206, 70318, 70393, 70452, 72167, 72620, 72729, 73011, 73029, 73048,
        73068, 73084, 73189, 74420, 74425, 74520, 74595, 75127, 75613, 75854, 75894, 75929,
        75940, 75979, 76124, 76135, 76216, 76837, 77145, 77179, 77625, 77943, 78068, 78354,
        78839, 79252, 79275, 79580, 79613, 79718, 79908, 79989, 80764, 81500, 81567, 81591,
        81751, 81797, 81853, 81898, 82328, 82412, 82506, 82865, 82872, 83143, 83165, 83196,
        83245, 83249, 83592, 83844, 83851, 84235, 84291, 84301, 84386, 84438, 84448, 84739,
        84851, 84852, 84967, 85582, 85642, 85666, 85820, 85835, 85982, 86260, 86441, 86589,
        86730, 86819, 87071, 87760, 88296, 88716, 89037, 89067, 89303, 89349, 89675, 89833,
        89922, 90273, 90442, 90799, 91191, 91233, 91237, 91413, 91414, 91498, 91757, 92242,
        92345, 92400, 92430, 92465, 92484, 92582, 92840, 93034, 93175, 93470, 93518, 93539,
        93668, 93702, 93939, 93960, 94125, 94262, 94824, 94870, 95056, 95057, 95216, 95257,
        95273, 95350, 95361, 95364, 95367, 95419, 95425, 95575, 95675, 95737, 95901, 95916,
        95930, 96025, 96114, 96127, 96358, 96536, 96572, 96650, 96907, 96919, 96980, 97008,
        97091, 97104, 97116, 97155, 97177, 97253, 97289, 97292, 97328, 97456, 97572, 97577,
        97586, 97652, 97657, 97670, 97708, 97766, 97976, 98165, 98194, 98320, 98323, 98379,
        98846, 98894, 98922, 99040, 99381, 99474, 99707, 100485, 100752, 100812, 101116, 101186,
        101195, 101315, 101518, 101616, 101651, 101813, 101915, 102545, 102583, 102647, 102704, 103834,
        103887, 103896, 104034, 104517, 104527, 104875, 105875, 105972, 107139, 107333, 107807, 108017,
        108172, 108280, 108332, 108650, 108871, 109155, 109180, 109278, 109503, 109579, 109676, 109695,
        112362, 112826, 113277, 113821, 113880, 113971, 114011, 114087, 114095, 114256, 114257, 114278,
        115607, 115695, 116046, 116090, 116388, 117246, 117973, 118022, 118085, 118087, 118098, 118120,
        119391, 122050, 122215, 122233, 122237, 122288, 122302, 122327, 122336, 122386, 122457, 122488,
        122498, 122504, 122519, 122556, 122601, 122687, 122733, 123013, 123029, 123030, 123057, 123061,
        123116, 123219, 123442, 123444, 123461, 123519, 123535, 123636
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'dagger citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM dagger_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING dagger_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 24 local citers name the method in title or abstract.
CREATE TEMP TABLE dagger_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dagger'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        23636, 23874, 26015, 55115, 56057, 56487, 58018, 58398, 68341, 68378, 70045, 83132,
        84185, 86311, 88641, 91288, 91553, 95189, 97969, 98919, 100574, 103946, 106982, 114279
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dagger_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM dagger_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 28 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE dagger_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dagger'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        23636, 23874, 26015, 55115, 56057, 56487, 58018, 58398, 63743, 68341, 68378, 70045,
        81832, 83132, 84185, 85594, 86311, 88641, 91288, 91553, 95189, 97969, 98919, 100574,
        103946, 106982, 114279, 117999
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dagger_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM dagger_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
