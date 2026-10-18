-- Add Self Forcing, introduced in arXiv 2506.08009.
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
    'self-forcing',
    'Self Forcing',
    'Self Forcing',
    'Self Forcing is a training paradigm for autoregressive video [diffusion](/methods/diffusion) models that closes the train-test gap known as exposure bias. Under [Teacher forcing](/methods/teacher-forcing) and [Diffusion Forcing](/methods/diffusion-forcing), each frame is denoised from ground-truth or noised ground-truth context, but at inference the model must condition on its own imperfect outputs. Self Forcing instead performs the full autoregressive rollout during training with [KV caching](/methods/key-value-cache), conditioning every frame on previously self-generated frames. It then applies a holistic video-level distribution-matching loss such as [DMD](/methods/dmd), SiD or a GAN objective to the generated sequence. Training stays tractable through a few-step diffusion generator and stochastic gradient truncation, and a rolling KV cache allows efficient video extrapolation. Implemented on the [flow matching](/methods/flow-matching) model Wan2.1-T2V-1.3B, it generates video in real time at 17 FPS with sub-second latency on a single H100 GPU. Its quality matches or exceeds much slower bidirectional and non-causal diffusion models. It is widely used as the base recipe for streaming video and interactive world models.',
    'self forcing, self-forcing',
    (
        SELECT id
        FROM areas
        WHERE name = 'Video'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2506.08009'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Self Forcing: Bridging the Train-Test Gap in Autoregressive Video Diffusion',
    'https://github.com/guandeh17/Self-Forcing',
    NULL,
    '[Self Forcing: Bridging the Train-Test Gap in Autoregressive Video Diffusion](/paper/2506.08009)'
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
WHERE slug = 'self-forcing' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'self-forcing' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 369 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE self_forcing_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'self-forcing'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        46097, 46334, 46483, 49162, 49531, 49660, 50856, 51582, 51687, 51824, 51947, 52023,
        52341, 52411, 52953, 52982, 53003, 53022, 53384, 53440, 53483, 53509, 53549, 53712,
        53758, 53800, 53839, 53950, 53993, 54197, 54359, 54361, 54362, 54384, 54392, 54447,
        54490, 54514, 54521, 54560, 54566, 54576, 54589, 54591, 54630, 54631, 54648, 54700,
        54735, 54755, 54778, 54794, 54800, 54847, 54880, 54888, 54928, 54946, 54971, 55009,
        55029, 55071, 55086, 55090, 55168, 55275, 55301, 55304, 55330, 55363, 55458, 55473,
        55512, 55549, 55581, 55673, 55728, 55790, 55809, 55838, 55842, 55860, 55955, 55958,
        55980, 56055, 56138, 56139, 56175, 56188, 56224, 56262, 56343, 56360, 56365, 56390,
        56471, 56495, 56552, 56577, 56583, 56599, 56623, 56728, 56734, 56756, 56823, 56836,
        56965, 57049, 57051, 57083, 57139, 57204, 57215, 57306, 57336, 57353, 57375, 57456,
        57503, 57520, 57559, 57581, 57639, 57640, 57781, 57875, 58870, 58899, 59034, 59268,
        59386, 59468, 59527, 59532, 59990, 59993, 60135, 60187, 60221, 60418, 60652, 60655,
        60680, 60914, 61287, 61776, 61794, 62129, 62229, 62247, 62365, 62886, 63155, 63229,
        63288, 63437, 63468, 63508, 63598, 63752, 63793, 63969, 64028, 64124, 64176, 64254,
        64390, 64619, 64958, 65214, 65220, 65486, 66365, 66733, 66956, 67033, 67126, 67194,
        69035, 69819, 70206, 71010, 71546, 82839, 82840, 82847, 83110, 83164, 83167, 83173,
        83189, 83211, 83238, 83281, 83367, 83455, 83506, 83589, 83594, 83597, 83602, 83616,
        83683, 83705, 83751, 83831, 83836, 83842, 83918, 83949, 84140, 84386, 84510, 84609,
        84650, 84782, 85037, 85104, 85422, 85650, 85665, 85680, 87499, 87507, 87509, 92478,
        92538, 92548, 94946, 97975, 98038, 98136, 98138, 98159, 98160, 98235, 98331, 98396,
        98408, 98420, 98423, 98469, 98775, 98803, 98854, 98954, 98958, 98972, 99001, 99040,
        99044, 99566, 99713, 99938, 100291, 102562, 102565, 102623, 102629, 102633, 102680, 102711,
        102726, 102757, 103834, 104220, 104449, 104455, 104512, 104798, 105852, 105919, 105937, 105953,
        106025, 106069, 108643, 108670, 108846, 108933, 108958, 109129, 109183, 109523, 109580, 109643,
        109649, 109664, 109761, 109769, 109776, 109842, 113744, 113746, 113801, 113810, 113845, 113884,
        113932, 114029, 114095, 114106, 114192, 114207, 114212, 114233, 118054, 118602, 119198, 119224,
        119228, 119262, 119280, 119333, 119383, 119386, 119410, 119418, 119438, 121733, 121900, 121960,
        121989, 121994, 122104, 122120, 122201, 122252, 122257, 122262, 122337, 122352, 122394, 122401,
        122575, 122595, 122646, 122658, 122663, 122672, 122679, 122691, 122740, 122783, 122791, 122830,
        122844, 122853, 122874, 122911, 122936, 122944, 122982, 123123, 123137, 123400, 123428, 123486,
        123496, 123497, 123532, 123540, 123550, 123560, 123572, 123589, 123598
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'self-forcing citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM self_forcing_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING self_forcing_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 32 local citers name the method in title or abstract.
CREATE TEMP TABLE self_forcing_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'self-forcing'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        53134, 54030, 54543, 54563, 55005, 55329, 55671, 55763, 55923, 56302, 56462, 56698,
        57050, 57230, 57772, 58790, 59207, 60747, 63724, 83188, 83366, 83399, 85686, 98812,
        102586, 102710, 104485, 104738, 109142, 109143, 119430, 122341
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM self_forcing_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM self_forcing_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 34 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE self_forcing_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'self-forcing'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        53134, 54030, 54543, 54563, 55005, 55329, 55671, 55763, 55923, 56302, 56462, 56698,
        57050, 57230, 57772, 58790, 59207, 59666, 60747, 63724, 83188, 83366, 83399, 85686,
        98812, 102586, 102710, 104445, 104485, 104738, 109142, 109143, 119430, 122341
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM self_forcing_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM self_forcing_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
