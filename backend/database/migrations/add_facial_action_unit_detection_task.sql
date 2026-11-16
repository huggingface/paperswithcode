-- Facial Action Unit Detection task (BP4D / DISFA AU benchmarks).
INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Facial Action Unit Detection',
    'facial-action-unit-detection',
    'Facial action unit detection predicts which facial muscle movements, the action units (AUs) of the Facial Action Coding System, are active in a face image or video frame, such as the inner brow raiser (AU1) or the lip corner puller (AU12). It is a multi-label problem, scored by the F1 of each AU averaged over the AUs annotated in benchmarks like BP4D and DISFA. It complements [Facial Expression Recognition](/tasks/facial-expression-recognition) and builds on [Face Detection](/tasks/face-detection) and [Facial Landmark Detection](/tasks/facial-landmark-detection).',
    'facial action unit detection, facial action unit recognition, action unit detection, action unit recognition, AU detection, AU recognition, facial action units, facial action coding system, FACS',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Learning Multi-dimensional Edge Feature-based AU Relation Graph for Facial Action Unit Recognition](/paper/2205.01782)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
