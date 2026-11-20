-- Model methods for frequently mentioned models whose launch pages were added
-- as external papers on 2026-11-20: ChatGPT, GPT-4 Turbo, o1-mini, o3-mini,
-- GPT-4.5, Claude 3, Claude 3 Opus, Vicuna, Alpaca, QwQ and Mistral Large.
-- GPT-3.5 has no single introducing release (the series predates the
-- gpt-3.5-turbo launch), so it keeps source_paper_id NULL and a reference URL.
-- Images are imported separately.

WITH new_methods (
    slug, name, full_name, description, keywords, introduced_year,
    source_external_id, abstract_linking, aliases
) AS (VALUES
    ('chatgpt', 'ChatGPT', 'ChatGPT',
     'ChatGPT is OpenAI''s conversational assistant, released as a research preview in November 2022. It is a sibling of [InstructGPT](/paper/2203.02155), trained with [RLHF](/methods/rlhf) on dialogue data in which human trainers played both user and assistant, and was fine-tuned from a model in the [GPT-3.5](/methods/gpt-3-5) series. The dialogue format lets it answer follow-up questions, admit mistakes, challenge incorrect premises and reject inappropriate requests; it is one of the most common baselines and objects of study in LLM papers.',
     -- Version compounds ("ChatGPT-4o") are keywords of the specific model
     -- below, so the longest match tags that model rather than ChatGPT.
     'ChatGPT, Chat-GPT', 2022,
     133666, 'always', ARRAY[]::text[]),
    ('gpt-4-turbo', 'GPT-4 Turbo', 'GPT-4 Turbo',
     'GPT-4 Turbo is the faster, cheaper successor to [GPT-4](/methods/gpt-4) that OpenAI announced at DevDay in November 2023, with a 128K-token context window, more recent world knowledge and lower prices. A vision-enabled version (GPT-4 Turbo with Vision) and later dated snapshots followed before [GPT-4o](/methods/gpt-4o) replaced it as the flagship.',
     'GPT-4 Turbo, GPT-4-Turbo, gpt-4-turbo, gpt-4-1106-preview, GPT-4 Turbo with Vision', 2023,
     133667, 'always', ARRAY['gpt-4-1106-preview']),
    ('o1-mini', 'o1-mini', 'OpenAI o1-mini',
     'o1-mini is OpenAI''s cost-efficient [reasoning model](/methods/reasoning-model) released in September 2024 alongside the [o1](/methods/o1) preview. It is specialized for STEM, especially math and coding, nearly matching o1 on benchmarks such as AIME and Codeforces at a much lower cost and latency, but with less broad world knowledge.',
     'o1-mini, OpenAI o1-mini', 2024,
     133668, 'judge', ARRAY['OpenAI o1-mini']),
    ('o3-mini', 'o3-mini', 'OpenAI o3-mini',
     'o3-mini is OpenAI''s small [reasoning model](/methods/reasoning-model) released in January 2025, the successor to [o1-mini](/methods/o1-mini) in the [o3](/methods/o3) generation. It targets science, math and coding at low cost and latency, was the first small OpenAI reasoning model with function calling and structured outputs, and lets developers choose low, medium or high reasoning effort.',
     'o3-mini, OpenAI o3-mini, o3-mini-high', 2025,
     133669, 'judge', ARRAY['OpenAI o3-mini']),
    ('gpt-4-5', 'GPT-4.5', 'GPT-4.5',
     'GPT-4.5 is OpenAI''s large chat model released as a research preview in February 2025. It scales unsupervised pre-training and post-training rather than chain-of-thought reasoning, which OpenAI reports gives broader knowledge, better intent following, more natural conversation and fewer hallucinations than [GPT-4o](/methods/gpt-4o).',
     'GPT-4.5, GPT-4.5-preview, gpt-4.5-preview', 2025,
     133670, 'always', ARRAY[]::text[]),
    ('claude-3', 'Claude 3', 'Claude 3',
     'Claude 3 is Anthropic''s model family released in March 2024 in three sizes of ascending capability: Claude 3 Haiku, Claude 3 Sonnet and [Claude 3 Opus](/methods/claude-3-opus). The family added image input and set new results on benchmarks such as MMLU, GPQA and GSM8K at launch; it was followed by [Claude 3.5 Sonnet](/methods/claude-3-5-sonnet).',
     -- No bare "Claude 3": the keyword linker matches capitalised keywords as
     -- substrings, so it would also tag "Claude 3.5 Haiku" papers.
     'Claude 3 Sonnet, Claude 3 Haiku, Claude 3 family, Claude 3 model family', 2024,
     97920, 'always', ARRAY['Claude 3 Sonnet', 'Claude 3 Haiku']),
    ('claude-3-opus', 'Claude 3 Opus', 'Claude 3 Opus',
     'Claude 3 Opus is the largest model of Anthropic''s [Claude 3](/methods/claude-3) family, released in March 2024. At launch it outperformed its peers on most common evaluations, including undergraduate-level knowledge (MMLU), graduate-level reasoning (GPQA) and basic mathematics (GSM8K), and it was a frequent strong baseline in 2024 papers.',
     'Claude 3 Opus, Claude-3-Opus, claude-3-opus', 2024,
     97920, 'always', ARRAY[]::text[]),
    ('vicuna', 'Vicuna', 'Vicuna',
     'Vicuna is an open chatbot from LMSYS, released in March 2023, made by fine-tuning [LLaMA](/methods/llama) on about 70K user-shared ChatGPT conversations from ShareGPT. Using GPT-4 as a judge, Vicuna-13B was rated at more than 90% of ChatGPT''s quality for about $300 of training; the release also popularized LLM-as-a-judge evaluation, later formalized in [MT-Bench and Chatbot Arena](/paper/2306.05685).',
     'Vicuna, Vicuna-7B, Vicuna-13B, Vicuna-33B, Vicuna v1.5', 2023,
     133671, 'judge', ARRAY[]::text[]),
    ('alpaca', 'Alpaca', 'Stanford Alpaca',
     'Alpaca is Stanford''s instruction-following model released in March 2023, made by fine-tuning [LLaMA](/methods/llama) 7B on 52K instruction-following demonstrations generated from text-davinci-003 with the [Self-Instruct](/methods/self-instruct) method. It behaved similarly to text-davinci-003 in single-turn instruction following while costing under $600 to reproduce, and its data and recipe were widely reused for instruction tuning.',
     -- Lowercase "alpaca" is matched as a whole word, so AlpacaEval and
     -- AlpacaFarm papers are not tagged.
     'alpaca, Stanford Alpaca', 2023,
     133672, 'judge', ARRAY['Stanford Alpaca']),
    ('qwq', 'QwQ', 'QwQ (Qwen with Questions)',
     'QwQ ("Qwen with Questions") is the Qwen team''s open [reasoning model](/methods/reasoning-model) line, introduced in November 2024 as the experimental QwQ-32B-Preview. It reasons with long chains of thought that question their own assumptions and explore alternative paths, with particular strength in math and coding; QwQ-32B (March 2025) scaled up reinforcement learning on the same base and preceded the reasoning modes of [Qwen3](/methods/qwen3).',
     'QwQ, QwQ-32B, QwQ-32B-Preview', 2024,
     133673, 'always', ARRAY[]::text[]),
    ('mistral-large', 'Mistral Large', 'Mistral Large',
     'Mistral Large is Mistral AI''s flagship API model line, introduced in February 2024 with strong multilingual reasoning, text understanding and code generation; at launch Mistral reported it as the second-ranked generally available API model after [GPT-4](/methods/gpt-4) on common benchmarks. Later versions include Mistral Large 2, Mistral Large 3 and Mistral Large 4.',
     'Mistral Large, Mistral-Large, mistral-large-latest', 2024,
     133674, 'always', ARRAY[]::text[])
)
INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
SELECT nm.slug, nm.name, nm.full_name, nm.description, nm.keywords,
       (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
       nm.introduced_year, p.id, NULL, p.title,
       NULL, NULL, '[' || p.title || '](/paper/' || p.id || ')',
       nm.abstract_linking, nm.aliases
FROM new_methods nm
JOIN papers p ON p.id = nm.source_external_id
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

-- GPT-3.5: no introducing release; reference the gpt-3.5-turbo API launch.
INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'gpt-3-5', 'GPT-3.5', 'GPT-3.5',
    'GPT-3.5 is OpenAI''s series of models between [GPT-3](/methods/gpt-3) and [GPT-4](/methods/gpt-4), trained on text and code and aligned with instruction tuning and [RLHF](/methods/rlhf). The series, which finished training in early 2022, includes code-davinci-002, text-davinci-002 and text-davinci-003; [ChatGPT](/methods/chatgpt) was fine-tuned from it, and gpt-3.5-turbo, launched in the API in March 2023, became the most widely used GPT-3.5 model and a standard baseline in papers.',
    'GPT-3.5, GPT3.5, GPT-3.5 Turbo, GPT-3.5-turbo, gpt-3.5-turbo, ChatGPT-3.5, text-davinci-003, text-davinci-002, code-davinci-002',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2022, NULL,
    'https://openai.com/index/introducing-chatgpt-and-whisper-apis/',
    'Introducing ChatGPT and Whisper APIs',
    NULL, NULL, NULL, 'always',
    ARRAY['GPT-3.5 Turbo', 'text-davinci-003', 'text-davinci-002', 'code-davinci-002']
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

-- "ChatGPT-4o", "ChatGPT-4" and "ChatGPT-5" name the underlying model; as
-- longer keywords they win the keyword linker's longest match over "ChatGPT".
UPDATE methods SET keywords = keywords || ', ' || v.keyword, updated_at = CURRENT_TIMESTAMP
FROM (VALUES ('gpt-4o', 'ChatGPT-4o'), ('gpt-4', 'ChatGPT-4'), ('gpt-5', 'ChatGPT-5')) AS v(slug, keyword)
WHERE methods.slug = v.slug
  AND NOT (v.keyword = ANY (string_to_array(replace(methods.keywords, ', ', ','), ',')));

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN (
    'chatgpt', 'gpt-4-turbo', 'o1-mini', 'o3-mini', 'gpt-4-5', 'claude-3',
    'claude-3-opus', 'vicuna', 'alpaca', 'qwq', 'mistral-large'
) AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
