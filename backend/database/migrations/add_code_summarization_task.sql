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
    'Code Summarization',
    'code-summarization',
    'Code summarization generates a short natural-language description of a piece of source code, such as a docstring for a function or a commit message for a diff, to support program comprehension and documentation. It is the reverse direction of [code generation](/tasks/code-generation) and a code-specific form of [summarization](/tasks/summarization). Standard evaluations use the CodeSearchNet-derived code-to-text split of CodeXGLUE across six programming languages and report smoothed BLEU-4, often alongside human or LLM-judged ratings.',
    'code summarization, source code summarization, code comment generation, code-to-text, code documentation generation, docstring generation, commit message generation',
    (SELECT area_id FROM tasks WHERE slug = 'summarization' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'summarization' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'summarization' LIMIT 1),
    NULL,
    '[code2seq: Generating Sequences from Structured Representations of Code](/paper/1808.01400)',
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
