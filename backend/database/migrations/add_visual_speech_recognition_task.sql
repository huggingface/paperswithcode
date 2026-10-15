-- Visual Speech Recognition task (Video): top-level.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Visual Speech Recognition',
    'visual-speech-recognition',
    'Visual speech recognition, also known as lip reading, transcribes spoken words from silent video of a speakers mouth and face without access to the audio. It is harder than audio [Automatic Speech Recognition](/tasks/automatic-speech-recognition) because many phonemes look alike on the lips (visemes), so models combine spatiotemporal visual front-ends with sequence models trained with CTC or attention objectives. Visual cues are also fused with audio in audio-visual speech recognition (AVSR) for robustness in noisy environments. It supports silent dictation and accessibility for people with hearing or speech impairments, and is benchmarked by word error rate on LRS2, LRS3 and LRW.',
    'visual speech recognition, lip reading, lipreading, lip-reading, visual-only speech recognition, audio-visual speech recognition, audiovisual speech recognition, AVSR',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[LipNet: End-to-End Sentence-level Lipreading](/paper/1611.01599)',
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

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, v.ord
FROM tasks t
CROSS JOIN (VALUES ('automatic-speech-recognition', 0)) AS v(slug, ord)
JOIN tasks s ON s.slug = v.slug
WHERE t.slug = 'visual-speech-recognition'
ON CONFLICT DO NOTHING;
