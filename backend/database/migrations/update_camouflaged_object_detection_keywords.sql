-- Append keyword aliases to tasks.camouflaged-object-detection: add the common "camouflage" spelling.
-- Append-only and idempotent: each alias is added only when missing.

UPDATE tasks
SET keywords = CASE WHEN coalesce(keywords, '') = '' THEN 'camouflage object detection' ELSE keywords || ', ' || 'camouflage object detection' END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'camouflaged-object-detection'
  AND NOT ('camouflage object detection' = ANY (regexp_split_to_array(coalesce(keywords, ''), '\s*,\s*')));
