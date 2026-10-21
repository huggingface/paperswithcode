INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit
)
VALUES (
    'continuous-diffusion-language-model',
    'Continuous Diffusion Language Model',
    'Continuous Diffusion Language Model (Continuous DLM)',
    'Continuous diffusion language models generate text by running Gaussian [Diffusion](/methods/diffusion) in a continuous space (word embeddings, a learned latent space, or the probability simplex) instead of corrupting discrete tokens as in [Discrete Diffusion](/methods/discrete-diffusion) or [MDLM](/methods/mdlm). Tokens are mapped into vectors, a denoiser iteratively refines a sequence of noisy vectors in parallel, and a rounding step maps the final vectors back to tokens. [Diffusion-LM](/paper/2205.14217) introduced the approach with an end-to-end learned embedding and rounding objective, and showed that gradient-based classifier guidance on the continuous latents enables fine-grained controllable generation such as syntax and semantic-content control. Later work extended it to sequence-to-sequence tasks ([DiffuSeq](/paper/2210.08933)), score interpolation and self-conditioning (CDCD), likelihood-based training at scale ([Plaid](/paper/2305.18619)), simplex diffusion ([SSD-LM](/paper/2210.17432)), and latent-space diffusion over autoencoder representations ([Latent Diffusion for Language Generation](/paper/2212.09462)).',
    'continuous diffusion language model, continuous diffusion LM, continuous DLM, Diffusion-LM, continuous text diffusion, embedding-space diffusion, latent diffusion language model',
    (SELECT id FROM areas WHERE name IN ('Language', 'Natural Language Processing')
     ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2205.14217'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Diffusion-LM Improves Controllable Text Generation',
    'https://github.com/XiangLi1999/Diffusion-LM/blob/main/improved-diffusion/improved_diffusion/gaussian_diffusion.py',
    NULL,
    '[Diffusion-LM Improves Controllable Text Generation](/paper/2205.14217)'
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
WHERE slug = 'continuous-diffusion-language-model' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'continuous-diffusion-language-model' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
