-- Video Question Answering task: subtask of video-understanding.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Video Question Answering',
    'video-question-answering',
    'Video question answering (VideoQA) answers natural-language questions about the content of a video, in multiple-choice or open-ended form. Questions range from descriptive ones (what, where, how many) to temporal and causal reasoning about how events unfold, and increasingly target long videos lasting minutes to hours. Classic benchmarks include MSRVTT-QA, ActivityNet-QA and NExT-QA, while recent video LLMs are compared on Video-MME, MVBench, EgoSchema and LongVideoBench. It is a core subtask of [Video Understanding](/tasks/video-understanding) and the video counterpart of [Question Answering](/tasks/question-answering).',
    'video question answering, video question-answering, video QA, Video QA, video-QA, VideoQA, video visual question answering',
    (SELECT area_id FROM tasks WHERE slug = 'video-understanding' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'video-understanding' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'video-understanding' LIMIT 1),
    true,
    NULL,
    '[NExT-QA: Next Phase of Question-Answering to Explaining Temporal Actions](/paper/2105.08276)',
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
