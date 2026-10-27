INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Harness Engineering',
    'harness-engineering',
    'Harness engineering designs the software around a language model that turns it into a working agent: the agent loop, tools and sandboxes, context and memory management, skills, sub-agent orchestration, verification and approval steps. The model''s weights stay fixed while the harness decides what it sees, what it can do and when it stops, so the same model can score very differently under different harnesses. Work in this area compares hand-built harnesses, optimizes or evolves them automatically from execution traces, and benchmarks their reliability, cost and safety. Related: [Agents](/tasks/agents), [Coding Agents](/tasks/coding-agents), [Long-Horizon Agents](/tasks/long-horizon-agents) and [Multi-Agent Systems](/tasks/multi-agent-systems).',
    'harness engineering, agent harness, agentic harness, LLM agent harness, harness design, harness optimization, meta-harness, agent scaffold, agent scaffolding',
    (SELECT area_id FROM tasks WHERE slug = 'agents' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'agents' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'agents' LIMIT 1),
    NULL,
    '[Externalization in LLM Agents: A Unified Review of Memory, Skills, Protocols and Harness Engineering](/paper/2604.08224)',
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
