-- Add SigLIP 2, introduced in arXiv 2502.14786.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url, image_url, image_credit
)
VALUES (
    'siglip-2',
    'SigLIP 2',
    'SigLIP 2',
    'SigLIP 2 is a family of multilingual vision-language encoders that extends [SigLIP](/methods/siglip) with a mix of training objectives. Alongside the sigmoid image-text loss it adds LocCa-style captioning decoders for dense captioning and referring expressions, self-distillation and masked prediction for better local features, and online data curation, and it is trained on a multilingual mix with de-biasing filters. Released in ViT-B, L, So400m and g sizes, with fixed-resolution and NaFlex variants, the models improve zero-shot classification, retrieval, localization and dense prediction, and serve as vision encoders in VLMs.',
    'SigLIP 2, SigLIP2, SigLIP-2',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2025,
    (SELECT id FROM papers WHERE arxiv_id = '2502.14786' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'SigLIP 2: Multilingual Vision-Language Encoders with Improved Semantic Understanding, Localization, and Dense Features',
    'https://github.com/google-research/big_vision/tree/main/big_vision/configs/proj/image_text',
    NULL,
    '[SigLIP 2: Multilingual Vision-Language Encoders with Improved Semantic Understanding, Localization, and Dense Features](/paper/2502.14786)'
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
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'siglip-2' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'siglip-2' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 605 local citers cite the source without naming the method in title or abstract; exclude them so the hourly reference backfill does not link them.
CREATE TEMP TABLE siglip_2_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'siglip-2'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        35673, 36369, 39757, 42755, 44005, 44358, 44367, 44572, 45277, 45889, 46082, 46195,
        46325, 46359, 46403, 46603, 46672, 46748, 47358, 47514, 47877, 47920, 48032, 48056,
        48535, 48731, 49108, 49124, 49180, 49221, 49461, 49487, 49509, 49567, 49730, 49731,
        49781, 49849, 49919, 49949, 50033, 50041, 50155, 50434, 50499, 50592, 50805, 50870,
        50902, 50967, 50985, 51061, 51394, 51449, 51521, 51572, 51737, 51749, 51750, 51758,
        51772, 51783, 51841, 51981, 52074, 52106, 52108, 52192, 52205, 52309, 52368, 52578,
        52606, 52715, 52744, 52858, 52861, 52888, 52964, 53132, 53185, 53197, 53278, 53407,
        53438, 53571, 53596, 53636, 53674, 53679, 53725, 53813, 53835, 53842, 53939, 53999,
        54080, 54189, 54252, 54291, 54309, 54349, 54398, 54449, 54456, 54536, 54567, 54575,
        54603, 54608, 54644, 54659, 54713, 54724, 54834, 54846, 54848, 54850, 54871, 54921,
        54923, 54946, 54974, 55028, 55114, 55331, 55454, 55561, 55661, 55739, 55848, 55961,
        55962, 55978, 56062, 56194, 56225, 56241, 56247, 56250, 56342, 56355, 56387, 56396,
        56397, 56421, 56472, 56507, 56509, 56544, 56560, 56567, 56661, 56672, 56714, 56800,
        56839, 56841, 56854, 56861, 56929, 56934, 56975, 57179, 57184, 57322, 57326, 57332,
        57366, 57371, 57463, 57477, 57525, 57531, 57532, 57533, 57563, 57590, 57663, 57677,
        57687, 57696, 57705, 57709, 57734, 57788, 57793, 57818, 57834, 57841, 57963, 57974,
        58015, 58030, 58194, 58260, 58271, 58328, 58384, 58409, 58586, 58606, 58734, 58817,
        58848, 58862, 58938, 58961, 58997, 59012, 59261, 59262, 59290, 59443, 59495, 59638,
        59768, 59771, 59916, 60169, 60201, 60259, 60289, 60314, 60411, 60451, 60511, 60635,
        60647, 60656, 60681, 60743, 60760, 60792, 60822, 60825, 60899, 60983, 61011, 61040,
        61142, 61157, 61186, 61248, 61301, 61376, 61590, 61806, 61894, 61907, 62069, 62184,
        62194, 62253, 62295, 62360, 62460, 62475, 62677, 62744, 62799, 62844, 63026, 63052,
        63141, 63216, 63423, 63449, 63499, 63502, 63563, 63592, 63604, 63630, 63662, 63686,
        63745, 63820, 63825, 63852, 63912, 63942, 63988, 64015, 64050, 64110, 64213, 64350,
        64371, 64386, 64525, 64587, 64680, 64684, 64773, 64857, 64935, 64952, 64962, 65015,
        65023, 65199, 65288, 65328, 65350, 65651, 65692, 66102, 66110, 66174, 66282, 66413,
        66549, 66551, 66558, 66823, 66844, 66975, 67024, 67128, 67149, 67184, 67279, 67315,
        67494, 67509, 67635, 67662, 68393, 68455, 68464, 68518, 68536, 68607, 68635, 68719,
        68724, 68771, 68832, 68924, 69039, 69193, 69461, 69530, 69550, 69593, 69697, 70025,
        70092, 70276, 70341, 70461, 70547, 70636, 70755, 70766, 71302, 71518, 71554, 71679,
        71702, 71757, 71947, 72104, 72193, 72318, 72370, 72743, 72887, 73011, 73240, 73339,
        73892, 74056, 74153, 74506, 75768, 76037, 77045, 82826, 82930, 82943, 82982, 83006,
        83298, 83367, 83608, 83619, 83684, 83727, 83799, 83812, 83845, 84037, 84092, 84170,
        84212, 84216, 84360, 84370, 84433, 84460, 84488, 84540, 84570, 84643, 84680, 84706,
        84744, 84749, 84760, 84818, 84857, 84878, 84891, 84947, 84955, 85013, 85078, 85095,
        85125, 85260, 85310, 85466, 85497, 85559, 85569, 85588, 85643, 85658, 85720, 85765,
        86047, 86170, 86887, 87094, 87222, 87245, 87497, 87524, 87526, 87530, 92474, 92615,
        94055, 94338, 94450, 94562, 94664, 94791, 94998, 95092, 97151, 97951, 97978, 97985,
        98126, 98254, 98256, 98371, 98414, 98462, 98580, 98596, 98757, 98848, 98934, 98979,
        98988, 99011, 99083, 99180, 99192, 99385, 99420, 99431, 99486, 99608, 99970, 99975,
        100015, 100110, 100111, 100133, 100972, 101318, 101799, 102079, 102247, 102574, 102635, 102759,
        103035, 103196, 103485, 103640, 103751, 103993, 104047, 104309, 104313, 104444, 104445, 104522,
        104523, 104548, 104556, 104581, 104589, 104729, 104737, 105848, 105936, 105994, 106030, 106073,
        106280, 106722, 106847, 107509, 108223, 108353, 108615, 108720, 108959, 109084, 109123, 109291,
        109298, 109302, 109305, 109428, 109463, 109619, 109642, 109697, 109846, 113803, 113814, 113886,
        113904, 113976, 114004, 114018, 114038, 114103, 114226, 117401, 117410, 117688, 117867, 118035,
        118051, 118122, 118156, 118162, 118341, 118448, 118548, 118631, 118760, 118822, 118832, 118910,
        119262, 119272, 119404, 119414, 119473, 119484, 119497, 119551, 119554, 119582, 120729, 120851,
        121098, 121306, 121759, 121979, 122014, 122023, 122180, 122201, 122284, 122297, 122324, 122422,
        122551, 122590, 122625, 122876, 122949, 122967, 122978, 122984, 123122, 123180, 123270, 123403,
        123408, 123413, 123510, 123534, 123544
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'siglip-2 citation review 2026-10-22: cites the source without naming the method in title or abstract'
FROM siglip_2_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING siglip_2_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 23 local citers name the method in title or abstract.
CREATE TEMP TABLE siglip_2_cited ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'siglip-2'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        46414, 48616, 49717, 50785, 50828, 54546, 55319, 55447, 56089, 57031, 63405, 63441,
        63814, 65868, 74534, 84875, 84932, 85877, 86374, 94182, 98969, 101966, 114011
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM siglip_2_cited x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM siglip_2_cited x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 33 papers match the method keywords (same matcher as the daily keyword backfill).
CREATE TEMP TABLE siglip_2_keyword ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'siglip-2'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        46414, 48616, 49717, 50785, 50828, 52207, 54546, 55319, 55447, 55525, 56089, 57031,
        60621, 63405, 63441, 63814, 65868, 74534, 83018, 83493, 84011, 84875, 84932, 85877,
        86374, 93394, 94182, 98867, 98969, 101966, 114011, 114204, 121601
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM siglip_2_keyword x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM siglip_2_keyword x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
