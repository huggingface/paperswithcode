-- Add Saliency Maps, introduced in arXiv 1312.6034. Production chat users looked it
-- up on 2026-10-15/16 and the catalog had no row. The source paper gets the
-- source evidence row (Introduced banner).

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'saliency-map',
    'Saliency Maps',
    'Gradient Saliency Maps (Simonyan et al.)',
    'Gradient saliency maps, also called vanilla gradients, explain an image classifier''s decision by computing the gradient of the class score with respect to the input pixels in a single backward pass. The magnitude of the gradient, taking the maximum over colour channels, shows which pixels would change the score most if perturbed, giving an image-specific class saliency map without extra training or model changes. Simonyan, Vedaldi and Zisserman introduced the method together with class model visualisation, which optimizes an input image to maximize a class score. They used the saliency maps for weakly supervised object localization with GraphCut and showed that the computation is closely related to deconvolutional network reconstruction. This is distinct from visual saliency prediction, which models where humans look. Later attribution methods such as SmoothGrad, Guided Backpropagation, [Integrated Gradients](/methods/integrated-gradients) and [Grad-CAM](/methods/grad-cam) refine these noisy gradient maps.',
    'gradient saliency map, gradient saliency maps, gradient-based saliency map, gradient-based saliency maps, image-specific class saliency, class saliency map, class saliency maps, vanilla gradient, vanilla gradients',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2013,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1312.6034'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Deep Inside Convolutional Networks: Visualising Image Classification Models and Saliency Maps',
    'https://github.com/pytorch/captum/blob/master/captum/attr/_core/saliency.py',
    NULL,
    '[Deep Inside Convolutional Networks: Visualising Image Classification Models and Saliency Maps](/paper/1312.6034)'
)
ON CONFLICT (slug) DO UPDATE
SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id
FROM methods
WHERE slug = 'saliency-map'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'saliency-map'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Citation review 2026-10-16: 55 of the 521 local papers that Semantic Scholar
-- lists as citing the source name Saliency Maps in their title or abstract.
CREATE TEMP TABLE saliency_map_linked_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'saliency-map'
  AND p.is_latest_version
  AND p.id IN (
        574, -- Exploiting saliency for object segmentation from image level labels
        662, -- Interpretable Explanations of Black Boxes by Meaningful Perturbation
        1028, -- Beyond saliency: understanding convolutional neural networks from salien
        1070, -- Understanding Deep Architectures by Visual Summaries
        1287, -- A Theoretical Explanation for Perplexing Behaviors of Backpropagation-ba
        1400, -- Explaining Image Classifiers by Counterfactual Generation
        1415, -- Regional Multi-scale Approach for Visually Pleasing Explanations of Deep
        1780, -- On the (In)fidelity and Sensitivity for Explanations
        2058, -- Full-Gradient Representation for Neural Network Visualization
        2137, -- Why do These Match? Explaining the Behavior of Image Similarity Models
        2224, -- XRAI: Better Attributions Through Regions
        2655, -- Explaining image classifiers by removing input features using generative
        3302, -- There and Back Again: Revisiting Backpropagation Saliency Methods
        3659, -- Exploration of Interpretability Techniques for Deep COVID-19 Classificat
        3663, -- Black-box Explanation of Object Detectors via Saliency Maps
        4146, -- Puzzle Mix: Exploiting Saliency and Local Statistics for Optimal Mixup
        4419, -- Towards falsifiable interpretability research
        4992, -- Co-Mixup: Saliency Guided Joint Mixup with Supermodular Diversity
        5096, -- Do Input Gradients Highlight Discriminative Features?
        8962, -- GlobEnc: Quantifying Global Token Attribution by Incorporating the Whole
        9340, -- Which Explanation Should I Choose? A Function Approximation Perspective
        9828, -- XG-BoT: An Explainable Deep Graph Neural Network for Botnet Detection an
        10085, -- UKP-SQuARE v2: Explainability and Adversarial Attacks for Trustworthy QA
        10340, -- Look where you look! Saliency-guided Q-networks for generalization in vi
        10932, -- Similarity of Neural Architectures using Adversarial Attack Transferabil
        11958, -- On the Relationship Between Explanation and Prediction: A Causal View
        14110, -- IDGI: A Framework to Eliminate Explanation Noise from Integrated Gradien
        14187, -- ACAT: Adversarial Counterfactual Attention for Classification and Detect
        15778, -- Diversifying Deep Ensembles: A Saliency Map Approach for Enhanced OOD De
        16577, -- Learning Perturbations to Explain Time Series Predictions
        16959, -- Input-gradient space particle inference for neural network ensembles
        22108, -- Can Large Language Models Explain Themselves? A Study of LLM-Generated S
        22206, -- SalUn: Empowering Machine Unlearning via Gradient-based Weight Saliency
        24215, -- SRTransGAN: Image Super-Resolution using Transformer based Generative Ad
        25171, -- Towards Generalization in Subitizing with Neuro-Symbolic Loss using Holo
        26552, -- Common Sense Reasoning for Deepfake Detection
        35120, -- Aggregated Attributions for Explanatory Analysis of 3D Segmentation Mode
        47839, -- Set You Straight: Auto-Steering Denoising Trajectories to Sidestep Unwan
        48353, -- Interpretable graph-based models on multimodal biomedical data integrati
        60027, -- MobileMold: A Smartphone-Based Microscopy Dataset for Food Mold Detectio
        60955, -- Validating Interpretability in siRNA Efficacy Prediction: A Perturbation
        61086, -- DAVE: Distribution-aware Attribution via ViT Gradient Decomposition
        61650, -- Pulling Back the Curtain on Deep Networks
        62561, -- PosIR: Position-Aware Heterogeneous Information Retrieval Benchmark
        78131, -- SimPSI: A Simple Strategy to Preserve Spectral Information in Time Serie
        81691, -- Convolutional neural network models for cancer type prediction based on
        84469, -- Hidden Monotonicity: Explaining Deep Neural Networks via their DC Decomp
        85445, -- H-Sets: Hessian-Guided Discovery of Set-Level Feature Interactions in Im
        87884, -- On the Complexity-Faithfulness Trade-off of Gradient-Based Explanations
        92502, -- GRAIL: Gradient-Reweighted Advantages for Reinforcement Learning with Ve
        103269, -- Outcome-Grounded Advantage Reshaping for Fine-Grained Credit Assignment
        113197, -- Regulating Model Reliance on Non-Robust Features by Smoothing Input Marg
        113517, -- Characterizing Model Robustness via Natural Input Gradients
        116521, -- Structured Gradient-based Interpretations via Norm-Regularized Adversari
        122820 -- ConEx: Human-Interpretable Saliency Maps via Concept-Aware Attribution
  );

