-- Added 2026-10-20 because production chat users looked it up with
-- pwc_get_task and it was missing from the catalog.

INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    level,
    parent_id,
    image_url,
    image_credit,
    useful_leaderboards
)
VALUES (
    'Code Generation',
    'code-generation',
    'Code generation is the task of producing source code from a specification, usually a natural-language description, a function signature with a docstring, or a partially written file. Models are judged by functional correctness: generated programs are executed against hidden unit tests and scored with pass@k, as in HumanEval, MBPP and the contamination-resistant LiveCodeBench, while competitive programming benchmarks such as CodeForces rate models against human contestants. Code generation is a core capability of [language models](/tasks/language-modeling) and the foundation for repository-level [coding agents](/tasks/coding-agents) and [text-to-SQL](/tasks/text-to-sql).',
    'code generation, code synthesis, program synthesis, text-to-code, text-to-code generation, natural language to code, NL2Code, code completion, code LLM, Code LLM, code language model, code large language model, competitive programming',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Evaluating Large Language Models Trained on Code](/paper/2107.03374)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
