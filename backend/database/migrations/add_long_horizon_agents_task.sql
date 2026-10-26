INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Long-Horizon Agents',
    'long-horizon-agents',
    'Long-horizon agents pursue goals that take many steps, hours of human-equivalent work, or long chains of tool calls, such as multi-hour software engineering, terminal and web tasks, or open-ended research. The core challenges are planning and decomposition, recovering from errors, managing memory and context over long trajectories, and training with sparse, delayed rewards. Progress is often reported as an agent''s task-completion time horizon. Related: [Agents](/tasks/agents), [Coding Agents](/tasks/coding-agents), [Computer Use Agents](/tasks/computer-use-agents), [Deep Research Agents](/tasks/deep-research-agents) and [Long Context](/tasks/long-context).',
    'long-horizon agent, long horizon agent, long-horizon agentic, long horizon agentic, long-horizon tool use, long-horizon tool-use, long-horizon software engineering, long-horizon coding, long-horizon terminal, long-horizon web',
    (SELECT area_id FROM tasks WHERE slug = 'agents' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'agents' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'agents' LIMIT 1),
    NULL,
    '[Measuring AI Ability to Complete Long Tasks](/paper/2503.14499)',
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