DELETE FROM paper_method_exclusions x
USING saliency_map_linked_papers l
WHERE x.paper_id = l.paper_id AND x.method_id = l.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM saliency_map_linked_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'reference' FROM saliency_map_linked_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- The other 466 local citers cite the source in passing; exclude them so the
-- hourly reference backfill does not re-link them.
CREATE TEMP TABLE saliency_map_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'saliency-map'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        55, 108, 111, 127, 131, 141, 190, 271, 276, 285, 291, 308,
        310, 343, 361, 385, 398, 416, 470, 479, 585, 601, 657, 658,
        676, 713, 756, 768, 774, 856, 884, 929, 945, 982, 987, 1020,
        1048, 1059, 1080, 1089, 1288, 1296, 1305, 1311, 1348, 1368, 1411, 1507,
        1648, 1726, 1735, 1812, 1818, 1934, 2004, 2018, 2061, 2322, 2329, 2363,
        2388, 2627, 2696, 2743, 2890, 3016, 3036, 3193, 3210, 3233, 3391, 3477,
        3521, 3639, 3719, 3796, 3820, 3872, 3913, 3939, 3940, 3966, 3977, 3992,
        4026, 4125, 4207, 4239, 4403, 4451, 4505, 4513, 4522, 4572, 4755, 4797,
        4852, 4943, 5132, 5305, 5364, 5517, 5820, 5929, 5979, 5993, 6102, 6180,
        6207, 6211, 6627, 6653, 6691, 6827, 6978, 7174, 7195, 7223, 7255, 7421,
        7454, 7610, 7809, 7838, 7863, 7975, 7980, 8021, 8148, 8169, 8562, 8772,
        8963, 9007, 9011, 9026, 9081, 9088, 9132, 9200, 9305, 9388, 9446, 9488,
        9495, 9730, 9811, 9839, 9934, 10631, 10665, 10693, 11116, 11125, 11268, 11428,
        11531, 11532, 11557, 11692, 11936, 11949, 12196, 12360, 12531, 12724, 13012, 13339,
        13356, 13404, 13474, 13743, 13816, 13864, 13969, 13976, 14162, 14199, 14243, 14441,
        14543, 14593, 14665, 14681, 14827, 14900, 15062, 15571, 15584, 15756, 15861, 16037,
        16081, 16175, 16270, 16679, 16831, 16853, 16862, 16864, 16968, 17005, 17194, 17279,
        17323, 17498, 17523, 17578, 17673, 17825, 18205, 18406, 18634, 19052, 19163, 19276,
        19646, 19951, 20417, 20651, 20873, 21222, 22442, 22544, 22697, 23088, 23512, 23750,
        23756, 23900, 24469, 24537, 24871, 25033, 25233, 25604, 26025, 26178, 26192, 26396,
        26425, 26847, 27047, 27652, 27824, 27920, 28762, 28862, 28966, 29204, 29256, 29921,
        30314, 30473, 30552, 31158, 31190, 31293, 31627, 31851, 32417, 33115, 33211, 33262,
        33389, 34312, 34329, 34969, 35498, 35926, 35988, 36228, 36469, 36473, 36684, 37943,
        38291, 38572, 39250, 39427, 39520, 39630, 40268, 40419, 40800, 40835, 40880, 41185,
        41938, 42088, 42382, 43445, 43951, 44484, 44802, 45195, 46290, 46368, 46387, 46665,
        46740, 47597, 47933, 48329, 48742, 50565, 50745, 50777, 51481, 52222, 52366, 53329,
        56043, 56550, 57651, 59342, 59952, 60384, 60521, 61085, 63463, 63883, 63939, 64015,
        64699, 64719, 65146, 65877, 66152, 67189, 68168, 68245, 69013, 69290, 70080, 71028,
        72121, 72892, 74529, 74758, 74877, 75009, 75764, 76052, 76735, 77273, 77558, 78168,
        78428, 78435, 78728, 78869, 79215, 79500, 80051, 80244, 80319, 80731, 81211, 81583,
        82170, 82183, 82253, 82324, 82329, 83542, 83977, 84095, 84212, 84522, 85099, 85819,
        86033, 86125, 86179, 86374, 86727, 86747, 86925, 87086, 87119, 87330, 87987, 88006,
        88101, 88575, 88773, 88929, 88966, 89305, 89444, 89580, 89774, 89926, 90028, 90232,
        90281, 90709, 90810, 91087, 91283, 91355, 91779, 92082, 92190, 92215, 92260, 92834,
        92896, 92966, 93409, 93444, 93741, 93847, 94391, 94694, 94877, 99440, 99571, 99974,
        100287, 100358, 100448, 100494, 100806, 101172, 101310, 101607, 101632, 101803, 102291, 102406,
        103096, 103286, 103512, 103688, 104071, 104124, 104582, 106327, 107207, 107446, 107569, 107869,
        108878, 108992, 110634, 111138, 111171, 111174, 112965, 113418, 115253, 116494, 116527, 116553,
        117202, 117437, 117476, 117946, 118206, 119093, 119153, 120529, 120606, 123501
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'saliency-map citation review 2026-10-16: cites the source without naming the method in title or abstract'
FROM saliency_map_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING saliency_map_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING saliency_map_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
