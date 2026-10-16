-- Add Integrated Gradients, introduced in arXiv 1703.01365. Production chat users looked it
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
    'integrated-gradients',
    'Integrated Gradients',
    'Integrated Gradients (IG)',
    'Integrated Gradients (IG) attributes a deep network''s prediction to its input features by integrating the gradient along a straight-line path from a baseline input (for example a black image or all-zero embeddings) to the actual input. The attribution of feature i is (x_i − x''_i) multiplied by the path integral of ∂F/∂x_i, approximated in practice with a Riemann sum over 20 to 300 interpolation steps. The paper derives the method from two axioms that plain gradients and several earlier attribution methods violate: Sensitivity and Implementation Invariance. IG also satisfies Completeness, meaning the attributions sum to F(x) − F(x''). It needs only gradient calls and no change to the model, and the paper applied it to image, text, molecular and retinal-imaging models. IG addresses the gradient saturation that affects [saliency maps](/methods/saliency-map). Variants such as XRAI, Guided IG and Expected Gradients build on it, and it is commonly compared with [SHAP](/methods/shap), [LIME](/methods/lime) and [Grad-CAM](/methods/grad-cam).',
    'integrated gradients, integrated gradient, integrated-gradients, Integrated Gradients, Integrated Gradient',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2017,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1703.01365'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Axiomatic Attribution for Deep Networks',
    'https://github.com/pytorch/captum/blob/master/captum/attr/_core/integrated_gradients.py',
    NULL,
    '[Axiomatic Attribution for Deep Networks](/paper/1703.01365)'
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
WHERE slug = 'integrated-gradients'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'integrated-gradients'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Citation review 2026-10-16: 37 of the 677 local papers that Semantic Scholar
-- lists as citing the source name Integrated Gradients in their title or abstract.
CREATE TEMP TABLE integrated_gradients_linked_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'integrated-gradients'
  AND p.is_latest_version
  AND p.id IN (
        2061, -- Visualizing Deep Networks by Optimizing with Integrated Gradients
        2224, -- XRAI: Better Attributions Through Regions
        3659, -- Exploration of Interpretability Techniques for Deep COVID-19 Classificat
        5662, -- Order in the Court: Explainable AI Methods Prone to Disagreement
        6239, -- Forecasting Thermoacoustic Instabilities in Liquid Propellant Rocket Eng
        7175, -- Natural Adversarial Objects
        7938, -- HaT5: Hate Language Identification using Text-to-Text Transfer Transform
        9026, -- Exploiting the Relationship Between Kendall's Rank Correlation and Cosin
        9340, -- Which Explanation Should I Choose? A Function Approximation Perspective
        12196, -- Impossibility Theorems for Feature Attribution
        14110, -- IDGI: A Framework to Eliminate Explanation Noise from Integrated Gradien
        18039, -- Interpretable Computer Vision Models through Adversarial Training: Unvei
        21636, -- An Attribution Method for Siamese Encoders
        24731, -- Conceptualizing Suicidal Behavior: Utilizing Explanations of Predicted O
        29484, -- Have Faith in Faithfulness: Going Beyond Circuit Overlap When Finding Mo
        29577, -- "Sorry, Come Again?" Prompting -- Enhancing Comprehension and Diminishin
        30552, -- Global Counterfactual Directions
        31708, -- Class Machine Unlearning for Complex Data via Concepts Inference and Dat
        33738, -- IRCAN: Mitigating Knowledge Conflicts in LLM Generation via Identifying
        49026, -- Time series saliency maps: explaining models across multiple domains
        56962, -- Progressive Training for Explainable Citation-Grounded Dialogue: Reducin
        61254, -- Bi-directional Bias Attribution: Debiasing Large Language Models without
        69013, -- RelP: Faithful and Efficient Circuit Discovery via Relevance Patching
        70795, -- GrAInS: Gradient-based Attribution for Inference-Time Steering of LLMs a
        76881, -- Which Neurons Matter in IR? Applying Integrated Gradients-based Methods
        84960, -- Fine-Grained Post-Training Quantization for Large Vision Language Models
        89976, -- TIMING: Temporality-Aware Integrated Gradients for Time Series Explanati
        92786, -- Segment-Level Attribution for Selective Learning of Long Reasoning Trace
        93832, -- Delta-XAI: A Unified Framework for Explaining Prediction Changes in Onli
        94923, -- IGU-LoRA: Adaptive Rank Allocation via Integrated Gradients and Uncertai
        101310, -- Manifold-Aligned Guided Integrated Gradients for Reliable Feature Attrib
        105203, -- Fine-tuning Vision Language Models with Graph-based Knowledge for Explai
        105211, -- Foundation-Model-Boosted Multimodal Learning for fMRI-based Neuropathic
        107887, -- LGAN: An Efficient High-Order Graph Neural Network via the Line Graph Ag
        116521, -- Structured Gradient-based Interpretations via Norm-Regularized Adversari
        117437, -- Diffusion Integrated Gradients: Controllable Path Generation for Flexibl
        119155 -- Explainability-aware Frustum Attack: Exposing Structural Vulnerabilities
  );

