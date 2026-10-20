-- Add TD3+BC, introduced in arXiv 2106.06860.
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
    'td3-bc',
    'TD3+BC',
    'TD3+BC',
    'TD3+BC is a minimalist offline reinforcement learning algorithm that adds a behavior cloning term to the policy update of TD3 (Twin Delayed DDPG) and normalizes states. The actor maximizes λQ(s, π(s)) − (π(s) − a)², where λ rescales the Q term by its average magnitude, which keeps the policy close to the dataset actions without extra networks or generative models of the behavior policy. With two small changes to an online algorithm it matched or beat more complex offline methods on the D4RL benchmark at a fraction of the runtime, and it is a standard baseline in [offline reinforcement learning](/tasks/offline-reinforcement-learning).',
    'TD3+BC, TD3-BC, TD3 + BC',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2021,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2106.06860'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'A Minimalist Approach to Offline Reinforcement Learning',
    'https://github.com/sfujim/TD3_BC',
    NULL,
    'Illustration by Papers with Code'
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
WHERE slug = 'td3-bc' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'td3-bc' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 251 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE td3_bc_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'td3-bc'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        6361, 7167, 7180, 7804, 7945, 9385, 9433, 9621, 9653, 10336, 10762, 10763,
        11467, 11683, 12187, 12708, 13088, 13105, 13157, 13680, 14094, 14141, 14290, 14409,
        14994, 15750, 15999, 16341, 16449, 16528, 16578, 16690, 16756, 16802, 16824, 17020,
        17023, 17266, 17289, 17321, 17342, 17706, 17764, 17999, 18078, 18472, 18599, 19958,
        20069, 20424, 20586, 20762, 21063, 21064, 21145, 21320, 21404, 21617, 21687, 21777,
        21819, 22149, 22232, 22493, 22651, 22667, 22776, 22793, 22814, 22840, 23002, 24396,
        24555, 25901, 25935, 26045, 26091, 26565, 26705, 26726, 26867, 26899, 27042, 27109,
        27619, 27649, 28209, 28283, 29183, 30138, 31557, 31910, 32054, 33188, 33705, 34567,
        34669, 35884, 36434, 37596, 39783, 41180, 41333, 42796, 43490, 44746, 45887, 46697,
        48753, 48994, 49327, 50107, 50783, 50934, 51944, 54128, 54455, 56095, 56151, 56851,
        56956, 57543, 59852, 61397, 61895, 62281, 64127, 64155, 65310, 66260, 66758, 67215,
        67940, 69462, 70013, 70038, 70893, 71229, 71899, 72547, 72913, 73691, 73840, 74370,
        75546, 75671, 76858, 77033, 77709, 77933, 79113, 79340, 79392, 80452, 80498, 83206,
        83560, 85696, 85770, 85775, 85835, 86417, 86538, 86583, 86981, 87399, 89048, 89109,
        89772, 89836, 89923, 91101, 91205, 91233, 91433, 91607, 91682, 91791, 91821, 91842,
        92074, 92196, 92429, 92675, 92685, 92706, 92775, 92801, 92815, 92854, 92861, 92876,
        92891, 93017, 93165, 93175, 93182, 93247, 93267, 93310, 93431, 93498, 93880, 93898,
        93971, 94138, 94364, 94455, 94524, 94739, 94794, 95679, 96823, 97269, 97801, 98129,
        99153, 99231, 99240, 99414, 99427, 99594, 99605, 99724, 99806, 99892, 100370, 100678,
        100691, 100767, 100769, 100772, 100912, 100997, 101031, 101282, 101518, 101626, 101651, 101749,
        102109, 102138, 102335, 102339, 102378, 103888, 107171, 108400, 108947, 122096, 122920
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'td3-bc citation review 2026-10-20: cites the source without naming the method in title or abstract'
FROM td3_bc_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING td3_bc_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 4 local citers name the method in title or abstract.
CREATE TEMP TABLE td3_bc_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'td3-bc'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        15634, 16728, 17047, 17699
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM td3_bc_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM td3_bc_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 3 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE td3_bc_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'td3-bc'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        15634, 16728, 17699
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM td3_bc_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM td3_bc_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
