-- Add Scene Graph Generation.
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_task and it was missing from the catalog.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Scene Graph Generation',
    'scene-graph-generation',
    'Scene graph generation turns an image into a structured graph whose nodes are detected objects and whose edges are the relationships between them, such as (man, riding, motorcycle) or (helmet, on, head). Models detect objects, then classify the predicate for each pair, and must cope with a long-tailed predicate distribution and the dominance of generic relations like ''on'' and ''has''. Scene graphs support captioning, visual question answering and retrieval, and the 3D counterpart is [3D Scene Graph Generation](/tasks/3d-scene-graph-generation). Standard benchmarks are Visual Genome and Open Images, scored with recall@K and mean recall@K.',
    'scene graph generation, scene graph prediction, scene graph parsing, scene graph detection, scene graph classification, visual relationship detection, visual relationship recognition, panoptic scene graph generation, unbiased scene graph generation, open-vocabulary scene graph generation, video scene graph generation, image scene graph generation',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Neural Motifs: Scene Graph Parsing with Global Context](/paper/1711.06640)',
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

-- 124 papers match the task keywords (same matcher as the
-- weekly keyword backfill).
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'auto'
FROM papers p
CROSS JOIN tasks t
WHERE t.slug = 'scene-graph-generation'
  AND p.id IN (
        557, 971, 1595, 3587, 3837, 3881, 6013, 6311, 8234, 9878, 10068, 13704,
        13804, 14049, 14122, 14221, 16432, 18982, 19199, 19396, 19410, 20122, 22038, 23506,
        23856, 23910, 25401, 25978, 28491, 28719, 30023, 30179, 30363, 32900, 32954, 34552,
        34711, 35037, 36934, 41222, 41273, 45420, 47273, 48600, 49340, 51419, 54535, 55449,
        56410, 58372, 59199, 59474, 59599, 59775, 65931, 66577, 70685, 71704, 71891, 72518,
        73885, 74185, 74274, 74677, 74983, 75234, 76724, 77199, 80129, 80177, 80242, 82272,
        84005, 85418, 88282, 88506, 90202, 90798, 90809, 90830, 90924, 90962, 90989, 92022,
        95417, 97911, 99056, 101277, 103686, 106597, 108566, 109331, 109332, 109333, 109334, 109335,
        109336, 109337, 109338, 109339, 112690, 112699, 113331, 113608, 113642, 115383, 115419, 115452,
        115664, 116181, 116223, 116803, 117015, 117100, 117163, 117199, 117726, 117727, 118902, 119497,
        120103, 120528, 121460, 121813
  )
ON CONFLICT DO NOTHING;
