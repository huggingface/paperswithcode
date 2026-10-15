-- Append the skip-gram aliases to the word2vec method keywords (append-only;
-- existing keywords are kept). Skip-gram is one of the two word2vec
-- architectures, and chat users looked the method up under that name.

UPDATE methods
SET keywords = keywords || ', skip-gram',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'word2vec'
  AND NOT (', ' || lower(keywords) || ',') LIKE '%, skip-gram,%';

UPDATE methods
SET keywords = keywords || ', skip gram',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'word2vec'
  AND NOT (', ' || lower(keywords) || ',') LIKE '%, skip gram,%';
