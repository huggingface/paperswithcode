-- Add QMIX method, introduced in arXiv 1803.11485. The source paper
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
    'qmix',
    'QMIX',
    'QMIX (Monotonic Value Function Factorisation)',
    'QMIX is a value-based method for cooperative multi-agent reinforcement learning under centralized training with decentralized execution. Each agent has its own utility network (a [DQN](/methods/dqn)-style recurrent Q-network over local observations), and a mixing network combines the per-agent values into a joint action value. The mixing weights are produced by [hypernetworks](/methods/hypernetwork) conditioned on the global state and constrained to be non-negative, so the joint value is monotonic in every agent''s value; maximizing each agent''s own Q-value therefore also maximizes the joint value, which makes decentralized greedy action selection consistent with the centralized objective. QMIX outperformed independent learners and value decomposition networks (VDN) on StarCraft II micromanagement tasks and became the standard baseline on the SMAC benchmark.',
    'QMIX',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2018,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1803.11485'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'QMIX: Monotonic Value Function Factorisation for Deep Multi-Agent Reinforcement Learning',
    'https://github.com/oxwhirl/pymarl/blob/master/src/modules/mixers/qmix.py',
    NULL,
    '[QMIX: Monotonic Value Function Factorisation for Deep Multi-Agent Reinforcement Learning](/paper/1803.11485)'
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
WHERE slug = 'qmix'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'qmix'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
