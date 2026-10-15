-- Isolation Forest was introduced by Liu, Ting & Zhou (ICDM 2008), which has no
-- local paper row, so the source is the paper's DOI and papers are linked from a
-- reviewed set.

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
    'isolation-forest',
    'Isolation Forest',
    'Isolation Forest (iForest)',
    'Isolation Forest (iForest) is an unsupervised anomaly detection algorithm that isolates anomalies instead of modeling normal data. It builds an ensemble of isolation trees, each grown on a small random subsample by repeatedly choosing a random feature and a random split value between that feature''s minimum and maximum. Because anomalies are few and different, they are separated from the rest of the data after fewer random splits, so they have shorter paths from the root. The anomaly score is the average path length across trees, normalized by the expected path length of an unsuccessful search in a binary search tree. Isolation Forest needs no distance or density computation, runs in linear time with low memory, and handles high-dimensional data, which made it a standard baseline for tabular, fraud and industrial anomaly detection. It is related to [random forests](/methods/random-forest), which use randomized trees for supervised prediction.',
    'isolation forest, iForest',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2008,
    NULL,
    'https://doi.org/10.1109/ICDM.2008.17',
    'Isolation Forest (Liu, Ting & Zhou, ICDM 2008)',
    'https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/ensemble/_iforest.py',
    NULL,
    '[Isolating an Anomalous Point](https://commons.wikimedia.org/wiki/File:Isolating_an_Anomalous_Point.png) by Sal Borrelli, CC BY-SA 4.0'
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

-- Curated 2026-10-15 from every title/abstract mention of "isolation forest": each paper below uses, benchmarks or analyzes Isolation Forest.
CREATE TEMP TABLE isolation_forest_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'isolation-forest'
  AND p.id IN (
        57803, -- Sample Selection Using Multi-Task Autoencoders in Federated Learning w
        63673, -- Pattern Recognition of Aluminium Arbitrage in Global Trade Data
        64502, -- Pattern Recognition of Ozone-Depleting Substance Exports in Global Tra
        65007, -- NegBLEURT Forest: Leveraging Inconsistencies for Detecting Jailbreak A
        71073, -- Text-ADBench: Text Anomaly Detection Benchmark based on LLMs Embedding
        78523, -- Astronomaly at scale: searching for anomalies amongst 4 million galaxi
        100126 -- Theoretical Investigation on Inductive Bias of Isolation Forest
  );

DELETE FROM paper_method_exclusions x
USING isolation_forest_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM isolation_forest_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM isolation_forest_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: Isolation Forest appears only as a comparison baseline.
CREATE TEMP TABLE isolation_forest_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'isolation-forest'
  AND p.id IN (
        3665, -- Dimensionless Anomaly Detection on Multivariate Streams with Variance
        6070, -- From Unsupervised to Semi-supervised Anomaly Detection Methods for HRR
        42637, -- Planing It by Ear: Convolutional Neural Networks for Acoustic Anomaly
        107045 -- IDK-S: Incremental Distributional Kernel for Streaming Anomaly Detecti
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'Isolation Forest curation 2026-10-15: compares against Isolation Forest without using it'
FROM isolation_forest_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING isolation_forest_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING isolation_forest_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
