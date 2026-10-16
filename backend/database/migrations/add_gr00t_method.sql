-- Add GR00T N1, introduced in arXiv 2503.14734. Production chat users looked it
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
    'gr00t',
    'GR00T N1',
    'NVIDIA Isaac GR00T N1',
    'GR00T N1 is NVIDIA''s open foundation model for generalist humanoid robots, a [vision-language-action model](/methods/vla) with a dual-system design. System 2, an Eagle-2 vision-language model, interprets images and language instructions, and System 1, a [diffusion transformer](/methods/diffusion-transformer-dit) trained with [flow matching](/methods/flow-matching), cross-attends to the VLM tokens and generates closed-loop motor actions at high frequency. Embodiment-specific state and action encoders let one model control single-arm, bimanual and humanoid robots. Training follows a data pyramid of real robot trajectories, human videos and synthetic data, including neural trajectories from video generation models; latent actions supply labels for unlabeled video. The 2B-parameter model outperformed imitation-learning baselines in simulation and on the Fourier GR-1 humanoid, and was followed by GR00T N1.5 and N1.6.',
    'GR00T, GR00T N1, GR00T-N1, GR00T N1.5, GR00T N1.6, Isaac GR00T',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2503.14734'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'GR00T N1: An Open Foundation Model for Generalist Humanoid Robots',
    'https://github.com/NVIDIA/Isaac-GR00T',
    NULL,
    '[GR00T N1: An Open Foundation Model for Generalist Humanoid Robots](/paper/2503.14734)'
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
WHERE slug = 'gr00t'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'gr00t'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Citation review 2026-10-16: 22 of the 596 local papers that Semantic Scholar
-- lists as citing the source name GR00T N1 in their title or abstract.
CREATE TEMP TABLE gr00t_linked_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gr00t'
  AND p.is_latest_version
  AND p.id IN (
        48989, -- DreamGen: Unlocking Generalization in Robot Learning through Video World
        52309, -- MolmoAct: Action Reasoning Models that can Reason in Space
        53616, -- VLA-0: Building State-of-the-Art VLAs with Zero Modification
        55010, -- Dream-VL & Dream-VLA: Open Vision-Language and Vision-Language-Action Mo
        56977, -- VP-VLA: Visual Prompting as an Interface for Vision-Language-Action Mode
        57940, -- CorridorVLA: Explicit Spatial Constraints for Generative Action Heads vi
        59579, -- World2Act: Latent Action Post-Training via Skill-Compositional World Mod
        59664, -- OmniGuide: Universal Guidance Fields for Enhancing Generalist Robot Poli
        62980, -- InternVLA-A1: Unifying Understanding, Generation and Action for Robotic
        63428, -- REALM: A Real-to-Sim Validated Benchmark for Generalization in Robotic M
        67218, -- HAMLET: Switch your Vision-Language-Action Model into a History-Aware Po
        84872, -- SaPaVe: Towards Active Perception and Manipulation in Vision-Language Ac
        98391, -- APT: Action Expert Pretraining Improves Instruction Generalization of Vi
        101353, -- XR-1: Towards Versatile Vision-Language-Action Models via Learning Unifi
        105918, -- πR^2: Reactive Real-time Flow Policies
        113732, -- Beyond Data Scaling: Representation-Centric Continued Pre-training for V
        113760, -- Act with Intent: Distilling Behavior Intent for Vision-Language-Action M
        119621, -- Understanding the Impact of Geometric Foundation Models on Vision-Langua
        122327, -- Recursive Harness Distillation across Agents for Robot Manipulation
        122518, -- The Low-Rank Structure of VLA Reinforcement Learning
        122849, -- Kinematic MeanFlow: One-Step Action Generation Policy for Robotic Founda
        123438 -- HumanoidToolBench: Benchmarking Humanoid Tool Use from Selection to Mobi
  );

