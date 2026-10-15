-- Append keyword aliases to tasks.coding-agents: add the "code agent" alias.
-- Append-only and idempotent: each alias is added only when missing.

UPDATE tasks
SET keywords = CASE WHEN coalesce(keywords, '') = '' THEN 'code agent' ELSE keywords || ', ' || 'code agent' END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'coding-agents'
  AND NOT ('code agent' = ANY (regexp_split_to_array(coalesce(keywords, ''), '\s*,\s*')));

UPDATE tasks
SET keywords = CASE WHEN coalesce(keywords, '') = '' THEN 'code agents' ELSE keywords || ', ' || 'code agents' END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'coding-agents'
  AND NOT ('code agents' = ANY (regexp_split_to_array(coalesce(keywords, ''), '\s*,\s*')));
