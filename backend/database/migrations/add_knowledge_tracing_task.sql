-- Add Knowledge Tracing as a top-level Other task; production chat users
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
    'Knowledge Tracing',
    'knowledge-tracing',
    'Knowledge tracing models a student''s evolving mastery of knowledge components from their sequence of interactions with exercises, and predicts whether the student will answer the next question correctly. It underpins intelligent tutoring systems and adaptive learning platforms, where estimated knowledge states drive question recommendation and feedback. Approaches range from Bayesian knowledge tracing to deep sequence models such as DKT, memory networks, and attention-based models, and are typically evaluated by next-response AUC and accuracy on datasets such as ASSISTments, EdNet, and Junyi.',
    'knowledge tracing, deep knowledge tracing, Bayesian knowledge tracing, student performance prediction, student modeling, student modelling, knowledge state estimation',
    (SELECT id FROM areas WHERE name = 'Other' LIMIT 1),
    NULL,
    0,
    NULL,
    '[A Survey of Knowledge Tracing: Models, Variants, and Applications](https://arxiv.org/abs/2105.15106)',
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
