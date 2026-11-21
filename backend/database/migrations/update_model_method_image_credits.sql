-- Model-family method images: credits, image sources and clears.
--
-- Image bytes are not stored in this file. Self-hosted figures are imported
-- separately with:
--   uv run --env-file backend/keys.env python backend/database/import_entity_image.py \
--       methods <slug> /tmp/paperswithcode_entity_image_seeds/methods/<slug>.png
-- (figures cropped at 3x from the source arXiv PDF, or the noted model card).
--
-- Idempotent: every statement sets fixed values by slug.

BEGIN;

-- 1. Self-hosted figures from the source arXiv paper (image_data imported
--    separately); credit = source paper page, no external image_url.
UPDATE methods SET image_url = NULL, image_credit = '[Qwen Technical Report](/paper/2309.16609)' WHERE slug = 'qwen';
UPDATE methods SET image_url = NULL, image_credit = '[Qwen2 Technical Report](/paper/2407.10671)' WHERE slug = 'qwen2';
UPDATE methods SET image_url = NULL, image_credit = '[Qwen2.5-Coder Technical Report](/paper/2409.12186)' WHERE slug = 'qwen2-5-coder';
UPDATE methods SET image_url = NULL, image_credit = '[Qwen2.5-Math Technical Report: Toward Mathematical Expert Model via Self-Improvement](/paper/2409.12122)' WHERE slug = 'qwen2-5-math';
UPDATE methods SET image_url = NULL, image_credit = '[Gemma: Open Models Based on Gemini Research and Technology](/paper/2403.08295)' WHERE slug = 'gemma';
UPDATE methods SET image_url = NULL, image_credit = '[Gemini: A Family of Highly Capable Multimodal Models](/paper/2312.11805)' WHERE slug = 'gemini-1-0';
UPDATE methods SET image_url = NULL, image_credit = '[InternVL: Scaling up Vision Foundation Models and Aligning for Generic Visual-Linguistic Tasks](/paper/2312.14238)' WHERE slug = 'internvl';
UPDATE methods SET image_url = NULL, image_credit = '[LLaVA-OneVision: Easy Visual Task Transfer](/paper/2408.03326)' WHERE slug = 'llava-onevision';
UPDATE methods SET image_url = NULL, image_credit = '[OLMo: Accelerating the Science of Language Models](/paper/2402.00838)' WHERE slug = 'olmo';
UPDATE methods SET image_url = NULL, image_credit = '[Code Llama: Open Foundation Models for Code](/paper/2308.12950)' WHERE slug = 'code-llama';
UPDATE methods SET image_url = NULL, image_credit = '[Phi-3 Technical Report: A Highly Capable Language Model Locally on Your Phone](/paper/2404.14219)' WHERE slug = 'phi-3';
UPDATE methods SET image_url = NULL, image_credit = '[Phi-4 Technical Report](/paper/2412.08905)' WHERE slug = 'phi-4';
UPDATE methods SET image_url = NULL, image_credit = '[Gemma 2: Improving Open Language Models at a Practical Size](/paper/2408.00118)' WHERE slug = 'gemma-2';
UPDATE methods SET image_url = NULL, image_credit = '[Llama 2: Open Foundation and Fine-Tuned Chat Models](/paper/2307.09288)' WHERE slug = 'llama-2';
UPDATE methods SET image_url = NULL, image_credit = '[Qwen2-VL: Enhancing Vision-Language Model''s Perception of the World at Any Resolution](/paper/2409.12191)' WHERE slug = 'qwen2-vl';
UPDATE methods SET image_url = NULL, image_credit = '[Qwen3-Omni Technical Report](/paper/2509.17765)' WHERE slug = 'qwen3-omni';
UPDATE methods SET image_url = NULL, image_credit = '[Qwen2.5-Omni Technical Report](/paper/2503.20215)' WHERE slug = 'qwen2-5-omni';
UPDATE methods SET image_url = NULL, image_credit = '[LLaMA: Open and Efficient Foundation Language Models](/paper/2302.13971)' WHERE slug = 'llama';
UPDATE methods SET image_url = NULL, image_credit = '[Visual Instruction Tuning](/paper/2304.08485)' WHERE slug = 'llava';
UPDATE methods SET image_url = NULL, image_credit = '[Qwen3 Technical Report](/paper/2505.09388)' WHERE slug = 'qwen3';
UPDATE methods SET image_url = NULL, image_credit = '[Gemini 2.5: Pushing the Frontier with Advanced Reasoning, Multimodality, Long Context, and Next Generation Agentic Capabilities](/paper/2507.06261)' WHERE slug = 'gemini-2-5';
UPDATE methods SET image_url = NULL, image_credit = '[Language Models are Few-Shot Learners](/paper/2005.14165)' WHERE slug = 'gpt-3';

-- 2. Self-hosted figure from the source launch page (benchmark table).
UPDATE methods SET image_url = NULL, image_credit = '[Introducing Claude 3.5 Sonnet](/paper/97918)' WHERE slug = 'claude-3-5-sonnet';

-- 3. Self-hosted figure from an Apache-2.0 Hugging Face model card.
UPDATE methods SET image_url = NULL, image_credit = '[Qwen3-Coder-480B-A35B-Instruct model card](https://huggingface.co/Qwen/Qwen3-Coder-480B-A35B-Instruct)' WHERE slug = 'qwen3-coder';

-- 4. Closed-model launch pages: reuse the external paper page's thumbnail
--    (same pattern as claude-opus-5 / gpt-5-2); no DB bytes.
UPDATE methods m SET image_data = NULL, image_mime_type = NULL, image_url = p.thumbnail_url,
    image_credit = '[Introducing Claude Fable 5.2 and Claude Mythos 5.2](/paper/132092)'
  FROM papers p WHERE p.id = 132092 AND m.slug = 'claude-fable-5-2';
UPDATE methods m SET image_data = NULL, image_mime_type = NULL, image_url = p.thumbnail_url,
    image_credit = '[Introducing Claude 4](/paper/97919)'
  FROM papers p WHERE p.id = 97919 AND m.slug IN ('claude-4', 'claude-opus-4', 'claude-sonnet-4');
UPDATE methods m SET image_data = NULL, image_mime_type = NULL, image_url = p.thumbnail_url,
    image_credit = '[Grok 4](/paper/133611)'
  FROM papers p WHERE p.id = 133611 AND m.slug = 'grok-4';
UPDATE methods m SET image_data = NULL, image_mime_type = NULL, image_url = p.thumbnail_url,
    image_credit = '[GLM-4.7: Advancing the Coding Capability](/paper/131725)'
  FROM papers p WHERE p.id = 131725 AND m.slug = 'glm-4-7';

-- 5. No reusable real figure: drop the generated illustration / unmatched credit.
--    gpt-4-1, gpt-5-1: launch-page thumbnails are generated text cards.
--    gpt-4o-mini: launch-page thumbnail is an unrelated "GPT-4o Model API Docs" card.
--    deepseek-v3-1, kimi-k2-5: model cards only carry logos.
--    llama-3-3: no source page; model card has no figure.
UPDATE methods SET image_data = NULL, image_mime_type = NULL, image_url = NULL, image_credit = NULL
  WHERE slug IN ('gpt-4-1', 'gpt-5-1', 'gpt-4o-mini', 'deepseek-v3-1', 'kimi-k2-5', 'llama-3-3');

COMMIT;
