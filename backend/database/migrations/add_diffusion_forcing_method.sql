-- Add Diffusion Forcing, introduced in arXiv 2407.01392.
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
    'diffusion-forcing',
    'Diffusion Forcing',
    'Diffusion Forcing',
    'Diffusion Forcing is a training paradigm for sequence generative models in which a [diffusion](/methods/diffusion) model denoises a set of tokens with independent per-token noise levels. Applied to a causal next-token model (an RNN or masked Transformer), it learns to generate one or several future tokens without fully diffusing past ones, treating noise as partial masking. This unifies the strengths of next-token prediction trained with [teacher forcing](/methods/teacher-forcing), such as variable-length generation, with those of full-sequence diffusion, such as guiding sampling toward desirable trajectories. The authors show it can roll out continuous token sequences such as video past the training horizon where baselines diverge, enables new sampling and guidance schemes (e.g. Monte Carlo Guidance) that improve decision-making and planning, and provably optimizes a variational lower bound on the likelihoods of all token subsequences. It underlies autoregressive video diffusion and world models, including [Self Forcing](/methods/self-forcing).',
    'diffusion forcing',
    (
        SELECT id
        FROM areas
        WHERE name = 'Video'
        LIMIT 1
    ),
    2024,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2407.01392'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Diffusion Forcing: Next-token Prediction Meets Full-Sequence Diffusion',
    'https://github.com/buoyancy99/diffusion-forcing',
    NULL,
    '[Diffusion Forcing: Next-token Prediction Meets Full-Sequence Diffusion](/paper/2407.01392)'
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
WHERE slug = 'diffusion-forcing' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'diffusion-forcing' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 439 local citers cite the source without naming the method in
-- title or abstract; exclude them so the hourly reference backfill does not
-- link them.
CREATE TEMP TABLE diffusion_forcing_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'diffusion-forcing'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        26335, 32242, 32499, 36268, 36459, 38083, 38263, 38530, 38910, 39004, 40221, 40422,
        40796, 41319, 41340, 42313, 42845, 43076, 43371, 43523, 43739, 43889, 43911, 44203,
        45765, 45790, 45981, 46061, 46077, 46097, 46334, 46345, 46429, 46553, 46673, 46675,
        46701, 46732, 46830, 47161, 47250, 47810, 47827, 48279, 48304, 48963, 49162, 49221,
        49827, 49990, 50134, 50179, 50353, 50363, 50487, 50639, 50817, 50856, 50920, 51317,
        51397, 51438, 51476, 51532, 51594, 51694, 51824, 51947, 52023, 52063, 52220, 52369,
        52378, 52411, 52571, 52939, 52953, 53003, 53022, 53059, 53134, 53267, 53440, 53483,
        53509, 53513, 53549, 53712, 53758, 53784, 53810, 53839, 53850, 53876, 53990, 53999,
        54030, 54159, 54197, 54359, 54362, 54392, 54443, 54447, 54490, 54514, 54543, 54560,
        54563, 54566, 54567, 54576, 54589, 54612, 54630, 54689, 54700, 54735, 54743, 54755,
        54776, 54784, 54794, 54800, 54847, 54888, 54928, 54946, 54974, 54984, 54987, 55005,
        55009, 55029, 55086, 55113, 55168, 55172, 55301, 55304, 55330, 55458, 55473, 55512,
        55549, 55581, 55623, 55671, 55728, 55763, 55790, 55809, 55838, 55842, 55912, 55923,
        55980, 56139, 56172, 56228, 56302, 56360, 56390, 56421, 56462, 56471, 56492, 56509,
        56544, 56545, 56599, 56728, 56777, 56823, 56856, 57049, 57051, 57083, 57204, 57215,
        57306, 57322, 57349, 57375, 57385, 57559, 57639, 57772, 57781, 57861, 58008, 58015,
        58576, 58899, 59194, 59235, 59268, 59386, 59468, 59527, 59532, 59581, 59666, 59768,
        59990, 59993, 60184, 60221, 60499, 60655, 60680, 60767, 60815, 61641, 61794, 61918,
        62129, 62229, 62236, 62386, 62597, 63288, 63329, 63468, 63508, 63598, 63686, 63752,
        63793, 63801, 63969, 63973, 64254, 64390, 64490, 64619, 64958, 65225, 65486, 65945,
        66594, 66687, 66715, 66733, 66929, 67031, 67033, 67194, 67468, 67534, 67728, 68625,
        68994, 69046, 69138, 69348, 69819, 69891, 70180, 70206, 70239, 71934, 72311, 72408,
        73510, 82829, 82839, 83164, 83189, 83281, 83366, 83506, 83589, 83616, 83831, 83842,
        84140, 84310, 84323, 84386, 84510, 84530, 84609, 84782, 85650, 85665, 85869, 86002,
        86020, 86244, 86830, 86967, 87192, 87507, 87509, 88185, 88436, 88658, 88776, 89099,
        89982, 90237, 91456, 92169, 92538, 92548, 92705, 92726, 92731, 92833, 93158, 93423,
        93939, 94198, 94393, 95763, 96025, 96581, 98008, 98130, 98136, 98159, 98160, 98242,
        98296, 98331, 98408, 98423, 98432, 98803, 98812, 98854, 98954, 98958, 99001, 100435,
        101167, 101754, 101799, 101988, 102565, 102586, 102613, 102633, 102710, 102711, 104434, 104449,
        104485, 104512, 104738, 104798, 104811, 105919, 105937, 105993, 106025, 106069, 106310, 106985,
        107279, 108373, 108643, 108846, 108870, 108958, 108964, 109129, 109142, 109143, 109183, 109278,
        109523, 109580, 109649, 109664, 109769, 109776, 109841, 109842, 112241, 113746, 113845, 113884,
        114029, 114106, 114192, 114212, 117969, 118032, 118509, 118649, 119198, 119207, 119220, 119228,
        119280, 119299, 119365, 119410, 119418, 119426, 119430, 119438, 119469, 121900, 121960, 121994,
        122104, 122201, 122341, 122352, 122411, 122455, 122595, 122618, 122631, 122672, 122740, 122770,
        122844, 122853, 122874, 122911, 122936, 122982, 123018, 123274, 123400, 123428, 123486, 123496,
        123497, 123532, 123540, 123550, 123560, 123589, 123598
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'diffusion-forcing citation review 2026-10-18: cites the source without naming the method in title or abstract'
FROM diffusion_forcing_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING diffusion_forcing_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- 19 local citers name the method in title or abstract.
CREATE TEMP TABLE diffusion_forcing_cited_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'diffusion-forcing'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        37016, 43953, 47854, 51852, 52341, 52982, 53626, 53950, 55071, 55329, 56341, 62247,
        64176, 87799, 93720, 96259, 99566, 105918, 108670
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM diffusion_forcing_cited_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM diffusion_forcing_cited_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- 21 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE diffusion_forcing_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'diffusion-forcing'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        37016, 43953, 47854, 52982, 53626, 53950, 55071, 55329, 56341, 60135, 62247, 64176,
        87799, 93720, 96259, 99009, 99566, 105918, 108670, 119333, 121044
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM diffusion_forcing_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM diffusion_forcing_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
