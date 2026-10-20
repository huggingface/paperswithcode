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
    'Code generation is the task of writing a self-contained program in a single pass from a specification, such as a natural-language description, a function signature with a docstring, or a design screenshot, with no execution environment or tool use while the model writes. Most benchmarks grade the output by running hidden unit tests and report pass@k: HumanEval, MBPP, their multilingual translation MultiPL-E, the contamination-resistant LiveCodeBench and the scientific-computing SciCode. Design2Code scores screenshot-to-HTML generation by visual similarity, and CRUXEval-O tests the related skill of predicting a program''s output. Repository-level, multi-step work, where a model explores a codebase, edits files, runs tests and iterates, belongs to [coding agents](/tasks/coding-agents). Code generation is a core capability of [language models](/tasks/language-modeling) and underlies [text-to-SQL](/tasks/text-to-sql).',
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
