UPDATE methods
SET image_credit = '[Unlocking Efficiency in Large Language Model Inference: A Comprehensive Survey of Speculative Decoding](/paper/2401.07851)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'speculative-decoding';

UPDATE methods
SET image_credit = '[How speculative decoding makes LLMs go brrr](https://leoniemonigatti.com/blog/speculative-decoding.html)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug IN ('medusa', 'eagle-3', 'dflash', 'dspark');
