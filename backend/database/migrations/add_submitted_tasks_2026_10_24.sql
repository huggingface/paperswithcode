-- Tasks suggested through the paper-page submission queue and approved in the
-- 2026-10-24 triage. Hero images are imported separately with
-- import_entity_image.py; this migration only records the taxonomy rows.

BEGIN;

CREATE TEMP TABLE submitted_tasks (
    slug text PRIMARY KEY,
    name text NOT NULL,
    parent_slug text,
    area_name text,
    keywords text NOT NULL,
    description text NOT NULL,
    ord int NOT NULL
) ON COMMIT DROP;

INSERT INTO submitted_tasks VALUES
('image-quality-assessment', 'Image Quality Assessment', NULL, 'Vision',
 'image quality assessment, IQA, full-reference image quality, perceptual quality assessment, blind image quality, image aesthetic assessment',
 'Image quality assessment (IQA) predicts how good an image looks to a human observer, either against a pristine reference (full-reference) or from the distorted image alone ([No-Reference Image Quality Assessment](/tasks/no-reference-image-quality-assessment)). Models are scored by rank and linear correlation (SRCC, PLCC) with human mean opinion scores, and are used to tune compression, restoration, and generative models. See also [Video Quality Assessment](/tasks/video-quality-assessment).',
 1),
('computer-aided-design', 'Computer-Aided Design', NULL, 'Other',
 'computer-aided design, CAD model generation, CAD generation, CAD reconstruction, CAD code generation, parametric CAD, B-rep, boundary representation, sketch-and-extrude',
 'Computer-aided design (CAD) tasks generate, reconstruct, or edit engineering models in the parametric form used by CAD software: sketch-and-extrude command sequences, boundary representations (B-rep), or CAD scripts. Inputs range from text and images to point clouds and scans. Related tasks: [3D generation](/tasks/3d-generation) and [Code Generation](/tasks/code-generation).',
 2),
('video-anomaly-detection', 'Video Anomaly Detection', 'anomaly-detection', NULL,
 'video anomaly detection, weakly supervised video anomaly detection, surveillance anomaly detection, abnormal event detection',
 'Video anomaly detection localizes frames or segments in a video where unusual events occur, such as accidents, fights, or abnormal motion in surveillance footage. Methods are trained with normal videos only, video-level weak labels, or no labels, and are scored with frame-level AUC or AP. A subtask of [Anomaly Detection](/tasks/anomaly-detection).',
 3),
('quantum-machine-learning', 'Quantum Machine Learning', NULL, 'Other',
 'quantum machine learning, QML, variational quantum circuit, quantum neural network, parameterized quantum circuit, quantum kernel',
 'Quantum machine learning studies learning algorithms that run on, or are inspired by, quantum computers, such as variational quantum circuits, quantum neural networks, and quantum kernel methods. It also covers classical machine learning used to simulate, control, or error-correct quantum systems.',
 4),
('cybersecurity', 'Cybersecurity', NULL, 'General',
 'cybersecurity, cyber security, intrusion detection, malware detection, malware classification, vulnerability detection, penetration testing, network intrusion, phishing detection, capture the flag',
 'Cybersecurity applications of machine learning detect and respond to attacks: intrusion and malware detection, phishing and fraud detection, vulnerability discovery in source code, and agentic penetration testing or capture-the-flag challenges. Related tasks: [Anomaly Detection](/tasks/anomaly-detection) and [Coding Agents](/tasks/coding-agents).',
 5),
('speech-deepfake-detection', 'Speech Deepfake Detection', 'deepfake-detection', 'Audio',
 'speech deepfake detection, audio deepfake detection, spoofing detection, speech anti-spoofing, voice anti-spoofing, synthetic speech detection, ASVspoof, spoofed speech',
 'Speech deepfake detection decides whether an utterance is bona fide or produced by text-to-speech or voice conversion, protecting speaker verification and media integrity. Standard evaluations include ASVspoof and In-the-Wild, scored by equal error rate (EER) and min t-DCF. A subtask of [Deepfake Detection](/tasks/deepfake-detection).',
 6),
('traffic-forecasting', 'Traffic Forecasting', 'time-series-forecasting', NULL,
 'traffic forecasting, traffic prediction, traffic flow prediction, traffic flow forecasting, traffic speed prediction',
 'Traffic forecasting predicts future traffic flow, speed, or demand on a road network from past sensor readings, usually with spatio-temporal graph models. Standard benchmarks include METR-LA, PEMS-BAY, and PEMS03/04/07/08, scored by MAE, RMSE, and MAPE. A subtask of [Time-series forecasting](/tasks/time-series-forecasting).',
 7),
('talking-head-generation', 'Talking Head Generation', 'video-generation', NULL,
 'talking head generation, talking head, talking face generation, audio-driven portrait animation, portrait animation, lip sync, lip-sync, audio-driven facial animation',
 'Talking head generation synthesizes a video of a person speaking from a reference portrait and a driving signal such as audio, text, or another video, with accurate lip sync, expressions, and head motion. Evaluations use FID, FVD, and lip-sync scores such as Sync-C/Sync-D. A subtask of [Video generation](/tasks/video-generation).',
 8),
('inverse-rendering', 'Inverse Rendering', NULL, 'Vision',
 'inverse rendering, intrinsic image decomposition, intrinsic decomposition, material estimation, SVBRDF estimation, relighting, lighting estimation',
 'Inverse rendering recovers the physical causes of an image—geometry, materials (albedo, roughness, BRDF), and illumination—from one or more photographs, enabling relighting and material editing. Related tasks: [3D understanding](/tasks/3d-understanding) and [3D generation](/tasks/3d-generation).',
 9),
