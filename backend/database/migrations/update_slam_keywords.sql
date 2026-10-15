-- Append keyword aliases to methods.slam: add lowercase visual slam alias ("visual SLAM" already present).
-- Append-only and idempotent: each alias is added only when missing.

UPDATE methods
SET keywords = CASE WHEN coalesce(keywords, '') = '' THEN 'visual SLAM' ELSE keywords || ', ' || 'visual SLAM' END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'slam'
  AND NOT ('visual SLAM' = ANY (regexp_split_to_array(coalesce(keywords, ''), '\s*,\s*')));

UPDATE methods
SET keywords = CASE WHEN coalesce(keywords, '') = '' THEN 'visual slam' ELSE keywords || ', ' || 'visual slam' END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'slam'
  AND NOT ('visual slam' = ANY (regexp_split_to_array(coalesce(keywords, ''), '\s*,\s*')));
