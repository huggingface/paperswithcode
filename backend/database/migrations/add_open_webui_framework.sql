-- Add Open WebUI to the Inference & Serving framework category.
-- Production chat users looked it up as "openwebui" on 2026-10-22; it is a
-- self-hosted chat front end for Ollama and OpenAI-compatible servers, not a method.

BEGIN;

INSERT INTO repositories (url, owner, name, num_stars, source)
VALUES (
    'https://github.com/open-webui/open-webui',
    'open-webui',
    'open-webui',
    0,
    'framework_catalog'
)
ON CONFLICT (url) DO NOTHING;

INSERT INTO frameworks (
    category_id,
    repository_id,
    slug,
    name,
    organization_name,
    description,
    when_to_use,
    docs_url,
    display_order
)
SELECT
    category.id,
    repository.id,
    'open-webui',
    'Open WebUI',
    'Open WebUI',
    'Self-hosted, offline-capable chat interface for LLMs that connects to Ollama and any OpenAI-compatible server, with multi-user accounts, retrieval-augmented generation over uploaded documents, web search, tools and pipelines.',
    'Give a team a ChatGPT-style web UI on top of models you already serve with Ollama, vLLM or llama.cpp, without sending data to a hosted service.',
    'https://docs.openwebui.com/',
    8
FROM framework_categories category
JOIN repositories repository
    ON repository.url = 'https://github.com/open-webui/open-webui'
WHERE category.slug = 'inference'
ON CONFLICT (slug) DO UPDATE SET
    category_id = EXCLUDED.category_id,
    repository_id = EXCLUDED.repository_id,
    name = EXCLUDED.name,
    organization_name = EXCLUDED.organization_name,
    description = EXCLUDED.description,
    when_to_use = EXCLUDED.when_to_use,
    docs_url = EXCLUDED.docs_url,
    display_order = EXCLUDED.display_order,
    updated_at = now();

INSERT INTO framework_platforms (framework_id, platform)
SELECT framework.id, 'cpu'
FROM frameworks framework
WHERE framework.slug = 'open-webui'
ON CONFLICT DO NOTHING;

COMMIT;
