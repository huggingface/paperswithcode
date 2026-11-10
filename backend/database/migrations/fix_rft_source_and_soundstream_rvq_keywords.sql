-- Follow-ups to the 2026-11-10 method gap fill.
--
-- Rejection Sampling Fine-Tuning has no introducing paper, but its reference
-- (Scaling Relationship on Learning Mathematical Reasoning, 2308.01825) has a
-- local page, so source_url points there instead of arXiv.
UPDATE methods
SET source_url = '/paper/2308.01825', updated_at = CURRENT_TIMESTAMP
WHERE slug = 'rejection-sampling-fine-tuning'
  AND source_url = 'https://arxiv.org/abs/2308.01825';

-- Residual vector quantization is now its own method, so SoundStream drops the
-- RVQ keywords; otherwise the daily keyword backfill keeps tagging every RVQ
-- paper as SoundStream.
UPDATE methods
SET keywords = 'SoundStream, soundstream, neural audio codec, end-to-end audio codec',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'soundstream'
  AND keywords = 'SoundStream, soundstream, neural audio codec, end-to-end audio codec, RVQ, residual vector quantizer';
