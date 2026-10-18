-- Add JiT, introduced in arXiv 2511.13720.
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
    'jit',
    'JiT',
    'Just image Transformers (JiT)',
    'JiT (Just image Transformers) is a pixel-space diffusion model built on the observation that natural images lie on a low-dimensional manifold, whereas noise and noised quantities do not. Most [diffusion](/methods/diffusion) and [flow matching](/methods/flow-matching) networks predict noise (ε) or velocity (v). JiT instead uses x-prediction, directly regressing the clean image. This lets an apparently under-capacity network operate on very high-dimensional inputs. The architecture is a plain [Vision Transformer](/methods/vision-transformer) over large raw-pixel patches (16 or 32 pixels, up to 3,072 values per token), with a bottleneck linear patch embedding. It uses no tokenizer or [VAE](/methods/vae), no pre-training and no auxiliary representation loss. On ImageNet with patch sizes where ε- or v-prediction fails catastrophically, x-prediction stays stable. The 2B-parameter JiT-G/16 reaches 1.82 FID at 256×256. The paper argues for returning to self-contained, tokenizer-free Transformer diffusion on raw data, and JiT has become a common pixel-space baseline.',
    'JiT, just image transformer',
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
        WHERE arxiv_id = '2511.13720'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Back to Basics: Let Denoising Generative Models Denoise',
    'https://github.com/LTH14/JiT',
    NULL,
    '[Back to Basics: Let Denoising Generative Models Denoise](/paper/2511.13720)'
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
WHERE slug = 'jit' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'jit' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 2 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE jit_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'jit'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        56631, 84164
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'jit citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM jit_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING jit_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 16 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE jit_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'jit'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        54772, 56781, 56801, 57032, 57424, 83121, 83931, 95078, 98466, 98529, 98589, 106401,
        109082, 117425, 122299, 123404
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM jit_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM jit_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
