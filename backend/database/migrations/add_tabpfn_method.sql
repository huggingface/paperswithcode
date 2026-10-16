-- Add TabPFN, introduced in arXiv 2207.01848. Production chat users looked it
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
    'tabpfn',
    'TabPFN',
    'Tabular Prior-data Fitted Network (TabPFN)',
    'TabPFN (Tabular Prior-data Fitted Network) is a [Transformer](/methods/transformer) that performs supervised classification on small tabular datasets through in-context learning. It is trained once, offline, on millions of synthetic datasets drawn from a prior built from structural causal models and Bayesian neural networks, so that it learns to approximate Bayesian posterior predictive inference. At inference the whole training set and the test points are passed as context and predictions come from a single forward pass, with no gradient updates or hyperparameter tuning. On OpenML-CC18 datasets with up to 1,000 training samples, 100 numerical features and 10 classes, the original TabPFN outperformed boosted trees such as [XGBoost](/methods/xgboost) and matched AutoML systems with up to 230× speedup (5,700× on a GPU). TabPFN v2, TabPFN-2.5 and TabPFN-3 scaled the approach to larger datasets, regression and mixed feature types, making it a leading tabular foundation model alongside [gradient-boosted decision trees](/methods/gbdt).',
    'TabPFN, TabPFNv2, TabPFN v2, TabPFN-2.5, prior-data fitted network, prior-data fitted networks',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2022,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2207.01848'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'TabPFN: A Transformer That Solves Small Tabular Classification Problems in a Second',
    'https://github.com/PriorLabs/TabPFN',
    NULL,
    '[TabPFN: A Transformer That Solves Small Tabular Classification Problems in a Second](/paper/2207.01848)'
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
WHERE slug = 'tabpfn'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'tabpfn'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Citation review 2026-10-16: 55 of the 170 local papers that Semantic Scholar
-- lists as citing the source name TabPFN in their title or abstract.
CREATE TEMP TABLE tabpfn_linked_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'tabpfn'
  AND p.is_latest_version
  AND p.id IN (
        15231, -- When Do Neural Nets Outperform Boosted Trees on Tabular Data?
        15724, -- Statistical Foundations of Prior-Data Fitted Networks
        27464, -- TuneTables: Context Optimization for Scalable Prior-Data Fitted Networks
        30790, -- In-Context Freeze-Thaw Bayesian Optimization for Hyperparameter Optimiza
        33193, -- Large Scale Transfer Learning for Tabular Data via Language Modeling
        34280, -- Unmasking Trees for Tabular Data
        42518, -- The Tabular Foundation Model TabPFN Outperforms Specialized Time Series
        43877, -- TabICL: A Tabular Foundation Model for In-Context Learning on Large Data
        47705, -- Tabular foundation model to detect empathy from visual cues
        50793, -- CausalPFN: Amortized Causal Effect Estimation via In-Context Learning
        51022, -- ConTextTab: A Semantics-Aware Tabular In-Context Learner
        54067, -- Orion-MSP: Multi-Scale Sparse Attention for Tabular In-Context Learning
        59576, -- Interventional Time Series Priors for Causal Foundation Models
        59910, -- Relational In-Context Learning via Synthetic Pre-training with Structura
        61882, -- MapPFN: Learning Causal Perturbation Maps in Context
        63378, -- Predicting Mycotoxin Contamination in Irish Oats Using Deep and Transfer
        65145, -- TabPFN-2.5: Advancing the State of the Art in Tabular Foundation Models
        65374, -- nanoTabPFN: A Lightweight and Educational Reimplementation of TabPFN
        65697, -- TabMGP: Martingale Posterior with TabPFN
        65924, -- Mitra: Mixed Synthetic Priors for Enhancing Tabular Foundation Models
        66723, -- FuelCast: Benchmarking Tabular and Temporal Models for Ship Fuel Consump
        68403, -- Tabular Data with Class Imbalance: Predicting Electric Vehicle Crash Sev
        68967, -- Chunked TabPFN: Exact Training-Free In-Context Learning for Long-Context
        72229, -- TabFlex: Scaling Tabular Learning to Millions with Linear Attention
        72702, -- TabPFN: One Model to Rule Them All?
        76078, -- Mamba4Cast: Efficient Zero-Shot Time Series Forecasting with State Space
        78284, -- ForecastPFN: Synthetically-Trained Zero-Shot Forecasting
        78297, -- Efficient Bayesian Learning Curve Extrapolation using Prior-Data Fitted
        84573, -- MultiModalPFN: Extending Prior-Data Fitted Networks for Multimodal Tabul
        85935, -- Effortless, Simulation-Efficient Bayesian Inference using Tabular Founda
        86899, -- EquiTabPFN: A Target-Permutation Equivariant Prior Fitted Network
        87368, -- A Closer Look at TabPFN v2: Understanding Its Strengths and Extending It
        88667, -- Test-Time Training Provably Improves Transformers as In-context Learners
        88698, -- Bayesian Neural Scaling Law Extrapolation with Prior-Data Fitted Network
        88817, -- Zero-shot Meta-learning for Tabular Prediction Tasks with Adversarially
        89071, -- TabPFN Unleashed: A Scalable and Effective Solution to Tabular Classific
        91241, -- Mixture of In-Context Prompters for Tabular PFNs
        92615, -- Efficient Credal Prediction through Decalibration
        93254, -- Foundation Models for Causal Inference via Prior-Data Fitted Networks
        93503, -- GIT-BO: High-Dimensional Bayesian Optimization with Tabular Foundation M
        93696, -- Efficient Autoregressive Inference for Transformer Probabilistic Models
        95140, -- Causal Longitudinal Prior-Fitted Networks for Counterfactual Outcome Pre
        98787, -- A Causal DAG Prior for Synthetic Time-Series Classification Datasets
        99379, -- pTNAS: Progressive Neural Architecture Search for Tabular Data
        99467, -- Mitigating Label Shift in Tabular In-Context Learning via Test-Time Post
        99685, -- LimiX-2M: Mitigating Low-Rank Collapse and Attention Bottlenecks in Tabu
        100667, -- Transformers Can Learn Posterior Predictive Distributions In-Context
        101115, -- GraphPFN: A Prior-Data Fitted Graph Foundation Model
        101312, -- Unveiling the Role of Data Uncertainty in Tabular Deep Learning
        102139, -- Multi-Task Bayesian In-Context Learning
        102384, -- TabSwift: An Efficient Tabular Foundation Model with Row-Wise Attention
        108248, -- Meta-Black-Box Optimization with Bi-Space Landscape Analysis and Dual-Co
        121981, -- LimiX-2: A Contextual Mechanism Network Towards General Structured-Data
        122766, -- Adapting prior-data fitted networks for tabular anomaly detection
        122776 -- Closing the Context Gap: Activation Alignment for Tabular In-Context Lea
  );

