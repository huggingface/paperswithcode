-- Add Test-Time Training method, introduced in arXiv 1909.13231. The source paper
-- gets the source evidence row (Introduced banner); citers are linked by
-- link_papers_by_source_citations.py and the hourly reference backfill.

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
    'test-time-training',
    'Test-Time Training',
    'Test-Time Training (TTT)',
    'Test-Time Training (TTT) improves robustness to distribution shift by updating a model on each test input before predicting. The network shares a feature extractor between the main task head and a self-supervised auxiliary head (rotation prediction in the original paper). After standard joint training, each unlabeled test sample, or a stream of test samples in the online variant, is used to take gradient steps on the self-supervised loss, adapting the shared features to the new distribution; the main head then makes the prediction. Without any labels from the target distribution, TTT improved accuracy on corrupted image benchmarks such as CIFAR-10-C and ImageNet-C. The idea underlies later test-time adaptation methods, TTT with masked autoencoders, and TTT layers that use test-time gradient updates as a sequence-modeling mechanism.',
    'test-time training, test time training',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2019,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1909.13231'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Test-Time Training with Self-Supervision for Generalization under Distribution Shifts',
    'https://github.com/yueatsprograms/ttt_cifar_release',
    NULL,
    '[Test-Time Training with Self-Supervision for Generalization under Distribution Shifts](/paper/1909.13231)'
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
WHERE slug = 'test-time-training'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'test-time-training'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 310 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention test-time training are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE test_time_training_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'test-time-training'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        3754, 3804, 3873, 3906, 4733, 5589, 6277, 6376, 7336, 7700, 7964, 8006,
        8370, 8391, 8420, 8582, 8805, 8855, 9311, 10076, 10299, 10641, 11568, 11658,
        11930, 12086, 12641, 12871, 13019, 13074, 13293, 13425, 13471, 13860, 13886, 14089,
        14294, 14934, 15935, 16470, 17041, 17138, 17560, 17735, 18692, 19012, 19150, 19511,
        19826, 19934, 20593, 20760, 20981, 22311, 22636, 25292, 25591, 25854, 27242, 28046,
        28710, 29973, 29974, 30056, 30070, 30748, 32033, 32444, 32447, 32724, 33013, 34077,
        34573, 35935, 36123, 37874, 39598, 40741, 40864, 41814, 42040, 42489, 43442, 45187,
        45903, 46181, 46428, 46882, 46913, 47404, 47495, 47517, 47844, 48663, 49049, 49723,
        51041, 53252, 53334, 53479, 53664, 54213, 54229, 54371, 55158, 55554, 55579, 55689,
        55838, 55984, 56164, 56403, 56616, 56952, 57498, 57597, 57712, 59055, 59237, 61074,
        62688, 62925, 63086, 63468, 63488, 64031, 64056, 64395, 64671, 65073, 65852, 66545,
        66740, 66763, 67448, 68795, 69047, 70261, 70710, 70820, 71058, 71624, 72218, 72490,
        72680, 72687, 73669, 74821, 75122, 76791, 77621, 80687, 81301, 82940, 83317, 84124,
        84438, 84746, 84855, 85008, 85139, 85144, 85155, 85385, 85580, 85773, 85841, 86354,
        86855, 87011, 87266, 87361, 87906, 87965, 88089, 88302, 88655, 88835, 89066, 89067,
        89068, 89356, 90508, 90738, 91007, 91088, 91505, 91943, 92148, 92320, 92689, 92981,
        93348, 93573, 94342, 94426, 94476, 94753, 99419, 99612, 101002, 101007, 102126, 102140,
        102210, 103162, 103738, 105661, 106079, 106485, 107250, 107402, 107411, 107549, 108642, 108737,
        108794, 109048, 110733, 110778, 112495, 112670, 112784, 113373, 113617, 113633, 115839, 116057,
        116152, 116283, 116691, 116735, 116837, 117010, 117023, 117703, 118131, 118148, 119636, 120980,
        121546, 122298, 122420, 123044, 123236
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'test-time-training citation review 2026-10-15: cites the source paper without using the method'
FROM test_time_training_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING test_time_training_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING test_time_training_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
