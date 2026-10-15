-- Append keyword aliases to tasks.3d-semantic-segmentation: add the generic point cloud segmentation alias.
-- Append-only and idempotent: each alias is added only when missing.

UPDATE tasks
SET keywords = CASE WHEN coalesce(keywords, '') = '' THEN 'point cloud segmentation' ELSE keywords || ', ' || 'point cloud segmentation' END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = '3d-semantic-segmentation'
  AND NOT ('point cloud segmentation' = ANY (regexp_split_to_array(coalesce(keywords, ''), '\s*,\s*')));
