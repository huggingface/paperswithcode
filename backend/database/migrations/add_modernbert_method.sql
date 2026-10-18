-- Add ModernBERT, introduced in arXiv 2412.13663.
-- Added 2026-10-18 from a scan of methods named by many recent papers but
-- missing from the catalog. The source paper gets the source evidence row (Introduced banner).

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'modernbert',
    'ModernBERT',
    'ModernBERT',
    'ModernBERT is an encoder-only [Transformer](/methods/transformer) that brings modern architecture and training optimizations to [BERT](/methods/bert)-style bidirectional models for retrieval and classification. It replaces absolute positions with [RoPE](/methods/rope), uses GeGLU activations and pre-normalization, drops most linear-layer bias terms, and alternates attention: every third layer uses global attention while the others use 128-token [sliding-window attention](/methods/sliding-window-attention). Unpadding with [FlashAttention](/methods/flash-attention) variable-length kernels avoids computing on padding tokens. Trained on 2 trillion tokens, including code, with a native 8192-token context, ModernBERT-base and ModernBERT-large reached state-of-the-art results across classification, single- and multi-vector ([ColBERT](/methods/colbert)) retrieval and code retrieval, while being the most speed- and memory-efficient encoder in its comparison and processing 8192-token sequences almost twice as fast as previous models. It is widely used as a drop-in backbone for embedding, reranking and classifier models.',
    'ModernBERT',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2024,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2412.13663'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Smarter, Better, Faster, Longer: A Modern Bidirectional Encoder for Fast, Memory Efficient, and Long Context Finetuning and Inference',
    'https://github.com/AnswerDotAI/ModernBERT',
    NULL,
    '[Finally, a Replacement for BERT: Introducing ModernBERT (Hugging Face blog)](https://huggingface.co/blog/modernbert)'
)
ON CONFLICT (slug) DO UPDATE
SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'modernbert' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'modernbert' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 195 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE modernbert_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'modernbert'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        19700, 20501, 22583, 35330, 38839, 41276, 42301, 43982, 44013, 44363, 44446, 44712,
        44774, 44789, 45017, 45022, 45055, 45211, 45291, 45450, 45458, 45622, 45800, 45843,
        46088, 46645, 46788, 46800, 46956, 47211, 47318, 47471, 47491, 47722, 47926, 48227,
        48272, 48363, 48770, 48876, 49013, 49136, 49251, 49292, 49309, 49314, 49466, 49713,
        49810, 49832, 50203, 50260, 50476, 50579, 50580, 50845, 50975, 50986, 51251, 51414,
        51614, 52152, 52304, 52348, 52516, 52568, 52695, 53139, 53274, 53592, 53612, 54456,
        55522, 55586, 55611, 55644, 55719, 55944, 56231, 56291, 56356, 56527, 56714, 57819,
        57883, 58369, 59512, 59940, 59957, 60035, 60374, 61157, 61237, 61768, 61829, 62458,
        62612, 62720, 63423, 63881, 64157, 64213, 64215, 65305, 65471, 65773, 65901, 66386,
        66441, 66658, 66690, 66809, 67042, 67156, 67210, 67644, 67703, 68005, 68346, 68673,
        68719, 69537, 69926, 70112, 70191, 70406, 70636, 70833, 71069, 71804, 72034, 72278,
        72691, 72829, 72873, 73470, 73512, 74352, 76322, 80074, 83472, 83932, 84065, 84573,
        87237, 89099, 92958, 94249, 98536, 98928, 98944, 99426, 101362, 101427, 101771, 101778,
        102143, 102270, 102632, 103472, 103474, 103538, 103566, 103625, 103733, 103767, 104596, 105843,
        106137, 106307, 106387, 108706, 108707, 108816, 109066, 109084, 109308, 109958, 110019, 110196,
        110251, 110299, 110370, 110755, 110937, 110977, 111007, 111953, 113977, 117434, 118341, 122552,
        122668, 122778, 123246
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'modernbert citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM modernbert_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING modernbert_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 33 local citers name the method in title or abstract.
CREATE TEMP TABLE modernbert_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'modernbert'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        44409, 44910, 45102, 47319, 47567, 49028, 50285, 50669, 51035, 51729, 51900, 51914,
        52908, 55480, 60276, 60310, 60523, 61241, 63249, 63794, 65983, 66442, 68202, 71302,
        71791, 73404, 74240, 74772, 83267, 98575, 108120, 110284, 123673
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM modernbert_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM modernbert_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 43 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE modernbert_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'modernbert'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        44206, 44409, 44910, 45102, 47319, 47567, 49028, 50285, 50669, 51035, 51328, 51729,
        51900, 51914, 52908, 55480, 59954, 60276, 60310, 60523, 60904, 61241, 63249, 63794,
        65116, 65983, 66442, 67261, 68202, 71302, 71791, 73404, 74240, 74772, 74873, 83267,
        87532, 98575, 108120, 110284, 110815, 111126, 123673
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM modernbert_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM modernbert_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
