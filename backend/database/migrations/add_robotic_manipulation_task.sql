INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id
)
VALUES (
    'Robotic Manipulation',
    'robotic-manipulation',
    'Robotic manipulation is the problem of getting a robot to physically interact with and change the state of objects (grasping, picking and placing, pushing, inserting, folding, using tools, or assembling) from sensory input such as camera images, depth, proprioception and touch, usually conditioned on a language instruction or goal. Policies output end-effector poses, joint commands or action chunks for single arms, bimanual setups and dexterous hands, and are learned through imitation learning, [reinforcement learning](/tasks/reinforcement-learning), vision-language-action models, or [world models](/tasks/world-models). It is a core subfield of [Robotics](/tasks/robotics) and the main proving ground for generalist robot foundation models, evaluated by task success rate in simulation suites such as LIBERO and RoboCasa and on real robots.',
    'robotic manipulation, robot manipulation, dexterous manipulation, bimanual manipulation, mobile manipulation, in-hand manipulation, contact-rich manipulation, deformable object manipulation, manipulation policy, manipulation policies, robotic grasping, robot grasping, dexterous grasping, grasp detection, grasp synthesis, pick-and-place, LIBERO',
    (SELECT area_id FROM tasks WHERE slug = 'robotics' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'robotics' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'robotics' LIMIT 1)
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;
