-- Add GraphRAG, introduced in arXiv 2404.16130.
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
    'graphrag',
    'GraphRAG',
    'Graph Retrieval-Augmented Generation (GraphRAG)',
    'GraphRAG is a [retrieval-augmented generation](/methods/rag) approach from Microsoft Research that answers global sensemaking questions over a whole private corpus, such as "What are the main themes in the dataset?", which plain vector-retrieval RAG handles poorly. At indexing time an LLM extracts entities, relationships and claims from text chunks to build a knowledge graph. Hierarchical Leiden community detection then partitions the graph, and the LLM pre-generates a summary for every community of closely related entities. At query time each relevant community summary produces a partial answer, and these are reduced into a final, query-focused response; a local mode instead retrieves around specific entities. On global questions over datasets in the 1 million token range, GraphRAG substantially improved the comprehensiveness and diversity of answers over a naive RAG baseline. The name is now also used for the wider family of graph-based RAG systems.',
    'GraphRAG, graph rag, graph-rag, graph retrieval-augmented generation',
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
        WHERE arxiv_id = '2404.16130'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'From Local to Global: A Graph RAG Approach to Query-Focused Summarization',
    'https://github.com/microsoft/graphrag',
    NULL,
    '[From Local to Global: A Graph RAG Approach to Query-Focused Summarization](/paper/2404.16130)'
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
WHERE slug = 'graphrag' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'graphrag' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 374 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE graphrag_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'graphrag'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        23967, 26698, 27186, 31624, 32067, 32519, 33109, 33312, 33417, 33732, 33871, 34193,
        34882, 35355, 35550, 35638, 35890, 36246, 36651, 36696, 36816, 36860, 36861, 37143,
        37205, 37208, 37411, 37434, 37745, 37969, 38068, 38085, 38253, 38313, 38421, 38494,
        38539, 38587, 38620, 38651, 38775, 38972, 39038, 39173, 39505, 39523, 39835, 40509,
        41037, 41169, 41676, 41934, 42069, 42667, 42756, 42930, 43235, 43291, 43351, 43410,
        43575, 43789, 43807, 43993, 44069, 44265, 44288, 44412, 44444, 44516, 44547, 44670,
        44713, 44860, 45012, 45173, 45249, 45346, 45448, 45534, 45570, 45584, 45641, 45691,
        45708, 45748, 45847, 46020, 46090, 46452, 46545, 46718, 46851, 46978, 47046, 47241,
        47274, 47973, 48044, 48084, 48179, 48284, 48295, 48397, 48446, 48597, 48720, 49000,
        49261, 49391, 49748, 49769, 49948, 49997, 50161, 50172, 50234, 50260, 50686, 50867,
        51000, 51075, 51223, 51666, 51684, 51727, 51974, 52314, 52351, 52362, 52383, 52751,
        52974, 53344, 53529, 53609, 53707, 53902, 54110, 54148, 54376, 54653, 54979, 54990,
        55062, 55094, 55154, 55240, 55268, 55429, 55535, 55579, 55776, 55835, 56164, 56370,
        57344, 57535, 58227, 58229, 58554, 58793, 59543, 59673, 59802, 60052, 60535, 60572,
        60659, 61104, 61192, 61203, 61211, 61351, 61501, 61666, 61799, 61877, 62047, 62159,
        62440, 62448, 62479, 62499, 62545, 62692, 62710, 62718, 62792, 62812, 62845, 62914,
        62957, 63071, 63346, 63387, 63478, 63849, 63894, 64086, 64088, 64181, 64492, 64782,
        64923, 65038, 65151, 65296, 65333, 65354, 65400, 65483, 65526, 65544, 65571, 65572,
        65635, 65748, 65903, 66058, 66147, 66267, 66382, 66485, 66503, 66741, 66783, 66973,
        67184, 67321, 67346, 67789, 67964, 68441, 68679, 68748, 68813, 69031, 69113, 69191,
        69458, 69686, 69762, 69989, 70033, 70034, 70172, 70298, 70567, 71144, 71459, 71647,
        71792, 71891, 72075, 72112, 72367, 72389, 72514, 72538, 72708, 72823, 73185, 73277,
        73336, 73624, 73824, 74033, 74361, 74959, 75637, 76245, 76314, 77513, 82830, 82934,
        83003, 83109, 83123, 83124, 83261, 83645, 83809, 83850, 84434, 84438, 84514, 85491,
        86179, 86297, 86832, 87443, 87687, 88664, 91172, 91217, 91326, 91642, 91964, 91968,
        92125, 92553, 92699, 92948, 92950, 94306, 94350, 94497, 94695, 94726, 98661, 99772,
        99815, 100382, 100638, 100808, 101366, 101847, 102136, 102149, 102676, 102874, 102885, 103026,
        103059, 103078, 103271, 103285, 103338, 103420, 103487, 103490, 103607, 104525, 104552, 104731,
        104736, 105935, 106096, 106138, 106154, 106846, 107613, 107721, 107899, 107912, 108343, 108795,
        108801, 109179, 109373, 109702, 110178, 110336, 110417, 110459, 110519, 110548, 110645, 110874,
        110947, 113847, 114030, 114193, 119479, 121198, 121563, 122108, 122167, 122238, 122239, 122310,
        122730, 123041
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'graphrag citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM graphrag_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING graphrag_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 66 local citers name the method in title or abstract.
CREATE TEMP TABLE graphrag_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'graphrag'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        31771, 35651, 35695, 35914, 35942, 39814, 40232, 42190, 43177, 43230, 43253, 43549,
        45695, 47197, 47342, 47469, 47574, 47759, 50543, 50682, 51489, 51692, 54451, 55662,
        58056, 58568, 59289, 59411, 60105, 60240, 60318, 60581, 60940, 61120, 61288, 61875,
        62427, 62552, 62660, 63139, 63591, 64323, 65459, 65730, 66263, 66369, 66595, 67714,
        67788, 69088, 70267, 70583, 72209, 72883, 73746, 74234, 74602, 74662, 94556, 101202,
        102549, 103542, 104311, 106659, 107352, 108231
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM graphrag_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM graphrag_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 93 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE graphrag_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'graphrag'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        31771, 31813, 35651, 35695, 35914, 35942, 37361, 39814, 40232, 41395, 42190, 42339,
        42469, 43177, 43230, 43253, 43549, 44006, 45690, 45695, 46844, 47197, 47342, 47469,
        47574, 47759, 49456, 50543, 50682, 51489, 54451, 55662, 57321, 58056, 58568, 59289,
        59411, 59474, 60105, 60240, 60318, 60581, 60940, 61068, 61120, 61288, 61875, 62033,
        62054, 62427, 62520, 62552, 62660, 63139, 63591, 63702, 64323, 65275, 65459, 65730,
        66263, 66369, 66595, 66673, 67714, 67788, 69088, 70267, 70478, 70583, 70835, 72209,
        72883, 72987, 73583, 73746, 74234, 74461, 74602, 74662, 76213, 83146, 94556, 101202,
        102549, 102708, 103542, 104311, 106659, 107352, 108231, 110770, 120953
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM graphrag_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM graphrag_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
