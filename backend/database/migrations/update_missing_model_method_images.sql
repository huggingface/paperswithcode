-- Launch-page methods reuse their source page's thumbnail (the pattern used by
-- claude-opus-5 and gpt-5-2); GPT-3.5 has no source page and stays without an image.
-- QwQ and GPT-4 Turbo instead carry self-hosted figures from their launch pages
-- (imported with import_entity_image.py), so they are left out here.
UPDATE methods m
SET image_data = NULL,
    image_mime_type = NULL,
    image_url = p.thumbnail_url,
    image_credit = '[' || p.title || '](/paper/' || p.id || ')',
    updated_at = CURRENT_TIMESTAMP
FROM papers p
WHERE p.id = m.source_paper_id
  AND p.thumbnail_url IS NOT NULL
  AND m.slug IN (
      'chatgpt', 'o1-mini', 'o3-mini', 'gpt-4-5', 'claude-3',
      'claude-3-opus', 'vicuna', 'alpaca', 'mistral-large'
  )
  AND m.image_url IS DISTINCT FROM p.thumbnail_url;

-- QwQ: the full-resolution results table from the QwQ-32B-Preview post.
-- GPT-4 Turbo: the DevDay post's Playground screenshot running gpt-4-1106-preview.
-- Their bytes live in image_data; clear any thumbnail URL so the API serves them.
UPDATE methods
SET image_url = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE slug IN ('qwq', 'gpt-4-turbo')
  AND image_mime_type IS NOT NULL
  AND image_url IS NOT NULL;
