-- Chat lookup-miss taxonomy gap fill (2026-11-23 chat health audit): tasks
-- that production chat looked up with pwc_get_task and did not find. Each was
-- checked against every existing task name, slug and keyword first.
--
-- Image Enhancement is the general task the audit asked for. It sits under
-- Image Restoration, and Low-Light Image Enhancement moves under it (level 2),
-- so it stays inside the restoration tree. Multi-Hop Question Answering did
-- not exist either; it is added so the MuSiQue benchmark has a task.
--
-- Keyword choices: the MuJoCo "Humanoid" environment is already a
-- continuous-control keyword, so Humanoid Robotics uses only phrases about
-- humanoid robots. "multi-hop reasoning" is not a multi-hop QA keyword because
-- it also covers knowledge-graph path reasoning. Hero images were imported
-- separately with import_entity_image.py; this file records their credits.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES
(
    'Spam Detection',
    'spam-detection',
    'Spam detection classifies messages as unsolicited bulk or malicious content (spam) or legitimate content (ham). The classic setting is email spam filtering, where early systems used naive Bayes over word counts and later ones used SVMs, gradient-boosted trees and fine-tuned language models over the subject, body, headers and URLs. The same task covers SMS spam, social-media and review spam, and spam bots, and it overlaps with phishing detection. Spammers adapt to deployed filters, so concept drift and adversarial robustness matter as much as accuracy. Standard corpora include Enron-Spam, SpamAssassin, Ling-Spam and the SMS Spam Collection. It is a subtask of [Text Classification](/tasks/text-classification).',
    'spam detection, email spam detection, spam email detection, email spam filtering, email spam classification, spam filtering, spam filter, spam classification, SMS spam detection, SMS spam filtering, review spam detection, social spam detection',
    (SELECT area_id FROM tasks WHERE slug = 'text-classification' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'text-classification' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'text-classification' LIMIT 1),
    NULL,
    NULL,
    NULL
),
(
    'Vehicle Routing Problem',
    'vehicle-routing-problem',
    'The vehicle routing problem (VRP) asks for the cheapest set of routes for a fleet of vehicles that start and end at a depot and together serve a set of customers. It generalizes the travelling salesman problem and is NP-hard. Common variants add vehicle capacities (CVRP), customer time windows (VRPTW), pickup and delivery, multiple depots or heterogeneous fleets. Operations research solves it with exact branch-and-price methods and heuristics such as LKH, HGS and large neighbourhood search; neural combinatorial optimization learns construction policies with attention models trained by reinforcement learning (Attention Model, POMO) or learns to guide local search, and is evaluated on CVRPLib instances and random uniform instances of 20 to 1,000+ nodes. It is a planning problem related to [Path Planning](/tasks/path-planning).',
    'vehicle routing problem, vehicle routing, VRP, CVRP, VRPTW, capacitated vehicle routing, capacitated vehicle routing problem, vehicle routing with time windows, neural vehicle routing',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    0,
    NULL,
    NULL,
    NULL,
    NULL
),
(
    'Air Pollution Forecasting',
    'air-pollution-forecasting',
    'Air pollution forecasting predicts future concentrations of pollutants such as PM2.5, PM10, NO2, O3 and SO2, or an air quality index, at monitoring stations or on a spatial grid, hours to days ahead. Inputs are past pollutant readings together with meteorological forecasts, emissions, traffic and satellite data. Methods range from chemical transport models and statistical regression to LSTMs, temporal convolutional networks and spatio-temporal graph neural networks that treat stations as nodes, and recent work fine-tunes weather and Earth-system foundation models for atmospheric composition. It is a domain of [Time-series Forecasting](/tasks/time-series-forecasting) closely related to [AI Weather Forecasting](/tasks/ai-weather-forecasting) and [Traffic Forecasting](/tasks/traffic-forecasting).',
    'air pollution forecasting, air pollution prediction, air quality forecasting, air quality prediction, air quality index prediction, air quality index forecasting, PM2.5 forecasting, PM2.5 prediction, PM2.5 concentration prediction, pollutant concentration forecasting',
    (SELECT area_id FROM tasks WHERE slug = 'time-series-forecasting' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'time-series-forecasting' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'time-series-forecasting' LIMIT 1),
    NULL,
    NULL,
    NULL
),
(
    'Humanoid Robotics',
    'humanoid-robotics',
    'Humanoid robotics builds control and learning methods for robots with a human-like body: two legs, two arms, often dexterous hands and a head with cameras. Core problems are bipedal locomotion over rough terrain, whole-body control that keeps balance while the arms manipulate objects (loco-manipulation), motion retargeting and imitation of human motion capture or video, and teleoperation for data collection. Current systems train policies in simulation with reinforcement learning and transfer them to hardware such as Unitree H1/G1, Digit or Atlas, and increasingly use [vision-language-action models](/tasks/robotics) trained on humanoid demonstrations as general-purpose controllers. It is a subtask of [Robotics](/tasks/robotics); simulated humanoid benchmarks such as MuJoCo Humanoid belong to [Continuous Control](/tasks/continuous-control).',
    'humanoid robotics, humanoid robot, humanoid robots, humanoid locomotion, humanoid whole-body control, whole-body humanoid control, humanoid loco-manipulation, humanoid manipulation, humanoid teleoperation, bipedal humanoid',
    (SELECT area_id FROM tasks WHERE slug = 'robotics' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'robotics' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'robotics' LIMIT 1),
    NULL,
    NULL,
    NULL
),
(
    'Image Enhancement',
    'image-enhancement',
    'Image enhancement improves the perceptual quality of a photo: brightness, exposure, contrast, colour and detail, usually without a single ground-truth "clean" image the way denoising or deblurring have one. Classic tools are histogram equalization, gamma correction, Retinex decomposition and tone curves; learned methods predict per-pixel or global adjustments (bilateral grids, 3D lookup tables, curve estimation), are trained on expert-retouched pairs such as MIT-Adobe FiveK, or learn without paired data through GANs, zero-reference losses or diffusion models. Important settings are [Low-Light Image Enhancement](/tasks/low-light-image-enhancement), exposure correction, underwater image enhancement and photo retouching. It is part of [Image Restoration](/tasks/image-restoration).',
    'image enhancement, photo enhancement, image retouching, photo retouching, exposure correction, underwater image enhancement, color enhancement, colour enhancement, image quality enhancement',
    (SELECT area_id FROM tasks WHERE slug = 'image-restoration' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'image-restoration' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'image-restoration' LIMIT 1),
    NULL,
    NULL,
    NULL
),
(
    'Multi-Hop Question Answering',
    'multi-hop-question-answering',
    'Multi-hop question answering asks questions whose answer requires combining several pieces of evidence, typically from different documents, for example "Which country is the director of film X from?" needs the director first and then their nationality. Systems must retrieve and chain the supporting facts, not just match the question to one passage, and are scored on answer exact match and F1 and often on supporting-fact prediction. Approaches include iterative retrieval, question decomposition into single-hop sub-questions, graph reasoning over entities, and retrieval-augmented LLM agents that interleave reasoning with search. HotpotQA, 2WikiMultiHopQA and MuSiQue are the standard benchmarks; MuSiQue was built to block shortcut answers that skip hops. It is a subtask of [Question Answering](/tasks/question-answering).',
    'multi-hop question answering, multihop question answering, multi-hop QA, multihop QA, multi-hop reading comprehension, multi-hop questions',
    (SELECT area_id FROM tasks WHERE slug = 'question-answering' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'question-answering' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'question-answering' LIMIT 1),
    NULL,
    NULL,
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
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;

UPDATE tasks SET
    parent_id = (SELECT id FROM tasks WHERE slug = 'image-enhancement' LIMIT 1),
    level = (SELECT level + 1 FROM tasks WHERE slug = 'image-enhancement' LIMIT 1),
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'low-light-image-enhancement';
