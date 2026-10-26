INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Egocentric Vision',
    'egocentric-vision',
    'Egocentric vision studies first-person video captured by head- or body-worn cameras such as smart glasses, where the camera wearer''s hands, gaze, and interactions with objects and people dominate the view. Models must cope with strong camera motion, frequent occlusion, and long, unscripted recordings while recognizing and anticipating actions, localizing hand-object interactions, answering questions about episodic memory, and tracking objects and scenes over time. Large-scale datasets such as [Ego4D](/paper/2110.07058), [EPIC-KITCHENS](/paper/1804.02748), and [Ego-Exo4D](/paper/2311.18259) have made it a core subfield of [Video Understanding](/tasks/video-understanding), closely tied to [Action Recognition](/tasks/action-recognition), [Action Anticipation](/tasks/action-anticipation), [Cross-view Object Correspondence](/tasks/cross-view-object-correspondence), and embodied AI for [Robotics](/tasks/robotics) and augmented reality.',
    'egocentric vision, egocentric video, egocentric videos, egocentric video understanding, egocentric perception, egocentric action recognition, egocentric activity recognition, egocentric video question answering, ego-centric video, ego-centric vision, first-person video, first-person videos, first-person vision, first person video, first-person perspective video, wearable camera video',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'video-understanding' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'video-understanding' LIMIT 1),
    NULL,
    '[Ego4D: Around the World in 3,000 Hours of Egocentric Video](/paper/2110.07058)',
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
