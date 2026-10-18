-- Add DINOv3, introduced in arXiv 2508.10104.
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
    'dinov3',
    'DINOv3',
    'DINOv3',
    'DINOv3 is Meta''s third-generation self-supervised vision foundation model, succeeding [DINOv2](/methods/dinov2) and the original [DINO](/methods/dino). It scales label-free self-distillation to a 7B-parameter [Vision Transformer](/methods/vision-transformer) trained on LVD-1689M, a curated set of 1,689 million web images. Its key new ingredient is Gram anchoring, a regularizer that fixes the known degradation of dense feature maps during long training schedules, followed by post-hoc high-resolution adaptation, alignment with text, and [knowledge distillation](/methods/knowledge-distillation) of the 7B teacher into a family of smaller ViT and [ConvNeXt](/methods/convnext) students. Without fine-tuning, the frozen backbone produces high-quality dense features and outperforms specialized state-of-the-art models across a broad range of vision tasks, surpassing earlier self- and weakly-supervised foundation models such as [CLIP](/methods/clip)-style encoders. DINOv3 is widely used as a frozen feature extractor for segmentation, depth, 3D, remote sensing and as a representation target for generative models.',
    'DINOv3, DINO v3, DINO-v3',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2508.10104'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'DINOv3',
    'https://github.com/facebookresearch/dinov3',
    NULL,
    '[DINOv3](/paper/2508.10104)'
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
WHERE slug = 'dinov3' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'dinov3' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 484 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE dinov3_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dinov3'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        38396, 45362, 45948, 47716, 49638, 50178, 50870, 50985, 51028, 51721, 51911, 51981,
        52379, 52673, 52871, 53417, 53636, 53842, 53868, 54156, 54188, 54230, 54252, 54398,
        54433, 54449, 54633, 54696, 54722, 54745, 54929, 54946, 54974, 55055, 55089, 55109,
        55141, 55161, 55232, 55346, 55432, 55457, 55492, 55545, 55561, 55600, 55613, 55629,
        55642, 55714, 55848, 55955, 55991, 56189, 56241, 56247, 56342, 56346, 56396, 56419,
        56441, 56560, 56658, 56661, 56765, 56828, 56841, 56854, 56970, 57045, 57057, 57070,
        57123, 57196, 57358, 57463, 57480, 57520, 57531, 57573, 57620, 57677, 57742, 57743,
        57788, 57994, 58000, 58030, 58031, 58246, 58419, 58478, 58480, 58531, 58556, 58562,
        58602, 58611, 58697, 58862, 58922, 59007, 59012, 59166, 59383, 59412, 59443, 59468,
        59510, 59511, 59633, 59636, 59711, 59771, 60046, 60080, 60182, 60283, 60288, 60311,
        60377, 60378, 60387, 60436, 60546, 60552, 60621, 60656, 60756, 60792, 60899, 60983,
        61011, 61159, 61181, 61248, 61317, 61475, 62184, 62230, 62410, 62505, 62709, 62854,
        62870, 63049, 63367, 63502, 63545, 63560, 63592, 63595, 63604, 63638, 63684, 63686,
        63757, 63788, 63820, 63889, 63912, 63914, 63933, 63982, 64192, 64197, 64257, 64419,
        64447, 64455, 64465, 64522, 64525, 64543, 64687, 64702, 64719, 64852, 64957, 65593,
        65717, 65791, 65876, 66102, 66119, 66282, 66326, 66413, 66421, 66551, 66716, 66855,
        66894, 66920, 67037, 67130, 67191, 67388, 67411, 67920, 68807, 69023, 69204, 69981,
        70613, 70869, 72077, 73318, 73892, 82847, 82947, 83114, 83152, 83271, 83309, 83315,
        83604, 83607, 83610, 83619, 83661, 83680, 83946, 84178, 84185, 84252, 84267, 84276,
        84283, 84300, 84309, 84336, 84342, 84364, 84388, 84392, 84445, 84475, 84486, 84548,
        84561, 84573, 84575, 84576, 84578, 84694, 84704, 84741, 84743, 84744, 84747, 84867,
        84892, 84894, 84947, 85015, 85020, 85029, 85046, 85059, 85146, 85158, 85179, 85221,
        85245, 85310, 85429, 85442, 85447, 85466, 85468, 85546, 85548, 85585, 85588, 85643,
        85649, 85683, 85769, 86829, 87522, 87530, 92474, 92484, 92826, 93258, 93529, 93713,
        94045, 94182, 94220, 94479, 94562, 94664, 94753, 94780, 94825, 94836, 95065, 95107,
        95423, 95433, 95742, 96962, 97195, 97292, 97985, 98086, 98254, 98268, 98428, 98449,
        98453, 98469, 98480, 98560, 98570, 98586, 98763, 98903, 98910, 98979, 98988, 99005,
        99011, 99083, 99136, 99145, 99155, 99180, 99183, 99307, 99338, 99373, 99385, 99474,
        99481, 99757, 99863, 99947, 100129, 100190, 100527, 100568, 100964, 101068, 101074, 101303,
        101306, 101438, 101753, 101771, 102124, 102143, 102647, 102652, 102655, 102677, 103819, 103875,
        103899, 103946, 103993, 104019, 104213, 104309, 104379, 104448, 104522, 104737, 104861, 105874,
        108641, 108782, 108962, 109009, 109040, 109044, 109086, 109111, 109302, 109344, 109345, 109448,
        109463, 109536, 113726, 113728, 113746, 113800, 113801, 113851, 113874, 113891, 113975, 114005,
        114018, 114022, 114029, 114050, 114221, 117414, 117422, 117435, 117689, 117718, 117763, 117766,
        117816, 117853, 117890, 117979, 117995, 118224, 118293, 118330, 118340, 118355, 118359, 118484,
        118760, 118766, 118896, 118922, 118924, 118942, 118982, 119017, 119057, 119064, 119066, 119106,
        119157, 119253, 119254, 119288, 119420, 119438, 119457, 119487, 119513, 119551, 119605, 119609,
        119668, 120771, 120812, 120851, 120889, 121306, 121391, 121605, 121935, 121959, 122014, 122107,
        122138, 122261, 122274, 122430, 122463, 122469, 122551, 122663, 122697, 122705, 122709, 122756,
        122757, 122802, 122835, 122890, 122926, 122959, 122984, 123045, 123169, 123190, 123241, 123348,
        123412, 123413, 123546, 123590
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'dinov3 citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM dinov3_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING dinov3_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 51 local citers name the method in title or abstract.
CREATE TEMP TABLE dinov3_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dinov3'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        52606, 52679, 52981, 54268, 54868, 55102, 55205, 56929, 56979, 57096, 57946, 58194,
        59161, 59260, 59776, 62586, 63405, 63552, 63775, 63811, 65197, 65898, 68015, 68483,
        68774, 68805, 69025, 69193, 84818, 84908, 85038, 85060, 85440, 95030, 98437, 99104,
        102574, 105893, 109046, 114011, 117544, 118305, 118317, 118811, 118823, 119510, 119535, 119568,
        119658, 123468, 123510
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dinov3_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM dinov3_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 91 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE dinov3_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'dinov3'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        52606, 52627, 52679, 52981, 54268, 54850, 54868, 55102, 55155, 55205, 55525, 56929,
        56979, 57096, 57946, 58194, 58610, 58789, 58958, 59161, 59260, 59776, 61356, 61590,
        61710, 61970, 62586, 63405, 63552, 63775, 63811, 64508, 64656, 65197, 65302, 65898,
        66790, 68015, 68483, 68774, 68805, 69025, 69193, 84438, 84818, 84908, 85038, 85060,
        85440, 94546, 95030, 95338, 98437, 98529, 98530, 99104, 100287, 102433, 102574, 102600,
        104026, 105893, 108660, 108994, 109046, 113986, 114011, 117544, 117556, 118305, 118317, 118811,
        118823, 118977, 119510, 119535, 119568, 119658, 121527, 121569, 121601, 121642, 121812, 121863,
        122353, 122422, 122647, 123122, 123140, 123468, 123510
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM dinov3_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM dinov3_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
