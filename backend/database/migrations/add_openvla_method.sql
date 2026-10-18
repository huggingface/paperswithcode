-- Add OpenVLA, introduced in arXiv 2406.09246.
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
    'openvla',
    'OpenVLA',
    'OpenVLA: Open-Source Vision-Language-Action Model',
    'OpenVLA is a 7B-parameter open-source [vision-language-action (VLA)](/methods/vla) model for generalist robot manipulation, trained on 970k real-world robot demonstrations from the Open X-Embodiment datasets. It builds on a [Llama](/methods/llama) 2 7B language model with a visual encoder that fuses pretrained [DINOv2](/methods/dinov2) and [SigLIP](/methods/siglip) features through an MLP projector; given a camera image and a language instruction, it predicts robot actions as discretized action tokens that are de-tokenized into a 7-DoF end-effector command. OpenVLA outperforms the closed 55B RT-2-X by 16.5% absolute task success rate across 29 tasks and multiple robot embodiments with 7x fewer parameters, and after fine-tuning beats from-scratch [imitation learning](/methods/imitation-learning) such as [Diffusion Policy](/methods/diffusion-policy) by 20.4%. It can be fine-tuned on consumer GPUs with [LoRA](/methods/lora) and served with [quantization](/methods/quantization) without losing success rate. Its fine-tuning recipe was later improved by [OpenVLA-OFT](/methods/openvla-oft).',
    'OpenVLA',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2024,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2406.09246'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'OpenVLA: An Open-Source Vision-Language-Action Model',
    'https://github.com/openvla/openvla',
    NULL,
    '[OpenVLA: An Open-Source Vision-Language-Action Model](/paper/2406.09246)'
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
WHERE slug = 'openvla' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'openvla' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 1296 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE openvla_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'openvla'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        21876, 23225, 27077, 27163, 31553, 33343, 33867, 34734, 35121, 35309, 36022, 36098,
        36337, 36707, 37286, 37411, 37554, 37571, 37630, 37638, 37862, 38096, 38236, 38551,
        38632, 38745, 38883, 38957, 39121, 39345, 39354, 39460, 39532, 39726, 40437, 40444,
        40517, 40615, 40667, 40744, 40745, 40759, 40968, 41045, 41070, 41075, 41084, 41172,
        41257, 41347, 41379, 41382, 41559, 41683, 41759, 41784, 41832, 41841, 41856, 41857,
        42152, 42460, 42508, 42574, 42628, 42775, 42893, 42965, 43208, 43286, 43306, 43326,
        43444, 43563, 43621, 43638, 43733, 43870, 44194, 44339, 44519, 44521, 44525, 44528,
        44988, 45071, 45090, 45214, 45226, 45240, 45324, 45349, 45402, 45485, 45631, 45716,
        45742, 45818, 45894, 45901, 45963, 45985, 46036, 46077, 46121, 46163, 46194, 46203,
        46356, 46359, 46406, 46479, 46673, 46714, 46732, 46760, 46866, 46909, 47017, 47025,
        47040, 47126, 47250, 47826, 47852, 47988, 48004, 48011, 48054, 48160, 48177, 48196,
        48242, 48265, 48340, 48538, 48541, 48558, 48619, 48658, 48728, 48736, 48747, 48905,
        48935, 49389, 49427, 49483, 49484, 49509, 49773, 49799, 49944, 49946, 50001, 50085,
        50088, 50160, 50202, 50247, 50288, 50292, 50309, 50310, 50406, 50419, 50642, 50667,
        50704, 50711, 50712, 50769, 50796, 50954, 50967, 50969, 50982, 51102, 51123, 51132,
        51172, 51263, 51276, 51297, 51338, 51345, 51355, 51418, 51437, 51474, 51525, 51585,
        51592, 51698, 51718, 51750, 51768, 51946, 51966, 51967, 52004, 52007, 52040, 52130,
        52180, 52270, 52281, 52309, 52315, 52320, 52398, 52415, 52433, 52476, 52488, 52553,
        52577, 52628, 52633, 52665, 52738, 52746, 52800, 52818, 52861, 52878, 52887, 52912,
        52931, 52934, 52944, 52950, 52979, 53020, 53099, 53162, 53163, 53306, 53332, 53397,
        53403, 53406, 53426, 53443, 53451, 53472, 53476, 53494, 53502, 53552, 53561, 53562,
        53569, 53578, 53581, 53613, 53616, 53749, 53840, 53841, 53856, 53874, 53875, 53891,
        53939, 53961, 53989, 53991, 53999, 54001, 54033, 54051, 54055, 54080, 54102, 54275,
        54284, 54299, 54303, 54313, 54393, 54394, 54416, 54454, 54455, 54502, 54508, 54517,
        54540, 54574, 54633, 54647, 54689, 54761, 54762, 54768, 54814, 54901, 54907, 54937,
        54984, 55010, 55021, 55027, 55050, 55067, 55091, 55114, 55115, 55161, 55180, 55266,
        55291, 55356, 55383, 55384, 55459, 55471, 55545, 55569, 55573, 55600, 55613, 55623,
        55775, 55900, 55959, 55961, 55962, 55997, 56050, 56055, 56057, 56060, 56096, 56102,
        56113, 56172, 56188, 56218, 56250, 56254, 56271, 56274, 56278, 56308, 56439, 56517,
        56537, 56643, 56661, 56684, 56717, 56757, 56759, 56775, 56828, 56833, 56851, 56854,
        56856, 56935, 56959, 56977, 56982, 56991, 57157, 57160, 57233, 57236, 57259, 57288,
        57326, 57349, 57396, 57525, 57679, 57725, 57727, 57735, 57795, 57836, 57973, 57994,
        58018, 58043, 58124, 58138, 58263, 58278, 58392, 58458, 58473, 58490, 58499, 58501,
        58762, 58820, 58910, 58994, 59013, 59137, 59140, 59194, 59250, 59354, 59395, 59479,
        59490, 59491, 59535, 59541, 59578, 59579, 59643, 59648, 59657, 59664, 59703, 59714,
        59725, 59834, 59869, 59944, 59984, 60018, 60223, 60283, 60289, 60363, 60400, 60413,
        60432, 60463, 60468, 60530, 60600, 60672, 60675, 60701, 60714, 60736, 60748, 60756,
        60767, 60768, 60796, 60851, 60857, 60871, 60910, 60958, 61090, 61093, 61166, 61242,
        61248, 61253, 61259, 61311, 61352, 61409, 61502, 61550, 61571, 61594, 61602, 61606,
        61628, 61641, 61894, 61895, 61966, 61981, 62029, 62073, 62140, 62189, 62278, 62416,
        62563, 62666, 62688, 62735, 62854, 62930, 62949, 62980, 63004, 63065, 63104, 63191,
        63275, 63277, 63279, 63295, 63402, 63404, 63428, 63454, 63493, 63499, 63508, 63549,
        63597, 63609, 63717, 63802, 63812, 63827, 63885, 63931, 63946, 63976, 64047, 64057,
        64071, 64098, 64108, 64112, 64138, 64164, 64193, 64207, 64263, 64266, 64325, 64344,
        64405, 64429, 64430, 64455, 64464, 64503, 64516, 64573, 64633, 64724, 64726, 64729,
        64771, 64779, 64813, 64828, 64966, 64987, 65002, 65067, 65072, 65199, 65295, 65298,
        65570, 65619, 65627, 65703, 65752, 65787, 65902, 65949, 66014, 66044, 66110, 66174,
        66200, 66208, 66240, 66381, 66404, 66405, 66439, 66480, 66520, 66551, 66594, 66625,
        66630, 66643, 66685, 66694, 66796, 66975, 67000, 67004, 67078, 67086, 67128, 67218,
        67278, 67305, 67351, 67365, 67428, 67468, 67470, 67621, 67699, 67745, 67787, 67814,
        67858, 67872, 67891, 67902, 67921, 67946, 67959, 68015, 68074, 68132, 68133, 68149,
        68184, 68218, 68254, 68270, 68342, 68361, 68385, 68407, 68444, 68557, 68607, 68616,
        68625, 68730, 68743, 68749, 68838, 68945, 68997, 69019, 69035, 69079, 69089, 69133,
        69214, 69495, 69514, 69621, 69684, 69690, 69736, 69792, 69813, 69861, 69886, 70013,
        70052, 70144, 70304, 70421, 70449, 70482, 70613, 70682, 70840, 71034, 71068, 71312,
        71367, 71395, 71527, 71577, 71613, 71636, 71743, 71797, 71944, 71984, 72111, 72150,
        72167, 72183, 72290, 72298, 72371, 72374, 72595, 72619, 72679, 72693, 72698, 72743,
        72858, 72887, 72945, 72955, 73010, 73030, 73049, 73068, 73085, 73088, 73113, 73169,
        73198, 73205, 73441, 73722, 73897, 74153, 74180, 74219, 74294, 74365, 74520, 74562,
        74694, 74728, 74939, 75328, 75378, 75408, 75422, 75940, 75957, 75985, 76101, 76120,
        76181, 76229, 76275, 76318, 76377, 76481, 77886, 78076, 82850, 82882, 83127, 83183,
        83247, 83283, 83377, 83393, 83527, 83661, 83699, 83808, 83824, 83849, 83862, 83915,
        83922, 83942, 83959, 83998, 84012, 84109, 84124, 84149, 84228, 84234, 84265, 84291,
        84363, 84416, 84632, 84663, 84733, 84739, 84809, 84835, 84851, 84872, 84875, 84924,
        85063, 85182, 85204, 85233, 85270, 85337, 85497, 85524, 85669, 85687, 85802, 86004,
        86023, 86181, 86187, 86311, 86468, 86499, 86583, 86646, 86656, 86680, 86813, 87253,
        87256, 87257, 87468, 87517, 87705, 87784, 87846, 87908, 87964, 88013, 88019, 88038,
        88044, 88107, 88194, 88211, 88241, 88281, 88627, 89082, 89175, 89349, 89607, 89922,
        90024, 90025, 90322, 90614, 90631, 90848, 90990, 91085, 91324, 91553, 92345, 92503,
        92554, 92781, 92872, 92981, 93088, 93126, 93182, 93193, 93271, 93639, 93764, 93782,
        93936, 93939, 93998, 94419, 94468, 94546, 94665, 94727, 94798, 94824, 94837, 94854,
        94882, 94915, 94992, 95017, 95029, 95075, 95087, 95175, 95204, 95285, 95301, 95310,
        95337, 95361, 95418, 95510, 95574, 95575, 95591, 95726, 95733, 95734, 95763, 95835,
        95861, 95886, 96024, 96080, 96101, 96140, 96172, 96175, 96180, 96192, 96219, 96242,
        96270, 96285, 96289, 96294, 96330, 96331, 96337, 96340, 96342, 96370, 96492, 96497,
        96499, 96507, 96544, 96591, 96606, 96627, 96647, 96654, 96661, 96675, 96678, 96693,
        96698, 96760, 96787, 96798, 96806, 96823, 96826, 96833, 96971, 96972, 96979, 97002,
        97047, 97078, 97095, 97108, 97151, 97187, 97198, 97242, 97256, 97287, 97306, 97343,
        97359, 97397, 97504, 97509, 97518, 97523, 97581, 97584, 97591, 97592, 97596, 97618,
        97619, 97634, 97657, 97670, 97684, 97692, 97719, 97831, 97856, 97885, 97890, 97895,
        97952, 98019, 98102, 98107, 98159, 98186, 98195, 98219, 98244, 98262, 98288, 98289,
        98320, 98363, 98378, 98380, 98381, 98388, 98389, 98391, 98421, 98428, 98449, 98463,
        98474, 98483, 98527, 98546, 98559, 98697, 98703, 98706, 98793, 98815, 98850, 98918,
        98922, 98935, 98938, 98956, 98992, 99039, 99040, 99049, 99084, 99113, 99131, 99219,
        99220, 99229, 99366, 99377, 99408, 99437, 99481, 99492, 99524, 99629, 99763, 99809,
        99889, 99964, 100027, 100200, 100210, 100242, 100273, 100419, 100455, 100486, 100502, 100612,
        100633, 100654, 100691, 100726, 100909, 100984, 101129, 101163, 101289, 101338, 101353, 101416,
        101421, 101438, 101447, 101518, 101572, 101880, 101917, 102104, 102214, 102462, 102546, 102561,
        102562, 102571, 102610, 102629, 102631, 102641, 102646, 102679, 102681, 102693, 102831, 103016,
        103296, 103693, 103830, 103951, 104036, 104219, 104307, 104378, 104389, 104479, 104727, 104735,
        105849, 105874, 105876, 105912, 105918, 105925, 105982, 105997, 106017, 106025, 106034, 106238,
        106414, 106587, 106875, 106964, 106994, 107345, 107347, 107501, 107839, 107899, 108118, 108373,
        108472, 108510, 108632, 108660, 108725, 108735, 108769, 108781, 108808, 108904, 108923, 108927,
        108947, 108960, 109009, 109036, 109040, 109041, 109042, 109044, 109045, 109046, 109048, 109049,
        109110, 109115, 109303, 109305, 109338, 109503, 109559, 109561, 109579, 109642, 109695, 109727,
        109763, 109772, 109809, 110232, 110361, 112308, 113732, 113737, 113747, 113760, 113821, 113857,
        113871, 113878, 113915, 113955, 114001, 114012, 114018, 114037, 114041, 114050, 114070, 114099,
        114150, 114176, 114185, 114191, 114205, 114207, 114209, 114218, 114227, 114257, 114260, 114263,
        114278, 117561, 117574, 117970, 117983, 117985, 118002, 118003, 118005, 118016, 118021, 118022,
        118035, 118062, 118081, 118087, 118102, 118103, 118833, 119295, 119401, 119426, 119446, 119537,
        119551, 119578, 119587, 119620, 119621, 119642, 119648, 119663, 119675, 119698, 119703, 119956,
        120065, 120373, 120812, 121220, 121299, 121459, 121838, 121875, 121981, 121987, 121999, 122016,
        122073, 122096, 122101, 122105, 122106, 122107, 122110, 122117, 122123, 122149, 122151, 122170,
        122186, 122202, 122206, 122235, 122240, 122251, 122318, 122327, 122340, 122429, 122481, 122574,
        122596, 122606, 122653, 122657, 122667, 122674, 122689, 122717, 122719, 122727, 122733, 122734,
        122764, 122797, 122803, 122806, 122809, 122816, 122834, 122835, 122838, 122841, 122849, 122852,
        122870, 122896, 122902, 122905, 122950, 122974, 122983, 122986, 123223, 123288, 123395, 123398,
        123402, 123412, 123460, 123466, 123519, 123564, 123578, 123582, 123584, 123588, 123617, 123659
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'openvla citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM openvla_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING openvla_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 57 local citers name the method in title or abstract.
CREATE TEMP TABLE openvla_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'openvla'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        37071, 37221, 38243, 38903, 38910, 39347, 40700, 41546, 43873, 43889, 44900, 45110,
        45419, 45798, 48572, 49645, 49983, 50956, 52047, 52569, 52590, 53318, 53607, 55505,
        56095, 56241, 59276, 60527, 63712, 64787, 66528, 66901, 67136, 67676, 68201, 69622,
        71688, 71740, 72543, 74259, 75546, 75894, 85511, 85666, 92701, 93968, 95999, 96210,
        96748, 97008, 98384, 100757, 108080, 110092, 110819, 118221, 119680
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM openvla_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM openvla_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 63 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE openvla_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'openvla'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        37071, 37221, 38243, 38903, 38910, 39347, 39811, 40700, 41546, 43873, 43889, 44900,
        45110, 45419, 45798, 48572, 49645, 49983, 50956, 52047, 52569, 52590, 53318, 53607,
        55505, 56095, 56241, 59276, 60527, 63712, 64787, 66528, 66901, 67136, 67676, 68201,
        69622, 71688, 71740, 72543, 74259, 75546, 75894, 85511, 85666, 92701, 93968, 95556,
        95999, 96195, 96210, 96748, 97008, 98384, 100757, 107372, 108080, 110092, 110819, 118221,
        119505, 119680, 121426
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM openvla_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM openvla_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
