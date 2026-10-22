-- Add Go-Explore, introduced in arXiv 1901.10995.
-- Added 2026-10-21 because production chat users looked it up with
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
    'go-explore',
    'Go-Explore',
    'Go-Explore',
    'Go-Explore is a family of algorithms for hard-exploration [reinforcement learning](/tasks/reinforcement-learning) problems with sparse or deceptive rewards. It keeps an archive of visited states, returns to a promising state without exploration noise, explores from there, and adds new states to the archive; a second phase then robustifies the best trajectory with imitation learning. Go-Explore solved Montezuma''s Revenge, scoring over 43,000 points, and was the first to make progress on Pitfall.',
    'Go-Explore, Go Explore',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2019,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1901.10995'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Go-Explore: a New Approach for Hard-Exploration Problems',
    'https://github.com/uber-research/go-explore',
    NULL,
    '[Go-Explore: a New Approach for Hard-Exploration Problems](/paper/1901.10995)'
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
WHERE slug = 'go-explore' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'go-explore' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 70 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE go_explore_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'go-explore'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        2558, 3774, 3833, 4993, 5693, 5857, 6511, 7140, 8576, 9524, 9680, 9771,
        10294, 11200, 11918, 12219, 13540, 13758, 14252, 14354, 15356, 15657, 16316, 16876,
        17640, 18389, 18772, 20130, 26119, 28212, 30786, 35341, 38509, 39386, 43663, 48060,
        50518, 50766, 50852, 51796, 52661, 53586, 53917, 56333, 57482, 62023, 62104, 62577,
        67921, 69643, 70178, 76506, 79892, 80942, 81614, 89349, 93264, 93550, 96123, 96699,
        99881, 100001, 101163, 103879, 103884, 103891, 106045, 106891, 118069, 121949
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'go-explore citation review 2026-10-21: cites the source without naming the method in title or abstract'
FROM go_explore_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING go_explore_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 3 local citers name the method in title or abstract.
CREATE TEMP TABLE go_explore_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'go-explore'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        10186, 31661, 103880
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM go_explore_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM go_explore_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 3 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE go_explore_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'go-explore'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        10186, 31661, 103880
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM go_explore_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM go_explore_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
