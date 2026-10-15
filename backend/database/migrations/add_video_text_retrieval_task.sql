-- Video-Text Retrieval task (Video): top-level.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Video-Text Retrieval',
    'video-text-retrieval',
    'Video-text retrieval matches natural-language queries with videos: text-to-video retrieval ranks a video collection for a caption or search query, and video-to-text retrieval ranks captions for a given video. Most models embed both modalities in a joint space, often initialized from image-text models such as CLIP with added temporal aggregation over frames, and are evaluated with Recall@K on MSR-VTT, MSVD, DiDeMo, ActivityNet Captions and LSMDC. It extends cross-modal [Retrieval](/tasks/retrieval) to video and complements [Video Temporal Grounding](/tasks/video-temporal-grounding), which localizes moments inside a single video.',
    'video-text retrieval, video text retrieval, text-video retrieval, text-to-video retrieval, text to video retrieval, video-to-text retrieval, video-language retrieval, video retrieval',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[CLIP4Clip: An Empirical Study of CLIP for End to End Video Clip Retrieval](/paper/2104.08860)',
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
