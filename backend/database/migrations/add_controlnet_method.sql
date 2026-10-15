-- Add ControlNet method, sourced from arXiv 2302.05543.

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
    'controlnet',
    'ControlNet',
    'ControlNet',
    'ControlNet adds spatial conditioning, such as Canny edges, depth maps, human pose, segmentation maps or scribbles, to a large pretrained text-to-image [diffusion](/methods/diffusion) model like [Stable Diffusion](/methods/stable-diffusion). It locks the original model weights and attaches a trainable copy of the [U-Net](/methods/u-net) encoder blocks, which receives the condition image and feeds its outputs back into the frozen decoder through zero convolutions: 1x1 convolutions initialized to zero, so training starts from the unchanged base model and no harmful noise reaches it. Because the backbone is preserved, ControlNet trains robustly on small (under 50k) as well as large (over 1m) datasets, and trained ControlNets transfer to community fine-tunes of the same base model. It became the standard way to add structural control to image generation.',
    'ControlNet',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2302.05543'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Adding Conditional Control to Text-to-Image Diffusion Models',
    'https://github.com/lllyasviel/ControlNet/blob/main/cldm/cldm.py',
    NULL,
    '[Adding Conditional Control to Text-to-Image Diffusion Models](/paper/2302.05543)'
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
WHERE slug = 'controlnet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'controlnet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
