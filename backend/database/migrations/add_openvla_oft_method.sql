-- Add OpenVLA-OFT, introduced in arXiv 2502.19645. Production chat users looked it
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
    'openvla-oft',
    'OpenVLA-OFT',
    'OpenVLA with Optimized Fine-Tuning (OpenVLA-OFT)',
    'OpenVLA-OFT applies an Optimized Fine-Tuning (OFT) recipe to the OpenVLA [vision-language-action model](/methods/vla). Instead of decoding discretized action tokens one at a time, it uses parallel decoding with bidirectional attention to predict a whole chunk of continuous actions in a single forward pass, trained with a simple L1 regression objective. On the LIBERO simulation benchmark this raised OpenVLA''s average success rate across four task suites from 76.5% to 97.1% while increasing action generation throughput 26-fold. The OFT+ variant adds FiLM conditioning for stronger language grounding and runs high-frequency bimanual control on the ALOHA robot, where it outperformed [π0](/methods/pi0), RDT-1B and policies trained from scratch such as [Diffusion Policy](/methods/diffusion-policy).',
    'OpenVLA-OFT, OpenVLA OFT, OpenVLA-OFT+, Optimized Fine-Tuning recipe',
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
        WHERE arxiv_id = '2502.19645'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Fine-Tuning Vision-Language-Action Models: Optimizing Speed and Success',
    'https://github.com/moojink/openvla-oft',
    NULL,
    '[Fine-Tuning Vision-Language-Action Models: Optimizing Speed and Success](/paper/2502.19645)'
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
WHERE slug = 'openvla-oft'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'openvla-oft'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Citation review 2026-10-16: 14 of the 363 local papers that Semantic Scholar
-- lists as citing the source name OpenVLA-OFT in their title or abstract.
CREATE TEMP TABLE openvla_oft_linked_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'openvla-oft'
  AND p.is_latest_version
  AND p.id IN (
        49484, -- Interactive Post-Training for Vision-Language-Action Models
        50769, -- BitVLA: 1-bit Vision-Language-Action Models for Robotics Manipulation
        52746, -- SimpleVLA-RL: Scaling VLA Training via Reinforcement Learning
        53318, -- RLinf-VLA: A Unified and Efficient Framework for VLA+RL Training
        53616, -- VLA-0: Building State-of-the-Art VLAs with Zero Modification
        64571, -- MAPS: Preserving Vision-Language Representations via Module-Wise Proximi
        67136, -- FailSafe: Reasoning and Recovery from Failures in Vision-Language-Action
        93764, -- Action-aware Dynamic Pruning for Efficient Vision-Language-Action Manipu
        96748, -- ExpReS-VLA: Specializing Vision-Language-Action Models through Experienc
        99131, -- From Abstraction to Instantiation: Learning Behavioral Representation fo
        104523, -- Patch Policy: Efficient Embodied Control via Dense Visual Representation
        113871, -- Trust Your Instincts: Confidence-Driven Test-Time RL for Vision-Language
        119620, -- Restoring Linguistic Grounding in VLA Models via Train-Free Attention Re
        122983 -- CARE: Certifying Acceleration for Vision-Language-Action Inference
  );

DELETE FROM paper_method_exclusions x
USING openvla_oft_linked_papers l
WHERE x.paper_id = l.paper_id AND x.method_id = l.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM openvla_oft_linked_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'reference' FROM openvla_oft_linked_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- The other 349 local citers cite the source in passing; exclude them so the
-- hourly reference backfill does not re-link them.
CREATE TEMP TABLE openvla_oft_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'openvla-oft'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        31553, 43638, 43889, 44230, 45214, 45402, 46479, 46653, 48196, 48507, 48650, 49773,
        49944, 50001, 50704, 50956, 50969, 51102, 51338, 51355, 51437, 51525, 51592, 51718,
        52004, 52047, 52130, 52281, 52309, 52315, 52553, 52569, 52577, 52665, 52738, 52800,
        52861, 52878, 52887, 53099, 53332, 53406, 53451, 53502, 53552, 53562, 53569, 53578,
        53607, 53613, 53709, 53874, 53891, 53989, 54001, 54033, 54055, 54129, 54284, 54299,
        54313, 54502, 54508, 54517, 54663, 54689, 54768, 54814, 54907, 55026, 55276, 55356,
        55384, 55445, 55459, 55471, 55573, 55623, 55900, 55962, 56055, 56095, 56096, 56102,
        56241, 56254, 56439, 56517, 56684, 56757, 56828, 56854, 56856, 56935, 56977, 57160,
        57236, 57259, 57396, 57525, 57679, 57695, 57725, 57727, 57940, 58086, 58138, 58263,
        58479, 58490, 58695, 58762, 58820, 59023, 59395, 59579, 59657, 59725, 59834, 59984,
        60223, 60463, 60468, 60527, 60655, 60768, 60851, 60857, 60871, 61090, 61093, 61166,
        61242, 61340, 61383, 61409, 61550, 61594, 61606, 62029, 62140, 62505, 62854, 63191,
        63275, 63549, 63712, 63802, 63946, 64071, 64164, 64325, 64464, 64573, 64633, 64729,
        64779, 64813, 64892, 65199, 65295, 65298, 65597, 65703, 65902, 66174, 66404, 66439,
        66528, 67128, 67365, 67428, 67946, 68133, 68149, 68838, 69079, 69133, 69514, 69684,
        69792, 71577, 71636, 71740, 71944, 72111, 72150, 72298, 72887, 72945, 73085, 73088,
        75894, 83118, 83183, 83279, 83377, 83411, 83661, 83699, 83808, 83824, 83915, 83942,
        84012, 84228, 84324, 84416, 84851, 84924, 85233, 85270, 85511, 85762, 86680, 87253,
        87257, 92701, 92781, 92872, 93182, 93639, 94882, 94915, 94992, 95029, 95095, 95098,
        96192, 96285, 96330, 96342, 96591, 96647, 97289, 97509, 97518, 97596, 98019, 98102,
        98195, 98244, 98288, 98378, 98387, 98391, 98421, 98449, 98546, 98698, 98777, 98935,
        98972, 99039, 99040, 99113, 99219, 99377, 99382, 99437, 99524, 99809, 99889, 99964,
        100200, 100221, 100277, 100339, 100419, 100612, 100726, 100800, 100984, 101163, 101289, 101421,
        101438, 102214, 102426, 102546, 102573, 102610, 102631, 102679, 102681, 102831, 103593, 103693,
        104307, 104389, 104479, 104727, 104735, 105874, 106238, 106994, 108080, 108632, 108660, 108781,
        108923, 108927, 108947, 109009, 109042, 109045, 109048, 109049, 109110, 109579, 109727, 110819,
        113732, 113821, 113857, 114012, 114050, 114207, 118005, 118062, 119426, 119587, 119663, 119698,
        121318, 121459, 122110, 122123, 122149, 122151, 122170, 122251, 122518, 122596, 122657, 122689,
        122717, 122719, 122764, 122835, 122871, 122896, 122898, 123288, 123358, 123388, 123482, 123582,
        123584
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'openvla-oft citation review 2026-10-16: cites the source without naming the method in title or abstract'
FROM openvla_oft_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING openvla_oft_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING openvla_oft_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
