-- Add CLAP method, introduced in arXiv 2206.04769. The source paper
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
    'clap',
    'CLAP',
    'CLAP (Contrastive Language-Audio Pretraining)',
    'CLAP (Contrastive Language-Audio Pretraining) learns a joint embedding space for audio and natural-language descriptions, the audio counterpart of [CLIP](/methods/clip). An audio encoder and a text encoder are trained with a symmetric [contrastive](/methods/contrastive-learning) loss on audio-caption pairs, so matching clips and captions land close together. At inference, class labels written as text prompts allow zero-shot audio classification, and the shared space supports text-to-audio and audio-to-text retrieval. Microsoft''s CLAP (Elizalde et al., 2022) trained on 128k audio-text pairs and set zero-shot state of the art across 16 downstream tasks. LAION-CLAP ([Wu et al., 2022](/paper/2211.06687)) scaled training to the LAION-Audio-630K dataset with feature fusion for variable-length audio and keyword-to-caption augmentation. CLAP encoders are widely used as text conditioners and evaluation metrics for text-to-audio and text-to-music generation.',
    'CLAP, contrastive language-audio pretraining, contrastive language-audio pre-training',
    (
        SELECT id
        FROM areas
        WHERE name = 'Audio'
        LIMIT 1
    ),
    2022,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2206.04769'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'CLAP: Learning Audio Concepts From Natural Language Supervision',
    'https://github.com/microsoft/CLAP',
    NULL,
    '[CLAP: Learning Audio Concepts From Natural Language Supervision](/paper/2206.04769)'
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
WHERE slug = 'clap'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'clap'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 332 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention CLAP are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE clap_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'clap'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        11414, 12047, 12591, 13557, 13725, 14297, 14866, 15033, 15704, 15737, 15774, 15797,
        15801, 16065, 16532, 17522, 17716, 17903, 19072, 19524, 20504, 20509, 20907, 20915,
        21762, 22068, 22432, 22734, 22875, 22876, 22922, 23278, 23996, 24092, 24758, 25307,
        25394, 25498, 25882, 26156, 26548, 26711, 26850, 26886, 28391, 29034, 29254, 29395,
        30220, 30288, 30408, 30653, 31138, 31304, 32168, 32796, 32916, 33151, 33229, 33497,
        33542, 33753, 34018, 34138, 34662, 35197, 35380, 36111, 36458, 36718, 36809, 36871,
        36887, 37178, 37368, 37714, 37742, 38003, 38091, 38656, 38689, 39035, 39167, 39195,
        39288, 39517, 39575, 40356, 40814, 41113, 41458, 41644, 41680, 41906, 41922, 43742,
        43996, 45121, 45420, 45889, 46004, 46056, 46569, 46773, 46837, 46993, 47195, 47516,
        48167, 48497, 48630, 48855, 49151, 49497, 49917, 50346, 50568, 50592, 50767, 50866,
        51007, 51379, 51428, 51619, 51658, 52211, 52432, 52914, 53381, 53521, 53541, 54506,
        54968, 55259, 56086, 56625, 56698, 56881, 57205, 57410, 57441, 58040, 58048, 58130,
        58745, 58887, 58982, 59166, 59261, 59399, 59577, 60183, 60334, 60369, 61367, 61379,
        61724, 61869, 62117, 62475, 62508, 62933, 62959, 63423, 63971, 63997, 64216, 64477,
        64763, 64890, 65995, 66115, 66738, 67089, 67180, 67717, 67919, 68058, 68155, 68157,
        68200, 68579, 68719, 69167, 69292, 69683, 69896, 70041, 70248, 70308, 70456, 70695,
        70837, 71787, 71841, 72047, 72098, 72548, 72553, 72761, 73136, 73531, 74579, 74832,
        75084, 76398, 76681, 76789, 77677, 78243, 78335, 78449, 78543, 79256, 80788, 83006,
        84146, 84706, 85942, 86025, 86128, 86906, 87139, 87860, 88274, 88402, 90530, 90626,
        91493, 92319, 92592, 93378, 93447, 94332, 94713, 98739, 98817, 99446, 99991, 100142,
        100223, 100325, 101068, 101212, 101296, 101767, 102728, 102770, 103205, 104280, 104730, 106692,
        107150, 108255, 108740, 109390, 109486, 109539, 110013, 111309, 111367, 111375, 111496, 111582,
        111606, 111839, 111871, 111982, 112000, 113302, 113984, 114231, 115470, 116172, 116407, 117771,
        118833, 119249, 119438, 122178, 122607, 123004
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'clap citation review 2026-10-15: cites the source paper without using the method'
FROM clap_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING clap_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING clap_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
