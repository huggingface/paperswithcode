-- Add Abliteration method.
-- The weight edit comes from Arditi et al. (arXiv 2406.11717), but the name
-- "abliteration" came from the community (FailSpy's abliterator library) and
-- was popularized by Maxime Labonne's Hugging Face blog post, which the user
-- chose as the source. source_paper_id therefore stays NULL, which also keeps
-- the hourly reference backfill from linking every citer of 2406.11717 (most
-- study refusal directions for steering or defense, not abliteration).

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
    image_credit,
    abstract_linking,
    aliases
)
VALUES (
    'abliteration',
    'Abliteration',
    'Abliteration',
    'Abliteration removes the refusal behavior of a safety-tuned language model without retraining. It runs the model on harmful and harmless instructions, takes the difference of the mean residual-stream activations at the last token to obtain a "refusal direction" per layer, and picks the candidate that best bypasses refusal. That direction is then projected out of every matrix that writes to the residual stream (token embeddings, attention outputs and MLP outputs), a rank-one weight orthogonalization that permanently stops the model from representing it. The technique comes from [Refusal in Language Models Is Mediated by a Single Direction](/paper/2406.11717), which showed that ablating one direction disables refusal across 13 open chat models up to 72B parameters; the name was coined in the open-model community and popularized by Maxime Labonne''s Hugging Face guide, which also showed that a short [DPO](/methods/direct-preference-optimization-dpo) "healing" run recovers most of the benchmark loss. Abliteration is widely used to release uncensored open-weight models and has prompted multi-direction variants and dedicated defenses.',
    'abliteration, Abliteration, abliterated, Abliterated, refusal direction ablation, refusal feature ablation',
    (
        SELECT id
        FROM areas
        WHERE name IN ('Language', 'Natural Language Processing')
        ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END
        LIMIT 1
    ),
    2024,
    NULL,
    'https://huggingface.co/blog/mlabonne/abliteration',
    'Uncensor any LLM with abliteration',
    'https://github.com/FailSpy/abliterator',
    NULL,
    '[Refusal in Language Models Is Mediated by a Single Direction](/paper/2406.11717)',
    'always',
    ARRAY['Refusal Direction Ablation', 'Refusal Feature Ablation (RFA)']
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

-- Curated 2026-10-27 from local papers whose title or abstract mentions
-- abliteration, refusal-direction ablation or weight orthogonalization. Each
-- paper below introduces, applies, extends, evaluates or defends against
-- abliteration. Papers that only steer along a refusal direction, analyze its
-- geometry, or orthogonalize weights against non-refusal directions are left
-- out; none of them match the keywords, so no exclusions are needed.
CREATE TEMP TABLE abliteration_curated_papers ON COMMIT DROP AS
SELECT DISTINCT ON (p.arxiv_id) p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'abliteration'
  AND p.arxiv_id IN (
      '2406.11717', -- Refusal in Language Models Is Mediated by a Single Direction
      '2502.17420', -- The Geometry of Refusal in Large Language Models
      '2505.17306', -- Refusal Direction is Universal Across Safety-Aligned Languages
      '2505.19056', -- An Embarrassingly Simple Defense Against LLM Abliteration Attacks
      '2509.04781', -- The LLM Has Left The Chat: Evidence of Bail Preferences in LLMs
      '2509.15202', -- Beyond Surface Alignment: ... Probabilistically Ablating Refusal Direction
      '2511.08379', -- SOM Directions are Better than One
      '2512.13655', -- Comparative Analysis of LLM Abliteration Methods
      '2512.18901', -- Gabliteration
      '2602.16977', -- Fail-Closed Alignment for Large Language Models
      '2603.04355', -- Efficient Refusal Ablation in LLM through Optimal Transport
      '2604.02574', -- Understanding the Effects of Safety Unalignment on LLMs
      '2605.06652', -- When No Benchmark Exists: Validating Comparative LLM Safety Scoring
      '2605.21706', -- Latent-space Attacks for Refusal Evasion in Language Models
      '2609.16204'  -- Decoy Direction Optimization: A Post-Hoc Defense Against LLM Abliteration
  )
ORDER BY p.arxiv_id, p.is_latest_version DESC, p.id DESC;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM abliteration_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM abliteration_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
