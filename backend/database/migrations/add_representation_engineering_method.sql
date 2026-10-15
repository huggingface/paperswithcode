-- Add Representation Engineering method, introduced in arXiv 2310.01405. The source paper
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
    'representation-engineering',
    'Representation Engineering',
    'Representation Engineering (RepE)',
    'Representation Engineering (RepE) is a top-down approach to AI transparency and control that treats population-level representations, rather than individual neurons or circuits, as the unit of analysis. For representation reading, Linear Artificial Tomography (LAT) presents a model with contrasting stimuli for a concept or function, such as honesty, collects hidden states, and extracts a reading vector, for example with [PCA](/methods/pca) on activation differences, which then serves as a linear probe. For representation control, these vectors are added to or subtracted from activations, or folded into the weights with low-rank representation adaptation, to steer behavior. The paper applied RepE to honesty, harmlessness, power-seeking, emotion and memorization, and improved TruthfulQA accuracy by steering toward honesty. It builds on activation-steering work such as [Activation Addition](/paper/2308.10248) and is related to [probing](/methods/probing).',
    'representation engineering, representation steering',
    (
        SELECT id
        FROM areas
        WHERE name = 'Language'
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2310.01405'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Representation Engineering: A Top-Down Approach to AI Transparency',
    'https://github.com/andyzoujm/representation-engineering',
    NULL,
    '[Representation Engineering: A Top-Down Approach to AI Transparency](/paper/2310.01405)'
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
WHERE slug = 'representation-engineering'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'representation-engineering'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed citers 2026-10-15: a sample of the 486 local papers citing the source showed most cite it only as related work or a baseline. Citers whose title or abstract does not mention representation engineering or steering are excluded so the hourly reference backfill does not re-link them.
CREATE TEMP TABLE representation_engineering_excluded_citers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'representation-engineering'
  AND p.id <> m.source_paper_id
  AND p.id IN (
        12379, 13062, 20053, 21460, 21985, 22419, 22816, 23054, 23197, 23267, 23577, 24380,
        24655, 24793, 24850, 25408, 26140, 26157, 26222, 26314, 26697, 26764, 27020, 27337,
        27709, 27855, 27989, 28002, 28094, 28116, 28219, 28446, 28504, 28560, 28593, 28634,
        28816, 28822, 28966, 29262, 29266, 29494, 29555, 29629, 29949, 30112, 30473, 30474,
        30504, 30811, 31009, 31170, 31538, 31547, 31963, 31968, 32100, 32115, 32244, 32245,
        32249, 32332, 32473, 32585, 32586, 32763, 33029, 33032, 33145, 33225, 33529, 33623,
        33750, 33791, 34355, 34503, 34548, 35007, 35051, 35109, 35311, 36133, 36287, 36431,
        36460, 37317, 37354, 37576, 37749, 37792, 37822, 37949, 38323, 38339, 38449, 38654,
        38728, 38807, 38898, 38940, 39331, 39388, 39522, 39845, 39901, 39968, 40102, 40256,
        40282, 40541, 40880, 41411, 42450, 43317, 43445, 43471, 43656, 43723, 43855, 43857,
        44004, 44034, 44096, 44109, 44171, 44189, 44317, 44327, 44603, 44828, 44885, 45438,
        45677, 46858, 46910, 47071, 47257, 47305, 47389, 47658, 47937, 48936, 49001, 49091,
        49100, 49111, 49373, 49424, 49652, 49807, 50240, 50474, 51125, 51248, 51672, 51915,
        51939, 52181, 52566, 52703, 53285, 53590, 53692, 54383, 54552, 54822, 55052, 55135,
        55366, 55553, 55779, 56169, 56321, 56374, 56401, 56426, 56626, 56723, 57444, 57524,
        57609, 57878, 58252, 58396, 58658, 59891, 60296, 60366, 60573, 60582, 60977, 61029,
        61114, 61576, 61755, 61864, 63463, 63510, 63782, 64005, 64083, 64351, 64609, 65256,
        66777, 67060, 67183, 68288, 68300, 68674, 69366, 70245, 70506, 70603, 70909, 70915,
        71115, 71634, 71739, 71763, 72036, 72163, 72489, 72521, 72527, 72835, 72859, 72899,
        73002, 73244, 73435, 73527, 74081, 74510, 74521, 74525, 75460, 75536, 76012, 76072,
        76183, 76814, 76827, 77312, 77732, 78252, 78267, 83246, 83381, 83384, 83408, 83813,
        85323, 85776, 85918, 86019, 86160, 86368, 86797, 87134, 87157, 87272, 87325, 87450,
        88598, 88666, 88755, 89153, 89305, 89323, 89604, 89702, 89724, 89863, 91080, 91152,
        91208, 91331, 91426, 91669, 91878, 92016, 92186, 92561, 92589, 92941, 93114, 93278,
        93295, 93343, 93487, 93573, 93615, 93619, 93649, 93655, 93688, 93705, 94111, 94136,
        94367, 94653, 94709, 95084, 98119, 98175, 98523, 98705, 98839, 98985, 99116, 99288,
        99335, 99948, 100028, 100035, 100162, 100165, 100210, 100229, 100426, 100820, 100860, 101297,
        101650, 101853, 102084, 102134, 102187, 102379, 102474, 102853, 102908, 103356, 103426, 103467,
        104475, 105964, 106103, 106109, 106111, 106282, 106283, 106327, 106400, 106601, 106689, 106860,
        106864, 106910, 107229, 108133, 108685, 108796, 109118, 109528, 109582, 109997, 110042, 110233,
        110275, 110481, 110634, 110783, 110979, 113753, 113865, 121964, 122126, 122209, 122471, 122600,
        122610, 122634, 122979
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'representation-engineering citation review 2026-10-15: cites the source paper without using the method'
FROM representation_engineering_excluded_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING representation_engineering_excluded_citers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING representation_engineering_excluded_citers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
