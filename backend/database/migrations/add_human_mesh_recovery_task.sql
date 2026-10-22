-- Add Human Mesh Recovery.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_task and it was missing from the catalog.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Human Mesh Recovery',
    'human-mesh-recovery',
    'Human mesh recovery estimates a full 3D body mesh, typically the pose and shape parameters of a parametric model such as SMPL, from a single image or a video. Compared with [3D Pose Estimation](/tasks/3d-pose-estimation), which predicts a sparse skeleton, it also recovers body shape and surface, which animation, motion capture, AR and avatar creation need. Methods range from regression networks like HMR and transformer-based METRO and HMR 2.0 to optimization-in-the-loop and diffusion approaches, and are evaluated with MPJPE, PA-MPJPE and PVE on benchmarks like Human3.6M and 3DPW.',
    'human mesh recovery, human mesh reconstruction, 3D human mesh recovery, 3D human mesh reconstruction, 3D human mesh estimation, human body mesh recovery, human pose and shape estimation, 3D human pose and shape estimation, whole-body mesh recovery, HMR, SMPL regression, 3D human shape estimation',
    (SELECT area_id FROM tasks WHERE slug = '3d-pose-estimation' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = '3d-pose-estimation' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = '3d-pose-estimation' LIMIT 1),
    NULL,
    '[JOTR: 3D Joint Contrastive Learning with Transformers for Occluded Human Mesh Recovery](/paper/2307.16377)',
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

-- 112 papers match the task keywords (same matcher as the
-- weekly keyword backfill).
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'auto'
FROM papers p
CROSS JOIN tasks t
WHERE t.slug = 'human-mesh-recovery'
  AND p.id IN (
        1435, 3285, 4569, 5549, 6826, 8134, 8871, 9784, 9922, 11452, 13717, 14083,
        14226, 14295, 14645, 16695, 17886, 17958, 18777, 19186, 19512, 19654, 19755, 19786,
        21110, 25893, 26734, 27818, 28032, 28979, 29097, 29138, 29508, 29805, 29845, 30781,
        36270, 36647, 40713, 41405, 42470, 42938, 45657, 45811, 46874, 47435, 52422, 53482,
        54679, 55099, 56189, 56850, 57123, 57436, 61715, 63075, 64547, 65376, 66428, 69310,
        70946, 71224, 73521, 75514, 78389, 78666, 78835, 83984, 84391, 84545, 84946, 84997,
        85477, 87968, 88082, 89500, 90087, 90146, 90355, 99557, 103963, 103969, 103970, 106543,
        107226, 107520, 109872, 112561, 113115, 113428, 114053, 115535, 115566, 115582, 115720, 115854,
        116078, 116631, 117030, 117071, 117083, 118261, 118962, 119250, 119253, 119270, 119794, 119955,
        120285, 120548, 121903, 123360
  )
ON CONFLICT DO NOTHING;
