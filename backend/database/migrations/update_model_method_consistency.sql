-- Make the model-family methods consistent with the add-method rules:
-- a source that exists as a local paper page is set through source_paper_id
-- (never an absolute paperswithcode.co, arXiv or launch-blog URL), the source
-- page lists the method so it shows the "Introduced" banner, model families
-- share the General area, and named model versions always link in abstracts.

UPDATE methods SET full_name = 'Gemini 1.5', updated_at = CURRENT_TIMESTAMP
WHERE slug = 'gemini-1-5' AND full_name <> 'Gemini 1.5';

-- DeepSeek-R1 was released in January 2025 (arXiv 2501.12948).
UPDATE methods SET introduced_year = 2025, updated_at = CURRENT_TIMESTAMP
WHERE slug = 'deepseek-r1' AND introduced_year <> 2025;

-- Rows that already have a source paper keep only the native route.
UPDATE methods SET source_url = NULL, updated_at = CURRENT_TIMESTAMP
WHERE slug IN ('deepseek-r1', 'gemini-1-5', 'gpt-3', 'gpt', 'gpt-2')
  AND source_paper_id IS NOT NULL AND source_url IS NOT NULL;

-- Point rows at the local paper or launch page that introduced them.
WITH sources (slug, paper_id) AS (
    SELECT 'deepseek-v4-flash', (SELECT id FROM papers WHERE arxiv_id = '2606.19348'
                                 ORDER BY is_latest_version DESC, id DESC LIMIT 1)
    UNION ALL SELECT 'deepseek-v4-pro', (SELECT id FROM papers WHERE arxiv_id = '2606.19348'
                                         ORDER BY is_latest_version DESC, id DESC LIMIT 1)
    UNION ALL SELECT 'gemini-2-5-flash', (SELECT id FROM papers WHERE arxiv_id = '2507.06261'
                                          ORDER BY is_latest_version DESC, id DESC LIMIT 1)
    UNION ALL SELECT 'gemini-2-5-pro', (SELECT id FROM papers WHERE arxiv_id = '2507.06261'
                                        ORDER BY is_latest_version DESC, id DESC LIMIT 1)
    UNION ALL SELECT 'llama-3-1', (SELECT id FROM papers WHERE arxiv_id = '2407.21783'
                                   ORDER BY is_latest_version DESC, id DESC LIMIT 1)
    -- External launch pages (source = 'external').
    UNION ALL SELECT 'claude-3-5-sonnet', 97918   -- Introducing Claude 3.5 Sonnet
    UNION ALL SELECT 'claude-4', 97919            -- Introducing Claude 4
    UNION ALL SELECT 'claude-opus-4', 97919
    UNION ALL SELECT 'claude-sonnet-4', 97919
    UNION ALL SELECT 'gpt-4-1', 131724            -- Introducing GPT-4.1 in the API
    UNION ALL SELECT 'gpt-5', 97929               -- Introducing GPT-5
    UNION ALL SELECT 'gpt-5-1', 133437            -- GPT-5.1: A smarter, more conversational ChatGPT
    UNION ALL SELECT 'glm-4-7', 131725            -- GLM-4.7: Advancing the Coding Capability
    UNION ALL SELECT 'grok-4', 133611             -- Grok 4
)
UPDATE methods m
SET source_paper_id = p.id,
    source_url = NULL,
    source_title = p.title,
    updated_at = CURRENT_TIMESTAMP
FROM sources s
JOIN papers p ON p.id = s.paper_id
WHERE m.slug = s.slug
  AND (m.source_paper_id IS DISTINCT FROM p.id OR m.source_url IS NOT NULL);

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN (
    'deepseek-v4-flash', 'deepseek-v4-pro', 'gemini-2-5-flash', 'gemini-2-5-pro',
    'llama-3-1', 'claude-3-5-sonnet', 'claude-4', 'claude-opus-4', 'claude-sonnet-4',
    'gpt-4-1', 'gpt-5', 'gpt-5-1', 'glm-4-7', 'grok-4'
) AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

-- Model families live in General; GPT (the architecture) and LLaVA (visual
-- instruction tuning) keep their technique areas.
UPDATE methods SET area_id = (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
                   updated_at = CURRENT_TIMESTAMP
WHERE slug IN ('gpt-2', 'gpt-4', 'llama')
  AND area_id IS DISTINCT FROM (SELECT id FROM areas WHERE name = 'General' LIMIT 1);

-- "GPT-3" and "GPT-4" name exactly one model wherever they appear; the matcher
-- already keeps "GPT-3.5", "GPT-4o" and "GPT-4 Turbo" apart.
UPDATE methods SET abstract_linking = 'always', updated_at = CURRENT_TIMESTAMP
WHERE slug IN ('gpt-3', 'gpt-4') AND abstract_linking <> 'always';
