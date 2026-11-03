-- Add DSPy method, introduced by Khattab et al., "DSPy: Compiling
-- Declarative Language Model Calls into Self-Improving Pipelines"
-- (arXiv 2310.03714).

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
    'dspy',
    'DSPy',
    'DSPy',
    'DSPy is a programming model for building and optimizing language model pipelines. Instead of hand-written prompt templates, a DSPy program declares typed signatures such as `"context, question -> answer"` and composes parameterized modules like `Predict`, `ChainOfThought`, `ReAct`, and `Retrieve` in a define-by-run style inspired by PyTorch. A compiler (originally called a teleprompter, now an optimizer) then tunes the program for a given metric by bootstrapping few-shot demonstrations, rewriting instructions, or finetuning the underlying model. This replaces manual [prompt engineering](/methods/prompt-engineering) with systematic optimization of [chain-of-thought](/methods/chain-of-thought-cot), [RAG](/methods/rag), and agent pipelines. In the original paper, a few lines of compiled DSPy let GPT-3.5 and Llama 2 13B Chat outperform standard [few-shot prompting](/methods/few-shot-prompting) by over 25% and 65% respectively. Later DSPy optimizers include MIPRO and [GEPA](/methods/gepa).',
    'DSPy, dspy, DSPy program, DSPy pipeline, DSPy optimizer, DSPy teleprompter',
    (
        SELECT id
        FROM areas
        WHERE name IN ('Language', 'Natural Language Processing')
        ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2310.03714'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines',
    'https://github.com/stanfordnlp/dspy/blob/main/dspy/predict/chain_of_thought.py',
    NULL,
    '[Learning DSPy (1): The power of good abstractions](https://thedataquarry.com/blog/learning-dspy-1-the-power-of-good-abstractions/), Prashanth Rao',
    'always',
    ARRAY[]::text[]
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

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id
FROM methods
WHERE slug = 'dspy' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
