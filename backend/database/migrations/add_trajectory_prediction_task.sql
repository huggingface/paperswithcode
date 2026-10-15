-- Trajectory Prediction task (General): top-level.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Trajectory Prediction',
    'trajectory-prediction',
    'Trajectory prediction forecasts the future positions of moving agents such as pedestrians, cyclists, vehicles or robots over the next few seconds, from their observed past motion and scene context such as maps, obstacles and neighbouring agents. Because the future is uncertain and agents interact, for example by avoiding each other, modern methods output multiple socially and physically plausible trajectories using generative models, transformers or diffusion. It is essential for safe planning in [Autonomous Driving](/tasks/autonomous-driving) and social [Robotics](/tasks/robotics). Pedestrian benchmarks include ETH/UCY and the Stanford Drone Dataset, while vehicle motion forecasting is benchmarked on Argoverse, the Waymo Open Motion Dataset and nuScenes using ADE/FDE and minADE/minFDE over K samples.',
    'trajectory prediction, trajectory forecasting, pedestrian trajectory prediction, human trajectory prediction, vehicle trajectory prediction, multi-agent trajectory prediction, motion forecasting, agent motion prediction, vehicle motion prediction, multi-agent motion prediction',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[Social GAN: Socially Acceptable Trajectories with Generative Adversarial Networks](/paper/1803.10892)',
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
