-- Append keyword aliases to tasks.zero-shot-segmentation: open-vocabulary segmentation is already a keyword; add spelling variants users look up.
-- Append-only and idempotent: each alias is added only when missing.

UPDATE tasks
SET keywords = CASE WHEN coalesce(keywords, '') = '' THEN 'open vocabulary segmentation' ELSE keywords || ', ' || 'open vocabulary segmentation' END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'zero-shot-segmentation'
  AND NOT ('open vocabulary segmentation' = ANY (regexp_split_to_array(coalesce(keywords, ''), '\s*,\s*')));

UPDATE tasks
SET keywords = CASE WHEN coalesce(keywords, '') = '' THEN 'open-vocabulary semantic segmentation' ELSE keywords || ', ' || 'open-vocabulary semantic segmentation' END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'zero-shot-segmentation'
  AND NOT ('open-vocabulary semantic segmentation' = ANY (regexp_split_to_array(coalesce(keywords, ''), '\s*,\s*')));

UPDATE tasks
SET keywords = CASE WHEN coalesce(keywords, '') = '' THEN 'open vocabulary semantic segmentation' ELSE keywords || ', ' || 'open vocabulary semantic segmentation' END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'zero-shot-segmentation'
  AND NOT ('open vocabulary semantic segmentation' = ANY (regexp_split_to_array(coalesce(keywords, ''), '\s*,\s*')));

UPDATE tasks
SET keywords = CASE WHEN coalesce(keywords, '') = '' THEN 'open-vocabulary panoptic segmentation' ELSE keywords || ', ' || 'open-vocabulary panoptic segmentation' END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'zero-shot-segmentation'
  AND NOT ('open-vocabulary panoptic segmentation' = ANY (regexp_split_to_array(coalesce(keywords, ''), '\s*,\s*')));
