-- Add 3D Gaussian Splatting aliases to the gaussian-splatting method.
-- Append-only and idempotent: each alias is added only when absent.

UPDATE methods
SET
    keywords = CASE
        WHEN keywords IS NULL OR btrim(keywords) = '' THEN '3D Gaussian Splatting'
        ELSE keywords || ', 3D Gaussian Splatting'
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'gaussian-splatting'
  AND NOT ('3D Gaussian Splatting' = ANY (string_to_array(regexp_replace(coalesce(keywords, ''), '\s*,\s*', ',', 'g'), ',')));

UPDATE methods
SET
    keywords = CASE
        WHEN keywords IS NULL OR btrim(keywords) = '' THEN '3DGS'
        ELSE keywords || ', 3DGS'
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'gaussian-splatting'
  AND NOT ('3DGS' = ANY (string_to_array(regexp_replace(coalesce(keywords, ''), '\s*,\s*', ',', 'g'), ',')));
