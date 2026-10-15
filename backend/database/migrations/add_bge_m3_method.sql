-- Add BGE-M3 method, introduced in arXiv 2402.03216. The source paper
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
    'bge-m3',
    'BGE-M3',
    'BGE M3-Embedding',
    'BGE-M3 (M3-Embedding) is a text [embedding](/methods/embedding) model named for its three "M"s: multi-linguality (more than 100 languages), multi-functionality and multi-granularity (inputs from short sentences up to 8,192-token documents). Multi-functionality means one model produces three kinds of retrieval signals at once: a dense sentence embedding, sparse lexical weights for each token, and multi-vector late-interaction representations in the style of [ColBERT](/methods/colbert). Training uses self-knowledge distillation, in which the combined relevance score of the three modes acts as a teacher for each individual mode, together with large-batch training and long-document data. Built on XLM-RoBERTa, BGE-M3 achieved state-of-the-art results on multilingual (MIRACL), cross-lingual (MKQA) and long-document (MLDR) retrieval benchmarks and is widely used for [RAG](/methods/rag) and hybrid search.',
    'BGE-M3, BGE M3, M3-Embedding',
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
        WHERE arxiv_id = '2402.03216'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation',
    'https://github.com/FlagOpen/FlagEmbedding',
    NULL,
    '[BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation](/paper/2402.03216)'
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
WHERE slug = 'bge-m3'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'bge-m3'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 450 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention BGE-M3 are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE bge_m3_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'bge-m3'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        15085, 21865, 23115, 25221, 27875, 28196, 29325, 30136, 30511, 30878, 31466, 32072,
        32105, 32300, 32443, 33238, 33376, 33483, 33844, 33871, 33943, 33947, 33969, 34078,
        34839, 34909, 35029, 35128, 35485, 36057, 36124, 36143, 36333, 36385, 36502, 36578,
        36696, 36931, 36938, 37208, 37254, 37626, 37795, 37895, 37956, 38085, 38086, 38135,
        38219, 38421, 38665, 38729, 39465, 39523, 39766, 39814, 39953, 40169, 40294, 40686,
        40890, 40908, 41303, 41369, 41387, 41417, 41727, 41731, 41771, 41817, 41896, 41945,
        42383, 42501, 42929, 42951, 43049, 43088, 43178, 43230, 43647, 43735, 44123, 44138,
        44294, 44349, 44440, 44516, 44565, 44577, 44798, 44904, 44916, 44932, 44975, 45022,
        45088, 45176, 45215, 45227, 45353, 45597, 45622, 45766, 45843, 46100, 46923, 47054,
        47111, 47171, 47476, 47681, 47687, 47861, 47931, 47978, 48066, 48069, 48194, 48398,
        48682, 48758, 48892, 48929, 48943, 49113, 49166, 49194, 49251, 49305, 49338, 49521,
        49598, 50060, 50200, 50350, 50619, 50628, 50629, 50647, 50834, 50867, 51005, 51075,
        51106, 51109, 51323, 51487, 51614, 51666, 51692, 52037, 52147, 52172, 52217, 52237,
        52302, 52314, 52362, 53149, 53593, 53832, 53934, 53938, 53973, 54318, 54538, 54615,
        54684, 54742, 54955, 55027, 55062, 55195, 55197, 55241, 55318, 55355, 55497, 55535,
        55644, 55807, 55827, 56034, 56145, 56159, 56266, 56396, 56405, 56454, 56466, 56484,
        56485, 56532, 56626, 56694, 56864, 56882, 57113, 57437, 57578, 57637, 57699, 57721,
        57870, 57979, 58045, 58330, 58451, 58653, 58747, 58749, 59054, 59148, 59325, 59600,
        59897, 59966, 60105, 60163, 60234, 60310, 60619, 60624, 60817, 60945, 60960, 61192,
        61265, 61500, 61509, 61563, 61589, 61691, 61809, 62021, 62054, 62118, 62427, 62478,
        62550, 62561, 62566, 62576, 62612, 62625, 62652, 62653, 62716, 62755, 62767, 62901,
        63381, 63581, 63849, 64086, 64088, 64181, 64509, 64510, 64559, 64742, 65296, 65333,
        65357, 65544, 65740, 65747, 65863, 66116, 66165, 66250, 66299, 66310, 66327, 66542,
        66560, 66568, 66667, 66695, 66720, 67253, 67298, 67396, 67538, 67945, 68212, 68314,
        68326, 68343, 68400, 68439, 68468, 68493, 68756, 68811, 68881, 68991, 69092, 69151,
        69210, 69213, 69279, 69762, 69974, 70118, 70141, 70172, 70309, 70324, 70431, 70636,
        70676, 70684, 70715, 70889, 70934, 71242, 71299, 71443, 71457, 71825, 71859, 71889,
        72014, 72113, 72129, 72259, 72285, 72421, 72842, 72853, 73177, 73303, 73361, 73406,
        73485, 73808, 74235, 74309, 74659, 74781, 74892, 77042, 77777, 83320, 83448, 83718,
        83812, 84281, 84393, 84573, 85490, 86456, 86636, 87527, 87739, 88587, 90269, 93228,
        93289, 93578, 94249, 94367, 94460, 94591, 95077, 96590, 98467, 98475, 98484, 98662,
        98676, 98677, 98707, 98911, 99719, 99834, 99927, 99953, 100197, 100316, 100422, 100614,
        101126, 101175, 101280, 101376, 101888, 102797, 102890, 102980, 103165, 103205, 103290, 103595,
        103716, 104547, 105435, 105850, 105927, 106064, 106147, 106154, 106161, 106185, 106208, 106913,
        107439, 107634, 108336, 108340, 108637, 108707, 109084, 109560, 109561, 110215, 110218, 110468,
        110651, 110799, 110905, 110920, 113741, 113890, 113923, 113926, 114075, 118652, 118723, 118760,
        122141, 122163, 122452, 122632, 123246, 123287
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'bge-m3 citation review 2026-10-15: cites the source paper without using the method'
FROM bge_m3_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING bge_m3_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING bge_m3_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
