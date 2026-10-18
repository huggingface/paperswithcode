-- Add NVFP4 (no single introducing paper).
-- Added 2026-10-18 from a scan of methods named by many recent papers but
-- missing from the catalog.

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
    'nvfp4',
    'NVFP4',
    'NVIDIA 4-bit Floating Point (NVFP4)',
    'NVFP4 is a 4-bit floating-point format introduced with NVIDIA''s Blackwell GPU architecture for low-precision LLM inference and training. Each element is stored as FP4 E2M1 (1 sign, 2 exponent and 1 mantissa bit), and every block of 16 contiguous elements shares an FP8 E4M3 scale factor, with an additional per-tensor FP32 scale that keeps block scales in range. Compared with the MXFP4 format of the [microscaling formats](/methods/microscaling-formats), the smaller blocks and more precise non-power-of-two scales reduce quantization error. [Pretraining Large Language Models with NVFP4](/paper/2509.25149) showed that NVFP4 training is stable at scale when combined with Random Hadamard transforms, a two-dimensional quantization scheme, stochastic rounding and a few higher-precision layers: a 12-billion-parameter model trained on 10 trillion tokens matched the training loss and downstream accuracy of an [FP8](/methods/fp8) baseline. NVFP4 is used for [quantization](/methods/quantization) of open-weight models and in [quantization-aware training](/methods/qat).',
    'NVFP4',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2024,
    NULL,
    'https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference/',
    'Introducing NVFP4 for Efficient and Accurate Low-Precision Inference',
    'https://github.com/NVIDIA/TransformerEngine',
    NULL,
    '[Pretraining Large Language Models with NVFP4](/paper/2509.25149)'
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

-- 31 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE nvfp4_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'nvfp4'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        49688, 53003, 53039, 53187, 53452, 53988, 54972, 55617, 57016, 57308, 57455, 58371,
        59127, 59722, 59868, 61653, 61948, 62617, 64248, 67395, 83167, 83366, 83513, 85697,
        98431, 100310, 101836, 113922, 122423, 122861, 123037
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM nvfp4_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM nvfp4_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
