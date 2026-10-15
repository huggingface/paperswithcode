-- Add WavLM method, introduced in arXiv 2110.13900. The source paper
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
    'wavlm',
    'WavLM',
    'WavLM',
    'WavLM is a self-supervised speech model pre-trained for full-stack speech processing, covering not only content tasks such as speech recognition but also speaker, paralinguistic and multi-speaker tasks. It builds on the masked prediction of discrete hidden units used by [HuBERT](/paper/2106.07447) and adds masked speech denoising: during pre-training, utterances are mixed with noise or with overlapping speech from other speakers, and the model must still predict the pseudo-labels of the main speaker in the masked regions. It also adds a gated relative position bias to the [Transformer](/methods/transformer) and scales pre-training to 94k hours of audio. WavLM Large reached state-of-the-art results on the SUPERB benchmark and improved speaker verification, speech separation and speaker diarization over [wav2vec 2.0](/methods/wav2vec) and HuBERT.',
    'WavLM',
    (
        SELECT id
        FROM areas
        WHERE name = 'Audio'
        LIMIT 1
    ),
    2021,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2110.13900'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'WavLM: Large-Scale Self-Supervised Pre-Training for Full Stack Speech Processing',
    'https://github.com/microsoft/unilm/tree/master/wavlm',
    NULL,
    '[WavLM: Large-Scale Self-Supervised Pre-Training for Full Stack Speech Processing](/paper/2110.13900)'
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
WHERE slug = 'wavlm'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'wavlm'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 773 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention WavLM are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE wavlm_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'wavlm'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        6931, 7896, 8056, 8475, 8504, 8508, 8512, 8533, 8596, 8627, 9036, 9099,
        9322, 9416, 9486, 9827, 10482, 10488, 10515, 10583, 11118, 11163, 11186, 11942,
        11975, 12047, 12144, 12316, 13311, 13545, 13956, 14776, 15033, 15504, 15581, 15615,
        15645, 15686, 15737, 15774, 15785, 15902, 15991, 16026, 16176, 16425, 16450, 16524,
        16591, 16707, 16752, 17035, 17036, 17073, 17322, 17690, 17696, 17801, 17819, 17893,
        18238, 18771, 19317, 19524, 19973, 20121, 20289, 20372, 20390, 20421, 20550, 20678,
        20718, 20865, 20874, 20907, 20980, 21140, 21591, 21920, 22272, 22322, 22521, 22897,
        22968, 23278, 23549, 24844, 25162, 25199, 25331, 25341, 25344, 25398, 25514, 25528,
        25554, 25687, 25810, 25846, 26074, 26850, 26913, 27058, 27061, 27179, 27235, 27292,
        27327, 27588, 27629, 27671, 27699, 28355, 28378, 28964, 28965, 29157, 29438, 29890,
        29920, 30164, 30327, 30680, 30994, 31137, 31176, 31276, 31465, 32203, 32207, 32302,
        32407, 32509, 32539, 32549, 32550, 32559, 32622, 32760, 32762, 32766, 32770, 32884,
        32950, 33012, 33103, 33210, 33217, 33319, 33390, 33433, 33517, 33525, 33628, 33702,
        33921, 34127, 34202, 34215, 34256, 34496, 34662, 34761, 34792, 34796, 34947, 35108,
        35189, 35231, 35415, 35456, 35546, 35684, 36016, 36272, 36293, 36297, 36379, 36382,
        36422, 36470, 36562, 36672, 36688, 36689, 36729, 36740, 36741, 36788, 36849, 36895,
        36921, 36958, 36973, 36996, 37041, 37062, 37149, 37210, 37267, 37537, 37559, 37786,
        37900, 37919, 38191, 38850, 38917, 38997, 39410, 39685, 40200, 40534, 40715, 41506,
        41628, 41992, 42040, 42343, 42423, 42572, 42708, 43290, 43446, 43689, 43706, 43720,
        43739, 43747, 43793, 43799, 43858, 43884, 43945, 44145, 44284, 44486, 44833, 44871,
        44925, 44996, 45560, 46034, 46070, 46772, 46773, 46982, 47021, 47516, 47588, 47602,
        47664, 47983, 48153, 48223, 48305, 48313, 48388, 48407, 48486, 48522, 49032, 49051,
        49176, 49184, 49209, 49241, 49433, 49443, 49532, 49538, 49718, 49795, 50306, 50342,
        50429, 50472, 50521, 50703, 50792, 50861, 51067, 51113, 51133, 51150, 51240, 51304,
        51354, 51385, 51671, 51863, 51941, 51952, 51980, 51995, 52010, 52028, 52169, 52213,
        52392, 52482, 52535, 52767, 52822, 52885, 52998, 53234, 53800, 53926, 54654, 55259,
        55333, 55400, 55426, 55451, 55506, 55847, 55849, 55856, 55932, 55973, 56048, 56299,
        56594, 56625, 56679, 56768, 56955, 57692, 57911, 58220, 58290, 58633, 58698, 58760,
        58887, 59027, 59080, 59190, 59247, 59286, 59399, 59485, 59525, 59551, 59582, 59660,
        59691, 59730, 59806, 59819, 60171, 60201, 60365, 60793, 60823, 60856, 61138, 61244,
        61379, 61477, 61791, 61903, 61993, 62001, 62146, 62214, 62381, 62419, 62508, 62516,
        62676, 62720, 62761, 62840, 62888, 63049, 63058, 63391, 63407, 63423, 63425, 63714,
        64111, 64379, 64544, 64763, 65152, 65187, 65390, 65497, 65513, 65630, 65736, 65973,
        65979, 66150, 66191, 66307, 66663, 66811, 66941, 66942, 67034, 67192, 67304, 67311,
        67454, 67543, 67610, 67700, 67718, 67870, 67992, 68159, 68196, 68204, 68210, 68224,
        68312, 68431, 68481, 68502, 68609, 69143, 69233, 69320, 69801, 69915, 69917, 69970,
        70041, 70248, 70505, 70855, 70991, 70999, 71078, 71494, 71530, 71637, 71732, 71856,
        71984, 71992, 72019, 72037, 72124, 72160, 72397, 72429, 72560, 72704, 72720, 72730,
        72770, 72865, 72909, 72925, 72961, 72990, 73103, 73160, 73262, 73291, 73589, 73652,
        73850, 73904, 74324, 75239, 75554, 75629, 75677, 75825, 75856, 75865, 75997, 76052,
        76116, 76287, 76364, 76411, 76419, 76497, 76513, 76533, 76545, 76789, 76893, 76906,
        76985, 76991, 77008, 77031, 77110, 77338, 77867, 77947, 77948, 78051, 78083, 78137,
        78366, 78393, 78410, 78423, 78449, 79055, 79097, 79309, 79372, 79458, 79626, 79909,
        80081, 80271, 80412, 83944, 84282, 85315, 85644, 85726, 85824, 85998, 86328, 87389,
        89472, 89899, 91369, 91512, 91781, 91824, 92109, 92564, 92577, 92623, 93075, 93130,
        93527, 93727, 94423, 94458, 97958, 98838, 98864, 99271, 99624, 99752, 100003, 100089,
        100206, 100305, 100709, 101695, 101715, 101842, 102603, 102731, 102827, 103081, 103104, 103175,
        103205, 103239, 103355, 103559, 103579, 103637, 103823, 104289, 104291, 104483, 104559, 105955,
        106059, 106579, 106692, 106732, 106985, 107579, 108003, 108058, 108349, 108487, 108555, 108819,
        108858, 109072, 109190, 109196, 109197, 109199, 109240, 109270, 109434, 109825, 110015, 110020,
        110471, 110472, 110555, 110658, 110751, 111155, 111156, 111171, 111173, 111183, 111188, 111201,
        111203, 111233, 111275, 111284, 111288, 111309, 111330, 111347, 111348, 111349, 111355, 111376,
        111402, 111411, 111416, 111425, 111445, 111460, 111475, 111476, 111478, 111479, 111486, 111493,
        111498, 111502, 111525, 111528, 111530, 111539, 111552, 111554, 111580, 111581, 111601, 111612,
        111614, 111629, 111668, 111670, 111672, 111679, 111685, 111698, 111705, 111732, 111740, 111756,
        111767, 111785, 111831, 111841, 111863, 111894, 111903, 111911, 111912, 111917, 111928, 111935,
        111940, 111943, 111945, 111946, 111947, 111949, 111951, 111953, 111956, 111959, 111963, 111979,
        111990, 111992, 112006, 112007, 112009, 112011, 112014, 112060, 112064, 112065, 112073, 112087,
        112094, 112125, 112131, 112134, 112151, 114229, 114230, 114302, 116506, 116530, 119213, 119249,
        119481, 120837, 121972, 122271, 122371, 122831, 123012, 123052, 123268
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'wavlm citation review 2026-10-15: cites the source paper without using the method'
FROM wavlm_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING wavlm_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING wavlm_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
