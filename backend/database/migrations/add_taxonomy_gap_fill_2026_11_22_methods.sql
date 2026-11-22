-- Chat lookup-miss taxonomy gap fill (2026-11-20 and 2026-11-22 chat health
-- audits): three methods that production chat looked up with pwc_get_method
-- and did not find, plus lookup keywords for existing methods.
--
-- pwc_get_method resolves a reference by name, full name or slug and then by a
-- keyword that exactly one method carries. It never reads methods.aliases, so
-- abbreviations users type (TSDF, ResNet-50) must be method keywords to
-- resolve. Cascade Mask R-CNN is the instance-segmentation form of Cascade
-- R-CNN, so it is a keyword and alias of the cascade-r-cnn method rather than
-- a method of its own.
--
-- Paper links from the new keywords and from citations of the source papers
-- were reviewed; reviewed negatives become durable exclusions at the end of
-- this file. Hero images were imported separately with import_entity_image.py.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES
(
    'double-dqn',
    'Double DQN',
    'Double Deep Q-Network (Double DQN)',
    'Double DQN reduces the overestimation bias of [DQN](/methods/dqn) by decoupling action selection from action evaluation in the bootstrap target. Standard [Q-learning](/methods/q-learning) uses the same max over noisy value estimates to both pick and score the next action, which systematically overestimates values. Double DQN adapts Double Q-learning to deep networks with almost no extra cost: the online network chooses the greedy next action and the periodically updated target network evaluates it, giving the target r + γ Q_target(s'', argmax_a Q_online(s'', a)). On Atari it produced more accurate value estimates, more stable learning and higher scores than DQN, and it became a standard component of later value-based agents such as Dueling DQN and Rainbow.',
    'Double DQN, DDQN, double deep q-network, double deep q-learning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2015,
    (SELECT id FROM papers WHERE arxiv_id = '1509.06461'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Deep Reinforcement Learning with Double Q-learning',
    NULL,
    NULL,
    '[Deep Reinforcement Learning with Double Q-learning](/paper/1509.06461)',
    'always',
    ARRAY['Double Deep Q-Network', 'Double Deep Q-Learning']
),
(
    'graphsage',
    'GraphSAGE',
    'GraphSAGE (SAmple and aggreGatE)',
    'GraphSAGE is an inductive framework for learning node embeddings on large graphs. Instead of learning a separate embedding for every node, as transductive methods such as DeepWalk do, it learns aggregator functions that build a node''s representation from a fixed-size sample of its neighbours'' features, layer by layer, so it can embed nodes and whole graphs never seen during training. Aggregators include mean, LSTM and max-pooling, and the concatenation of a node''s own representation with the aggregated neighbourhood plays the role of a skip connection. Neighbour sampling keeps the cost per node bounded, which made mini-batch training of [graph neural networks](/methods/graph-neural-network) practical on graphs with millions of nodes. It is a standard baseline next to [GCN](/methods/gcn) and [GAT](/methods/graph-attention-network) and underlies production recommender systems such as PinSage.',
    'GraphSAGE, GraphSage, graph sage',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2017,
    (SELECT id FROM papers WHERE arxiv_id = '1706.02216'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Inductive Representation Learning on Large Graphs',
    'https://github.com/williamleif/GraphSAGE',
    NULL,
    '[Inductive Representation Learning on Large Graphs](/paper/1706.02216)',
    'always',
    ARRAY[]::text[]
),
(
    'cascade-r-cnn',
    'Cascade R-CNN',
    'Cascade R-CNN',
    'Cascade R-CNN is a multi-stage object detector that trains a sequence of detection heads with increasing IoU thresholds (for example 0.5, 0.6 and 0.7). A single [Faster R-CNN](/methods/faster-r-cnn) head trained at IoU 0.5 produces noisy, loosely localized boxes, but simply raising the threshold overfits because few proposals are that accurate. In the cascade, each stage refines the boxes of the previous one, so the next stage receives a higher-quality distribution of proposals and can be trained at a stricter threshold, and at inference the same cascade is applied. This yields large gains in high-IoU average precision on COCO with any backbone. Cascade Mask R-CNN adds a [Mask R-CNN](/methods/mask-r-cnn) mask branch to the cascade for instance segmentation, and both are standard strong baselines in detection toolkits such as MMDetection and Detectron2.',
    'Cascade R-CNN, Cascade RCNN, Cascade Mask R-CNN, Cascade Mask RCNN',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2017,
    (SELECT id FROM papers WHERE arxiv_id = '1712.00726'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Cascade R-CNN: Delving into High Quality Object Detection',
    'https://github.com/zhaoweicai/cascade-rcnn',
    NULL,
    '[Cascade R-CNN: Delving into High Quality Object Detection](/paper/1712.00726)',
    'always',
    ARRAY['Cascade Mask R-CNN']
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN ('double-dqn', 'graphsage', 'cascade-r-cnn')
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

-- Lookup keywords for existing methods. "CNN" and "convolutional neural
-- network" also sat on the convolution method, so neither lookup was unique
-- and "convolutional neural network" resolved to nothing; they now belong to
-- CNN alone. ICP is deliberately not a keyword of iterative-closest-point:
-- capitalised method keywords match as substrings, and "ICP" would tag ICPC
-- coding benchmarks, in-context policy (ICP) papers and similar.
UPDATE methods SET keywords = 'convolution', updated_at = CURRENT_TIMESTAMP
WHERE slug = 'convolution';

UPDATE methods SET
    keywords = 'VAE, variatonal autoencoder, variatonal auto-encoder, variational autoencoder, variational auto-encoder, auto-encoding variational bayes, AEVB',
    aliases = ARRAY['Auto-Encoding Variational Bayes (AEVB)'],
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'vae';

UPDATE methods SET
    keywords = 'resnet, resnet-18, resnet-34, resnet-50, resnet-101, resnet-152, resnet18, resnet34, resnet50, resnet101, resnet152',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'resnet';

UPDATE methods SET
    keywords = 'signed distance function, signed distance functions, signed distance field, signed distance fields, TSDF, truncated signed distance function, truncated signed distance functions, truncated signed distance field, truncated signed distance fields',
    aliases = ARRAY['Signed Distance Field', 'Neural SDF', 'Neural Signed Distance Function', 'Truncated Signed Distance Function (TSDF)'],
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'signed-distance-function';

-- Reviewed citers of the three source papers that do not name the method in
-- their title or abstract. The hourly reference backfill would link them.

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT p.id, m.id, 'taxonomy gap fill 2026-11-22 citation review: cites the source without naming the method in title or abstract'
FROM unnest(ARRAY[
    271, 301, 395, 531, 569, 759, 809, 896, 903, 1021, 1184, 1310, 1344,
    1624, 1792, 1888, 2876, 2985, 3321, 3435, 3551, 3835, 3882, 4597, 4638,
    4878, 5528, 5753, 5764, 5976, 6067, 6166, 6433, 6808, 6848, 7107, 7167,
    7677, 8112, 8194, 8239, 9038, 9232, 9280, 9297, 9371, 9441, 9537, 9781,
    9877, 10038, 10064, 10377, 10769, 11015, 12545, 12708, 12735, 12742,
    12882, 13078, 13450, 13477, 13877, 14473, 15000, 15137, 16341, 16448,
    16489, 16631, 16855, 17289, 17678, 17731, 18544, 19001, 21135, 21284,
    21420, 21439, 21653, 21679, 22568, 22805, 23463, 23933, 24012, 24396,
    25485, 25833, 25904, 25908, 26525, 26756, 27616, 27619, 27809, 27930,
    28209, 28360, 28722, 28830, 30777, 31553, 33174, 33595, 33620, 33666,
    34886, 35792, 36850, 36935, 38385, 40346, 41701, 42982, 43025, 43184,
    43490, 43598, 45379, 45400, 47026, 49130, 49283, 49624, 52001, 52826,
    53013, 53401, 53697, 53917, 57838, 60075, 63209, 64822, 65377, 67518,
    67688, 67921, 68209, 69475, 69506, 70270, 70389, 71042, 71079, 71854,
    74420, 75671, 77316, 77752, 78270, 78527, 78962, 78969, 79228, 79559,
    79580, 79727, 79795, 79892, 79976, 80097, 80197, 80238, 80466, 80675,
    81214, 81437, 81458, 81581, 81587, 81604, 82059, 82161, 82276, 82423,
    82454, 83259, 85764, 85841, 85857, 85888, 86652, 87317, 87454, 88587,
    88618, 88635, 88754, 89098, 89519, 89675, 89758, 89770, 89857, 90238,
    91314, 91325, 91629, 91777, 91814, 92312, 92313, 92815, 92930, 93021,
    93042, 93124, 93240, 93264, 93267, 93328, 93498, 93742, 94023, 94294,
    94364, 94629, 94820, 95024, 95831, 96508, 96684, 97250, 97269, 99256,
    99605, 99806, 100965, 101184, 101337, 101909, 101932, 102127, 103892,
    103990, 105548, 105875, 106891, 106930, 107393, 124658, 124829, 125062,
    125684, 129494, 129709, 130773, 130828, 130879, 132474, 132670, 132690
]::bigint[]) AS v(paper_id)
JOIN papers p ON p.id = v.paper_id
JOIN methods m ON m.slug = 'double-dqn'
ON CONFLICT (paper_id, method_id) DO NOTHING;

DELETE FROM paper_methods pm
USING paper_method_exclusions e, methods m
WHERE m.slug = 'double-dqn' AND e.method_id = m.id AND pm.method_id = m.id
  AND pm.paper_id = e.paper_id AND e.reason = 'taxonomy gap fill 2026-11-22 citation review: cites the source without naming the method in title or abstract';

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT p.id, m.id, 'taxonomy gap fill 2026-11-22 citation review: cites the source without naming the method in title or abstract'
FROM unnest(ARRAY[
    26578, 26591, 26648, 26744, 26760, 26768, 27074, 27082, 27126, 27166,
    27226, 27241, 27272, 27466, 27526, 27664, 27756, 27793, 27943, 28021,
    28306, 28317, 28544, 28572, 28898, 28969, 29342, 29669, 30049, 30554,
    30616, 30810, 31147, 31312, 31541, 31553, 31797, 31862, 31944, 31993,
    32610, 32792, 32824, 32982, 33565, 33903, 34675, 34719, 34795, 34830,
    34854, 35022, 35303, 35386, 35914, 36083, 36123, 36156, 36767, 37280,
    37617, 37745, 37910, 38185, 38337, 38455, 38494, 38742, 39675, 39907,
    39977, 40171, 40331, 40358, 40378, 40787, 40866, 40899, 41438, 41632,
    41685, 41711, 42021, 42024, 42154, 42213, 42379, 42475, 42871, 43177,
    43728, 44547, 44660, 44841, 45168, 45343, 45520, 45928, 47113, 47604,
    48082, 48151, 48209, 48368, 49223, 49525, 49618, 49966, 50686, 50938,
    51403, 55850, 55994, 56111, 56198, 56461, 57321, 58052, 58272, 58306,
    59334, 59991, 60006, 60669, 61595, 62976, 63078, 63339, 63608, 63709,
    63711, 63993, 64354, 64458, 64560, 64757, 64937, 64957, 65147, 65360,
    65394, 65423, 65767, 65836, 65926, 66065, 66472, 66653, 66908, 67599,
    67670, 68087, 68834, 69059, 69205, 69393, 69452, 69546, 69874, 69953,
    70081, 70656, 70760, 71318, 71447, 72412, 72469, 72607, 72673, 72883,
    73185, 73473, 73484, 73516, 73783, 74286, 74442, 74470, 74617, 74645,
    74716, 74732, 74745, 75073, 75167, 75397, 75487, 75655, 75917, 76668,
    76760, 77052, 77062, 77115, 77147, 77225, 77273, 77289, 77366, 77614,
    77854, 83815, 84308, 84608, 84893, 85003, 85379, 85744, 85757, 85899,
    85947, 85979, 86166, 86175, 86199, 86272, 86316, 86449, 86477, 86523,
    86617, 86632, 86786, 86931, 86960, 86972, 87121, 87124, 87143, 87156,
    87171, 87188, 87189, 87389, 87438, 87928, 88601, 88664, 88684, 88815,
    88957, 88962, 88978, 89049, 89097, 89110, 89135, 89181, 89202, 89224,
    89330, 89355, 89471, 89516, 89517, 89524, 89529, 89557, 89648, 89652,
    89712, 89797, 89800, 89882, 89944, 90027, 90092, 90561, 90645, 90662,
    90668, 91062, 91154, 91172, 91174, 91214, 91216, 91281, 91317, 91318,
    91376, 91378, 91385, 91421, 91487, 91525, 91587, 91599, 91611, 91615,
    91625, 91661, 91662, 91678, 91683, 91694, 91710, 91822, 91841, 91867,
    91887, 91927, 91944, 91957, 91960, 92027, 92249, 92275, 92318, 92346,
    92375, 92386, 92417, 92424, 92610, 92747, 92752, 92957, 93092, 93110,
    93252, 93307, 93313, 93381, 93551, 93575, 93599, 93716, 93813, 93928,
    93997, 94038, 94071, 94295, 94314, 94695, 94767, 94844, 94990, 98790,
    98976, 99102, 99129, 99149, 99158, 99159, 99161, 99303, 99348, 99353,
    99419, 99532, 99593, 99746, 99786, 99868, 100037, 100103, 100108,
    100158, 100168, 100171, 100183, 100322, 100433, 100491, 100528, 100639,
    100669, 100679, 100686, 100718, 100728, 100740, 100845, 100914, 100968,
    101023, 101072, 101077, 101089, 101115, 101153, 101208, 101225, 101281,
    101409, 101431, 101460, 101467, 101590, 101653, 101802, 101846, 102002,
    102054, 102132, 102263, 102308, 102317, 102361, 102434, 102538, 102744,
    103050, 103405, 103639, 103739, 104510, 104789, 104919, 105203, 106404,
    106513, 106643, 106652, 106680, 106696, 106700, 106704, 106709, 106730,
    106791, 106856, 106871, 106897, 106939, 107145, 107147, 107193, 107194,
    107204, 107214, 107350, 107370, 107446, 107543, 107702, 107903, 108035,
    108144, 108147, 108234, 108271, 108386, 108413, 108516, 108538, 109235,
    110208, 110609, 110801, 110831, 110897, 112232, 112418, 112518, 113160,
    113198, 113271, 113637, 114490, 115265, 115573, 116356, 116440, 117138,
    117756, 117796, 119118, 119520, 119611, 120244, 123676, 124541, 124572,
    124910, 124911, 124954, 125000, 125164, 125401, 125713, 126198, 126320,
    126511, 126624, 126687, 126858, 126911, 127031, 127276, 128001, 128002,
    128063, 128991, 129056, 129462, 130262, 130452, 130515, 130634, 130935,
    131085, 131116, 131284, 132906, 133246
]::bigint[]) AS v(paper_id)
JOIN papers p ON p.id = v.paper_id
JOIN methods m ON m.slug = 'graphsage'
ON CONFLICT (paper_id, method_id) DO NOTHING;

DELETE FROM paper_methods pm
USING paper_method_exclusions e, methods m
WHERE m.slug = 'graphsage' AND e.method_id = m.id AND pm.method_id = m.id
  AND pm.paper_id = e.paper_id AND e.reason = 'taxonomy gap fill 2026-11-22 citation review: cites the source without naming the method in title or abstract';

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT p.id, m.id, 'taxonomy gap fill 2026-11-22 citation review: cites the source without naming the method in title or abstract'
FROM unnest(ARRAY[
    1665, 1678, 1742, 1864, 1963, 1980, 2045, 2052, 2090, 2273, 2352, 2408,
    2440, 2528, 2819, 2827, 2834, 2902, 3008, 3180, 3378, 3396, 3539, 3658,
    3922, 3987, 4016, 4612, 4730, 4785, 4789, 4905, 4955, 4970, 5087, 5140,
    5167, 5279, 5548, 5581, 5691, 6008, 6123, 6164, 6168, 6419, 6431, 6540,
    6651, 6739, 6917, 7037, 7043, 7168, 7229, 7259, 7274, 7282, 7316, 7331,
    7388, 7389, 7431, 7475, 7563, 7658, 7673, 7911, 7949, 7961, 8143, 8383,
    8688, 8721, 8722, 8724, 8762, 8767, 8849, 8904, 9220, 9628, 9866, 9931,
    10214, 10215, 10469, 10550, 10760, 11031, 11297, 11308, 11327, 11470,
    11587, 11735, 11933, 11982, 11988, 12015, 12208, 12303, 12559, 12606,
    13108, 13244, 13264, 13402, 13480, 13787, 13790, 13806, 14118, 14142,
    14172, 14288, 14487, 14531, 14564, 14629, 14668, 14736, 14898, 15340,
    15495, 15530, 15625, 15738, 17033, 17133, 17182, 17196, 17366, 17542,
    18123, 18323, 18478, 18624, 18835, 18902, 18933, 18993, 19003, 19010,
    19059, 19117, 19309, 19376, 19718, 19848, 19890, 19897, 20067, 20226,
    20510, 20693, 21275, 21361, 21797, 22078, 22343, 22533, 22783, 22852,
    22973, 23470, 23560, 24056, 24612, 24618, 24671, 24706, 24772, 24984,
    25290, 25570, 25729, 25926, 26342, 26461, 26527, 27029, 27052, 27195,
    27814, 28201, 28921, 29053, 29104, 29284, 29333, 29899, 29940, 30541,
    30739, 30822, 31318, 32103, 32274, 32361, 32458, 32568, 33148, 34123,
    34742, 35180, 35422, 35602, 35938, 37509, 38084, 38856, 39916, 40448,
    42815, 45147, 45793, 46304, 47002, 47151, 47185, 47229, 47877, 48318,
    48557, 51074, 51818, 51827, 52057, 52074, 54315, 58320, 59627, 63949,
    64007, 64794, 65268, 68023, 68894, 69195, 69436, 69883, 70780, 71190,
    71565, 71631, 71924, 72041, 72042, 72433, 73758, 74078, 74676, 75262,
    76517, 76733, 77459, 77596, 77599, 77658, 78079, 78429, 79122, 79979,
    80139, 80564, 80621, 80633, 80712, 80800, 80802, 80828, 80878, 80913,
    80948, 81535, 83666, 84949, 86032, 86412, 87622, 87623, 87652, 88165,
    88287, 88302, 88362, 89555, 90229, 90328, 91013, 91723, 92068, 94240,
    98031, 98277, 98772, 98795, 103857, 104321, 104323, 105419, 106595,
    106842, 106867, 107681, 107705, 107841, 107978, 109323, 109882, 112521,
    112537, 112562, 112590, 112728, 112816, 112924, 112978, 113182, 113224,
    113371, 113943, 114098, 114143, 114384, 114434, 115688, 116301, 116306,
    116373, 116797, 116869, 116897, 117080, 118108, 118795, 118799, 119005,
    119111, 120335, 120627, 123325, 123737, 123869, 124118
]::bigint[]) AS v(paper_id)
JOIN papers p ON p.id = v.paper_id
JOIN methods m ON m.slug = 'cascade-r-cnn'
ON CONFLICT (paper_id, method_id) DO NOTHING;

DELETE FROM paper_methods pm
USING paper_method_exclusions e, methods m
WHERE m.slug = 'cascade-r-cnn' AND e.method_id = m.id AND pm.method_id = m.id
  AND pm.paper_id = e.paper_id AND e.reason = 'taxonomy gap fill 2026-11-22 citation review: cites the source without naming the method in title or abstract';
