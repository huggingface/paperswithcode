-- Add GANomaly, introduced in arXiv 1805.06725.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url, image_url, image_credit
)
VALUES (
    'ganomaly',
    'GANomaly',
    'GANomaly',
    'GANomaly is a semi-supervised anomaly detector trained only on normal data. A generator made of an encoder-decoder-encoder pipeline reconstructs each image and re-encodes the reconstruction, while a discriminator, as in a [GAN](/methods/gan), pushes reconstructions to look real. Because the model only learns the distribution of normal samples, the distance between the latent code of the input and that of its reconstruction serves as the anomaly score: anomalous inputs are encoded and reconstructed poorly, so the two codes diverge. It was evaluated on CIFAR-10, MNIST and X-ray security data.',
    'GANomaly',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2018,
    (SELECT id FROM papers WHERE arxiv_id = '1805.06725' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'GANomaly: Semi-Supervised Anomaly Detection via Adversarial Training',
    'https://github.com/samet-akcay/ganomaly',
    NULL,
    '[GANomaly: Semi-Supervised Anomaly Detection via Adversarial Training](/paper/1805.06725)'
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
WHERE slug = 'ganomaly' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'ganomaly' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 70 local citers cite the source without naming the method in title or abstract; exclude them so the hourly reference backfill does not link them.
CREATE TEMP TABLE ganomaly_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ganomaly'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        3633, 4773, 5400, 6004, 6439, 7098, 7314, 7817, 9264, 10495, 11477, 13387,
        14086, 14133, 14380, 18959, 19277, 19592, 19866, 20556, 21491, 23458, 29104, 30019,
        31575, 34080, 34208, 35590, 52531, 58531, 59162, 59741, 59742, 67553, 70768, 70935,
        71073, 74812, 76384, 77083, 78095, 80844, 81012, 88269, 88335, 100434, 104059, 105208,
        105258, 105889, 105891, 105895, 105896, 105897, 105899, 105901, 105903, 105905, 105908, 105910,
        107047, 112789, 113096, 113433, 115249, 115253, 115310, 116596, 116748, 116907
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'ganomaly citation review 2026-10-22: cites the source without naming the method in title or abstract'
FROM ganomaly_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING ganomaly_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
