-- Add REPA, introduced in arXiv 2410.06940.
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
    'repa',
    'REPA',
    'Representation Alignment (REPA)',
    'REPA (REPresentation Alignment) is a training regularizer for [diffusion transformers](/methods/diffusion-transformer-dit) and flow-based transformers such as SiT. It projects the hidden states of an early denoiser block, computed on noisy inputs, through a small MLP and aligns them with patch features of the clean image from a frozen, pretrained self-supervised visual encoder such as [DINOv2](/methods/dinov2). The motivation is that a large part of the cost of training generative diffusion models goes into learning good internal representations, which can instead be borrowed from an external encoder. Added to the standard denoising objective, REPA sped up SiT training by over 17.5×, matching a SiT-XL trained for 7M steps (without [classifier-free guidance](/methods/classifier-free-guidance)) in under 400K steps, and reached FID 1.42 on ImageNet 256×256 with guidance interval. Follow-ups include [REPA-E](/paper/2504.10483), which uses the alignment loss to tune the [VAE](/methods/vae) end to end with the diffusion model, and [Representation Autoencoders](/methods/representation-autoencoder), which put the representation encoder in the latent space directly.',
    'REPA-E, REPresentation Alignment, representation alignment for generation, (REPA), REPA-, REPA), REPA.',
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
        WHERE arxiv_id = '2410.06940'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Representation Alignment for Generation: Training Diffusion Transformers Is Easier Than You Think',
    'https://github.com/sihyun-yu/REPA',
    NULL,
    '[Representation Alignment for Generation: Training Diffusion Transformers Is Easier Than You Think](/paper/2410.06940)'
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
WHERE slug = 'repa' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'repa' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 418 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE repa_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'repa'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        38873, 39935, 40296, 40450, 40729, 40921, 41187, 41199, 41204, 41258, 41472, 41589,
        41855, 42229, 42365, 42429, 42495, 42635, 42674, 43112, 43208, 43259, 43710, 44430,
        44638, 45174, 45185, 45195, 45230, 45297, 45662, 45769, 45829, 45909, 45956, 46103,
        46347, 46400, 46712, 47049, 47132, 47407, 47571, 47734, 47742, 47747, 47877, 48056,
        48243, 48403, 48417, 48544, 48822, 48843, 49072, 49279, 49552, 49565, 49582, 49681,
        49919, 50134, 50493, 50635, 50664, 50808, 50856, 51318, 51390, 51424, 51686, 51824,
        51841, 52019, 52119, 52406, 52457, 52462, 52654, 52706, 52715, 52858, 52860, 52943,
        52979, 52989, 53132, 53214, 53317, 53341, 53355, 53453, 53458, 53502, 53503, 53558,
        53619, 53648, 53669, 53798, 53829, 53838, 53869, 53958, 53969, 53999, 54039, 54135,
        54321, 54414, 54419, 54449, 54458, 54501, 54567, 54637, 54644, 54713, 54732, 54773,
        54895, 54946, 54987, 55051, 55086, 55153, 55232, 55330, 55392, 55447, 55454, 55594,
        55602, 55629, 55641, 55666, 55848, 55978, 55991, 56119, 56280, 56306, 56365, 56421,
        56441, 56492, 56535, 56658, 56672, 56782, 56831, 56855, 56904, 57134, 57135, 57309,
        57362, 57424, 57466, 57475, 57531, 57556, 57577, 57705, 57709, 57734, 57818, 57841,
        58008, 58216, 58271, 58511, 58527, 58698, 58722, 58862, 58904, 58909, 58945, 58975,
        59011, 59036, 59061, 59125, 59164, 59205, 59433, 59658, 59768, 59811, 60252, 60353,
        60552, 60950, 60983, 61142, 61225, 61230, 61248, 61274, 61685, 61719, 61827, 61894,
        61895, 62453, 62603, 62764, 63046, 63052, 63352, 63600, 63756, 63772, 63775, 63810,
        63927, 64001, 64171, 64192, 64247, 64525, 64619, 64640, 64695, 64906, 64935, 65214,
        65602, 65729, 65754, 65825, 65828, 65923, 65925, 66102, 66431, 66558, 66775, 66841,
        66882, 66929, 66956, 66970, 67031, 67167, 67191, 67395, 67431, 67469, 67555, 67700,
        67766, 67818, 68253, 68257, 68655, 68683, 68893, 69143, 69320, 70334, 70426, 70473,
        70785, 72723, 72887, 73000, 73262, 73648, 73912, 74514, 74955, 75007, 75631, 82847,
        82930, 82943, 83121, 83197, 83236, 83302, 83367, 83461, 83515, 83526, 83619, 83775,
        83804, 84140, 84175, 84229, 84338, 84352, 84486, 84507, 84530, 84826, 85004, 85588,
        85643, 85882, 86020, 86693, 86966, 87415, 87452, 87737, 87917, 88343, 88418, 90310,
        90517, 92853, 93272, 93504, 94458, 94566, 94775, 94912, 95014, 98251, 98254, 98256,
        98414, 98421, 98466, 98546, 98757, 98864, 98873, 98927, 98945, 98988, 98999, 99005,
        99078, 99083, 99088, 99104, 99173, 99183, 99268, 99331, 99334, 99432, 99472, 99499,
        99546, 99573, 99648, 99938, 100150, 100273, 100684, 100779, 101714, 102105, 102344, 102585,
        102727, 103906, 104019, 104578, 105847, 105854, 105926, 105949, 108846, 108945, 109302, 109378,
        109619, 111740, 113760, 113803, 113851, 113932, 114018, 117390, 117425, 118448, 118494, 118509,
        118517, 118531, 118572, 118607, 119189, 119221, 119356, 119457, 120695, 121585, 121827, 122138,
        122180, 122261, 122299, 122422, 122463, 122551, 122658, 122764, 122827, 122911, 122926, 123045,
        123121, 123125, 123127, 123169, 123392, 123413, 123463, 123546, 123550, 123590
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'repa citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM repa_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING repa_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 42 local citers name the method in title or abstract.
CREATE TEMP TABLE repa_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'repa'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        44154, 45857, 46626, 47657, 47684, 49441, 50132, 50914, 54342, 54738, 54772, 54871,
        55492, 55955, 55983, 56127, 56560, 56765, 56801, 57032, 60815, 61313, 62072, 62600,
        63437, 64150, 64621, 71525, 72095, 72583, 74164, 82915, 83336, 83683, 84053, 84744,
        86362, 99011, 100076, 122351, 122565, 122625
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM repa_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM repa_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 32 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE repa_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'repa'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        41445, 45857, 46243, 46626, 47684, 49441, 50132, 50914, 54738, 54772, 55492, 55983,
        56560, 56765, 56801, 57032, 58141, 61313, 64150, 64621, 72095, 72583, 82915, 83336,
        83683, 83692, 99394, 100076, 106401, 122351, 122565, 122625
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM repa_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM repa_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
