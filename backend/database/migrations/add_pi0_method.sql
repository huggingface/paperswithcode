-- Add π0, introduced in arXiv 2410.24164. Production chat users looked it
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
    'pi0',
    'π0',
    'π0 Vision-Language-Action Flow Model',
    'π0 (pi-zero) is a generalist robot policy from Physical Intelligence that turns a pre-trained vision-language model into a [vision-language-action model](/methods/vla). A PaliGemma backbone (SigLIP 400M + Gemma 2.6B) reads camera images and a language command, and a separate 300M-parameter action expert attends to its tokens and generates chunks of 50 continuous actions with [flow matching](/methods/flow-matching), which supports high-frequency dexterous control at up to 50 Hz. The model is pre-trained on more than 10,000 hours of data from 7 robot configurations and 68 tasks plus the Open X-Embodiment mixture, then post-trained for complex tasks such as folding laundry, bussing tables and assembling boxes. Successors include π0-FAST and π0.5, and the open-source openpi release made π0 a common VLA baseline.',
    'pi0, pi-0, pi_0, π0, π_0, π₀, openpi',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    2024,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2410.24164'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'π0: A Vision-Language-Action Flow Model for General Robot Control',
    'https://github.com/Physical-Intelligence/openpi',
    NULL,
    '[π0: A Vision-Language-Action Flow Model for General Robot Control](/paper/2410.24164)'
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
WHERE slug = 'pi0'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'pi0'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Citation review 2026-10-16: 111 of the 1075 local papers that Semantic Scholar
-- lists as citing the source name π0 in their title or abstract.
CREATE TEMP TABLE pi0_linked_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'pi0'
  AND p.is_latest_version
  AND p.id IN (
        45110, -- Fine-Tuning Vision-Language-Action Models: Optimizing Speed and Success
        48054, -- $π_{0.5}$: a Vision-Language-Action Model with Open-World Generalization
        49389, -- DriveMoE: Mixture-of-Experts for Vision-Language-Action Model in End-to-
        49645, -- VLA-RL: Towards Masterful and General Robotic Manipulation with Scalable
        49983, -- ChatVLA-2: Vision-Language-Action Model with Open-World Embodied Reasoni
        50001, -- ForceVLA: Enhancing VLA Models with a Force-aware MoE for Contact-rich M
        50956, -- SAFE: Multitask Failure Detection for Vision-Language-Action Models
        51437, -- Unified Vision-Language-Action Model
        52004, -- GR-3 Technical Report
        52281, -- Shortcut Learning in Generalist Robot Policies: The Role of Dataset Dive
        52309, -- MolmoAct: Action Reasoning Models that can Reason in Space
        52746, -- SimpleVLA-RL: Scaling VLA Training via Reinforcement Learning
        53403, -- Fidelity-Aware Data Composition for Robust Robot Generalization
        53616, -- VLA-0: Building State-of-the-Art VLAs with Zero Modification
        53989, -- π_RL: Online RL Fine-tuning for Flow-based Vision-Language-Action Models
        54303, -- Mantis: A Versatile Vision-Language-Action Model with Disentangled Visua
        54502, -- Mixture of Horizons in Action Chunking
        54744, -- Task adaptation of Vision-Language-Action model: 1st Place Solution for
        54761, -- Openpi Comet: Competition Solution For 2025 BEHAVIOR Challenge
        55010, -- Dream-VL & Dream-VLA: Open Vision-Language and Vision-Language-Action Mo
        56057, -- χ_{0}: Resource-Aware Robust Manipulation via Taming Distributional Inco
        56095, -- RLinf-Co: Reinforcement Learning-Based Sim-Real Co-Training for VLA Mode
        56254, -- SimVLA: A Simple VLA Baseline for Robotic Manipulation
        56759, -- OxyGen: Unified KV Cache Management for Vision-Language-Action Models un
        56800, -- MolmoB0T: Large-Scale Simulation Enables Zero-Shot Manipulation
        56856, -- FASTER: Rethinking Real-Time Flow VLAs
        56982, -- VTAM: Video-Tactile-Action Models for Complex Physical Interaction Beyon
        57233, -- Do World Action Models Generalize Better than VLAs? A Robustness Study
        58458, -- SnapFlow: One-Step Action Generation for Flow-Matching VLAs via Progress
        58603, -- UAV-Track VLA: Embodied Aerial Tracking via Vision-Language-Action Model
        59500, -- One-Step Flow Policy: Self-Distillation for Fast Visuomotor Policies
        59648, -- TiPToP: A Modular Open-Vocabulary Planning System for Robotic Manipulati
        59664, -- OmniGuide: Universal Guidance Fields for Enhancing Generalist Robot Poli
        60314, -- HALO: A Unified Vision-Language-Action Model for Embodied Multimodal Cha
        60413, -- The Price Is Not Right: Neuro-Symbolic Methods Outperform VLAs on Struct
        60527, -- Learning Physics from Pretrained Video Models: A Multimodal Continuous a
        60756, -- LDA-1B: Scaling Latent Dynamics Action Model via Universal Embodied Data
        62980, -- InternVLA-A1: Unifying Understanding, Generation and Action for Robotic
        63404, -- LoLA: Long Horizon Latent Action Learning for General Robot Manipulation
        63428, -- REALM: A Real-to-Sim Validated Benchmark for Generalization in Robotic M
        63609, -- MiVLA: Towards Generalizable Vision-Language-Action Model with Human-Rob
        63712, -- OXE-AugE: A Large-Scale Robot Augmentation of OXE for Scaling Cross-Embo
        64057, -- Training-Time Action Conditioning for Efficient Real-Time Chunking
        64726, -- SPEAR-1: Scaling Beyond Robot Demonstrations via 3D Understanding
        64771, -- InternData-A1: Pioneering High-Fidelity Synthetic Data for Pre-training
        65298, -- TwinVLA: Data-Efficient Bimanual Manipulation with Twin Single-Arm Visio
        65615, -- Running VLAs at Real-time Speed
        66528, -- DropVLA: An Action-Level Backdoor Attack on Vision-Language-Action Model
        67136, -- FailSafe: Reasoning and Recovery from Failures in Vision-Language-Action
        68254, -- CLAW: A Vision-Language-Action Framework for Weight-Aware Robotic Graspi
        69133, -- MemoryVLA: Perceptual-Cognitive Memory in Vision-Language-Action Models
        70304, -- RICL: Adding In-Context Adaptability to Pre-Trained Vision-Language-Acti
        70482, -- H-RDT: Human Manipulation Enhanced Bimanual Robotic Manipulation
        83393, -- DexHoldem: Playing Texas Hold'em with Dexterous Embodied System
        83699, -- Rethinking Muon Beyond Pretraining: Spectral Failures and High-Pass Reme
        84363, -- Affordance Field Intervention: Enabling VLAs to Escape Memory Traps in R
        84851, -- RC-NF: Robot-Conditioned Normalizing Flow for Real-Time Anomaly Detectio
        84872, -- SaPaVe: Towards Active Perception and Manipulation in Vision-Language Ac
        84924, -- ForceVLA2: Unleashing Hybrid Force-Position Control with Force Awareness
        85337, -- FlowHijack: A Dynamics-Aware Backdoor Attack on Flow-Matching Vision-Lan
        85666, -- Hide-and-Seek in Trajectories: Discovering Failure Signals for VLA Runti
        85687, -- Benchmarking the Generality of Vision-Language-Action Models
        87256, -- Exploring the Limits of Vision-Language-Action Manipulations in Cross-ta
        93968, -- Policy Contrastive Decoding for Robotic Foundation Models
        95301, -- Developing Vision-Language-Action Model from Egocentric Videos
        95999, -- Augmented Reality for RObots (ARRO): Pointing Visuomotor Policies toward
        96101, -- Adaptive Capacity Allocation for Vision Language Action Fine-Tuning
        96210, -- Reinforcement Fine-Tuning of Flow-Matching Policies for Vision-Language-
        96331, -- INSIGHT: INference-Time Sequence Introspection for Generating Help Trigg
        96693, -- IntentionVLA: Generalizable and Efficient Embodied Intention Reasoning f
        96748, -- ExpReS-VLA: Specializing Vision-Language-Action Models through Experienc
        97642, -- Reliable and Scalable Robot Policy Evaluation with Imperfect Simulators
        97692, -- VistaBot: View-Robust Robot Manipulation Via Spatiotemporal-Aware View S
        98195, -- Embodied-R1.5: Evolving Physical Intelligence via Embodied Foundation Mo
        98324, -- μ_0: A Scalable 3D Interaction-Trace World Model
        98815, -- EBench: Elemental Diagnosis of Generalist Mobile Manipulation Policies
        98918, -- Translation as a Bridging Action: Transferring Manipulation Skills from
        98935, -- Qwen-RobotManip Technical Report: Alignment Unlocks Scale for Robotic Ma
        99113, -- Embodied.cpp: A Portable Inference Runtime of Embodied AI Models on Hete
        99219, -- VLA-ATTC: Adaptive Test-Time Compute for VLA Models with Relative Action
        99220, -- Sentinel-VLA: A Metacognitive VLA Model with Active Status Monitoring fo
        100486, -- Move-Then-Operate: Behavioral Phasing for Human-Like Robotic Manipulatio
        100654, -- Seeing Realism from Simulation: Efficient Video Transfer for Vision-Lang
        101353, -- XR-1: Towards Versatile Vision-Language-Action Models via Learning Unifi
        103830, -- RhinoVLA Technical Report
        104378, -- See like a Robot: Robot-Centric Pointmaps for Vision-Language-Action Mod
        104735, -- HiFi-UMI: Learning Deployable Manipulation Policies from High-Fidelity U
        108904, -- DRIFT: Derailing Denoising Trajectories of Flow-Matching VLAs with Adver
        109041, -- $π_{0.7}$: a Steerable Generalist Robotic Foundation Model with Emergent
        109579, -- Flex-$π$: A Multi-Stream World-Action Model with Compute Flexibility
        109763, -- StreamPI: Streaming Multimodal Temporal Modeling for Vision-Language-Act
        113731, -- PonderPounce: A Pretrained MLLM as an Episode Context Engine for Robot C
        113760, -- Act with Intent: Distilling Behavior Intent for Vision-Language-Action M
        114001, -- EmbodiedSkills: A Unified Framework for Orchestrating, Training, and Dep
        114176, -- Breaking the Vision-Action Shortcut: Latent Interface Training for Gener
        118021, -- EchoVLA: Robotic Vision-Language-Action Model with Synergistic Declarati
        119620, -- Restoring Linguistic Grounding in VLA Models via Train-Free Attention Re
        122101, -- Transferring the Intelligence of VLMs to Robotic Control
        122105, -- Grounded Action Model: 3D Grounding as a Foundation for Robotics
        122170, -- MemBodied: Recurrent Associative Memory for Vision-Language-Action Model
        122518, -- The Low-Rank Structure of VLA Reinforcement Learning
        122727, -- Arm-wise Compositional Generalization in Dual-Arm Vision-Language-Action
        122834, -- Toward Real-Time VLAs: Stage-Aware Two-Step Flow Denoising and System-Le
        122838, -- Conditional Trajectory Peaks: Single-Pass Multimodal Policies over Actio
        122871, -- Long-WAM: Scaling the Context of World-Action Models
        122914, -- FastOPD: On-Policy Distillation for Lightweight VLA Deployment
        122983, -- CARE: Certifying Acceleration for Vision-Language-Action Inference
        123388, -- GreenWAM: A World Foundation Model for Robotics
        123402, -- Let the Mind Conceive, Let the Hand Achieve: Following Multimodal Instru
        123460, -- G^3VLA: Geometric Inductive Bias for Vision-Language-Action Models
        123582 -- PINT: A Unified Model with Shared Predictive Intent for Robot Manipulati
  );