DELETE FROM paper_method_exclusions x
USING gr00t_linked_papers l
WHERE x.paper_id = l.paper_id AND x.method_id = l.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gr00t_linked_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'reference' FROM gr00t_linked_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- The other 574 local citers cite the source in passing; exclude them so the
-- hourly reference backfill does not re-link them.
CREATE TEMP TABLE gr00t_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gr00t'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        23225, 27163, 31553, 40933, 43889, 45188, 45631, 46077, 47262, 48054, 48340, 48470,
        48558, 48619, 48736, 48935, 49944, 49983, 50001, 50202, 50406, 50419, 50484, 50769,
        50824, 50956, 50967, 51123, 51276, 51297, 51338, 51437, 51532, 51610, 51698, 51768,
        52004, 52007, 52040, 52047, 52130, 52270, 52281, 52315, 52553, 52554, 52577, 52628,
        52665, 52702, 52738, 52800, 52861, 52878, 52931, 53099, 53306, 53332, 53406, 53451,
        53472, 53476, 53502, 53552, 53562, 53569, 53607, 53749, 53840, 53841, 53875, 53989,
        53999, 54001, 54016, 54033, 54039, 54276, 54284, 54299, 54454, 54455, 54495, 54502,
        54508, 54517, 54689, 54727, 54744, 54762, 54901, 54907, 55021, 55026, 55050, 55114,
        55115, 55180, 55291, 55356, 55360, 55384, 55418, 55445, 55459, 55471, 55529, 55569,
        55573, 55623, 55762, 55860, 55962, 55967, 56050, 56055, 56095, 56102, 56172, 56188,
        56241, 56250, 56254, 56274, 56439, 56517, 56537, 56757, 56759, 56800, 56828, 56833,
        56856, 56935, 57160, 57259, 57349, 57463, 57525, 57530, 57575, 57679, 57695, 57725,
        57795, 57994, 58018, 58035, 58043, 58086, 58124, 58490, 58695, 58700, 58762, 58799,
        58820, 58870, 58910, 59013, 59194, 59250, 59395, 59479, 59500, 59541, 59578, 59648,
        59657, 59703, 59890, 60226, 60283, 60289, 60314, 60363, 60413, 60463, 60468, 60520,
        60527, 60600, 60672, 60701, 60743, 60748, 60756, 60768, 60796, 60830, 60851, 60857,
        60871, 60958, 61090, 61242, 61248, 61352, 61405, 61550, 61628, 61981, 62140, 62189,
        62416, 62666, 63004, 63191, 63275, 63277, 63279, 63295, 63305, 63402, 63549, 63598,
        63639, 63686, 63712, 63717, 63802, 63931, 63946, 63976, 64057, 64071, 64112, 64193,
        64263, 64266, 64325, 64430, 64455, 64464, 64633, 64724, 64729, 64771, 64813, 65192,
        65199, 65295, 65570, 65573, 65597, 65607, 65619, 65703, 65902, 65954, 66110, 66144,
        66200, 66229, 66405, 66439, 66551, 66625, 66630, 66758, 66901, 66975, 67000, 67128,
        67136, 67216, 67278, 67365, 67470, 67621, 67676, 67679, 67858, 67921, 67946, 68218,
        68270, 68361, 68378, 68385, 68407, 68444, 68743, 68838, 69035, 69195, 69514, 69792,
        69813, 70393, 70840, 71158, 71367, 71527, 71577, 71740, 71743, 71797, 71944, 72150,
        72167, 72298, 72393, 72885, 72887, 72955, 73010, 73088, 73169, 73198, 73671, 74520,
        82912, 83118, 83183, 83279, 83283, 83377, 83411, 83808, 83824, 84012, 84109, 84149,
        84185, 84191, 84228, 84235, 84265, 84279, 84450, 84739, 84798, 84851, 84924, 85182,
        85233, 85270, 85337, 85511, 85524, 85666, 85993, 86004, 86680, 87253, 87521, 89349,
        92474, 92503, 92528, 92781, 92872, 93639, 93764, 93939, 94016, 94665, 94822, 94882,
        94915, 95029, 95075, 95095, 95098, 95301, 95574, 95741, 95789, 95849, 95861, 95984,
        96025, 96043, 96175, 96192, 96497, 96647, 96661, 96748, 96760, 96781, 96806, 96979,
        97170, 97242, 97306, 97348, 97509, 97581, 97591, 97657, 97719, 97737, 97890, 97952,
        98021, 98102, 98159, 98194, 98195, 98244, 98288, 98320, 98363, 98378, 98381, 98388,
        98389, 98415, 98421, 98428, 98449, 98463, 98541, 98546, 98559, 98691, 98698, 98703,
        98793, 98815, 98916, 98918, 98922, 98935, 98938, 98956, 99029, 99039, 99040, 99049,
        99113, 99131, 99366, 99377, 99412, 99437, 99524, 99889, 99964, 100200, 100221, 100273,
        100486, 100502, 100612, 100726, 100988, 101129, 101149, 101163, 101438, 101572, 101721, 101749,
        102138, 102424, 102426, 102562, 102571, 102573, 102610, 102631, 102641, 102646, 102681, 102831,
        103593, 103830, 103866, 103951, 104012, 104307, 104378, 104389, 104390, 104479, 104574, 104727,
        104735, 105845, 105849, 105874, 105997, 106017, 106030, 106238, 106481, 106994, 108080, 108632,
        108735, 108781, 108808, 108923, 108927, 109041, 109042, 109045, 109046, 109049, 109115, 109338,
        109503, 109579, 109636, 109695, 109727, 109763, 109809, 109841, 113731, 113857, 113871, 113880,
        114012, 114018, 114037, 114050, 114070, 114185, 114209, 114214, 118005, 118017, 118021, 118221,
        119295, 119380, 119426, 119451, 119620, 119642, 119663, 119698, 121459, 121643, 121875, 122101,
        122107, 122110, 122151, 122186, 122240, 122318, 122340, 122411, 122596, 122667, 122674, 122689,
        122705, 122717, 122719, 122764, 122797, 122806, 122816, 122835, 122870, 122871, 122896, 122914,
        122920, 122923, 122950, 123147, 123288, 123398, 123412, 123460, 123482, 123578
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'gr00t citation review 2026-10-16: cites the source without naming the method in title or abstract'
FROM gr00t_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING gr00t_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING gr00t_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
