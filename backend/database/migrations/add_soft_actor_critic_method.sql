-- Add Soft Actor-Critic, introduced in arXiv 1801.01290.
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
    'soft-actor-critic',
    'Soft Actor-Critic',
    'Soft Actor-Critic (SAC)',
    'Soft Actor-Critic (SAC) is an off-policy actor-critic deep reinforcement learning algorithm based on the maximum entropy framework: the actor maximizes expected reward while also maximizing the entropy of its stochastic policy, i.e. it tries to succeed at the task while acting as randomly as possible. Earlier maximum-entropy deep RL methods were formulated as Q-learning; SAC combines off-policy updates from a replay buffer with a stable stochastic actor-critic formulation, learning a soft Q-function and state-value function together with a reparameterized stochastic policy. On continuous-control benchmarks it outperformed prior on-policy ([PPO](/methods/ppo)) and off-policy (DDPG, TD3) methods and, unlike other off-policy algorithms, achieved very similar performance across random seeds. A follow-up, [Soft Actor-Critic Algorithms and Applications](/paper/1812.05905), added automatic entropy-temperature tuning and real-robot results. SAC is a default baseline for continuous control, robot learning and [offline RL](/methods/offline-rl), alongside value-based methods such as [DQN](/methods/dqn).',
    'soft actor-critic, soft actor critic',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2018,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1801.01290'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement Learning with a Stochastic Actor',
    'https://github.com/haarnoja/sac',
    NULL,
    '[Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement Learning with a Stochastic Actor](/paper/1801.01290)'
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
WHERE slug = 'soft-actor-critic' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'soft-actor-critic' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 988 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE soft_actor_critic_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'soft-actor-critic'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        1128, 1201, 1486, 2433, 2687, 2719, 2892, 3013, 3232, 3363, 3518, 3551,
        3565, 3608, 3809, 3889, 4455, 4563, 4567, 4878, 4967, 5059, 5220, 5346,
        5397, 5434, 5465, 6005, 6120, 6166, 6176, 6354, 6361, 6362, 6379, 6511,
        6808, 6957, 7008, 7120, 7155, 7180, 7201, 7233, 7373, 7428, 7731, 7753,
        7804, 7915, 7969, 8402, 8555, 9083, 9280, 9307, 9371, 9405, 9441, 9465,
        9534, 9556, 9615, 9621, 9786, 9850, 9852, 9877, 9892, 9932, 10065, 10186,
        10294, 10307, 10402, 10417, 10483, 10498, 10539, 10719, 10798, 11026, 11241, 11310,
        11408, 11440, 11467, 11583, 11668, 11683, 12187, 12204, 12295, 12363, 12568, 12609,
        12667, 12734, 12783, 12817, 12870, 12882, 12883, 12908, 12941, 13006, 13063, 13105,
        13157, 13302, 13313, 13429, 13486, 13540, 13548, 13556, 13680, 13879, 14073, 14290,
        14373, 14536, 14809, 14914, 14977, 15073, 15223, 15227, 15381, 15517, 15634, 15639,
        15712, 15922, 15998, 15999, 16033, 16351, 16387, 16426, 16448, 16449, 16492, 16525,
        16528, 16557, 16593, 16670, 16671, 16739, 16760, 16802, 16842, 16937, 17000, 17023,
        17039, 17158, 17266, 17321, 17412, 17420, 17450, 17508, 17515, 17589, 17640, 17647,
        17678, 17779, 17875, 18028, 18080, 18236, 18452, 18544, 18665, 18740, 18772, 18856,
        18918, 19101, 19276, 19624, 19854, 19958, 19998, 20069, 20167, 20266, 20341, 20687,
        20857, 20950, 21045, 21063, 21064, 21148, 21155, 21284, 21289, 21320, 21376, 21380,
        21386, 21420, 21439, 21506, 21520, 21770, 21839, 21875, 21936, 21949, 22120, 22214,
        22227, 22297, 22651, 22661, 22739, 22776, 22805, 22814, 22818, 22915, 22924, 22935,
        23002, 23250, 23431, 23529, 23607, 23636, 24012, 24219, 24396, 24505, 25028, 25282,
        25540, 25582, 25759, 26038, 26086, 26090, 26119, 26207, 26220, 26249, 26336, 26407,
        26726, 26803, 26813, 26881, 27126, 27161, 27583, 27616, 27619, 27776, 27809, 27994,
        28104, 28106, 28209, 28245, 28283, 28360, 28638, 28842, 29559, 29970, 30033, 30213,
        30286, 30430, 30526, 30572, 30683, 30784, 30786, 30830, 30869, 30984, 31003, 31361,
        31522, 31545, 31553, 31656, 31726, 31816, 31910, 32054, 32058, 32344, 32420, 32556,
        32664, 32949, 33213, 33966, 34244, 34469, 34488, 34567, 34690, 34886, 35206, 35476,
        35537, 35637, 35731, 35972, 36459, 37033, 37433, 37703, 37871, 37966, 38318, 38319,
        38532, 38549, 38814, 38821, 38861, 38862, 38887, 39011, 39068, 39132, 39232, 39354,
        39487, 39533, 39649, 40346, 40933, 41121, 41333, 41576, 41766, 41791, 41996, 42796,
        42982, 43296, 43323, 43489, 43490, 43560, 43684, 43704, 44230, 44759, 44781, 45259,
        45263, 45558, 45763, 45872, 46043, 46663, 46697, 46906, 46937, 47026, 47370, 47421,
        47466, 47981, 47988, 48126, 48204, 48349, 48681, 49149, 49262, 49283, 49444, 49664,
        49767, 49886, 49995, 50020, 50281, 50667, 50783, 51237, 51276, 51543, 51790, 51834,
        52001, 52407, 52710, 52747, 52799, 52800, 52854, 52856, 52954, 52955, 52980, 53284,
        53318, 53401, 53489, 53917, 54289, 54394, 54504, 54843, 54907, 54935, 55067, 55145,
        55158, 55237, 55554, 55582, 55740, 55797, 55908, 56091, 56101, 56278, 56417, 56894,
        57402, 57419, 57543, 57836, 57996, 58029, 58088, 58192, 58993, 59311, 59393, 59561,
        59805, 60018, 60194, 60226, 60289, 60321, 60539, 60719, 60958, 61326, 61360, 61399,
        61423, 61543, 61969, 62022, 62281, 62363, 62382, 62644, 62775, 62936, 63030, 63175,
        63178, 63220, 63258, 63763, 63846, 64112, 64132, 64134, 64155, 64321, 64373, 64646,
        64783, 64822, 64863, 65067, 65310, 65532, 66113, 66297, 66487, 66590, 66731, 67163,
        67307, 67383, 67405, 67688, 67802, 67872, 67921, 67957, 68167, 68335, 68697, 68874,
        69170, 69192, 69334, 69514, 69614, 69626, 69684, 70038, 70126, 70282, 70385, 70667,
        70675, 71303, 71417, 71520, 71827, 71854, 72999, 73033, 73042, 73049, 73078, 73079,
        73086, 73672, 74238, 74259, 74341, 74374, 74416, 74420, 74829, 74929, 75044, 75166,
        75671, 75762, 75824, 75937, 76020, 76160, 76165, 76333, 76387, 76451, 76802, 76858,
        76864, 77033, 77075, 77135, 77150, 77509, 77538, 77632, 77639, 77752, 77801, 77933,
        78054, 78068, 78165, 78403, 78409, 78414, 78421, 78490, 78841, 78867, 78988, 79013,
        79088, 79113, 79217, 79339, 79362, 79580, 79832, 80235, 80238, 80498, 80675, 80684,
        80822, 80853, 80861, 80879, 80922, 80933, 81276, 82071, 82899, 82909, 82927, 82947,
        83290, 83503, 84124, 84152, 85676, 85696, 85739, 85761, 85763, 85775, 85805, 85835,
        85841, 85901, 85912, 85956, 86011, 86021, 86060, 86117, 86124, 86130, 86188, 86311,
        86401, 86410, 86429, 86441, 86507, 86538, 86583, 86652, 86730, 86831, 86886, 86937,
        86951, 86959, 87071, 87080, 87136, 87137, 87356, 87399, 87441, 87462, 87819, 88127,
        88594, 88606, 88627, 88635, 88753, 88754, 88775, 88823, 88894, 88918, 89048, 89082,
        89098, 89106, 89109, 89122, 89175, 89179, 89209, 89267, 89386, 89401, 89411, 89443,
        89520, 89536, 89562, 89565, 89623, 89643, 89647, 89664, 89675, 89700, 89734, 89772,
        89833, 89857, 89951, 89979, 90016, 90021, 90781, 90852, 90897, 91075, 91081, 91127,
        91191, 91201, 91204, 91233, 91237, 91297, 91340, 91367, 91371, 91377, 91383, 91418,
        91433, 91447, 91464, 91472, 91518, 91629, 91635, 91682, 91731, 91757, 91814, 91829,
        91842, 91846, 91908, 91925, 92007, 92023, 92074, 92123, 92138, 92183, 92213, 92227,
        92313, 92390, 92391, 92430, 92528, 92606, 92661, 92694, 92706, 92799, 92804, 92815,
        92825, 92861, 92876, 92891, 92898, 92920, 92930, 92940, 92956, 93042, 93089, 93165,
        93175, 93185, 93188, 93216, 93227, 93247, 93429, 93446, 93451, 93485, 93498, 93539,
        93568, 93608, 93635, 93668, 93768, 93798, 93854, 93875, 93880, 93898, 93949, 93988,
        94030, 94116, 94129, 94324, 94405, 94447, 94455, 94476, 94582, 94631, 94663, 94739,
        94740, 94823, 94828, 94837, 95062, 95156, 95189, 95249, 95317, 95350, 95362, 95388,
        95465, 95471, 95501, 95528, 95529, 95573, 95679, 95732, 96057, 96210, 96374, 96429,
        96437, 96468, 96530, 96581, 96699, 96711, 96796, 96799, 96980, 97081, 97091, 97110,
        97165, 97166, 97189, 97214, 97269, 97316, 97344, 97506, 97538, 97683, 97738, 97742,
        97779, 97783, 97801, 98129, 98147, 98225, 98367, 98518, 98793, 98830, 99043, 99107,
        99140, 99148, 99196, 99221, 99240, 99256, 99275, 99366, 99407, 99459, 99474, 99572,
        99582, 99724, 99862, 99896, 99988, 100001, 100073, 100149, 100159, 100210, 100241, 100251,
        100339, 100395, 100418, 100419, 100435, 100467, 100509, 100540, 100559, 100561, 100572, 100589,
        100600, 100604, 100609, 100633, 100678, 100769, 100771, 100772, 100900, 100965, 100990, 101031,
        101104, 101184, 101218, 101250, 101289, 101356, 101403, 101424, 101472, 101483, 101501, 101525,
        101526, 101543, 101549, 101565, 101616, 101626, 101651, 101702, 101719, 101721, 101726, 101728,
        101765, 101829, 101915, 101923, 101954, 102047, 102109, 102295, 102354, 102359, 102404, 102528,
        102530, 102534, 103431, 103887, 104387, 105875, 106415, 106452, 106483, 106606, 106746, 106835,
        106881, 106900, 106946, 106990, 107104, 107193, 107275, 107298, 107333, 107386, 107411, 107661,
        107672, 107707, 107714, 108173, 108359, 108413, 108442, 109561, 109767, 110280, 110549, 112947,
        113467, 114216, 114974, 115481, 115632, 116641, 118599, 118867, 119597, 122052, 122056, 122278,
        122476, 122855, 122884, 123426
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'soft-actor-critic citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM soft_actor_critic_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING soft_actor_critic_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 50 local citers name the method in title or abstract.
CREATE TEMP TABLE soft_actor_critic_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'soft-actor-critic'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        5528, 5976, 6795, 7045, 8346, 8806, 10340, 11699, 12192, 12708, 16004, 17580,
        21653, 25329, 29939, 38345, 38385, 38609, 41214, 43769, 44746, 50696, 52110, 53386,
        55516, 55927, 56844, 68773, 71981, 75546, 78848, 79727, 79755, 80563, 80603, 85764,
        88986, 89026, 89163, 92626, 93143, 93194, 94957, 95024, 95164, 95780, 95845, 96983,
        101094, 101464
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM soft_actor_critic_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM soft_actor_critic_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 49 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE soft_actor_critic_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'soft-actor-critic'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        1702, 2686, 2985, 3435, 3599, 3771, 5528, 6795, 8806, 10340, 10424, 11699,
        12192, 12708, 16004, 17580, 21653, 25329, 29939, 38345, 38609, 41214, 44746, 52110,
        55927, 56844, 71981, 78848, 79727, 80563, 88986, 89026, 89163, 94848, 95024, 95164,
        95780, 95845, 96659, 97358, 97597, 97772, 97870, 98761, 101094, 101464, 102138, 105839,
        107659
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM soft_actor_critic_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM soft_actor_critic_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
