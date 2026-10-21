INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit
)
VALUES (
    'cosmos',
    'Cosmos',
    'NVIDIA Cosmos World Foundation Models (Cosmos WFM)',
    'Cosmos is NVIDIA''s family of open-weight world foundation models (WFMs) for Physical AI. Pre-trained on clips curated from about 20M hours of video, a Cosmos model takes past video frames plus a text or action condition and generates the future state of the world as video. The platform pairs a video curation pipeline and continuous and discrete video tokenizers with two kinds of pre-trained WFMs: latent [diffusion](/methods/diffusion-transformer-dit) models and autoregressive [Transformer](/methods/transformer) models over discrete tokens. Developers then post-train these generalists for camera control, robotic manipulation and autonomous driving, behind a guardrail system. Later releases extend the family: Cosmos-Predict2 and Cosmos-Predict2.5 world generators, Cosmos-Transfer for multimodal control, Cosmos-Reason for physical reasoning, and Cosmos 3; and robotics and driving work often uses Cosmos as a video world model, simulator or policy backbone.',
    'NVIDIA Cosmos, Cosmos World Foundation Model, Cosmos World Foundation Models, Cosmos WFM, Cosmos WFMs, Cosmos-Predict, Cosmos Predict, Cosmos-Transfer, Cosmos Transfer, Cosmos Tokenizer, Cosmos-Tokenizer, Cosmos-Reason, Cosmos Reason, Cosmos-Drive, Cosmos Policy, Cosmos-Policy, Cosmos 3, Cosmos3',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    2025,
    (SELECT id FROM papers WHERE arxiv_id = '2501.03575'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Cosmos World Foundation Model Platform for Physical AI',
    'https://github.com/nvidia-cosmos/cosmos-predict1',
    NULL,
    '[Cosmos World Foundation Model Platform for Physical AI](/paper/2501.03575)'
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
WHERE slug = 'cosmos' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'cosmos' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
