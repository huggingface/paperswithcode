-- Add Representation Autoencoder, introduced in arXiv 2510.11690.
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
    'representation-autoencoder',
    'Representation Autoencoder',
    'Representation Autoencoder (RAE)',
    'A Representation Autoencoder (RAE) replaces the [VAE](/methods/vae) used in latent [diffusion transformers](/methods/diffusion-transformer-dit) with a frozen, pretrained representation encoder, such as [DINOv2](/methods/dinov2), [SigLIP](/methods/siglip) or a [Masked Autoencoder](/methods/masked-autoencoder), paired with a trained [ViT](/methods/vision-transformer) decoder. Standard SD-VAE latents are low-dimensional and learned purely for reconstruction. RAE latents are high-dimensional and semantically rich, yet still give high-quality reconstructions. The paper analyzes why diffusion transformers struggle in such wide latent spaces and proposes theoretically motivated fixes: matching transformer width to token dimension, a dimension-dependent noise schedule shift, and a lightweight wide DDT head (DiT^DH). With these, training converges faster without the auxiliary alignment loss of [REPA](/methods/repa), and reaches 1.51 FID on ImageNet 256×256 without guidance and 1.13 at both 256×256 and 512×512 with guidance. RAE has since been extended to text-to-image scaling, video latents and world models.',
    'representation autoencoder',
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
        WHERE arxiv_id = '2510.11690'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Diffusion Transformers with Representation Autoencoders',
    'https://github.com/bytetriper/RAE',
    NULL,
    '[Diffusion Transformers with Representation Autoencoders](/paper/2510.11690)'
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
WHERE slug = 'representation-autoencoder' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'representation-autoencoder' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 157 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE representation_autoencoder_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'representation-autoencoder'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        45230, 50041, 53132, 53503, 53669, 53990, 54329, 54342, 54419, 54449, 54501, 54567,
        54631, 54637, 54644, 54732, 54773, 54871, 54895, 54905, 54923, 54946, 54987, 55051,
        55330, 55401, 55432, 55454, 55629, 55666, 55677, 55794, 55848, 55991, 56119, 56201,
        56302, 56441, 56509, 56535, 56634, 56672, 56765, 56801, 56861, 56934, 56988, 57032,
        57101, 57179, 57196, 57309, 57322, 57424, 57466, 57531, 57577, 57687, 57709, 57734,
        57818, 57841, 58008, 59036, 59061, 59163, 59164, 59298, 59306, 59390, 59768, 59811,
        60171, 60358, 61142, 61894, 62771, 63437, 63686, 63756, 64150, 64247, 64525, 66102,
        82930, 82943, 82947, 83114, 83121, 83197, 83227, 83302, 83367, 83525, 83526, 83674,
        83683, 83775, 83799, 83804, 84251, 84274, 85004, 85588, 85643, 98256, 98414, 98466,
        98757, 98927, 98945, 99011, 99083, 99827, 102247, 102585, 102600, 103906, 104019, 104578,
        105854, 105937, 105949, 106030, 108615, 108720, 108945, 108962, 109082, 109619, 113803, 114050,
        117410, 117425, 118509, 119169, 119356, 119457, 121094, 122138, 122144, 122289, 122299, 122551,
        122552, 122590, 122625, 122827, 123012, 123045, 123125, 123392, 123406, 123413, 123468, 123550,
        123590
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'representation-autoencoder citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM representation_autoencoder_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING representation_autoencoder_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 21 local citers name the method in title or abstract.
CREATE TEMP TABLE representation_autoencoder_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'representation-autoencoder'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        54713, 55447, 56421, 56808, 58271, 64935, 83236, 83336, 83619, 98254, 98318, 104309,
        104589, 108914, 109302, 118035, 122180, 122261, 122422, 122463, 123169
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM representation_autoencoder_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM representation_autoencoder_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 25 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE representation_autoencoder_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'representation-autoencoder'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        54713, 55447, 56421, 56808, 58271, 60983, 61225, 64935, 83236, 83336, 83619, 98254,
        98318, 102575, 102577, 104309, 104589, 108914, 109302, 118035, 122180, 122261, 122422, 122463,
        123169
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM representation_autoencoder_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM representation_autoencoder_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
