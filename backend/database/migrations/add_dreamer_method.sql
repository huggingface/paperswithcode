-- Add Dreamer method, introduced in arXiv 1912.01603. The source paper
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
    'dreamer',
    'Dreamer',
    'Dreamer',
    'Dreamer is a model-based reinforcement learning agent that learns behaviors purely by latent imagination. From past experience it learns a world model, a recurrent state-space model (RSSM) that encodes image observations into compact latent states and predicts future latents and rewards. An actor and a value network are then trained entirely on trajectories imagined in this latent space, and the actor is optimized by backpropagating analytic gradients of the predicted multi-step values through the learned dynamics. Dreamer outperformed earlier model-based and model-free agents in data efficiency, compute time and final performance on 20 visual DeepMind Control Suite tasks. DreamerV2 added discrete latents and reached human-level Atari performance, and [DreamerV3](/paper/2301.04104) used one fixed set of hyperparameters across domains and was the first algorithm to collect diamonds in Minecraft from scratch.',
    'DreamerV1, DreamerV2, DreamerV3, Dreamer agent',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2019,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1912.01603'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Dream to Control: Learning Behaviors by Latent Imagination',
    'https://github.com/danijar/dreamer',
    NULL,
    '[Dream to Control: Learning Behaviors by Latent Imagination](/paper/1912.01603)'
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
WHERE slug = 'dreamer'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'dreamer'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 555 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention Dreamer are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE dreamer_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dreamer'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        3321, 3833, 3882, 4205, 5161, 5215, 5348, 5434, 5465, 5561, 5924, 5938,
        6166, 6205, 6281, 6511, 6666, 6808, 7008, 7045, 7107, 7620, 7677, 7836,
        7921, 8164, 8194, 8555, 8773, 9417, 9534, 9602, 9631, 9656, 9786, 9940,
        10307, 10402, 10498, 10798, 10915, 11015, 11216, 11583, 12215, 12342, 12575, 12827,
        12909, 12941, 12966, 13006, 13070, 13088, 13307, 13517, 13551, 14409, 14485, 15087,
        15687, 15712, 16181, 16536, 16638, 16754, 17020, 17022, 17205, 17472, 17486, 17507,
        17508, 17647, 17678, 17706, 17783, 17867, 17882, 18028, 18452, 18472, 19130, 19251,
        19581, 19998, 21146, 21496, 21770, 21936, 22622, 22763, 22914, 23550, 23987, 24219,
        24422, 24457, 24632, 25028, 25063, 25282, 25505, 25540, 25908, 26038, 26335, 26867,
        27053, 27109, 27149, 27745, 27901, 28077, 28242, 28283, 28638, 28762, 28781, 28891,
        29059, 29207, 30227, 30286, 30314, 30526, 30559, 30752, 30898, 31089, 31455, 31553,
        31668, 31843, 31947, 32219, 32232, 32344, 32504, 32843, 32908, 33005, 33705, 33804,
        33962, 34033, 34488, 35582, 36268, 36282, 36482, 37056, 37859, 38209, 38318, 38319,
        38453, 38686, 38845, 38856, 38903, 39132, 39533, 39614, 39753, 39819, 40679, 40996,
        40999, 41070, 42223, 43563, 43677, 44343, 45123, 45986, 46043, 46053, 46430, 46663,
        47066, 47078, 47466, 47548, 47810, 47852, 47905, 47914, 48126, 48340, 48436, 49109,
        49162, 49268, 49827, 50639, 50642, 50964, 50967, 50974, 51185, 51351, 51437, 51532,
        51544, 51859, 51954, 52754, 52979, 53099, 53356, 53396, 53522, 53620, 53800, 54016,
        54032, 54079, 54172, 54197, 54299, 54343, 54455, 54574, 54720, 54727, 55013, 55021,
        55148, 55459, 55477, 55700, 55965, 56055, 56188, 56302, 56346, 56412, 56421, 56503,
        56509, 56521, 56583, 56613, 56904, 56958, 56976, 57043, 57115, 57204, 57215, 57233,
        57234, 57317, 57322, 57385, 57423, 57491, 57578, 57838, 58190, 58870, 58993, 59320,
        59444, 59510, 59813, 60438, 60767, 60841, 61403, 61459, 61693, 61771, 62192, 62382,
        62461, 62577, 62597, 62766, 62872, 63117, 63283, 63686, 63874, 64552, 64755, 64822,
        65199, 65276, 65537, 66014, 66202, 66594, 66902, 66923, 67033, 67203, 67215, 67872,
        68767, 69236, 69348, 69684, 69760, 70013, 70180, 70241, 70318, 70893, 71312, 71899,
        72028, 72268, 72407, 73079, 73292, 73373, 74219, 74773, 75001, 75152, 75166, 75411,
        75749, 76081, 76160, 76333, 76393, 77034, 77752, 77913, 78354, 78369, 78880, 79318,
        79892, 79908, 80019, 80238, 80877, 83232, 83259, 83289, 83484, 83606, 83695, 83760,
        84140, 84474, 84482, 84550, 84602, 85835, 85841, 85901, 85985, 86130, 86541, 86643,
        86959, 87141, 87354, 87512, 87529, 87760, 87840, 87912, 88024, 88080, 88228, 88281,
        88296, 88937, 89303, 89357, 89426, 89443, 89520, 89816, 89840, 89923, 90025, 90082,
        90237, 91033, 91034, 91075, 91090, 91204, 91389, 91433, 91441, 91515, 91606, 91730,
        92123, 92390, 92391, 92473, 92503, 92706, 92791, 92792, 92833, 92873, 93034, 93042,
        93089, 93158, 93971, 94063, 94070, 94324, 94750, 94848, 95310, 95726, 96210, 96340,
        96623, 96652, 96654, 97161, 97506, 97655, 97952, 98088, 98167, 98194, 98242, 98379,
        98396, 98461, 98503, 98762, 98850, 98852, 98860, 98874, 99043, 99140, 99277, 99366,
        99896, 99897, 100027, 100208, 100365, 100418, 100589, 101565, 102090, 102377, 102421, 102524,
        102528, 102533, 102576, 102600, 102630, 103254, 103942, 103943, 103952, 104224, 105993, 105997,
        106005, 106016, 106025, 106276, 106805, 106975, 106990, 107386, 107492, 108657, 108934, 108947,
        109045, 109048, 109102, 109377, 109588, 109643, 109664, 109687, 109695, 109806, 109812, 109848,
        110361, 112763, 113857, 113858, 114018, 114050, 114082, 114211, 116386, 117965, 117975, 117985,
        118000, 118026, 118102, 118103, 118120, 118867, 119436, 120475, 122052, 122373, 122571, 122704,
        122835, 122937, 122982, 123016, 123017, 123138, 123141, 123156, 123358
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'dreamer citation review 2026-10-15: cites the source paper without using the method'
FROM dreamer_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING dreamer_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING dreamer_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
