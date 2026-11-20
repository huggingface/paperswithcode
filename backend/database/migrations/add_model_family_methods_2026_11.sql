-- Model-family methods for the most-mentioned open and closed models that had
-- no method page, each sourced from the paper or launch page that introduced it.
-- Images are imported separately with import_entity_image.py.

WITH new_methods (
    slug, name, full_name, description, keywords, introduced_year,
    source_arxiv_id, source_external_id, abstract_linking, aliases
) AS (VALUES
    ('qwen', 'Qwen', 'Qwen',
     'Qwen is Alibaba''s first large language model series, released in 2023 as base models (Qwen) and chat models (Qwen-Chat) aligned with SFT and RLHF, including variants with tool use and agent abilities. It started the family continued by [Qwen2](/methods/qwen2), [Qwen2.5](/methods/qwen2-5) and [Qwen3](/methods/qwen3), and papers often write "Qwen" for the family as a whole.',
     'Qwen, Qwen-7B, Qwen-14B, Qwen-Chat, Qwen-1.8B, Qwen-72B', 2023,
     '2309.16609', NULL, 'always', ARRAY[]::text[]),
    ('qwen2', 'Qwen2', 'Qwen2',
     'Qwen2 is the 2024 successor to [Qwen](/methods/qwen), a suite of dense and [Mixture-of-Experts](/methods/mixture-of-experts) language models from 0.5B to 72B parameters with base and instruction-tuned checkpoints. The flagship Qwen2-72B scores 84.2 on MMLU as a base model, surpassing most earlier open-weight models, and the series was followed by [Qwen2.5](/methods/qwen2-5).',
     'Qwen2, Qwen-2, Qwen2-7B, Qwen2-72B', 2024,
     '2407.10671', NULL, 'always', ARRAY['Qwen-2']),
    ('qwen2-5-coder', 'Qwen2.5-Coder', 'Qwen2.5-Coder',
     'Qwen2.5-Coder is a code-specialized series built on [Qwen2.5](/methods/qwen2-5) and continually pretrained on more than 5.5 trillion tokens, released in sizes from 0.5B to 32B parameters. Careful data cleaning, synthetic data and balanced mixing give state-of-the-art open-model results on more than ten code generation, completion, reasoning and repair benchmarks while keeping general and math skills.',
     'Qwen2.5-Coder, Qwen2.5 Coder, Qwen-2.5-Coder', 2024,
     '2409.12186', NULL, 'always', ARRAY[]::text[]),
    ('qwen2-5-math', 'Qwen2.5-Math', 'Qwen2.5-Math',
     'Qwen2.5-Math is a math-specialized series of [Qwen2.5](/methods/qwen2-5) models (1.5B, 7B and 72B) trained with self-improvement throughout the pipeline: earlier math models generate pretraining data, a reward model guides iterative [supervised fine-tuning](/methods/supervised-fine-tuning-sft), and the same reward model drives reinforcement learning and reranking at inference. It supports both chain-of-thought and tool-integrated reasoning in English and Chinese.',
     'Qwen2.5-Math, Qwen2.5 Math, Qwen-2.5-Math', 2024,
     '2409.12122', NULL, 'always', ARRAY[]::text[]),
    ('gemma', 'Gemma', 'Gemma',
     'Gemma is Google DeepMind''s family of lightweight open models built from the research and technology behind [Gemini](/methods/gemini-1-0), first released in 2024 at 2B and 7B parameters with pretrained and instruction-tuned checkpoints. It outperformed similarly sized open models on 11 of 18 text tasks and was followed by [Gemma 2](/methods/gemma-2), [Gemma 3](/methods/gemma-3) and [Gemma 4](/methods/gemma-4).',
     'Gemma, Gemma-2B, Gemma-7B, Gemma 1, Gemma 1.1', 2024,
     '2403.08295', NULL, 'always', ARRAY[]::text[]),
    ('gemini-1-0', 'Gemini 1.0', 'Gemini 1.0',
     'Gemini 1.0 is the first generation of Google''s natively multimodal Gemini models, released in December 2023 in Ultra, Pro and Nano sizes that understand images, audio, video and text. Gemini Ultra advanced the state of the art on 30 of 32 reported benchmarks and was the first model to reach human-expert performance on MMLU; it was succeeded by [Gemini 1.5](/methods/gemini-1-5).',
     'Gemini 1.0, Gemini 1.0 Pro, Gemini 1.0 Ultra, Gemini 1.0 Nano, Gemini Ultra, Gemini Nano', 2023,
     '2312.11805', NULL, 'always', ARRAY['Gemini 1.0 Pro', 'Gemini 1.0 Ultra', 'Gemini 1.0 Nano', 'Gemini Ultra']),
    ('internvl', 'InternVL', 'InternVL',
     'InternVL is an open vision-language foundation model that scales the vision encoder to 6 billion parameters (InternViT-6B) and progressively aligns it with a large language model on web-scale image-text data. One model covers perception tasks, zero-shot classification and retrieval, and multimodal dialogue, with state-of-the-art results on 32 visual-linguistic benchmarks; later InternVL releases became widely used open multimodal LLMs.',
     'InternVL, InternVL-Chat, InternViT, InternViT-6B, InternVL2, InternVL2.5, InternVL3', 2023,
     '2312.14238', NULL, 'always', ARRAY[]::text[]),
    ('llava-onevision', 'LLaVA-OneVision', 'LLaVA-OneVision',
     'LLaVA-OneVision is a family of open large multimodal models that consolidates the [LLaVA](/methods/llava)-NeXT line into one model for single-image, multi-image and video scenarios. Training across all three settings transfers capabilities between them, so strong video understanding emerges from image-centric training.',
     'LLaVA-OneVision, LLaVA-OV, LLaVA OneVision', 2024,
     '2408.03326', NULL, 'always', ARRAY['LLaVA-OV']),
    ('olmo', 'OLMo', 'Open Language Model (OLMo)',
     'OLMo is the Allen Institute for AI''s fully open language model, released in 2024 together with its training data, training and evaluation code, intermediate checkpoints and logs rather than weights alone, so the whole development process can be studied. Later OLMo 2 and OLMo 3 releases kept the same fully open approach.',
     'OLMo, OLMo-7B, OLMo-1B, OLMo 2, OLMo-2, OLMo 3', 2024,
     '2402.00838', NULL, 'always', ARRAY[]::text[]),
    ('code-llama', 'Code Llama', 'Code Llama',
     'Code Llama is Meta''s family of code models built on [Llama 2](/methods/llama-2), released in 2023 as foundation, Python-specialized and instruction-following variants at 7B to 70B parameters. The models are trained on 16k-token sequences, handle inputs up to 100k tokens, support infilling, and reached state-of-the-art results among open models on several code benchmarks.',
     'Code Llama, CodeLlama, Code-Llama, Code Llama - Python, Code Llama - Instruct', 2023,
     '2308.12950', NULL, 'always', ARRAY['CodeLlama']),
    ('phi-3', 'Phi-3', 'Phi-3',
     'Phi-3 is Microsoft''s 2024 family of small language models, led by the 3.8B-parameter phi-3-mini trained on 3.3 trillion tokens of heavily filtered web and synthetic data. It rivals Mixtral 8x7B and GPT-3.5 (69% on MMLU) while running locally on a phone, with larger phi-3-small and phi-3-medium models and later vision variants.',
     'Phi-3, phi-3, Phi3, phi-3-mini, phi-3-small, phi-3-medium, Phi-3.5, Phi-3-vision', 2024,
     '2404.14219', NULL, 'always', ARRAY[]::text[]),
    ('phi-4', 'Phi-4', 'Phi-4',
     'Phi-4 is Microsoft''s 14B-parameter language model whose training recipe centers on data quality, using synthetic data throughout pretraining and post-training. With minimal changes to the [Phi-3](/methods/phi-3) architecture, it surpasses its teacher GPT-4 on STEM question answering and is strong on reasoning benchmarks for its size.',
     'Phi-4, phi-4, Phi4, Phi-4-mini, Phi-4-reasoning', 2024,
     '2412.08905', NULL, 'always', ARRAY[]::text[]),
    ('gpt-4o-mini', 'GPT-4o mini', 'GPT-4o mini',
     'GPT-4o mini is OpenAI''s cost-efficient small model released in July 2024, a smaller sibling of [GPT-4o](/methods/gpt-4o) that accepts text and images. It outperformed earlier small models on reasoning, math, coding and multimodal benchmarks such as MMLU, MGSM, HumanEval and MMMU at a much lower price, and it is a common low-cost backbone and judge in papers.',
     'GPT-4o mini, GPT-4o-mini, gpt-4o-mini', 2024,
     NULL, 97935, 'always', ARRAY['GPT-4o-mini']),
    ('claude-fable-5-2', 'Claude Fable 5.2', 'Claude Fable 5.2',
     'Claude Fable 5.2 is Anthropic''s November 2026 successor to [Claude Fable 5.1](/methods/claude-fable-5-1), with improvements in coding, reasoning and vision. As with earlier Fable releases, it is the same underlying model as Claude Mythos 5.2 but carries strong cybersecurity and biology safeguards, which lets Anthropic make it available to all users.',
     'Claude Fable 5.2, Claude-Fable-5.2, Fable 5.2', 2026,
     NULL, 132092, 'always', ARRAY['Fable 5.2'])
)
INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
SELECT nm.slug, nm.name, nm.full_name, nm.description, nm.keywords,
       (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
       nm.introduced_year, p.id, NULL, p.title,
       NULL, NULL,
       '[' || p.title || '](/paper/' || COALESCE(p.arxiv_id, p.id::text) || ')',
       nm.abstract_linking, nm.aliases
FROM new_methods nm
JOIN LATERAL (
    SELECT id, arxiv_id, title FROM papers
    WHERE (nm.source_arxiv_id IS NOT NULL AND arxiv_id = nm.source_arxiv_id)
       OR (nm.source_external_id IS NOT NULL AND id = nm.source_external_id)
    ORDER BY is_latest_version DESC, id DESC LIMIT 1
) p ON TRUE
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN (
    'qwen', 'qwen2', 'qwen2-5-coder', 'qwen2-5-math', 'gemma', 'gemini-1-0',
    'internvl', 'llava-onevision', 'olmo', 'code-llama', 'phi-3', 'phi-4',
    'gpt-4o-mini', 'claude-fable-5-2'
) AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
