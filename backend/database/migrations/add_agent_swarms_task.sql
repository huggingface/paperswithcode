INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Agent Swarms',
    'agent-swarms',
    'Agent swarms solve a task with many LLM agents working in parallel, typically an orchestrator that decomposes the problem, spawns dozens to hundreds of specialized sub-agents, and merges their results, or a decentralized population that coordinates through messages or shared state. The goal is to finish broad, long tasks faster and beyond a single agent''s context window. Key questions are when parallelism actually helps, how to train the orchestrator (for example with reinforcement learning), and how to control communication cost and error propagation across the swarm. A subtask of [Multi-Agent Systems](/tasks/multi-agent-systems); related: [Agents](/tasks/agents), [Deep Research Agents](/tasks/deep-research-agents) and [Harness Engineering](/tasks/harness-engineering).',
    'agent swarm, LLM swarm, LLM agent swarm, agentic swarm, swarm of agents, swarms of agents, swarm of LLM agents, parallel sub-agents, parallel subagents',
    (SELECT area_id FROM tasks WHERE slug = 'multi-agent-systems' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'multi-agent-systems' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'multi-agent-systems' LIMIT 1),
    NULL,
    '[Kimi K2.5: Visual Agentic Intelligence](/paper/2602.02276)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
