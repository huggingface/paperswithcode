-- Add VAR, introduced in arXiv 2404.02905.
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
    'var',
    'VAR',
    'Visual Autoregressive Modeling (VAR)',
    'Visual AutoRegressive modeling (VAR) is an image generation paradigm that redefines autoregressive learning on images as coarse-to-fine next-scale (or next-resolution) prediction instead of raster-scan next-token prediction. A multi-scale [VQ-VAE](/methods/vq-vae)-style tokenizer encodes an image into token maps at increasing resolutions, and a GPT-style [Transformer](/methods/transformer) predicts each whole token map conditioned on all coarser ones, generating the tokens of a scale in parallel. This lets AR models learn visual distributions fast and generalize well: for the first time GPT-like AR models surpass [diffusion transformers](/methods/diffusion-transformer-dit). On ImageNet 256x256, VAR improves the AR baseline from 18.65 to 1.73 FID and from 80.4 to 350.2 inception score with about 20x faster inference. VAR models show power-law [scaling laws](/methods/scaling-laws) with linear correlation coefficients near -0.998, and zero-shot generalization to in-painting, out-painting and editing. The paper received the NeurIPS 2024 Best Paper Award and spawned many next-scale prediction follow-ups for text-to-image, video and 3D.',
    'next-scale prediction, next scale prediction, next-scale autoregressive, scale-wise autoregressive, Visual AutoRegressive, Visual Autoregressive (VAR), Visual autoregressive (VAR), visual autoregressive (VAR), Visual Auto-Regressive (VAR), visual auto-regressive (VAR), Visual Autoregressive Modeling (VAR), Visual autoregressive modeling (VAR), Visual Autoregressive Models (VAR), visual autoregressive models (VAR)',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2024,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2404.02905'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Visual Autoregressive Modeling: Scalable Image Generation via Next-Scale Prediction',
    'https://github.com/FoundationVision/VAR',
    NULL,
    '[Visual Autoregressive Modeling: Scalable Image Generation via Next-Scale Prediction](/paper/2404.02905)'
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
WHERE slug = 'var' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'var' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 602 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE var_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'var'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        15767, 30711, 31553, 31804, 31859, 32314, 32640, 32852, 32894, 32906, 33169, 33850,
        33915, 34917, 35216, 36126, 36593, 36651, 36656, 36657, 36726, 36964, 37210, 37281,
        37677, 37684, 37701, 37791, 37808, 37865, 37868, 38083, 38264, 38351, 38468, 38501,
        38610, 38628, 38671, 38756, 38760, 38762, 38824, 38942, 39014, 39121, 39225, 39529,
        39605, 39722, 39819, 39867, 40103, 40136, 40296, 40450, 40467, 40469, 40546, 40602,
        40737, 40803, 40815, 40865, 40914, 40922, 40947, 41031, 41057, 41187, 41199, 41224,
        41253, 41257, 41319, 41479, 41534, 41589, 41855, 41907, 41914, 41953, 42064, 42223,
        42337, 42385, 42429, 42489, 42534, 42634, 42693, 42757, 43052, 43260, 43295, 43413,
        43622, 43710, 44049, 44154, 44385, 44426, 44430, 44511, 44837, 44949, 45117, 45174,
        45175, 45185, 45297, 45446, 45608, 45698, 45729, 45756, 45765, 45769, 45774, 45783,
        45805, 45867, 45870, 45896, 45909, 45956, 45981, 46018, 46045, 46059, 46096, 46125,
        46151, 46238, 46269, 46342, 46344, 46387, 46464, 46471, 46494, 46498, 46579, 46675,
        46712, 46739, 46794, 47132, 47183, 47193, 47239, 47249, 47263, 47325, 47461, 47571,
        47605, 47643, 47684, 47738, 47747, 47748, 47833, 48056, 48097, 48114, 48121, 48321,
        48403, 48498, 48507, 48535, 48544, 48637, 48660, 48843, 49068, 49072, 49281, 49325,
        49333, 49415, 49489, 49538, 49582, 49629, 49671, 49677, 49681, 49693, 49702, 49720,
        49730, 49857, 49864, 49949, 49999, 50134, 50356, 50377, 50434, 50493, 50716, 50717,
        50742, 50745, 50928, 50969, 51224, 51292, 51318, 51338, 51356, 51372, 51394, 51434,
        51450, 51491, 51606, 51633, 51643, 51668, 51712, 51758, 51830, 51841, 51852, 51862,
        51902, 51954, 52019, 52057, 52168, 52191, 52221, 52257, 52369, 52406, 52508, 52642,
        52654, 52821, 52837, 52845, 52860, 52861, 52874, 52934, 52987, 53041, 53108, 53132,
        53157, 53314, 53341, 53351, 53453, 53458, 53669, 53680, 53797, 53838, 53854, 53862,
        53958, 54419, 54426, 54509, 54545, 54567, 54637, 54644, 54650, 54713, 54732, 54773,
        54811, 54865, 54871, 54895, 54923, 54987, 55051, 55153, 55171, 55177, 55232, 55281,
        55347, 55401, 55415, 55629, 55633, 55848, 55957, 55966, 55978, 56119, 56127, 56306,
        56379, 56451, 56462, 56560, 56651, 56658, 56672, 56861, 56959, 57074, 57135, 57309,
        57322, 57466, 57475, 57557, 57687, 57705, 57841, 58159, 58497, 58722, 58904, 59011,
        59059, 59061, 59290, 59468, 59518, 59590, 59866, 60527, 60686, 60913, 60950, 61002,
        61011, 61189, 61225, 61229, 61234, 61333, 61550, 61766, 61794, 61806, 61844, 61872,
        61894, 62229, 62247, 62279, 63052, 63204, 63301, 63329, 63437, 63553, 63600, 63775,
        63810, 64150, 64171, 64247, 64483, 64496, 64525, 64574, 64891, 64935, 65143, 65237,
        65325, 65390, 65602, 65729, 65866, 65923, 65979, 65991, 66102, 66293, 66365, 66431,
        66493, 66609, 66895, 66929, 66956, 67013, 67149, 67189, 67191, 67315, 67431, 67524,
        67548, 67555, 68139, 68459, 68463, 68683, 68752, 68771, 68893, 69046, 69152, 69426,
        69450, 69736, 69790, 69798, 69891, 69941, 69974, 70026, 70305, 70892, 70929, 71134,
        71398, 71477, 71511, 71525, 71623, 72071, 72393, 72723, 72926, 73113, 73243, 73272,
        74113, 74615, 74660, 74685, 74773, 74842, 75007, 75152, 75631, 76006, 82925, 82967,
        83285, 83367, 83461, 83674, 83684, 83692, 83708, 83755, 83775, 83874, 83980, 84008,
        84081, 84175, 84184, 84230, 84454, 84486, 84529, 84581, 84769, 84786, 85123, 85180,
        85387, 85460, 85905, 86283, 86320, 86364, 86458, 86541, 86617, 86659, 86830, 86897,
        87655, 87696, 87705, 87842, 87939, 88002, 88027, 88080, 88093, 88166, 88182, 88350,
        88400, 88418, 88485, 89195, 89774, 89788, 90093, 90617, 90619, 90751, 90875, 90988,
        91005, 91313, 91453, 91640, 92666, 93762, 93899, 93941, 94246, 94879, 94912, 95007,
        95008, 95029, 95056, 97693, 98130, 98254, 98466, 98927, 98945, 99011, 99083, 99305,
        99963, 100014, 100124, 100190, 101508, 101634, 101777, 102105, 103447, 104556, 104788, 105031,
        105206, 105848, 107047, 107745, 107756, 107868, 108087, 108140, 108283, 108482, 109365, 109408,
        110790, 113365, 113803, 113950, 114166, 117410, 117423, 117434, 117691, 117702, 118108, 118362,
        118377, 118387, 118391, 118401, 118412, 118433, 118456, 118475, 118494, 118509, 118531, 118651,
        119110, 119146, 119229, 119356, 119377, 119450, 119510, 119546, 121289, 121486, 121565, 122089,
        122144, 122289, 122351, 122625, 122652, 122758, 122767, 122900, 122967, 123055, 123406, 123419,
        123534, 123590
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'var citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM var_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING var_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 72 local citers name the method in title or abstract.
CREATE TEMP TABLE var_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'var'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        32927, 33020, 35482, 40492, 40552, 40859, 41066, 41927, 43068, 45172, 46278, 46483,
        47008, 47596, 48657, 49754, 50100, 50585, 51699, 51975, 52059, 52466, 52620, 52702,
        54309, 54648, 54917, 55086, 55088, 55199, 55794, 57259, 57931, 57954, 58767, 63280,
        64778, 64938, 70689, 72967, 74151, 84289, 84435, 84505, 85266, 86748, 88196, 88493,
        93600, 93871, 94282, 94626, 94661, 94961, 96928, 99354, 100822, 101568, 101623, 102608,
        104960, 105056, 105280, 106837, 107018, 107398, 118038, 118533, 119285, 119478, 121371, 122916
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM var_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM var_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 81 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE var_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'var'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        32927, 35482, 40036, 40048, 40492, 40552, 40859, 41066, 41927, 42310, 42610, 43068,
        45172, 46278, 46483, 47008, 47596, 48657, 49754, 50100, 50585, 51699, 51975, 52059,
        52466, 52620, 52702, 54309, 54648, 54917, 55086, 55088, 55199, 55794, 57931, 57954,
        58767, 63280, 64778, 64938, 67206, 70689, 72967, 74151, 84289, 84435, 84505, 85266,
        86748, 88196, 88493, 89959, 93600, 93871, 94282, 94626, 94661, 94961, 95042, 96928,
        99354, 100822, 101568, 101623, 102608, 104960, 105056, 105185, 106837, 107018, 107398, 108573,
        118038, 118398, 118533, 119285, 121144, 121206, 121371, 121595, 122916
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM var_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM var_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
