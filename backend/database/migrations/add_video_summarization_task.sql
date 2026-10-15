-- Video Summarization task (Video): top-level.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Video Summarization',
    'video-summarization',
    'Video summarization condenses a long video into a short summary, either a set of keyframes (a storyboard) or a sequence of selected shots (a video skim), that preserves its most important and diverse content. Models score frames or shots for importance, learning from human annotations or from unsupervised representativeness and diversity objectives, and may condition on a user query; the closely related highlight detection task ranks the most interesting moments. Common benchmarks are SumMe, TVSum and QVHighlights. It is the visual counterpart of text [Summarization](/tasks/summarization) and builds on [Video Understanding](/tasks/video-understanding).',
    'video summarization, video summarisation, video highlight detection, highlight detection, keyframe extraction, key frame extraction, video skimming',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[Video Summarization Using Deep Neural Networks: A Survey](https://arxiv.org/abs/2101.06072)',
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
