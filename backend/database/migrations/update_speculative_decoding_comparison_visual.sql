UPDATE methods
SET source_url = NULL,
    image_url = NULL,
    image_credit = 'User-provided comparison graphic',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'speculative-decoding';

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'speculative-decoding' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
