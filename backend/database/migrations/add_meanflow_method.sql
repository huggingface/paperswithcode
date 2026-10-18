-- Add MeanFlow, introduced in arXiv 2505.13447.
-- Added 2026-10-18 from a scan of methods named by many recent papers but
-- missing from the catalog. The source paper gets the source evidence row (Introduced banner).

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
    'meanflow',
    'MeanFlow',
    'Mean Flows (MeanFlow)',
    'MeanFlow is a framework for one-step generative modeling that trains a network to predict the average velocity of a flow over a time interval, rather than the instantaneous velocity modeled by [flow matching](/methods/flow-matching). The average velocity u(z, r, t) is defined as the displacement between times r and t divided by the interval length. The authors derive an identity linking it to the instantaneous velocity and use this identity, computed with a Jacobian-vector product, as the training target. Sampling then needs a single network evaluation that jumps directly from noise to data. MeanFlow is trained from scratch and needs no pre-training, distillation or curriculum, unlike most [consistency models](/methods/consistency-models). It supports [classifier-free guidance](/methods/classifier-free-guidance) folded into the target field at no extra sampling cost. On ImageNet 256×256 it reached an FID of 3.43 with one function evaluation (1-NFE), well ahead of previous one-step diffusion and flow models. MeanFlow has become a common baseline for one-step image, audio and policy generation, with follow-ups such as Improved Mean Flows and pixel-space MeanFlow.',
    'MeanFlow, mean flow, mean flows',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2505.13447'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Mean Flows for One-step Generative Modeling',
    'https://github.com/Gsunshine/meanflow',
    NULL,
    '[Mean Flows for One-step Generative Modeling](/paper/2505.13447)'
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
SELECT source_paper_id, id FROM methods
WHERE slug = 'meanflow' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'meanflow' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 214 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE meanflow_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'meanflow'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        38110, 41462, 44073, 45230, 45765, 49162, 51224, 51807, 52653, 52654, 52655, 52878,
        53024, 53041, 53204, 53214, 53384, 53536, 53618, 53993, 54342, 54389, 54419, 54428,
        54497, 54543, 54600, 54772, 54774, 54794, 54867, 54895, 55032, 55178, 55330, 55666,
        55671, 55677, 55714, 55978, 55983, 56064, 56306, 56360, 56365, 56575, 56777, 56856,
        56885, 57205, 57230, 57311, 57460, 57537, 57818, 58458, 58460, 58556, 58909, 59036,
        59163, 59427, 59497, 59500, 59558, 59993, 60081, 60654, 61230, 61285, 62450, 63628,
        64171, 64263, 64267, 64290, 64433, 64578, 65925, 66470, 66686, 66929, 67319, 67395,
        67417, 67431, 67454, 67468, 67673, 68471, 69462, 70222, 70625, 71543, 72095, 72756,
        72926, 74506, 77222, 82925, 82967, 82971, 82992, 83110, 83302, 83560, 83756, 83775,
        83842, 84063, 84203, 84627, 84700, 84744, 84939, 85004, 85063, 85505, 85843, 92535,
        93336, 93433, 93633, 93636, 93877, 94079, 94236, 94364, 94452, 94486, 94661, 94739,
        94883, 95056, 95284, 97596, 98892, 99083, 99107, 99305, 99427, 99429, 99483, 99596,
        99648, 99713, 99765, 99987, 99993, 100024, 100040, 100042, 100317, 100675, 100840, 100945,
        100967, 101124, 101282, 101580, 101595, 101627, 101749, 101756, 102026, 102049, 102369, 102585,
        102647, 102718, 102727, 104019, 104392, 104556, 104753, 104813, 105847, 105949, 106425, 106481,
        106933, 107063, 108258, 109769, 109811, 114018, 114034, 117957, 118072, 118203, 118374, 118443,
        118468, 118494, 118501, 118509, 118516, 118531, 118607, 118609, 118687, 119221, 122289, 122290,
        122337, 122549, 122717, 122747, 122828, 122854, 122914, 123123, 123463, 123515
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'meanflow citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM meanflow_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING meanflow_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 51 local citers name the method in title or abstract.
CREATE TEMP TABLE meanflow_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'meanflow'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        53619, 53798, 54458, 55594, 56560, 57577, 59390, 61032, 61171, 61229, 61895, 63600,
        64247, 64935, 65729, 66712, 66746, 67469, 68205, 69249, 69896, 69996, 70863, 71135,
        84168, 84230, 84410, 93722, 93785, 94040, 94330, 94824, 97958, 98692, 98757, 98812,
        99210, 99217, 99499, 99618, 100551, 100609, 101685, 101873, 104043, 107255, 107735, 113932,
        119252, 122849, 123452
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM meanflow_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM meanflow_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 59 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE meanflow_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'meanflow'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        53619, 53798, 54458, 55594, 56560, 57577, 58913, 59390, 59852, 61032, 61171, 61229,
        61895, 63600, 64247, 64935, 65729, 66712, 66746, 67469, 68205, 69249, 69896, 69996,
        70863, 71135, 84168, 84230, 84410, 86934, 93722, 93785, 94330, 94824, 97958, 98692,
        98757, 98812, 99210, 99217, 99499, 100551, 100609, 101685, 101873, 104043, 107255, 107735,
        113932, 117416, 118549, 119252, 121241, 121360, 121418, 121758, 122849, 123182, 123452
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM meanflow_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM meanflow_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
