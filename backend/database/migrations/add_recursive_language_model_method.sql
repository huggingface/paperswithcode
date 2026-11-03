-- Add Recursive Language Model (RLM) method, introduced by Zhang, Kraska &
-- Khattab, "Recursive Language Models" (arXiv 2512.24601).
-- "RLM" also abbreviates reasoning and reward language models in many
-- abstracts, so abstract linking is judged per abstract and the bare
-- acronym is left out of keywords (keyword tagging is literal).

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
    'recursive-language-model',
    'Recursive Language Model',
    'Recursive Language Model (RLM)',
    'A Recursive Language Model (RLM) is an inference strategy for arbitrarily long prompts. Instead of feeding the whole prompt into the context window, an RLM loads it as a variable in a Python REPL environment and lets the language model write code to inspect, split, and search it, recursively calling itself on selected snippets through an `llm_query` function before returning a final answer. This turns long-context processing into a form of [test-time scaling](/methods/test-time-scaling) and [context engineering](/methods/context-engineering) driven by the model itself. RLMs handle inputs up to two orders of magnitude beyond the model context window and, on long-context benchmarks such as OOLONG and BrowseComp-Plus, outperform the base model and common long-context scaffolds such as context compaction and retrieval agents at comparable or lower cost per query.',
    'recursive language model, recursive language models, recursive LM',
    (
        SELECT id
        FROM areas
        WHERE name IN ('Language', 'Natural Language Processing')
        ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2512.24601'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Recursive Language Models',
    'https://github.com/alexzhang13/rlm',
    NULL,
    '[Recursive Language Models](/paper/2512.24601)',
    'judge',
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
WHERE slug = 'recursive-language-model' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
