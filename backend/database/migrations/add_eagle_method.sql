-- Add EAGLE, introduced in arXiv 2401.15077.
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
    'eagle',
    'EAGLE',
    'Extrapolation Algorithm for Greater Language-model Efficiency (EAGLE)',
    'EAGLE (Extrapolation Algorithm for Greater Language-model Efficiency) is a [speculative decoding](/methods/speculative-decoding) framework that drafts tokens by autoregression over the target LLM''s second-to-top-layer features rather than over tokens. A lightweight draft head (a single decoder layer) reuses the frozen embedding and LM head of the target model and takes the feature sequence together with the token sequence advanced by one step, which resolves the uncertainty of feature-level prediction. Drafts form a tree that the target model verifies in one pass, so the output distribution is unchanged. On LLaMA2-Chat 70B, EAGLE achieved a 2.7x-3.5x latency speedup and doubled throughput. [EAGLE-2: Faster Inference of Language Models with Dynamic Draft Trees](/paper/2406.16858) replaced the static draft tree with a context-aware dynamic tree based on draft-model confidence, reaching 3.05x-4.26x speedups, 20-40% faster than EAGLE-1. [EAGLE-3](/methods/eagle-3) later dropped feature prediction for training-time test. It is a widely used alternative to [Medusa](/methods/medusa) draft heads.',
    'EAGLE-1, EAGLE-2, EAGLE2, Extrapolation Algorithm for Greater Language-model Efficiency',
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
        WHERE arxiv_id = '2401.15077'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'EAGLE: Speculative Sampling Requires Rethinking Feature Uncertainty',
    'https://github.com/SafeAILab/EAGLE',
    NULL,
    '[EAGLE: Speculative Sampling Requires Rethinking Feature Uncertainty](/paper/2401.15077)'
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
WHERE slug = 'eagle' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'eagle' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 251 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE eagle_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'eagle'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        25165, 25829, 26733, 27595, 27596, 27608, 27741, 27967, 28750, 28896, 29553, 29658,
        30493, 30734, 30899, 30910, 31115, 31234, 31555, 31961, 31997, 32036, 32329, 32510,
        32615, 33307, 33373, 33596, 33636, 33650, 33723, 34009, 34098, 34778, 35263, 35724,
        35865, 35903, 36954, 37619, 37677, 37865, 38052, 38155, 39299, 40091, 40136, 40199,
        40862, 41736, 41914, 42064, 42202, 42224, 43471, 43474, 43593, 43660, 43746, 43880,
        44117, 44130, 44218, 44268, 44739, 44766, 44913, 44943, 45042, 45117, 45279, 45481,
        45612, 46019, 46858, 46927, 47327, 47432, 48149, 48170, 48203, 48462, 48721, 48779,
        48993, 49015, 49244, 49263, 49563, 49634, 49694, 49699, 49700, 49757, 49903, 49967,
        50207, 50522, 50553, 50603, 51195, 51432, 51650, 51846, 52181, 52651, 52937, 53313,
        53440, 53573, 53750, 53782, 53854, 53900, 53949, 54457, 54832, 54846, 54933, 55225,
        55823, 55907, 56759, 56966, 57303, 57341, 57399, 57412, 57467, 57796, 58147, 58607,
        59154, 59331, 59946, 60502, 60559, 60708, 60790, 61074, 61462, 61534, 61682, 62220,
        62337, 62610, 62731, 62990, 63246, 63297, 63871, 64232, 64343, 64870, 65276, 65535,
        65623, 66062, 66117, 66304, 66981, 67455, 67503, 67564, 67704, 67761, 67890, 68187,
        68268, 68331, 68845, 69223, 69837, 71093, 72820, 73572, 73870, 74858, 74868, 82941,
        82988, 83467, 83860, 84174, 85743, 86540, 86872, 87102, 87489, 87493, 87513, 88683,
        91477, 93320, 93620, 93634, 94425, 94611, 94705, 94929, 95021, 98192, 98511, 98859,
        98995, 99209, 99753, 99877, 100087, 100101, 101160, 101862, 102261, 102601, 102638, 102653,
        102930, 102990, 103311, 103368, 103451, 103747, 105922, 106153, 106260, 108232, 108929, 109020,
        109131, 109280, 109443, 109805, 110074, 110150, 110291, 110819, 110969, 113816, 114058, 114153,
        118362, 118678, 118751, 119506, 122006, 122240, 122621, 122895, 122945, 123115, 123145
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'eagle citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM eagle_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING eagle_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 23 local citers name the method in title or abstract.
CREATE TEMP TABLE eagle_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'eagle'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        32088, 33612, 36319, 36437, 37907, 40066, 40600, 44881, 45365, 48662, 49034, 51558,
        53641, 54705, 55177, 56609, 57064, 58370, 61514, 68379, 70723, 72586, 74407
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM eagle_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM eagle_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 18 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE eagle_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'eagle'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        33612, 36319, 36437, 37907, 40066, 40600, 44703, 44881, 45365, 48662, 55177, 57064,
        68379, 72586, 74407, 75842, 93167, 99712
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM eagle_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM eagle_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
