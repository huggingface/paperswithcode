-- Add Luong Attention method, introduced in arXiv 1508.04025. The source paper
-- gets the source evidence row (Introduced banner); citers are linked by
-- link_papers_by_source_citations.py and the hourly reference backfill.

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
    'luong-attention',
    'Luong Attention',
    'Luong Attention (Global and Local Attention)',
    'Luong attention is the family of attention mechanisms for encoder-decoder neural machine translation proposed by Luong, Pham and Manning. Global attention attends over all source hidden states, while local attention first predicts an aligned source position and attends only over a window around it. Alignment scores are computed with a dot product, a bilinear "general" form (often called multiplicative attention) or a concatenation-based form, and the resulting context vector is combined with the decoder''s top [LSTM](/methods/lstm) state to form an attentional hidden state that is also fed back as input to the next step (input feeding). Compared with the additive attention of [Bahdanau et al.](/paper/1409.0473), it uses the current rather than the previous decoder state and simpler scoring functions. Attention gave gains of up to 5.0 BLEU over non-attentional systems, and an ensemble set a new state of the art on WMT''15 English to German. The dot-product scoring foreshadows the scaled dot-product [attention](/methods/attention) used in the [Transformer](/methods/transformer).',
    'luong attention, luong-style attention, multiplicative attention',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2015,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1508.04025'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Effective Approaches to Attention-based Neural Machine Translation',
    'https://github.com/lmthang/nmt.matlab',
    NULL,
    '[Effective Approaches to Attention-based Neural Machine Translation](/paper/1508.04025)'
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
SELECT source_paper_id, id
FROM methods
WHERE slug = 'luong-attention'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'luong-attention'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 325 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention Luong-style attention are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE luong_attention_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'luong-attention'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        233, 256, 277, 393, 417, 438, 458, 464, 496, 505, 568, 591,
        628, 652, 690, 711, 731, 755, 766, 817, 868, 911, 942, 955,
        966, 999, 1104, 1106, 1137, 1166, 1180, 1195, 1219, 1222, 1248, 1264,
        1284, 1295, 1303, 1332, 1354, 1386, 1426, 1430, 1437, 1465, 1502, 1508,
        1509, 1511, 1616, 1700, 1714, 1732, 1736, 1749, 1760, 1778, 1786, 1903,
        1943, 1965, 1970, 1973, 1984, 2001, 2030, 2054, 2104, 2136, 2210, 2234,
        2246, 2249, 2251, 2287, 2296, 2303, 2304, 2308, 2318, 2434, 2476, 2484,
        2500, 2580, 2634, 2669, 2690, 2721, 2794, 2836, 2844, 2847, 2871, 2879,
        2884, 2914, 2923, 2952, 3060, 3214, 3235, 3259, 3381, 3460, 3475, 3546,
        3596, 3612, 3622, 3640, 3647, 3811, 3839, 3968, 4065, 4202, 4207, 4253,
        4272, 4310, 4311, 4314, 4335, 4444, 4489, 4583, 4705, 4734, 4917, 5001,
        5102, 5177, 5192, 5247, 5317, 5323, 5384, 5426, 5436, 5454, 5537, 5591,
        5592, 5798, 5803, 5812, 5858, 5886, 5899, 5981, 6143, 6177, 6183, 6218,
        6222, 6380, 6642, 6656, 6681, 7030, 7059, 7188, 7584, 7590, 7623, 7646,
        7854, 7948, 7955, 8123, 8235, 8338, 8349, 8658, 8788, 8829, 8875, 9138,
        9191, 9240, 9243, 9401, 9520, 9588, 9727, 10375, 10385, 10817, 10818, 10842,
        10903, 11071, 11373, 11731, 11889, 12407, 12720, 12999, 13001, 13669, 13945, 13963,
        14209, 14547, 14716, 15079, 15302, 15836, 15845, 15956, 16443, 16684, 16794, 17854,
        18180, 18693, 18904, 19305, 19696, 20033, 20086, 20126, 22462, 22916, 23082, 23970,
        24787, 24919, 25202, 26688, 29751, 30322, 30345, 30929, 32340, 33534, 33931, 34388,
        35408, 37431, 38732, 40500, 42005, 42475, 45799, 46689, 46734, 46800, 46990, 51050,
        53320, 54855, 60219, 62224, 63479, 64549, 64665, 66336, 68258, 69536, 69729, 69997,
        70751, 73732, 78234, 78652, 78973, 79203, 79247, 79483, 79770, 80006, 80166, 80534,
        80664, 80780, 80841, 80895, 80949, 81030, 81080, 81297, 81512, 81566, 81583, 81595,
        81606, 81627, 81700, 81751, 81851, 81884, 81904, 81923, 81995, 82001, 82221, 82329,
        84184, 86138, 88482, 91404, 92052, 93618, 100106, 100214, 100244, 100554, 101522, 103543,
        103720, 103974, 103983, 109256, 110623, 113116, 116092, 119888, 122941, 123494
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'luong-attention citation review 2026-10-15: cites the source paper without using the method'
FROM luong_attention_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING luong_attention_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING luong_attention_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
