-- Add Chain-of-Verification, introduced in arXiv 2309.11495.
-- Added 2026-10-20 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.
-- The source paper gets the source evidence row (Introduced banner).

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
    'chain-of-verification',
    'Chain-of-Verification',
    'Chain-of-Verification (CoVe)',
    'Chain-of-Verification (CoVe) is a prompting method that reduces hallucination in large language models. The model first drafts a response, then plans verification questions that fact-check the claims in the draft, answers those questions independently so the answers are not biased by the draft, and finally writes a revised response consistent with the verified facts. Answering verification questions in separate contexts (the factored variant) works best. CoVe improved precision on list-based Wikidata questions, closed-book MultiSpanQA and long-form biography generation compared with the baseline model, and is a widely used self-verification baseline alongside [chain-of-thought](/methods/chain-of-thought-cot) prompting.',
    'chain-of-verification, chain of verification',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2309.11495'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Chain-of-Verification Reduces Hallucination in Large Language Models',
    NULL,
    NULL,
    '[Chain-of-Verification Reduces Hallucination in Large Language Models](/paper/2309.11495)'
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
WHERE slug = 'chain-of-verification' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'chain-of-verification' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 124 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE chain_of_verification_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'chain-of-verification'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        16053, 17840, 19240, 20053, 20307, 20357, 20861, 21487, 21799, 22041, 22058, 22130,
        22234, 22382, 22774, 23115, 23320, 23386, 23554, 23897, 24167, 24385, 24769, 24910,
        24959, 25207, 25409, 25471, 25550, 25694, 25868, 26111, 26522, 26706, 27223, 27453,
        27937, 28091, 28581, 30330, 30687, 30986, 32269, 32718, 32909, 33529, 34217, 35355,
        35989, 37432, 37822, 38444, 38666, 39171, 40111, 40275, 40522, 42135, 43118, 43606,
        44186, 44790, 45386, 47093, 47204, 47214, 47284, 49373, 50757, 51865, 51867, 51982,
        52430, 53122, 53642, 53656, 53888, 56707, 58510, 59753, 60244, 61718, 62367, 63055,
        63826, 65489, 66266, 66961, 66967, 67133, 67549, 70957, 71358, 71630, 71927, 72377,
        73186, 73624, 75713, 76640, 82827, 86641, 87446, 90518, 91879, 91926, 92875, 94889,
        94965, 102051, 102172, 103583, 104434, 105948, 106094, 106148, 106154, 106334, 109647, 110042,
        122356, 123139, 123154, 123237
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'chain-of-verification citation review 2026-10-20: cites the source without naming the method in title or abstract'
FROM chain_of_verification_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING chain_of_verification_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 2 local citers name the method in title or abstract.
CREATE TEMP TABLE chain_of_verification_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'chain-of-verification'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        28023, 60873
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM chain_of_verification_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM chain_of_verification_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 2 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE chain_of_verification_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'chain-of-verification'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        38070, 60873
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM chain_of_verification_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM chain_of_verification_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
