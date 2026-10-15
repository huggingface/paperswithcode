-- Action Anticipation task: subtask of video-understanding.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Action Anticipation',
    'action-anticipation',
    'Action anticipation predicts which action will happen next, from seconds to minutes into the future, using only the video observed so far, before the action itself is visible. Short-term anticipation forecasts the next action after a fixed time gap, while long-term anticipation predicts a whole sequence of future actions. It matters for assistive robots, egocentric AR assistants and autonomous systems that must act ahead of people, and is benchmarked on EPIC-Kitchens-100, Ego4D and Breakfast. It complements [Action Recognition](/tasks/action-recognition) and [Temporal Action Localization](/tasks/temporal-action-localization), which reason only about frames that have already been observed.',
    'action anticipation, future action anticipation, egocentric action anticipation, short-term action anticipation, long-term action anticipation, activity anticipation, anticipating future actions, future action prediction',
    (SELECT area_id FROM tasks WHERE slug = 'video-understanding' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'video-understanding' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'video-understanding' LIMIT 1),
    true,
    NULL,
    '[Anticipative Video Transformer](https://arxiv.org/abs/2106.02036)',
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
