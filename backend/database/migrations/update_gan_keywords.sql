-- Add conditional GAN alias to the gan method; generative adversarial network is already present.
-- Append-only and idempotent: each alias is added only when absent.

UPDATE methods
SET
    keywords = CASE
        WHEN keywords IS NULL OR btrim(keywords) = '' THEN 'generative adversarial network'
        ELSE keywords || ', generative adversarial network'
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'gan'
  AND NOT ('generative adversarial network' = ANY (string_to_array(regexp_replace(coalesce(keywords, ''), '\s*,\s*', ',', 'g'), ',')));

UPDATE methods
SET
    keywords = CASE
        WHEN keywords IS NULL OR btrim(keywords) = '' THEN 'conditional GAN'
        ELSE keywords || ', conditional GAN'
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'gan'
  AND NOT ('conditional GAN' = ANY (string_to_array(regexp_replace(coalesce(keywords, ''), '\s*,\s*', ',', 'g'), ',')));