DELETE FROM paper_method_exclusions x
USING integrated_gradients_linked_papers l
WHERE x.paper_id = l.paper_id AND x.method_id = l.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM integrated_gradients_linked_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'reference' FROM integrated_gradients_linked_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- The other 640 local citers cite the source in passing; exclude them so the
-- hourly reference backfill does not re-link them.
CREATE TEMP TABLE integrated_gradients_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'integrated-gradients'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        713, 756, 996, 1028, 1089, 1296, 1305, 1311, 1368, 1369, 1425, 1648,
        1780, 1818, 1887, 1934, 2058, 2145, 2241, 2295, 2363, 2388, 2437, 2510,
        2533, 2617, 2627, 2655, 2667, 2676, 2787, 2890, 3016, 3164, 3210, 3233,
        3295, 3302, 3391, 3462, 3501, 3521, 3568, 3639, 3789, 3796, 3816, 3872,
        3940, 3992, 4026, 4125, 4127, 4158, 4284, 4394, 4419, 4451, 4513, 4515,
        4522, 4755, 4791, 4797, 4868, 5096, 5190, 5299, 5305, 5364, 5572, 5645,
        5788, 5796, 5820, 5993, 6102, 6177, 6180, 6219, 6255, 6322, 6339, 6399,
        6522, 6537, 6546, 6627, 6714, 6798, 6827, 6975, 6978, 7174, 7195, 7223,
        7454, 7458, 7786, 7821, 7845, 7863, 7929, 7975, 8148, 8215, 8388, 8676,
        8699, 8963, 8977, 9081, 9088, 9132, 9200, 9240, 9388, 9420, 9446, 9690,
        9726, 9730, 9828, 10085, 10088, 10199, 10443, 10459, 10684, 10723, 10793, 10932,
        11048, 11166, 11195, 11428, 11528, 11531, 11557, 11637, 11696, 11925, 11958, 12126,
        12276, 12379, 12428, 12447, 12590, 12724, 12750, 13012, 13020, 13312, 13339, 13404,
        13422, 13428, 13822, 13864, 13907, 13969, 13976, 14187, 14243, 14441, 14593, 14665,
        14681, 15062, 15520, 15571, 15584, 15653, 15756, 15795, 15861, 16081, 16175, 16270,
        16274, 16577, 16649, 16652, 16679, 16831, 16853, 16959, 16968, 16969, 17112, 17227,
        17279, 17323, 17482, 17523, 17649, 18451, 18564, 18634, 18788, 18883, 19163, 19276,
        19917, 19951, 20080, 20161, 20274, 20280, 20417, 20515, 20599, 20651, 20815, 20873,
        21160, 21169, 21222, 21461, 21630, 21647, 21666, 21826, 21841, 22071, 22108, 22117,
        22160, 22181, 22206, 22347, 22442, 22519, 22544, 22697, 22740, 23084, 23088, 23241,
        23345, 23512, 23639, 23750, 23801, 23846, 23871, 24176, 24537, 24747, 25113, 25834,
        25855, 25875, 26025, 26178, 26190, 26192, 26328, 26552, 26593, 26611, 26631, 26697,
        26793, 26847, 27020, 27047, 27572, 27652, 27660, 27887, 28219, 28328, 28516, 28618,
        28729, 28862, 28931, 29204, 29241, 29256, 29269, 29629, 29642, 29804, 29870, 29921,
        30473, 30494, 31190, 31288, 31293, 31315, 31393, 31451, 31595, 31919, 32290, 32743,
        33115, 33211, 33262, 33389, 33844, 34000, 34312, 34329, 34667, 34975, 34980, 35120,
        35286, 35498, 35597, 35736, 35747, 36009, 36228, 36339, 36865, 36924, 37134, 37138,
        37169, 37184, 37469, 37687, 38181, 38343, 38572, 38606, 39081, 39250, 39520, 39630,
        40414, 40419, 41161, 41185, 41711, 41868, 41938, 42142, 42187, 42420, 42733, 43277,
        43352, 43445, 43816, 43951, 44096, 44484, 44802, 44866, 45195, 45200, 45252, 45934,
        45958, 46368, 46380, 46387, 47615, 47839, 47933, 48329, 48353, 48742, 48930, 49105,
        49612, 50044, 50432, 50565, 50745, 50777, 50872, 51481, 52222, 52366, 53294, 54290,
        54316, 54346, 54857, 55391, 55400, 55939, 56043, 57300, 57651, 57763, 59732, 59734,
        59941, 60459, 60488, 60521, 60666, 60906, 60955, 61086, 61252, 61451, 61458, 61650,
        62130, 62353, 62358, 62694, 62700, 63416, 63463, 63883, 63939, 64015, 64074, 64584,
        64699, 64719, 66530, 66727, 66771, 66833, 67065, 67678, 68041, 68368, 68585, 69014,
        69177, 69870, 70080, 70224, 70394, 70866, 71249, 71399, 71766, 72121, 72265, 72562,
        72591, 72803, 72810, 72962, 74022, 74529, 74877, 75009, 75764, 75902, 76524, 76827,
        76903, 76992, 77159, 77558, 77725, 77846, 78168, 78794, 78905, 78931, 79178, 79215,
        79580, 79946, 80051, 80319, 80401, 80648, 80767, 81263, 81333, 83427, 83542, 83850,
        83977, 84212, 84469, 84512, 84522, 84569, 84928, 85204, 85278, 85445, 85520, 85819,
        85858, 86022, 86033, 86310, 86390, 86461, 86695, 86727, 86747, 87086, 87119, 87275,
        87330, 87347, 87593, 87848, 87884, 87987, 88238, 88595, 88778, 88929, 88949, 89336,
        89633, 89774, 90028, 90066, 90232, 90533, 90709, 91087, 91283, 91375, 91437, 91605,
        91708, 91779, 91992, 92055, 92082, 92190, 92260, 92364, 92385, 92502, 92756, 92814,
        92834, 92879, 92896, 92942, 92966, 92986, 93061, 93288, 93444, 93467, 93483, 93657,
        94055, 94093, 94391, 94429, 94620, 94694, 94723, 94888, 96530, 98459, 98840, 99183,
        99295, 99459, 99571, 99923, 99974, 100320, 100448, 100494, 100676, 100803, 100806, 101053,
        101090, 101172, 101213, 101328, 101489, 102163, 102171, 102406, 102771, 102867, 102938, 102974,
        103213, 103269, 103393, 103602, 104988, 104990, 105248, 105319, 106307, 107207, 107535, 108066,
        108107, 108290, 108370, 108810, 108833, 108992, 109215, 109315, 109702, 110251, 110634, 110661,
        110811, 110851, 110993, 112965, 113197, 113418, 113672, 113678, 113690, 113877, 114843, 115151,
        115600, 115678, 115821, 115926, 116266, 116527, 117180, 119153, 119583, 119664, 119909, 120606,
        121781, 122403, 122759, 123501
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'integrated-gradients citation review 2026-10-16: cites the source without naming the method in title or abstract'
FROM integrated_gradients_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING integrated_gradients_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING integrated_gradients_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
