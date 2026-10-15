-- Echo state networks were introduced in Jaeger's 2001 GMD technical report,
-- which has no local paper row, so the source is the report itself and papers are
-- linked from a reviewed set.

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
    'echo-state-network',
    'Echo State Network',
    'Echo State Network (ESN)',
    'An echo state network (ESN) is a recurrent neural network in which only the output layer is trained. A large, sparsely and randomly connected recurrent layer, the reservoir, is generated once and kept fixed; it is scaled, typically to a spectral radius below one, so that it has the echo state property, meaning its state depends on the recent input history and forgets the initial condition. The input drives the reservoir, and a linear readout from the reservoir states to the target is fit by linear or ridge regression, which avoids backpropagation through time and makes training fast and stable. ESNs excel at predicting chaotic time series, such as the Mackey-Glass system. Introduced by Jaeger in 2001 and developed concurrently with liquid state machines, ESNs founded the field of reservoir computing, which also includes physical and photonic reservoirs. They are a lightweight alternative to gradient-trained [RNNs](/methods/rnn) such as the [LSTM](/methods/lstm).',
    'echo state network',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2001,
    NULL,
    'https://www.ai.rug.nl/minds/uploads/EchoStatesTechRep.pdf',
    'The "echo state" approach to analysing and training recurrent neural networks (Jaeger, 2001)',
    'https://github.com/reservoirpy/reservoirpy',
    NULL,
    NULL
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

-- Curated 2026-10-15 from every title/abstract mention of "echo state network": each paper below builds on or uses echo state networks.
CREATE TEMP TABLE echo_state_network_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'echo-state-network'
  AND p.id IN (
        52580, -- Deep Residual Echo State Networks: exploring residual orthogonal conne
        60321, -- Body-Reservoir Governance in Repeated Games: Embodied Decision-Making,
        61763, -- ParalESN: Enabling parallel information processing in Reservoir Comput
        80945, -- Automatic-differentiated Physics-Informed Echo State Network (API-ESN)
        81135 -- Reservoir Memory Machines as Neural Computers
  );

DELETE FROM paper_method_exclusions x
USING echo_state_network_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM echo_state_network_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM echo_state_network_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: echo state networks appear only as a baseline or in passing.
CREATE TEMP TABLE echo_state_network_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'echo-state-network'
  AND p.id IN (
        71231, -- Adaptive Nonlinear Vector Autoregression: Robust Forecasting for Noisy
        72564 -- Quantum Reservoir Computing for Corrosion Prediction in Aerospace: A H
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'Echo state network curation 2026-10-15: mentions echo state networks without using them'
FROM echo_state_network_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING echo_state_network_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING echo_state_network_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
