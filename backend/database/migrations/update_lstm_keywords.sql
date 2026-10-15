-- Append the standard spelling "long short-term memory" to the LSTM method
-- keywords (append-only; existing keywords are kept). Chat users looked up
-- the method under this name and got no match.

UPDATE methods
SET keywords = keywords || ', long short-term memory',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'lstm'
  AND NOT (', ' || lower(keywords) || ',') LIKE '%, long short-term memory,%';
