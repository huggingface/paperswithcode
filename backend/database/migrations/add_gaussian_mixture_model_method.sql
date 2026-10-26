-- Add Gaussian Mixture Model (no introducing paper in the catalog; external reference).
-- Added 2026-10-22 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url, image_url, image_credit
)
VALUES (
    'gaussian-mixture-model',
    'Gaussian Mixture Model',
    'Gaussian Mixture Model (GMM)',
    'A Gaussian Mixture Model (GMM) represents a probability density as a weighted sum of Gaussian components, each with its own mean and covariance. Fitting is usually done with the expectation-maximization algorithm, which alternates between soft-assigning points to components and re-estimating the parameters, and it can be read as a soft version of [k-means clustering](/methods/k-means-clustering). GMMs are used for density estimation, clustering, anomaly detection and as the classic acoustic model in speech recognition, and mixtures of Gaussians also appear as priors and output distributions inside deep models.',
    'gaussian mixture model, mixture of gaussians, gaussian mixture density',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1007/978-0-387-73003-5_196',
    'Gaussian Mixture Models (Reynolds, Encyclopedia of Biometrics)',
    NULL,
    NULL,
    'Illustration by Papers with Code'
)
ON CONFLICT (slug) DO UPDATE SET
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

-- 152 papers match the method keywords (same matcher as the daily keyword backfill).
CREATE TEMP TABLE gaussian_mixture_model_keyword ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gaussian-mixture-model'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        206, 565, 853, 1069, 1167, 2157, 2687, 3199, 4441, 4488, 5528, 5544,
        5934, 6992, 10171, 10214, 10472, 11675, 11713, 13189, 13456, 13562, 13748, 14051,
        14220, 15112, 15412, 15458, 16380, 16431, 16566, 18010, 19068, 20812, 21114, 21221,
        21451, 21991, 23082, 24226, 27288, 31420, 32108, 36263, 36307, 36647, 40397, 40668,
        40971, 41067, 43653, 44986, 45446, 48262, 48285, 49748, 56542, 58113, 61665, 67205,
        67758, 67958, 68574, 71253, 72079, 72224, 73233, 73861, 75057, 76379, 76654, 76863,
        77106, 77110, 77581, 77840, 78075, 78968, 79353, 79410, 79876, 80385, 81280, 81490,
        81932, 82368, 82645, 85450, 86138, 86475, 86543, 86741, 87179, 87322, 87579, 88275,
        89782, 91074, 91682, 91781, 92397, 92590, 92878, 93091, 93912, 94395, 95240, 95479,
        95533, 95976, 96237, 96337, 96649, 96738, 97110, 97587, 98260, 99410, 99702, 100194,
        100795, 101449, 101802, 101822, 102923, 105075, 105754, 107284, 111846, 112403, 112714, 112876,
        113203, 113377, 113498, 113527, 114042, 114458, 114972, 115889, 116668, 116698, 117072, 117933,
        120010, 120201, 120342, 120705, 121307, 121346, 121437, 122665
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gaussian_mixture_model_keyword x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM gaussian_mixture_model_keyword x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
