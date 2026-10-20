-- Add Swin Transformer, introduced in arXiv 2103.14030.
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
    'swin-transformer',
    'Swin Transformer',
    'Swin Transformer',
    'Swin Transformer is a hierarchical [Vision Transformer](/methods/vision-transformer) that computes self-attention inside non-overlapping local windows and shifts the window partition between consecutive blocks, so information flows across windows while cost stays linear in image size. Patch-merging layers build a feature pyramid like a CNN, which makes Swin a general-purpose backbone for [image classification](/tasks/image-classification), [object detection](/tasks/object-detection) and [semantic segmentation](/tasks/image-segmentation). At release Swin-L reached 58.7 box AP on COCO test-dev and 53.5 mIoU on ADE20K, and Swin Transformer V2 later scaled the design to 3 billion parameters.',
    'Swin Transformer, Swin-Transformer, SwinTransformer, Swin Transformers, Swin-T, Swin-B, Swin-L, SwinV2, Swin Transformer V2',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2021,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2103.14030'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Swin Transformer: Hierarchical Vision Transformer using Shifted Windows',
    'https://github.com/microsoft/Swin-Transformer/blob/main/models/swin_transformer.py',
    NULL,
    '[Swin Transformer: Hierarchical Vision Transformer using Shifted Windows](/paper/2103.14030)'
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
WHERE slug = 'swin-transformer' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'swin-transformer' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 592 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE swin_transformer_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'swin-transformer'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        52032, 52139, 52140, 52216, 52252, 52354, 52539, 52605, 52821, 52936, 53023, 53399,
        53721, 53773, 54001, 54183, 54474, 54520, 54585, 54588, 54633, 54717, 54791, 54809,
        54828, 54848, 54946, 54969, 55017, 55046, 55055, 55153, 55184, 55205, 55223, 55574,
        55820, 56496, 56737, 56803, 56841, 56880, 56958, 57037, 57040, 57135, 57137, 57208,
        57642, 57759, 57931, 57935, 58006, 58324, 58375, 58455, 58476, 58570, 58602, 58613,
        58676, 58789, 58877, 58968, 58978, 59012, 59052, 59102, 59136, 59161, 59165, 59178,
        59241, 59246, 59262, 59283, 59360, 59415, 59436, 59443, 59476, 59565, 59627, 59655,
        59739, 59755, 59807, 59974, 59997, 60027, 60074, 60214, 60291, 60299, 60328, 60378,
        60412, 60460, 60465, 60660, 60670, 60674, 60681, 60768, 60798, 61011, 61089, 61118,
        61130, 61179, 61252, 61363, 61439, 61924, 61952, 61980, 61983, 62083, 62097, 62178,
        62300, 62348, 62547, 62913, 62953, 62988, 63095, 63231, 63235, 63289, 63299, 63332,
        63414, 63521, 63534, 63560, 63653, 63696, 63720, 63784, 63892, 63919, 63988, 63989,
        64050, 64077, 64082, 64227, 64286, 64331, 64348, 64352, 64397, 64438, 64794, 64801,
        64815, 64866, 64887, 64895, 64901, 64904, 64922, 64952, 65077, 65128, 65131, 65140,
        65181, 65223, 65266, 65268, 65285, 65292, 65301, 65340, 65428, 65462, 65519, 65550,
        65554, 65601, 65638, 65707, 65753, 65760, 65898, 66000, 66087, 66190, 66228, 66336,
        66340, 66395, 66437, 66543, 66567, 66588, 66601, 66686, 66950, 67067, 67117, 67129,
        67170, 67201, 67275, 67333, 67361, 67369, 67403, 67429, 67440, 67542, 67548, 67555,
        67656, 67690, 67784, 67831, 67880, 67974, 68023, 68095, 68173, 68174, 68337, 68367,
        68368, 68474, 68482, 68490, 68495, 68506, 68604, 68626, 68640, 68677, 68715, 68804,
        69020, 69021, 69023, 69039, 69084, 69090, 69211, 69270, 69325, 69376, 69401, 69405,
        69455, 69568, 69589, 69632, 69665, 69683, 69709, 69776, 69790, 69810, 69828, 69876,
        69992, 70025, 70068, 70096, 70106, 70123, 70154, 82831, 82944, 83144, 83276, 84067,
        84113, 84139, 84170, 84172, 84179, 84217, 84239, 84252, 84288, 84304, 84306, 84356,
        84430, 84526, 84630, 84657, 84664, 84669, 84674, 84695, 84714, 84741, 84792, 84826,
        84864, 84869, 84874, 84948, 84950, 84979, 84980, 85029, 85083, 85086, 85098, 85120,
        85131, 85135, 85158, 85190, 85218, 85261, 85264, 85275, 85279, 85294, 85310, 85342,
        85359, 85360, 85364, 85365, 85402, 85465, 85510, 85523, 85531, 85557, 85577, 85663,
        85728, 85755, 85756, 86037, 86200, 86386, 86516, 86659, 86922, 86933, 87140, 87244,
        87291, 87345, 87622, 87651, 87732, 87805, 87817, 87898, 88006, 88138, 88167, 88239,
        88311, 88372, 88373, 88390, 88457, 92638, 92725, 92900, 92927, 92966, 93096, 93155,
        93319, 93372, 93537, 93930, 93975, 94021, 94057, 94127, 94128, 94180, 94225, 94325,
        94465, 94509, 94562, 94573, 94643, 94690, 94696, 94753, 94956, 94977, 94988, 94998,
        95702, 97117, 98038, 98055, 98086, 98530, 98542, 99076, 99095, 99157, 99173, 99183,
        99272, 99282, 99307, 99373, 99380, 99383, 99402, 99484, 99491, 99510, 99548, 99565,
        99605, 99609, 99665, 99680, 99693, 99709, 99718, 99757, 99810, 100328, 100369, 100686,
        100716, 100759, 100912, 101197, 101208, 101306, 101346, 101400, 101455, 101522, 101642, 101648,
        101652, 101757, 101764, 101772, 101865, 101911, 102276, 102352, 102381, 102433, 102493, 102611,
        102705, 103029, 103402, 103406, 103816, 103993, 104019, 104480, 104523, 104729, 105245, 105285,
        105315, 105481, 105760, 106494, 106498, 106526, 106554, 106568, 106593, 106669, 106722, 106728,
        106758, 106761, 106799, 106836, 106887, 106901, 106957, 107119, 107128, 107148, 107201, 107207,
        107249, 107280, 107293, 107314, 107381, 107421, 107425, 107440, 107528, 107547, 107603, 107667,
        107678, 107681, 107743, 107768, 107794, 107852, 107986, 108008, 108111, 108134, 108290, 108298,
        108326, 108353, 108367, 108433, 108462, 108491, 108546, 108576, 108930, 108992, 109303, 109434,
        109796, 109846, 110542, 110658, 112687, 113939, 113995, 114061, 114131, 117264, 117358, 117433,
        117451, 117727, 117731, 117748, 117781, 117824, 117830, 117847, 117868, 117885, 117937, 117957,
        117967, 118046, 118101, 118187, 118600, 118639, 118836, 118847, 118853, 118866, 118912, 118923,
        118992, 118999, 119035, 119077, 119110, 119122, 119143, 119153, 119392, 119406, 119497, 119520,
        119525, 119531, 119550, 119555, 119568, 120820, 120843, 120882, 121276, 121909, 122080, 122212,
        122320, 122565, 123121, 123355
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'swin-transformer citation review 2026-10-20: cites the source without naming the method in title or abstract'
FROM swin_transformer_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING swin_transformer_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 29 local citers name the method in title or abstract.
CREATE TEMP TABLE swin_transformer_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'swin-transformer'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        52439, 52846, 54790, 56482, 58448, 58635, 59430, 59862, 61654, 64170, 64316, 64608,
        66428, 67649, 68484, 68516, 68611, 68695, 69738, 84186, 84567, 84785, 84912, 94605,
        99341, 101206, 107653, 108914, 119138
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM swin_transformer_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM swin_transformer_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 193 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE swin_transformer_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'swin-transformer'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        5576, 5691, 6019, 6114, 6123, 6164, 6168, 6469, 6492, 6842, 7259, 7260,
        7332, 7605, 7638, 7643, 7673, 7774, 7949, 8018, 8086, 8098, 8229, 8595,
        8629, 8721, 8722, 8750, 8767, 8780, 8794, 9197, 9403, 9538, 9550, 9817,
        9866, 9893, 9931, 9980, 10386, 10469, 11134, 11326, 11558, 11658, 11687, 11821,
        12247, 12318, 12530, 13065, 13534, 13583, 13803, 14587, 14802, 14842, 15209, 17618,
        17726, 17763, 17990, 18225, 18251, 18323, 18374, 18447, 18533, 18679, 18865, 18881,
        18885, 18902, 19397, 19452, 19633, 19699, 20067, 20717, 21797, 21933, 22209, 23004,
        24753, 24768, 25926, 26642, 29075, 29261, 29620, 29793, 29886, 30619, 31250, 31289,
        31300, 32921, 33625, 33843, 34912, 34989, 35472, 35642, 36039, 39487, 39862, 40425,
        40480, 41351, 42707, 42743, 43731, 45657, 46654, 46763, 47450, 49939, 50850, 51656,
        52057, 54790, 56482, 58320, 58448, 58635, 59430, 59862, 59882, 63409, 64170, 64316,
        64548, 64608, 65033, 66428, 67649, 68484, 68516, 68611, 68695, 71340, 71956, 73556,
        74012, 74210, 75308, 75543, 76129, 77088, 77440, 77665, 78299, 78609, 79690, 79914,
        80137, 80671, 84186, 84567, 84785, 84912, 87381, 89822, 89855, 90083, 94581, 94605,
        98902, 99341, 101206, 104319, 104351, 105441, 105666, 107564, 111673, 113004, 113369, 113627,
        113639, 114845, 115007, 115116, 115514, 115914, 116120, 116453, 116466, 117096, 120468, 120933,
        121161
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM swin_transformer_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM swin_transformer_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
