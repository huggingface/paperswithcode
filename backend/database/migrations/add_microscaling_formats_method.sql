-- Add Microscaling Formats, introduced in arXiv 2310.10537.
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
    'microscaling-formats',
    'Microscaling Formats',
    'Microscaling (MX) Data Formats',
    'Microscaling (MX) data formats are block-scaled number formats for deep learning in which a block of k narrow elements shares a single scale. The concrete MX-compliant formats in the Open Compute Project specification use blocks of 32 elements and an 8-bit power-of-two (E8M0) shared scale with FP8 (MXFP8, E4M3 or E5M2), FP6 (MXFP6), FP4 (MXFP4, E2M1) or INT8 (MXINT8) elements. The shared scale gives each block FP32-like dynamic range while elements stay 4-8 bits wide, balancing hardware efficiency, accuracy and ease of use. Across more than two dozen benchmarks, Rouhani et al. found MX formats to be practical drop-in replacements for FP32 in inference and training, and showed the first training of generative language models at sub-8-bit weights, activations and gradients with minimal accuracy loss and no changes to the training recipe. MX formats are natively supported by recent accelerators and inspired NVIDIA''s [NVFP4](/methods/nvfp4); they are widely used for low-bit [quantization](/methods/quantization) and [FP8](/methods/fp8) training.',
    'MXFP, MXINT, microscaling',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2310.10537'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Microscaling Data Formats for Deep Learning',
    'https://github.com/microsoft/microxcaling',
    NULL,
    '[Microscaling Data Formats for Deep Learning](/paper/2310.10537)'
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
WHERE slug = 'microscaling-formats' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'microscaling-formats' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 38 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE microscaling_formats_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'microscaling-formats'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        26767, 29662, 31126, 35154, 35165, 35743, 37300, 38450, 39764, 43348, 44903, 47354,
        47846, 48326, 49154, 49688, 52592, 54619, 55599, 61520, 61712, 61948, 64248, 65457,
        69378, 70120, 72689, 83366, 83744, 85852, 92436, 98567, 99139, 99452, 100310, 104584,
        109583, 113922
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'microscaling-formats citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM microscaling_formats_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING microscaling_formats_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 10 local citers name the method in title or abstract.
CREATE TEMP TABLE microscaling_formats_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'microscaling-formats'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        48881, 53988, 58371, 59284, 70904, 89228, 89765, 93576, 100521, 109699
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM microscaling_formats_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM microscaling_formats_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 26 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE microscaling_formats_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'microscaling-formats'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        48881, 50822, 53187, 53988, 54577, 58017, 58371, 58595, 59284, 59868, 61653, 62617,
        68009, 70904, 74418, 89228, 89765, 93576, 94140, 94517, 99600, 100521, 103212, 103597,
        109015, 109699
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM microscaling_formats_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM microscaling_formats_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
