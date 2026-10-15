-- Video Inpainting task: subtask of video-restoration.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Video Inpainting',
    'video-inpainting',
    'Video inpainting fills missing or masked regions in every frame of a video with content that is both plausible and temporally consistent, enabling object removal, watermark and logo removal, scratch repair and video retargeting. Unlike [Image Inpainting](/tasks/image-inpainting), it can borrow real pixels visible in other frames, so methods combine optical-flow-guided propagation with transformer or diffusion models that synthesize regions never seen in the video. It is typically evaluated on YouTube-VOS and DAVIS with PSNR, SSIM, VFID and flow warping error, and sits alongside [Video Restoration](/tasks/video-restoration) and [Video Editing](/tasks/video-editing).',
    'video inpainting, video in-painting, video completion, video object removal, video hole filling, flow-guided video inpainting',
    (SELECT area_id FROM tasks WHERE slug = 'video-restoration' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'video-restoration' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'video-restoration' LIMIT 1),
    true,
    NULL,
    '[ProPainter: Improving Propagation and Transformer for Video Inpainting](/paper/2309.03897)',
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
CROSS JOIN (VALUES ('image-inpainting', 0), ('video-editing', 1)) AS v(slug, ord)
JOIN tasks s ON s.slug = v.slug
WHERE t.slug = 'video-inpainting'
ON CONFLICT DO NOTHING;
