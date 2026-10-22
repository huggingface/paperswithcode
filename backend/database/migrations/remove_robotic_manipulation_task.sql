-- Robotic Manipulation (added 2026-10-21) duplicated Robotics: every robot
-- leaderboard already lives on Robotics. Fold the task into Robotics, then remove it.
-- Its papers get the Robotics tag (a manual tag stays manual), and its keywords join
-- Robotics' so the weekly keyword linker keeps tagging manipulation papers.
-- Applied 2026-10-22.

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT pt.paper_id, r.id, pt.source FROM paper_tasks pt
JOIN tasks m ON m.id = pt.task_id AND m.slug = 'robotic-manipulation', tasks r
WHERE r.slug = 'robotics'
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
WHERE EXCLUDED.source = 'manual';

UPDATE tasks r SET keywords = 'vision-language-action, vision language action model, VLA, robotic manipulation, robot manipulation, dexterous manipulation, bimanual manipulation, mobile manipulation, in-hand manipulation, contact-rich manipulation, deformable object manipulation, manipulation policy, manipulation policies, robotic grasping, robot grasping, dexterous grasping, grasp detection, grasp synthesis, pick-and-place, LIBERO'
WHERE r.slug = 'robotics' AND EXISTS (SELECT 1 FROM tasks WHERE slug = 'robotic-manipulation');

DELETE FROM paper_tasks pt USING tasks m
WHERE m.slug = 'robotic-manipulation' AND pt.task_id = m.id;

DELETE FROM tasks WHERE slug = 'robotic-manipulation';