DELETE FROM paper_method_exclusions x
USING pi0_linked_papers l
WHERE x.paper_id = l.paper_id AND x.method_id = l.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM pi0_linked_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'reference' FROM pi0_linked_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- The other 964 local citers cite the source in passing; exclude them so the
-- hourly reference backfill does not re-link them.
CREATE TEMP TABLE pi0_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'pi0'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        23225, 27163, 31553, 36292, 40667, 40744, 40933, 41070, 41841, 42152, 43208, 43286,
        43444, 43638, 43870, 43873, 44194, 44339, 44501, 44691, 45090, 45214, 45240, 45349,
        45402, 45445, 45485, 45631, 45798, 45894, 45963, 45985, 46036, 46077, 46082, 46163,
        46194, 46203, 46271, 46359, 46714, 46732, 46936, 47033, 47040, 47126, 47988, 48196,
        48340, 48470, 48507, 48546, 48558, 48650, 48660, 48728, 48736, 48822, 48935, 48989,
        49427, 49483, 49484, 49509, 49910, 49944, 49946, 50085, 50088, 50107, 50160, 50202,
        50288, 50292, 50310, 50394, 50406, 50523, 50704, 50711, 50712, 50769, 50796, 50967,
        50982, 51020, 51102, 51185, 51276, 51281, 51297, 51338, 51355, 51474, 51525, 51574,
        51592, 51698, 51718, 51750, 51768, 51946, 52007, 52047, 52130, 52315, 52488, 52553,
        52569, 52577, 52628, 52633, 52665, 52702, 52738, 52800, 52861, 52878, 52887, 52931,
        52934, 52950, 53306, 53332, 53397, 53406, 53426, 53451, 53472, 53494, 53502, 53552,
        53562, 53569, 53578, 53607, 53613, 53749, 53812, 53840, 53841, 53856, 53874, 53891,
        53939, 53999, 54001, 54033, 54039, 54050, 54051, 54055, 54284, 54288, 54299, 54313,
        54356, 54394, 54399, 54416, 54454, 54455, 54508, 54517, 54574, 54647, 54663, 54687,
        54689, 54691, 54762, 54768, 54814, 54901, 54937, 55021, 55026, 55067, 55091, 55114,
        55115, 55161, 55266, 55291, 55356, 55360, 55384, 55445, 55459, 55529, 55569, 55573,
        55623, 55712, 55775, 55860, 55900, 55908, 55961, 55962, 55967, 56050, 56055, 56096,
        56102, 56113, 56172, 56179, 56188, 56210, 56241, 56274, 56308, 56343, 56439, 56561,
        56643, 56661, 56684, 56757, 56828, 56833, 56851, 56859, 56885, 56935, 56959, 56977,
        57160, 57184, 57234, 57259, 57288, 57326, 57349, 57525, 57530, 57575, 57679, 57695,
        57727, 57735, 57795, 57836, 57838, 57940, 57973, 58018, 58043, 58124, 58138, 58263,
        58278, 58490, 58499, 58560, 58695, 58700, 58709, 58762, 58799, 58816, 58870, 58899,
        58994, 59013, 59017, 59023, 59194, 59250, 59354, 59395, 59490, 59541, 59579, 59657,
        59703, 59725, 59834, 59890, 59944, 60015, 60018, 60223, 60226, 60283, 60289, 60363,
        60468, 60530, 60600, 60655, 60672, 60701, 60719, 60743, 60767, 60768, 60796, 60830,
        60851, 60857, 60871, 60910, 60958, 61090, 61093, 61166, 61242, 61248, 61259, 61311,
        61352, 61383, 61409, 61448, 61550, 61594, 61606, 61628, 61641, 61895, 61966, 61981,
        62029, 62140, 62416, 62505, 62563, 62666, 62735, 62854, 62949, 63004, 63104, 63191,
        63228, 63275, 63277, 63279, 63295, 63402, 63493, 63499, 63508, 63597, 63598, 63802,
        63813, 63931, 63946, 63976, 64059, 64071, 64108, 64164, 64193, 64263, 64266, 64325,
        64344, 64405, 64429, 64464, 64503, 64573, 64596, 64633, 64729, 64779, 64787, 64813,
        64863, 64892, 64987, 65002, 65072, 65199, 65295, 65311, 65570, 65597, 65619, 65627,
        65703, 65902, 65949, 66014, 66044, 66110, 66174, 66200, 66208, 66229, 66296, 66297,
        66381, 66405, 66421, 66439, 66480, 66520, 66551, 66577, 66594, 66625, 66630, 66643,
        66694, 66746, 66758, 66796, 66975, 67000, 67004, 67106, 67128, 67216, 67218, 67278,
        67356, 67375, 67390, 67428, 67470, 67745, 67787, 67814, 67858, 67872, 67891, 67902,
        67921, 67946, 67959, 68135, 68201, 68218, 68342, 68361, 68407, 68411, 68607, 68616,
        68838, 68945, 68997, 69035, 69514, 69621, 69622, 69684, 69792, 69886, 69932, 70013,
        70052, 70137, 70144, 70287, 70385, 70393, 70421, 70613, 70682, 71068, 71256, 71367,
        71395, 71554, 71577, 71597, 71636, 71740, 71745, 71797, 71944, 72030, 72150, 72167,
        72298, 72328, 72371, 72612, 72643, 72693, 72743, 72756, 72887, 72913, 72945, 72955,
        73010, 73049, 73068, 73085, 73169, 73198, 73441, 73659, 73734, 74153, 74259, 74294,
        74562, 74694, 74728, 75894, 82872, 83247, 83279, 83377, 83411, 83808, 83824, 83862,
        83915, 83942, 84012, 84109, 84149, 84228, 84235, 84258, 84401, 84416, 84519, 84632,
        84648, 84663, 84697, 84733, 84739, 84798, 84835, 84999, 85063, 85182, 85204, 85233,
        85251, 85270, 85497, 85511, 85524, 85551, 85669, 85762, 85770, 85901, 86004, 86023,
        86311, 86410, 86499, 86625, 86646, 86656, 86680, 86813, 87253, 87257, 87321, 87399,
        87468, 87784, 87846, 87964, 88019, 88038, 88044, 88074, 88194, 88228, 89349, 90614,
        92474, 92503, 92528, 92701, 92781, 92801, 92872, 92891, 93336, 93470, 93498, 93782,
        94023, 94289, 94419, 94665, 94727, 94739, 94750, 94766, 94798, 94824, 94854, 94882,
        94915, 94992, 95029, 95087, 95175, 95189, 95204, 95321, 95329, 95337, 95361, 95488,
        95574, 95575, 95591, 95666, 95726, 95733, 95734, 95763, 95764, 95789, 95835, 95849,
        95859, 95861, 95886, 95984, 96020, 96025, 96080, 96114, 96140, 96142, 96145, 96180,
        96192, 96203, 96242, 96259, 96285, 96330, 96340, 96370, 96497, 96544, 96591, 96606,
        96627, 96647, 96649, 96654, 96661, 96675, 96678, 96714, 96760, 96781, 96787, 96798,
        96800, 96806, 96819, 96833, 96971, 96972, 96979, 97044, 97050, 97051, 97072, 97091,
        97108, 97151, 97187, 97198, 97229, 97242, 97256, 97272, 97289, 97313, 97344, 97348,
        97359, 97397, 97504, 97509, 97518, 97562, 97581, 97584, 97591, 97592, 97596, 97619,
        97634, 97657, 97664, 97670, 97684, 97719, 97737, 97742, 97889, 97890, 97895, 97952,
        98019, 98102, 98159, 98186, 98219, 98225, 98244, 98288, 98320, 98363, 98380, 98381,
        98386, 98389, 98391, 98421, 98449, 98463, 98474, 98483, 98494, 98509, 98527, 98546,
        98559, 98698, 98703, 98706, 98850, 98916, 98922, 98956, 98972, 98992, 99039, 99040,
        99049, 99084, 99131, 99229, 99366, 99377, 99382, 99437, 99474, 99481, 99492, 99524,
        99763, 99766, 99809, 99889, 99964, 100200, 100210, 100221, 100273, 100304, 100419, 100501,
        100612, 100618, 100633, 100752, 100757, 100909, 100984, 101129, 101163, 101289, 101421, 101447,
        101518, 101626, 101721, 101749, 101880, 101964, 102104, 102167, 102214, 102404, 102424, 102462,
        102561, 102562, 102571, 102573, 102610, 102613, 102629, 102630, 102631, 102646, 102679, 102681,
        103016, 103888, 104012, 104036, 104219, 104307, 104389, 104390, 104398, 104479, 104481, 104523,
        104727, 105845, 105849, 105874, 105918, 105982, 105997, 106017, 106025, 106034, 106238, 106481,
        106875, 106994, 107345, 107807, 108373, 108510, 108632, 108660, 108725, 108732, 108735, 108781,
        108808, 108923, 108960, 109009, 109037, 109040, 109042, 109044, 109045, 109046, 109048, 109049,
        109288, 109503, 109526, 109559, 109695, 109727, 109772, 109809, 109841, 110092, 113732, 113821,
        113857, 113871, 113880, 114012, 114018, 114037, 114041, 114050, 114070, 114150, 114185, 114191,
        114205, 114209, 114214, 114218, 114227, 114257, 114274, 114277, 114278, 117574, 117714, 117979,
        117985, 118003, 118005, 118016, 118062, 118087, 118102, 118279, 119263, 119401, 119426, 119446,
        119578, 119587, 119621, 119642, 119648, 119663, 119680, 119698, 120065, 120812, 121318, 121459,
        121838, 121875, 121987, 121999, 122073, 122107, 122110, 122117, 122149, 122151, 122186, 122206,
        122235, 122262, 122318, 122327, 122340, 122411, 122429, 122481, 122596, 122606, 122624, 122657,
        122667, 122674, 122687, 122689, 122698, 122717, 122719, 122733, 122734, 122764, 122797, 122806,
        122816, 122833, 122835, 122841, 122849, 122870, 122896, 122899, 122905, 122950, 122974, 123223,
        123271, 123412, 123482, 123578
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'pi0 citation review 2026-10-16: cites the source without naming the method in title or abstract'
FROM pi0_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING pi0_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING pi0_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