('autoformalization', 'Autoformalization', 'math', NULL,
 'autoformalization, autoformalisation, auto-formalization, statement formalization, formalization of mathematics',
 'Autoformalization translates informal mathematics—statements and proofs written in natural language—into formal languages checked by proof assistants such as Lean, Isabelle, or Coq. It is evaluated by type-checking rate and semantic faithfulness to the source, and underpins formal theorem proving. A subtask of [Mathematics](/tasks/math).',
 10),
('multi-agent-systems', 'Multi-Agent Systems', 'agents', NULL,
 'multi-agent system, multi-agent LLM, LLM-based multi-agent, multi-agent collaboration, multi-agent debate, agent orchestration',
 'Multi-agent systems coordinate several LLM agents—often with distinct roles, tools, or models—through debate, delegation, or shared memory to solve tasks that a single agent handles poorly. A subtask of [Agents](/tasks/agents); for reinforcement-learning agents see [Multi-Agent Reinforcement Learning](/tasks/multi-agent-reinforcement-learning).',
 11),
('multi-label-image-classification', 'Multi-label Image Classification', 'image-classification', NULL,
 'multi-label image classification, multi-label image recognition, multi-label recognition',
 'Multi-label image classification predicts every category present in an image rather than a single label. Standard benchmarks include MS-COCO, PASCAL VOC 2007, and NUS-WIDE, scored by mean average precision (mAP). A subtask of [Image Classification](/tasks/image-classification).',
 12),
('causal-inference', 'Causal Inference', NULL, 'Other',
 'causal inference, causal discovery, treatment effect estimation, causal effect estimation, counterfactual inference, structural causal model, causal representation learning',
 'Causal inference estimates the effect of interventions and uncovers cause-and-effect structure from data: treatment-effect estimation, counterfactual prediction, causal discovery of graphs, and causal representation learning. It matters wherever decisions depend on what would happen under a change, not just on correlation.',
 13),
('spatial-understanding', 'Spatial Understanding', NULL, 'Vision',
 'spatial understanding, spatial reasoning, visual spatial reasoning, spatial intelligence, 3D spatial reasoning',
 'Spatial understanding evaluates whether models perceive and reason about where things are: relative position, distance, size, orientation, and viewpoint changes across images, video, and 3D scenes. It is a common weakness of vision-language models and is measured by benchmarks such as VSI-Bench and SpatialEval. Related tasks: [3D understanding](/tasks/3d-understanding) and [Visual Grounding](/tasks/visual-grounding).',
 14),
('materials-and-chemistry', 'Materials & Chemistry', NULL, 'Other',
 'materials discovery, materials science, machine learning interatomic potential, interatomic potential, MLIP, crystal structure prediction, crystal generation, computational chemistry, molecule generation, retrosynthesis',
 'Machine learning for materials and chemistry: property prediction, machine-learning interatomic potentials for fast simulation, generative design of crystals and molecules, and reaction and retrosynthesis planning. Related tasks: [Molecular Property Prediction](/tasks/molecular-property-prediction).',
 15),
('test-time-adaptation', 'Test-time Adaptation', NULL, 'Vision',
 'test-time adaptation, test time adaptation, fully test-time adaptation, continual test-time adaptation, source-free domain adaptation, test-time training',
 'Test-time adaptation (TTA) updates a deployed model on unlabeled test data as it arrives, to recover accuracy under distribution shift without access to the source training data. Benchmarks include ImageNet-C, CIFAR-10-C/100-C, and continual shift protocols. Related to [Unsupervised Domain Adaptation](/tasks/unsupervised-domain-adaptation).',
 16),
('streaming-video-understanding', 'Streaming Video Understanding', 'video-understanding', NULL,
 'streaming video understanding, online video understanding, streaming video, real-time video understanding, proactive video assistant, live video interaction',
 'Streaming video understanding processes video as a live stream: models must answer questions, narrate, or respond proactively in real time using only the frames seen so far, under bounded memory and latency. A subtask of [Video Understanding](/tasks/video-understanding).',
 17),
('finance', 'Finance', NULL, 'Other',
 'financial forecasting, stock prediction, stock movement prediction, quantitative trading, algorithmic trading, portfolio optimization, financial NLP, financial question answering, financial LLM',
 'Machine learning for finance: stock and market forecasting, quantitative and algorithmic trading, portfolio optimization, fraud and risk modeling, and financial language understanding and question answering. Related tasks: [Time-series forecasting](/tasks/time-series-forecasting).',
 18),
('composed-image-retrieval', 'Composed Image Retrieval', 'image-retrieval', NULL,
 'composed image retrieval, zero-shot composed image retrieval, text-guided image retrieval, image retrieval with text feedback',
 'Composed image retrieval (CIR) retrieves target images from a query made of a reference image plus a text modification (for example, "the same dress in red"). Benchmarks include FashionIQ, CIRR, CIRCO, and i-CIR, scored by Recall@K or mAP. A subtask of [Image Retrieval](/tasks/image-retrieval).',
 19);

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
SELECT s.name, s.slug, s.description, s.keywords,
       COALESCE(a.id, p.area_id),
       COALESCE(p.level + 1, 0),
       p.id
FROM submitted_tasks s
LEFT JOIN tasks p ON p.slug = s.parent_slug
LEFT JOIN areas a ON a.name = s.area_name
ORDER BY s.ord
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

-- No-reference IQA becomes a subtask of the broader Image Quality Assessment.
UPDATE tasks
SET parent_id = (SELECT id FROM tasks WHERE slug = 'image-quality-assessment'),
    level = 1,
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'no-reference-image-quality-assessment';

COMMIT;
