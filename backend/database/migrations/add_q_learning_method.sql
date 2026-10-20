-- Add Q-learning (no introducing paper in the catalog; external reference).
-- Added 2026-10-20 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

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
    'q-learning',
    'Q-learning',
    'Q-learning',
    'Q-learning is a model-free, off-policy temporal-difference reinforcement learning algorithm that learns the optimal action-value function Q(s, a) directly from experience. After each transition it moves Q(s, a) toward the bootstrapped target r + γ max_a'' Q(s'', a''), so it learns the greedy policy''s values while the agent may follow an exploratory policy such as ε-greedy. Introduced in Watkins'' 1989 PhD thesis and proven to converge in the tabular case by Watkins and Dayan (1992), it underlies [DQN](/methods/dqn), double Q-learning and offline methods such as conservative and implicit Q-learning.',
    'q-learning, q learning, tabular q-learning',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    1989,
    NULL,
    'https://doi.org/10.1007/BF00992698',
    'Q-learning (Watkins & Dayan, Machine Learning 1992)',
    NULL,
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

-- 159 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE q_learning_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'q-learning'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        46, 64, 239, 745, 898, 1021, 1128, 1184, 1731, 3110, 4204, 6067,
        6166, 6361, 6587, 6795, 6813, 7444, 7476, 8239, 8713, 8828, 9657, 9771,
        11190, 12295, 14649, 14829, 15681, 15999, 16096, 16113, 16435, 17731, 18035, 19849,
        20344, 20586, 20762, 21185, 22232, 23486, 23793, 25329, 25904, 26806, 26867, 27149,
        27573, 28292, 28722, 30534, 31003, 36504, 36991, 37299, 38814, 39783, 43490, 43870,
        45558, 48831, 49384, 53077, 56956, 57324, 57836, 58674, 58718, 60166, 62041, 62281,
        63253, 63511, 63911, 64262, 66758, 69423, 69462, 71417, 73179, 75331, 75868, 76802,
        77075, 77211, 78311, 78962, 79113, 79232, 79317, 79727, 80452, 80857, 80922, 81581,
        81616, 81903, 81909, 82115, 82186, 82263, 82466, 83259, 84279, 85626, 85764, 85963,
        86867, 86957, 87028, 87319, 87366, 89015, 89520, 89593, 89900, 92528, 92854, 92857,
        93238, 93485, 93742, 93999, 94129, 94629, 94663, 96176, 96997, 97178, 97338, 97539,
        99123, 99414, 99427, 99594, 100242, 100691, 100772, 101387, 101501, 101651, 101801, 101909,
        102060, 102109, 103882, 103885, 103888, 103890, 107171, 107255, 107737, 108023, 112185, 112556,
        113467, 114457, 122920
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM q_learning_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM q_learning_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