DELETE FROM paper_method_exclusions x
USING tabpfn_linked_papers l
WHERE x.paper_id = l.paper_id AND x.method_id = l.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM tabpfn_linked_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'reference' FROM tabpfn_linked_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- The other 115 local citers cite the source in passing; exclude them so the
-- hourly reference backfill does not re-link them.
CREATE TEMP TABLE tabpfn_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'tabpfn'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        11671, 11872, 12338, 12424, 12460, 14620, 15212, 15259, 15404, 17395, 17745, 18363,
        18671, 21456, 21783, 22981, 23539, 23637, 26893, 27811, 27990, 28348, 28392, 29667,
        30546, 31005, 33812, 34111, 34166, 34469, 35759, 35997, 37829, 37878, 37988, 38779,
        39078, 39466, 40939, 43653, 44772, 44780, 46336, 48551, 48795, 49061, 49173, 49576,
        49892, 51619, 52689, 54068, 57141, 59162, 60883, 60939, 61299, 61329, 64385, 64807,
        65676, 66852, 68643, 70246, 72854, 76296, 79259, 82857, 82932, 83109, 83113, 85690,
        85875, 86207, 88976, 89074, 89338, 89704, 89925, 92524, 92610, 92842, 92854, 93301,
        93599, 93773, 98173, 99637, 100035, 100176, 100193, 100483, 100516, 100669, 100891, 101161,
        101182, 101462, 101683, 101965, 102061, 102093, 102202, 102476, 102510, 105991, 106143, 106357,
        109259, 114009, 122268, 122277, 122312, 122739, 123354
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'tabpfn citation review 2026-10-16: cites the source without naming the method in title or abstract'
FROM tabpfn_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING tabpfn_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING tabpfn_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
