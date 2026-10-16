-- Add NVIDIA TensorRT-LLM to the Inference & Serving framework category.
-- Production chat users looked it up with pwc_get_method on 2026-10-16; it is
-- an inference engine like vLLM and SGLang, not a method.

BEGIN;

INSERT INTO repositories (url, owner, name, num_stars, source)
VALUES (
    'https://github.com/nvidia/tensorrt-llm',
    'NVIDIA',
    'TensorRT-LLM',
    0,
    'framework_catalog'
)
ON CONFLICT (url) DO NOTHING;

INSERT INTO frameworks (
    category_id,
    repository_id,
    slug,
    name,
    organization_name,
    description,
    when_to_use,
    docs_url,
    display_order
)
SELECT
    category.id,
    repository.id,
    'tensorrt-llm',
    'TensorRT-LLM',
    'NVIDIA',
    'NVIDIA''s open-source library for optimized LLM inference on NVIDIA GPUs, with fused attention kernels, paged KV caching, in-flight batching, speculative decoding, and FP8/FP4 quantization.',
    'Squeeze maximum throughput and lowest latency out of NVIDIA data-center GPUs, especially Hopper and Blackwell, or serve through Triton and NVIDIA Dynamo.',
    'https://nvidia.github.io/TensorRT-LLM/',
    7
FROM framework_categories category
JOIN repositories repository
    ON repository.url = 'https://github.com/nvidia/tensorrt-llm'
WHERE category.slug = 'inference'
ON CONFLICT (slug) DO UPDATE SET
    category_id = EXCLUDED.category_id,
    repository_id = EXCLUDED.repository_id,
    name = EXCLUDED.name,
    organization_name = EXCLUDED.organization_name,
    description = EXCLUDED.description,
    when_to_use = EXCLUDED.when_to_use,
    docs_url = EXCLUDED.docs_url,
    display_order = EXCLUDED.display_order,
    updated_at = now();

INSERT INTO framework_platforms (framework_id, platform)
SELECT framework.id, 'gpu'
FROM frameworks framework
WHERE framework.slug = 'tensorrt-llm'
ON CONFLICT DO NOTHING;

COMMIT;
