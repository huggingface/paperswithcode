-- Chat lookup-miss taxonomy gap fill (2026-11-20 and 2026-11-22 chat health
-- audits): nine tasks that production chat looked up with pwc_get_task and
-- did not find. Each was checked against every existing task name, slug and
-- keyword first.
--
-- Keyword choices: "GTSRB" is not a traffic-sign keyword because most papers
-- that mention it only use it as an adversarial or backdoor benchmark, and
-- "AAC" is not an audio-captioning keyword because it also means Advanced
-- Audio Coding. Hero images were imported separately with
-- import_entity_image.py; this file records their credits.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES
(
    'Visual Servoing',
    'visual-servoing',
    'Visual servoing controls the motion of a robot or camera in closed loop from visual feedback. At each step the controller compares the current camera image (or features extracted from it) with a desired goal image or pose and computes a velocity command that drives the error to zero. Classic image-based (IBVS) and position-based (PBVS) schemes rely on hand-designed features and an interaction matrix, while learned approaches regress the relative pose or the control signal directly with a CNN, or train servoing policies end to end with reinforcement learning. It is used for positioning, grasping and alignment in [Robotics](/tasks/robotics), drone and vehicle control, and medical robots.',
    'visual servoing, visual servo control, visual servo, image-based visual servoing, position-based visual servoing, IBVS, PBVS, deep visual servoing',
    (SELECT area_id FROM tasks WHERE slug = 'robotics' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'robotics' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'robotics' LIMIT 1),
    NULL,
    '[Training Deep Neural Networks for Visual Servoing](https://arxiv.org/abs/1705.08940)',
    NULL
),
(
    'Formal Verification',
    'formal-verification',
    'Formal verification proves mathematically that a system satisfies a specification, instead of testing it on examples. In machine learning it covers two directions. Neural network verification certifies properties of a trained model, such as robustness of a classifier to every perturbation inside a norm ball, with SMT solvers, mixed-integer programming or bound propagation. Verified code generation asks language models to write programs together with the specifications, loop invariants and proof annotations that a verifier such as Dafny, Verus, F* or Coq accepts. It is closely related to [Autoformalization](/tasks/autoformalization) and formal theorem proving in [Mathematics](/tasks/math).',
    'formal verification, formally verified, neural network verification, verification of neural networks, verified code generation, program verification, software verification, Dafny, Verus',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    0,
    NULL,
    NULL,
    '[DafnyBench: A Benchmark for Formal Software Verification](https://arxiv.org/abs/2406.08467)',
    NULL
),
(
    'Audio Captioning',
    'audio-captioning',
    'Audio captioning, also called automated audio captioning, generates a natural-language sentence that describes the content of an audio clip: the sound events, their sources, the acoustic scene and how they relate in time, for example "a dog barks while cars pass by on a wet road". Systems typically pair a pretrained audio encoder with a text decoder or a large language model and are evaluated on Clotho and AudioCaps with captioning metrics such as SPIDEr, CIDEr and FENSE. It is the audio counterpart of [Image Captioning](/tasks/image-captioning) and [Video Captioning](/tasks/video-captioning), and a core capability of [audio-language models](/tasks/audio-understanding).',
    'audio captioning, automated audio captioning, automatic audio captioning, sound captioning, audio caption generation',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Audio Captioning Transformer](https://arxiv.org/abs/2107.09817)',
    NULL
),
(
    'Keyword Spotting',
    'keyword-spotting',
    'Keyword spotting (KWS) detects a small set of spoken words or phrases, such as wake words ("Hey Siri", "Alexa") or short commands ("yes", "stop"), in a continuous audio stream. Because it runs always-on, often on microcontrollers and phones, models must be tiny, low-latency and power-efficient; small CNNs, depthwise-separable and attention models over MFCC or log-mel features are typical. Open-vocabulary and few-shot variants detect user-defined keywords from text or a few examples. Google Speech Commands is the standard benchmark. It is a lightweight relative of [Automatic Speech Recognition](/tasks/automatic-speech-recognition).',
    'keyword spotting, KWS, wake word detection, wake-word detection, wakeword detection, hotword detection, spoken keyword detection, spoken term detection, query-by-example spoken term detection, user-defined keyword spotting, open-vocabulary keyword spotting',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Hello Edge: Keyword Spotting on Microcontrollers](/paper/1711.07128)',
    NULL
),
(
    'Lane Detection',
    'lane-detection',
    'Lane detection localizes the lane markings and lane boundaries of a road in camera images, usually as a set of curves or polylines. Methods segment lane pixels, regress anchor-based or row-wise lane positions, or fit parametric curves, and 3D lane detection estimates the lanes in road coordinates from a monocular image. Robustness to occlusion, missing markings, night and curved roads matters, and benchmarks include TuSimple, CULane, CurveLanes and OpenLane. Lane detection is a basic perception module of [Autonomous Driving](/tasks/autonomous-driving) and driver-assistance systems.',
    'lane detection, lane line detection, lane marking detection, lane boundary detection, lane segmentation, 3D lane detection, monocular 3D lane detection',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Keep your Eyes on the Lane: Real-time Attention-guided Lane Detection](https://arxiv.org/abs/2010.12035)',
    NULL
),
(
    'Video Captioning',
    'video-captioning',
    'Video captioning generates natural-language descriptions of a video. Single-sentence captioning summarizes a short clip, while dense video captioning localizes multiple events in a long untrimmed video and writes a caption for each, and paragraph captioning produces a coherent multi-sentence story. Early models encoded frames with CNNs and decoded with LSTMs; current systems use video transformers and video-language models trained on large narrated datasets. Common benchmarks are MSR-VTT, MSVD, VATEX, ActivityNet Captions and YouCook2, scored with CIDEr, METEOR and BLEU. It extends [Image Captioning](/tasks/image-captioning) to time and is closely tied to [Video Understanding](/tasks/video-understanding).',
    'video captioning, dense video captioning, video caption generation, video description generation, video paragraph captioning, video-to-text generation',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Sequence to Sequence -- Video to Text](https://arxiv.org/abs/1505.00487)',
    NULL
),
(
    'Path Planning',
    'path-planning',
    'Path planning, or motion planning, finds a collision-free path or trajectory that moves a robot, vehicle or agent from a start to a goal configuration while respecting obstacles, kinematic and dynamic constraints, and costs such as length, time or smoothness. Classic planners include graph search (A*, Dijkstra), sampling-based methods (PRM, RRT, RRT*) and trajectory optimization; learned planners predict paths or guide sampling with neural networks, and multi-agent path finding coordinates many agents at once. It is a core component of [Robotics](/tasks/robotics), [Autonomous Driving](/tasks/autonomous-driving) and drone navigation.',
    'path planning, motion planning, trajectory planning, robot path planning, collision-free path planning, sampling-based motion planning, multi-agent path finding',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Motion Planning Networks](/paper/1806.05767)',
    NULL
),
(
    'Traffic Sign Recognition',
    'traffic-sign-recognition',
    'Traffic sign recognition detects traffic signs in road-scene images and classifies them into their sign categories, such as speed limits, stop or yield. The task combines small-object [Object Detection](/tasks/object-detection) in high-resolution street images with fine-grained classification across hundreds of classes that vary by country, under blur, occlusion and changing light. Benchmarks include GTSRB and GTSDB, Tsinghua-Tencent 100K and the Mapillary Traffic Sign Dataset. It is part of the perception stack of [Autonomous Driving](/tasks/autonomous-driving) and driver-assistance systems.',
    'traffic sign recognition, traffic sign detection, traffic sign classification, traffic-sign recognition, traffic-sign detection, road sign recognition, road sign detection',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[The Mapillary Traffic Sign Dataset for Detection and Classification on a Global Scale](/paper/1909.04422)',
    NULL
),
(
    'Hand Detection',
    'hand-detection',
    'Hand detection localizes human hands in images or video with bounding boxes, often together with their side (left or right), contact state and the object they hold. Hands are small, deformable, frequently occluded and seen from many viewpoints, especially in egocentric video. Hand detectors are the first stage of hand pose estimation, [Gesture Recognition](/tasks/gesture-recognition), hand-object interaction understanding and sign language systems. It is a specialization of [Object Detection](/tasks/object-detection).',
    'hand detection, hand detector, hand localization, hand-object detection, hand object detection, egocentric hand detection',
    (SELECT area_id FROM tasks WHERE slug = 'object-detection' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'object-detection' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'object-detection' LIMIT 1),
    NULL,
    '[Understanding Human Hands in Contact at Internet Scale](https://arxiv.org/abs/2006.06669)',
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
