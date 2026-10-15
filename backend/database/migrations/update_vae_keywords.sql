-- Add Variational Autoencoder aliases to the vae method (chat lookups missed them).
-- Append-only and idempotent: each alias is added only when absent.

UPDATE methods
SET
    keywords = CASE
        WHEN keywords IS NULL OR btrim(keywords) = '' THEN 'variational autoencoder'
        ELSE keywords || ', variational autoencoder'
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'vae'
  AND NOT ('variational autoencoder' = ANY (string_to_array(regexp_replace(coalesce(keywords, ''), '\s*,\s*', ',', 'g'), ',')));

UPDATE methods
SET
    keywords = CASE
        WHEN keywords IS NULL OR btrim(keywords) = '' THEN 'variational auto-encoder'
        ELSE keywords || ', variational auto-encoder'
    END,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'vae'
  AND NOT ('variational auto-encoder' = ANY (string_to_array(regexp_replace(coalesce(keywords, ''), '\s*,\s*', ',', 'g'), ',')));
