-- Launch-page methods reuse their source page's thumbnail (the pattern used by
-- claude-opus-5 and gpt-5-2); GPT-3.5 has no source page and stays without an image.
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
      'chatgpt', 'gpt-4-turbo', 'o1-mini', 'o3-mini', 'gpt-4-5', 'claude-3',
      'claude-3-opus', 'vicuna', 'alpaca', 'qwq', 'mistral-large'
  )
  AND m.image_url IS DISTINCT FROM p.thumbnail_url;
