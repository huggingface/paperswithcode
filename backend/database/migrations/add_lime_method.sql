-- Add LIME, introduced in arXiv 1602.04938. Production chat users looked it
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
    'lime',
    'LIME',
    'Local Interpretable Model-agnostic Explanations (LIME)',
    'LIME (Local Interpretable Model-agnostic Explanations) explains an individual prediction of any classifier by fitting an interpretable surrogate around it. It samples perturbations of the instance, such as removing words from a text or greying out superpixels of an image, queries the black-box model on them, weights each sample by its proximity to the original input, and fits a sparse linear model whose coefficients show which features drove the prediction. Because it only needs model outputs, the same procedure works for text, image and tabular models. The paper also introduced SP-LIME, which uses submodular optimization to pick a small, diverse set of explanations that summarizes the model globally, and user studies showed that explanations help people choose the better classifier and spot untrustworthy ones, such as a husky-versus-wolf classifier that relied on snow. [SHAP](/methods/shap) later showed that LIME belongs to the family of additive feature attribution methods.',
    'local interpretable model-agnostic explanations, Local Interpretable Model-agnostic Explanations, Local Interpretable Model-Agnostic Explanations, SP-LIME',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2016,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1602.04938'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    '"Why Should I Trust You?": Explaining the Predictions of Any Classifier',
    'https://github.com/marcotcr/lime',
    NULL,
    '["Why Should I Trust You?": Explaining the Predictions of Any Classifier](/paper/1602.04938)'
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
WHERE slug = 'lime'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'lime'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Citation review 2026-10-16: 12 of the 279 local papers that Semantic Scholar
-- lists as citing the source name LIME in their title or abstract.
CREATE TEMP TABLE lime_linked_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lime'
  AND p.is_latest_version
  AND p.id IN (
        36165, -- Underwater SONAR Image Classification and Analysis using LIME-based Expl
        39366, -- Feature Responsiveness Scores: Model-Agnostic Explanations for Recourse
        48070, -- Learning Explainable Dense Reward Shapes via Bayesian Optimization
        62130, -- StealthMark: Harmless and Stealthy Ownership Verification for Medical Se
        63539, -- UniCoMTE: A Universal Counterfactual Framework for Explaining Time-Serie
        66618, -- CARLE: A Hybrid Deep-Shallow Learning Framework for Robust and Explainab
        71826, -- AQUA20: A Benchmark Dataset for Underwater Species Classification under
        73455, -- Long-context Non-factoid Question Answering in Indic Languages
        73649, -- Outcome-Based Education: Evaluating Students' Perspectives Using Transfo
        75764, -- DLBacktrace: A Model Agnostic Explainability for any Deep Learning Model
        89780, -- ExpProof : Operationalizing Explanations for Confidential Models with ZK
        102450 -- Hierarchical Causal Abduction: A Foundation Framework for Explainable Mo
  );

DELETE FROM paper_method_exclusions x
USING lime_linked_papers l
WHERE x.paper_id = l.paper_id AND x.method_id = l.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM lime_linked_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'reference' FROM lime_linked_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- The other 267 local citers cite the source in passing; exclude them so the
-- hourly reference backfill does not re-link them.
CREATE TEMP TABLE lime_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'lime'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        31994, 32489, 32526, 32613, 33115, 33262, 33564, 34095, 34189, 34203, 34382, 34439,
        34969, 34975, 35004, 35120, 35259, 35298, 35591, 35809, 35988, 36164, 36228, 36433,
        36469, 36595, 36887, 37038, 37134, 37323, 37687, 37699, 37943, 37950, 38208, 38291,
        38606, 39520, 39559, 39630, 40419, 40835, 40880, 41765, 41856, 41938, 41965, 42204,
        42599, 42769, 42772, 42917, 43277, 43445, 43816, 43976, 44139, 44158, 44315, 45031,
        45195, 46392, 46698, 46740, 47018, 47206, 47344, 48329, 48353, 50165, 50556, 50565,
        50777, 51092, 51522, 52222, 52366, 52689, 53294, 53403, 54346, 54857, 55820, 56043,
        57763, 58407, 59432, 60488, 60521, 61071, 61252, 61650, 62107, 62119, 62134, 62700,
        63156, 63883, 63939, 64015, 64382, 64418, 64532, 64699, 64844, 64972, 65228, 65422,
        65564, 65942, 66227, 66650, 66661, 66682, 66727, 67678, 69014, 69153, 70641, 70671,
        71016, 71304, 71333, 71399, 71590, 71630, 71641, 71877, 72265, 72962, 73135, 73151,
        73226, 73799, 74337, 74521, 74620, 74985, 75460, 76449, 76735, 76827, 76881, 76903,
        76962, 83427, 83762, 84003, 84170, 84383, 84469, 84512, 85099, 85255, 85278, 85445,
        85690, 86019, 86030, 86242, 86390, 86695, 87672, 87848, 88575, 88585, 88723, 88774,
        88778, 88920, 88929, 88949, 88964, 89259, 89338, 89361, 89444, 89624, 89628, 89641,
        89976, 90232, 90709, 90764, 91087, 91283, 91309, 91437, 92006, 92055, 92082, 92190,
        92366, 92524, 92814, 92879, 92896, 93061, 93435, 93467, 93483, 93605, 93677, 93741,
        93832, 94261, 94661, 94888, 96024, 96204, 98840, 99237, 99283, 99288, 99440, 99459,
        99923, 100448, 100494, 100523, 100750, 100803, 101703, 101918, 101921, 101971, 101979, 102054,
        102269, 102840, 102867, 102872, 102974, 103393, 104092, 104122, 104582, 105248, 105319, 106264,
        106640, 107535, 108053, 108071, 108290, 108992, 108993, 109702, 110175, 110251, 110440, 110546,
        110634, 111171, 111174, 111381, 112566, 112965, 113197, 113301, 113418, 113656, 113672, 114843,
        119063, 119074, 119153
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'lime citation review 2026-10-16: cites the source without naming the method in title or abstract'
FROM lime_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING lime_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING lime_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
