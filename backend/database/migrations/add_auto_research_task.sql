-- Add auto-research (agents that run research experiments autonomously) as a
-- subtask of Agents. The term comes from Karpathy's autoresearch repository.

BEGIN;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Auto-Research',
    'auto-research',
    'Auto-research lets AI [agents](/tasks/agents) carry out the research loop themselves: they propose a hypothesis, edit code, run experiments, read the results, and keep or discard each change, often for hundreds of iterations without human input. The term was coined by Andrej Karpathy''s autoresearch project, where a coding agent repeatedly modifies a small LLM training script, trains for a fixed five-minute budget, and keeps changes that lower validation bits per byte. The task covers AI scientist systems, autonomous ML research and engineering agents, and benchmarks that measure whether agents can reproduce papers, improve baselines, or make new discoveries. It overlaps with [Coding Agents](/tasks/coding-agents), but is judged by research progress rather than passing tests, and differs from [Deep Research Agents](/tasks/deep-research-agents), which search and synthesize existing literature instead of running new experiments.',
    'autoresearch, auto-research, auto research, AutoResearch, AI scientist, AI Scientist, AI co-scientist, AI research agent, AI research agents, autonomous research, automated research, automated AI research, automated ML research, autonomous scientific discovery, automated scientific discovery, research automation, MLE-bench, RE-Bench',
    (SELECT area_id FROM tasks WHERE slug = 'agents' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'agents' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'agents' LIMIT 1),
    TRUE,
    NULL,
    '[karpathy/autoresearch](https://github.com/karpathy/autoresearch)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;

COMMIT;
