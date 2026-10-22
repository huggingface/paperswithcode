-- Add BS-RoFormer, introduced in arXiv 2309.02612.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url, image_url, image_credit
)
VALUES (
    'bs-roformer',
    'BS-RoFormer',
    'Band-Split RoPE Transformer (BS-RoFormer)',
    'BS-RoFormer is a music source separation model that splits the complex spectrogram into frequency bands, embeds each band, and processes the result with stacked [Transformer](/methods/transformer) blocks using rotary position embeddings (RoPE). Each layer attends first along the time axis and then along the frequency-band axis, and a multi-band mask estimation module predicts a mask per source for the inverse STFT. A system built on it ranked first in the music source separation track of the Sound Demixing Challenge 2023, and a smaller version reached 9.80 dB average SDR on MUSDB18HQ without extra training data.',
    'BS-RoFormer, BS RoFormer, band-split RoPE transformer, Band-Split RoPE Transformer',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2309.02612' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Music Source Separation with Band-Split RoPE Transformer',
    'https://github.com/lucidrains/BS-RoFormer',
    NULL,
    '[Music Source Separation with Band-Split RoPE Transformer](/paper/2309.02612)'
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
WHERE slug = 'bs-roformer' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'bs-roformer' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 16 local citers cite the source without naming the method in title or abstract; exclude them so the hourly reference backfill does not link them.
CREATE TEMP TABLE bs_roformer_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bs-roformer'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        30345, 33764, 36297, 39552, 51901, 60998, 61381, 64544, 68156, 68257, 73096, 73300,
        76972, 99991, 111236, 123563
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'bs-roformer citation review 2026-10-22: cites the source without naming the method in title or abstract'
FROM bs_roformer_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING bs_roformer_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 2 local citers name the method in title or abstract.
CREATE TEMP TABLE bs_roformer_cited ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bs-roformer'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        61273, 78432
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM bs_roformer_cited x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM bs_roformer_cited x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 2 papers match the method keywords (same matcher as the daily keyword backfill).
CREATE TEMP TABLE bs_roformer_keyword ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bs-roformer'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        61273, 78432
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM bs_roformer_keyword x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM bs_roformer_keyword x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
