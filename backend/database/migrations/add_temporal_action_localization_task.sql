-- Temporal Action Localization task: subtask of video-understanding.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Temporal Action Localization',
    'temporal-action-localization',
    'Temporal action localization, also called temporal action detection, finds when actions happen in long, untrimmed videos: a model predicts the start and end time of every action instance together with its class label. Unlike [Action Recognition](/tasks/action-recognition), which labels pre-trimmed clips, it must separate actions from background and handle instances of widely varying duration. Standard benchmarks include THUMOS14, ActivityNet-1.3 and EPIC-Kitchens 100. The closely related [Video Temporal Grounding](/tasks/video-temporal-grounding) task localizes moments described in natural language instead of a fixed set of action classes.',
    'temporal action localization, temporal action localisation, temporal action detection, temporal action proposal generation, temporal action proposal, action localization in untrimmed videos, action detection in untrimmed videos',
    (SELECT area_id FROM tasks WHERE slug = 'video-understanding' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'video-understanding' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'video-understanding' LIMIT 1),
    true,
    NULL,
    '[ActionFormer: Localizing Moments of Actions with Transformers](https://arxiv.org/abs/2202.07925)',
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
