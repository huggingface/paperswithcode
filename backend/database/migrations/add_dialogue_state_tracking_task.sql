-- Add Dialogue State Tracking as a top-level Language task; production chat users
-- searched for it but the catalog had no matching task.

INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    parent_id,
    level,
    image_url,
    image_credit,
    is_visible
)
VALUES (
    'Dialogue State Tracking',
    'dialogue-state-tracking',
    'Dialogue state tracking (DST) estimates the user''s goal at each turn of a task-oriented conversation as a set of slot-value pairs, such as the area, price range, and booking time of a restaurant, accumulating information across turns and domains. The tracked state drives database queries and system actions in task-oriented dialogue systems. Methods range from classification over ontologies to generative and schema-guided models and LLM prompting for zero-shot transfer to new domains, and are evaluated by joint goal accuracy and slot accuracy on MultiWOZ, the Schema-Guided Dialogue (SGD) dataset, and WOZ 2.0. Related tasks include [Question Answering](/tasks/question-answering) and [Agents](/tasks/agents).',
    'dialogue state tracking, dialog state tracking, belief state tracking, multi-domain dialogue state tracking, zero-shot dialogue state tracking, schema-guided dialogue, task-oriented dialogue state, MultiWOZ',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    NULL,
    0,
    NULL,
    '[Transferable Multi-Domain State Generator for Task-Oriented Dialogue Systems](https://arxiv.org/abs/1905.08743)',
    true
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    parent_id = EXCLUDED.parent_id,
    level = EXCLUDED.level,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    is_visible = EXCLUDED.is_visible,
    updated_at = CURRENT_TIMESTAMP;
