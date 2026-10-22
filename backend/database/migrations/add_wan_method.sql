-- Add Wan, Alibaba's open video generation model family, introduced in
-- arXiv 2503.20314. The source paper gets the source evidence row (Introduced
-- banner).

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
    'wan',
    'Wan',
    'Wan (Wan2.1 / Wan2.2 video foundation models)',
    'Wan is Alibaba''s family of open video foundation models for text-to-video, image-to-video and video editing. It follows the [diffusion transformer](/methods/diffusion-transformer-dit) paradigm trained with [flow matching](/methods/flow-matching): a causal 3D [VAE](/methods/vae), Wan-VAE, compresses video by 4x8x8 in time and space and can encode and decode unlimited-length 1080p video, a stack of DiT blocks denoises the latent video tokens, and a multilingual umT5 [text encoder](/methods/t5) conditions each block through cross-attention, with timestep modulation shared across blocks. Wan2.1 shipped as a 1.3B model that runs on consumer GPUs and a 14B model trained on billions of images and videos, which outperformed open and commercial models on the authors'' benchmarks and VBench. Follow-ups include Wan2.2, which adds a two-expert [mixture-of-experts](/methods/mixture-of-experts) denoiser, as well as Wan-I2V, VACE, Wan-S2V and Wan-Animate, and its open weights became a common base for [video generation](/tasks/video-generation) research.',
    'Wan2.1, Wan2.2, Wan2.5, Wan2.6, Wan 2.1, Wan 2.2, Wan 2.5, Wan-2.1, Wan-2.2, Wan-I2V, Wan-T2V, Wan-VAE, Wan-S2V, Wan-Animate, Wan-Move, Wan-14B, Wan-1.3B, Wan-Video, WanVideo',
    (
        SELECT id
        FROM areas
        WHERE name = 'Video'
        LIMIT 1
    ),
    2025,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2503.20314'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Wan: Open and Advanced Large-Scale Video Generative Models',
    'https://github.com/Wan-Video/Wan2.1',
    NULL,
    '[Wan: Open and Advanced Large-Scale Video Generative Models](/paper/2503.20314)'
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
WHERE slug = 'wan'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'wan'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Review 2026-10-21: 113 papers whose title or abstract shows they build on,
-- fine-tune, distill, accelerate or otherwise run a Wan model (citers of the
-- source plus non-citers that name a Wan release), and 123907 (Video
-- Prediction Policy 2, built on Wan2.1-I2V-14B). Papers that only compare
-- against Wan or benchmark it among other generators are excluded below.
CREATE TEMP TABLE wan_linked_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'wan'
  AND p.is_latest_version
  AND p.id IN (
        37517, -- Replace Anyone in Videos
        46281, -- FiVE: A Fine-grained Video Editing Benchmark for Evaluating Emerging Diffus
        46666, -- CFG-Zero*: Improved Classifier-Free Guidance for Flow Matching Models
        47269, -- Model Reveals What to Cache: Profiling-Based Feature Reuse for Video Diffus
        47729, -- UniAnimate-DiT: Human Image Animation with Large-Scale Video Diffusion Tran
        47982, -- RealisDance-DiT: Simple yet Strong Baseline towards Controllable Character
        49057, -- Faster Video Diffusion with Trainable Sparse Attention
        49660, -- Sparse VideoGen2: Accelerate Video Generation with Sparse Attention via Sem
        49693, -- SRDiffusion: Accelerate Video Diffusion Inference via Sketching-Rendering C
        50353, -- Temporal In-Context Fine-Tuning for Versatile Control of Video Diffusion
        50482, -- Sparse-vDiT: Unleashing the Power of Sparse Attention to Accelerate   Video
        50599, -- FPSAttention: Training-Aware FP8 and Sparsity Co-Design for Fast Video Diff
        50904, -- MagCache: Fast Video Generation with Magnitude-Aware Cache
        51163, -- UltraVideo: High-Quality UHD Video Dataset with Comprehensive Captions
        51439, -- Radial Attention: $O(n\log n)$ Sparse Attention with Energy Decay for   Lon
        51599, -- FreeLong++: Training-Free Long Video Generation via Multi-band   SpectralFu
        51972, -- $\nabla$NABLA: Neighborhood Adaptive Block-Level Attention
        52023, -- PUSA V1.0: Surpassing Wan-I2V with $500 Training Cost by Vectorized   Times
        52522, -- Wan-S2V: Audio-Driven Cinematic Video Generation
        52841, -- Wan-Animate: Unified Character Animation and Replacement with Holistic   Re
        52997, -- SLA: Beyond Sparsity in Diffusion Transformers via Fine-Tunable   Sparse-Li
        53056, -- DC-VideoGen: Efficient Video Generation with Deep Compression Video   Autoe
        53384, -- Large Scale Diffusion Distillation via Score-Regularized Continuous-Time
        53993, -- Phased DMD: Few-step Distribution Matching Distillation via Score   Matchin
        54203, -- EmoVid: A Multimodal Emotion Video Dataset for Emotion-Centric Video Unders
        54656, -- Wan-Move: Motion-controllable Video Generation via Latent Trajectory Guidan
        54720, -- H2R-Grounder: A Paired-Data-Free Paradigm for Translating Human Interaction
        54727, -- X-Humanoid: Robotize Human Videos to Generate Humanoid Videos at Scale
        54965, -- TurboDiffusion: Accelerating Video Diffusion Models by 100-200 Times
        54971, -- HiStream: Efficient High-Resolution Video Generation via Redundancy-Elimina
        55309, -- Focal Guidance: Unlocking Controllability from Semantic-Weak Layers in Vide
        55330, -- Transition Matching Distillation for Fast Video Generation
        55705, -- PISA: Piecewise Sparse Attention Is Wiser for Efficient Diffusion Transform
        55983, -- Stable Velocity: A Variance Perspective on Flow Matching
        56193, -- Optimizing Few-Step Generation with Adaptive Matching Distillation
        56206, -- DDiT: Dynamic Patch Scheduling for Efficient Diffusion Transformers
        56305, -- JavisDiT++: Unified Modeling and Optimization for Joint Audio-Video Generat
        56369, -- SenCache: Accelerating Diffusion Model Inference via Sensitivity-Aware Cach
        56623, -- SVG-EAR: Parameter-Free Linear Compensation for Sparse Video Generation via
        57189, -- Video Models Reason Early: Exploiting Plan Commitment for Maze Solving
        57230, -- Salt: Self-Consistent Distribution Matching with Cache-Aware Training for F
        57333, -- When Numbers Speak: Aligning Textual Numerals and Visual Instances in Text-
        57722, -- Building a Precise Video Language with Human-AI Oversight
        58790, -- KV Cache Quantization for Self-Forcing Video Generation: A 33-Method Empiri
        62365, -- S2DiT: Sandwich Diffusion Transformer for Mobile Streaming Video Generation
        63634, -- TalkVerse: Democratizing Minute-Long Audio-Driven Video Generation
        63695, -- Soul: Breathe Life into Digital Human for High-fidelity Long-term Multimoda
        64461, -- MoGAN: Improving Motion Quality in Video Diffusion via Few-Step Motion Adve
        64578, -- Rectified SpaAttn: Revisiting Attention Sparsity for Efficient Video Genera
        65118, -- FSampler: Training Free Acceleration of Diffusion Sampling via Epsilon Extr
        66337, -- Identity-Preserving Image-to-Video Generation via Reward-Guided Optimizatio
        67424, -- Wan-Alpha: High-Quality Text-to-Video Generation with Alpha Channel
        67436, -- Attention Surgery: An Efficient Recipe to Linearize Your Video Diffusion
        69100, -- ERTACache: Error Rectification and Timesteps Adjustment for Efficient   Dif
        69655, -- Video-BLADE: Block-Sparse Attention Meets Step Distillation for   Efficient
        69800, -- TaoCache: Structure-Maintained Video Generation Acceleration
        69830, -- VSF: Simple, Efficient, and Effective Negative Guidance in Few-Step   Image
        70285, -- Forecasting When to Forecast: Accelerating Diffusion Models with   Confiden
        70726, -- RealisVSR: Detail-enhanced Diffusion for Real-World 4K Video   Super-Resolu
        71469, -- Less is Enough: Training-Free Video Diffusion Acceleration via Runtime-Adap
        83918, -- minWM: A Full-Stack Open-Source Framework for Real-Time Interactive Video W
        84274, -- Toward Diffusible High-Dimensional Latent Spaces: A Frequency Perspective
        84460, -- Mind the Generative Details: Direct Localized Detail Preference Optimizatio
        84700, -- Adaptive Spectral Feature Forecasting for Diffusion Sampling Acceleration
        85017, -- SURF: Signature-Retained Fast Video Generation
        85123, -- Wan-Weaver: Interleaved Multi-modal Generation via Decoupled Training
        85416, -- AdaCluster: Adaptive Query-Key Clustering for Sparse Attention in Video Gen
        87505, -- LVSA: Training-Free Sparse Attention for Long Video Diffusion
        94309, -- DiffSparse: Accelerating Diffusion Transformers with Learned Token Sparsity
        94969, -- TS-Attn: Temporal-wise Separable Attention for Multi-Event Video Generation
        98000, -- VDOT: Efficient Unified Video Creation via Optimal Transport Distillation —
        98408, -- Steady-Forcing: Balancing Spatial Persistence and Motion Continuity in Long
        98550, -- LooseControlVideo: Directorial Video Control using Spatial Blocking
        98803, -- Wan-Streamer v0.1: End-to-end Real-time Interactive Foundation Models
        98812, -- Causal-rCM: A Unified Teacher-Forcing and Self-Forcing Open Recipe for Auto
        98910, -- PhysisForcing: Physics Reinforced World Simulator for Robotic Manipulation
        98960, -- DreamForge-World 0.1 Preview: A Low-Compute Real-Time Controllable World Mo
        99463, -- Veda: Scalable Video Diffusion via Distilled Sparse Attention
        99664, -- Attention Sparsity is Input-Stable: Training-Free Sparse Attention for Vide
        99729, -- Budget-Constrained Step-Level Diffusion Caching
        99852, -- NaviCache: Test-Time Self-Calibration Caching for Video Generation
        100607, -- SIPO: Stabilized and Improved Preference Optimization for Aligning Diffusio
        101676, -- Physics-Guided Motion Loss for Video Generation Model
        102550, -- OrbitQuant: Data-Agnostic Quantization for Image and Video Diffusion Transf
        102565, -- Wan-Streamer v0.2: Higher Resolution, Same Latency
        102715, -- OpenCoF: Learning to Reason Through Video Generation
        102723, -- CineMobile: On-Device Image-to-Video Diffusion for Cinematic Camera Motion
        104043, -- MeanFlowNFT: Bringing Forward-Process RL to Average-Velocity Generators
        104488, -- FVAttn: Adaptive Sparse Attention with Runtime Load Balancing for Video Gen
        105919, -- DistillAlign: Coordinating Mode Covering and Mode Seeking in Autoregressive
        107658, -- Phased One-Step Adversarial Equilibrium for Video Diffusion Models
        109459, -- CoinVE-200K: A Large-Scale High-Quality Dataset for Compositional Instructi
        109842, -- EditaLive! Unified Character Video Editing for Live Streaming
        113884, -- SolarWM: Open Data and Scalable Training for Long-Horizon Video World Model
        114022, -- VidaForge: Open Research Infrastructure for Video Pretraining Data Recipes
        118410, -- SyncCache: Exploiting Asymmetric Dynamics for Fast Audio-Driven Portrait An
        118515, -- LatSearch: Latent Reward-Guided Search for Faster Inference-Time Scaling in
        118605, -- Cross-Resolution Distribution Matching for Diffusion Distillation
        119406, -- Accelerating Text-to-Video Generation with Calibrated Sparse Attention
        120751, -- DeltaQuant: 4-bit Video Diffusion Models with Spatiotemporal Delta Smoothin
        120963, -- FlashDecoder: Real-Time Latent-to-Pixel Streaming Decoder with Transformers
        121046, -- TC-Pade: Trajectory-Consistent Pade Approximation for Diffusion Acceleratio
        121140, -- RAPID: Reusing Attention Sparsity with Inter-step Adaptation for Efficient
        121227, -- D2Cache: Second-Order Delta Caching for Higher Video Diffusion Acceleration
        121989, -- VC-Attention: Value Smoothing and Softmax Casting for Low-bit Attention
        122365, -- GeoVerse: World-Consistent Novel View Synthesis in Geometric Latent Space
        122465, -- Physis-Lang: Self-Evolving Language as a Physical Representation for Video
        122854, -- DMAD: Distribution Matching as Adversarial Distillation for Fast Visual Gen
        122872, -- GRACE: Generation-aware latent compression for efficient video generation
        123137, -- Scaling Reinforcement Learning for Diffusion Models via Velocity Matching
        123382, -- LightVAE: Towards Compact and Efficient Video Autoencoders
        123892, -- SpecKCast: Spectral Kalman Forecasting for Diffusion Acceleration
        123907 -- Video Prediction Policy 2: Predict Better, Act Better
  );

DELETE FROM paper_method_exclusions x
USING wan_linked_papers l
WHERE x.paper_id = l.paper_id AND x.method_id = l.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM wan_linked_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM wan_linked_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- The other 1552 reviewed papers (local Semantic Scholar citers of the source,
-- plus keyword matches that only compare against or benchmark Wan) do not use
-- it; exclude them so the reference and keyword backfills do not re-link them.
CREATE TEMP TABLE wan_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'wan'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id NOT IN (SELECT paper_id FROM wan_linked_papers)
  AND p.id IN (
        29062, 35247, 37210, 39408, 40089, 40223, 40325, 40547, 40588, 40989, 41297, 41326,
        41448, 41751, 43603, 43634, 43852, 44011, 44030, 44688, 44694, 45247, 45418, 45724,
        45812, 45814, 45851, 46016, 46061, 46136, 46151, 46324, 46334, 46353, 46359, 46483,
        46491, 46553, 46677, 46701, 46824, 46875, 46878, 47010, 47224, 47562, 47564, 47645,
        47827, 47976, 48017, 48123, 48279, 48280, 48341, 48403, 48417, 48489, 48543, 48651,
        48764, 48788, 48822, 48874, 48963, 48977, 48989, 49052, 49098, 49225, 49267, 49279,
        49452, 49461, 49531, 49539, 49562, 49691, 49727, 49781, 49822, 49842, 49861, 49925,
        49932, 49937, 49950, 49991, 50025, 50053, 50057, 50062, 50085, 50114, 50132, 50148,
        50179, 50279, 50355, 50365, 50403, 50419, 50487, 50490, 50491, 50500, 50514, 50620,
        50639, 50659, 50732, 50750, 50788, 50812, 50813, 50817, 50876, 50909, 50914, 50920,
        50966, 50974, 50981, 51014, 51015, 51040, 51213, 51259, 51284, 51386, 51387, 51397,
        51433, 51434, 51582, 51586, 51686, 51694, 51741, 51758, 51807, 51823, 51824, 51852,
        51933, 51934, 51942, 51946, 51947, 51948, 51969, 52059, 52100, 52180, 52192, 52199,
        52220, 52308, 52311, 52313, 52344, 52386, 52408, 52410, 52411, 52416, 52445, 52457,
        52462, 52467, 52519, 52570, 52673, 52728, 52741, 52748, 52857, 52858, 52890, 52907,
        52939, 52953, 52976, 52979, 52982, 52989, 53003, 53014, 53022, 53104, 53127, 53148,
        53219, 53222, 53237, 53244, 53303, 53317, 53327, 53337, 53359, 53363, 53372, 53375,
        53377, 53381, 53410, 53471, 53483, 53509, 53534, 53549, 53585, 53597, 53621, 53623,
        53646, 53648, 53655, 53672, 53709, 53712, 53721, 53724, 53749, 53784, 53810, 53820,
        53839, 53849, 53850, 53876, 53885, 53899, 53908, 53933, 53950, 53964, 53965, 54015,
        54016, 54030, 54060, 54065, 54077, 54131, 54135, 54159, 54172, 54173, 54197, 54244,
        54261, 54270, 54272, 54273, 54277, 54282, 54286, 54301, 54312, 54324, 54327, 54329,
        54332, 54337, 54339, 54343, 54345, 54356, 54359, 54361, 54362, 54364, 54370, 54375,
        54384, 54389, 54392, 54394, 54411, 54412, 54419, 54435, 54446, 54447, 54449, 54475,
        54483, 54490, 54493, 54506, 54509, 54513, 54514, 54515, 54521, 54524, 54542, 54543,
        54560, 54563, 54566, 54576, 54583, 54587, 54589, 54597, 54605, 54607, 54612, 54618,
        54626, 54628, 54636, 54640, 54647, 54659, 54663, 54683, 54691, 54700, 54701, 54724,
        54730, 54733, 54735, 54736, 54738, 54755, 54759, 54771, 54775, 54776, 54792, 54793,
        54794, 54798, 54800, 54808, 54838, 54839, 54847, 54849, 54862, 54866, 54867, 54873,
        54880, 54889, 54914, 54924, 54926, 54928, 54943, 54946, 54967, 54968, 54986, 55000,
        55005, 55008, 55012, 55029, 55032, 55048, 55051, 55054, 55066, 55067, 55070, 55087,
        55090, 55110, 55116, 55126, 55141, 55142, 55152, 55161, 55165, 55168, 55174, 55181,
        55199, 55201, 55271, 55275, 55301, 55304, 55321, 55334, 55360, 55372, 55377, 55418,
        55447, 55454, 55457, 55458, 55459, 55476, 55489, 55494, 55507, 55512, 55549, 55581,
        55612, 55623, 55625, 55671, 55673, 55677, 55682, 55710, 55712, 55714, 55720, 55728,
        55756, 55769, 55774, 55790, 55809, 55822, 55837, 55838, 55842, 55845, 55848, 55860,
        55912, 55923, 55955, 55958, 55965, 55972, 55980, 56019, 56050, 56060, 56063, 56080,
        56092, 56108, 56138, 56139, 56178, 56188, 56199, 56224, 56240, 56241, 56250, 56262,
        56299, 56300, 56302, 56306, 56308, 56312, 56360, 56379, 56390, 56412, 56421, 56425,
        56428, 56435, 56436, 56439, 56462, 56471, 56492, 56511, 56519, 56545, 56552, 56577,
        56599, 56606, 56631, 56633, 56643, 56650, 56652, 56654, 56656, 56667, 56672, 56692,
        56698, 56703, 56704, 56707, 56728, 56734, 56748, 56754, 56765, 56775, 56776, 56777,
        56808, 56818, 56823, 56836, 56854, 56855, 56857, 56868, 56892, 56896, 56904, 56914,
        56923, 56924, 56931, 56949, 56965, 56972, 56983, 56991, 57007, 57013, 57022, 57049,
        57050, 57051, 57057, 57060, 57083, 57092, 57105, 57112, 57114, 57135, 57140, 57174,
        57177, 57182, 57197, 57204, 57215, 57216, 57234, 57253, 57278, 57288, 57306, 57317,
        57336, 57353, 57358, 57362, 57375, 57385, 57396, 57403, 57406, 57414, 57432, 57456,
        57463, 57466, 57475, 57511, 57513, 57520, 57531, 57556, 57576, 57581, 57627, 57629,
        57639, 57647, 57667, 57685, 57694, 57698, 57702, 57731, 57734, 57742, 57745, 57772,
        57781, 57793, 57795, 57810, 57813, 57827, 57830, 57861, 57875, 57923, 58231, 58271,
        58278, 58297, 58321, 58341, 58344, 58364, 58536, 58538, 58539, 58560, 58573, 58612,
        58668, 58685, 58709, 58758, 58764, 58828, 58860, 58862, 58928, 59011, 59034, 59048,
        59064, 59100, 59143, 59152, 59194, 59211, 59222, 59268, 59300, 59304, 59386, 59406,
        59433, 59442, 59446, 59449, 59468, 59522, 59527, 59528, 59532, 59579, 59581, 59629,
        59666, 59667, 59711, 59768, 59786, 59788, 59840, 59841, 59882, 59916, 59993, 60040,
        60047, 60090, 60155, 60187, 60190, 60195, 60317, 60330, 60346, 60358, 60376, 60381,
        60546, 60587, 60625, 60652, 60654, 60655, 60680, 60696, 60760, 60789, 60793, 60814,
        60856, 60889, 60902, 60913, 60914, 60963, 60974, 60978, 61050, 61067, 61093, 61157,
        61258, 61274, 61632, 61672, 61776, 61780, 61794, 61806, 61887, 61928, 62034, 62072,
        62124, 62129, 62184, 62192, 62227, 62229, 62247, 62326, 62382, 62453, 62469, 62596,
        62730, 62764, 62848, 63007, 63011, 63154, 63155, 63158, 63229, 63257, 63288, 63303,
        63305, 63466, 63468, 63508, 63530, 63547, 63571, 63598, 63607, 63684, 63696, 63701,
        63718, 63724, 63752, 63755, 63757, 63764, 63772, 63785, 63793, 63801, 63810, 63816,
        63821, 63856, 63898, 63913, 63959, 63960, 63994, 63997, 64028, 64087, 64098, 64119,
        64124, 64146, 64176, 64201, 64246, 64254, 64261, 64297, 64341, 64377, 64414, 64443,
        64467, 64489, 64520, 64546, 64573, 64595, 64601, 64609, 64619, 64620, 64634, 64638,
        64677, 64698, 64705, 64709, 64739, 64743, 64958, 65002, 65214, 65225, 65241, 65325,
        65362, 65486, 65729, 65891, 65907, 65923, 66093, 66309, 66312, 66365, 66431, 66463,
        66549, 66558, 66567, 66594, 66608, 66694, 66699, 66715, 66733, 66740, 66762, 66773,
        66791, 66917, 66998, 67090, 67091, 67126, 67130, 67171, 67173, 67175, 67194, 67203,
        67392, 67395, 67421, 67428, 67456, 67474, 67515, 67524, 67530, 67544, 67699, 67728,
        67745, 67746, 67757, 67779, 67851, 67852, 68085, 68098, 68278, 68429, 68657, 68864,
        68885, 69021, 69035, 69137, 69221, 69236, 69251, 69281, 69348, 69430, 69450, 69532,
        69613, 69648, 69732, 69765, 69771, 69781, 69819, 69821, 69856, 70000, 70029, 70059,
        70062, 70137, 70193, 70197, 70206, 70427, 70662, 70892, 70911, 71119, 71433, 71635,
        71753, 71812, 71868, 71917, 71943, 71957, 72073, 72125, 72232, 72311, 72312, 72383,
        72426, 72583, 72631, 72640, 72684, 72757, 73000, 73276, 73388, 73511, 73544, 74249,
        74410, 75433, 75749, 77222, 82839, 82840, 82847, 82850, 82894, 82902, 82907, 82915,
        82930, 82967, 82975, 82992, 83110, 83114, 83115, 83127, 83164, 83167, 83188, 83189,
        83194, 83227, 83238, 83247, 83274, 83281, 83287, 83289, 83297, 83313, 83366, 83367,
        83399, 83451, 83452, 83455, 83459, 83506, 83524, 83592, 83594, 83597, 83608, 83683,
        83695, 83697, 83705, 83751, 83761, 83764, 83796, 83800, 83831, 83836, 83842, 83857,
        83919, 83924, 83949, 83951, 84027, 84052, 84118, 84129, 84180, 84194, 84196, 84211,
        84212, 84230, 84248, 84260, 84307, 84358, 84377, 84396, 84407, 84422, 84459, 84478,
        84479, 84497, 84505, 84506, 84529, 84530, 84555, 84650, 84681, 84774, 84782, 84820,
        84897, 84943, 84990, 84995, 85004, 85025, 85044, 85047, 85056, 85084, 85085, 85093,
        85104, 85112, 85122, 85210, 85245, 85332, 85408, 85438, 85470, 85536, 85558, 85643,
        85649, 85650, 85665, 85674, 85680, 86020, 86913, 87496, 87499, 87501, 87507, 87509,
        87526, 87604, 87782, 88022, 88158, 88313, 92469, 92478, 92503, 92538, 92548, 92602,
        92705, 93025, 93272, 93562, 93582, 93685, 93761, 93780, 93851, 93902, 93934, 93989,
        94008, 94014, 94209, 94285, 94296, 94312, 94452, 94467, 94646, 94730, 94778, 94805,
        94900, 94912, 94950, 94989, 95013, 95076, 95081, 95087, 95849, 96242, 97287, 97950,
        97962, 97972, 97975, 98008, 98012, 98019, 98038, 98102, 98122, 98138, 98159, 98160,
        98167, 98219, 98235, 98293, 98322, 98333, 98396, 98415, 98420, 98432, 98437, 98440,
        98448, 98449, 98455, 98469, 98480, 98501, 98503, 98527, 98544, 98548, 98706, 98736,
        98742, 98762, 98775, 98806, 98814, 98817, 98844, 98848, 98860, 98868, 98873, 98874,
        98929, 98947, 98953, 98954, 98956, 98968, 98972, 98999, 99001, 99040, 99044, 99085,
        99238, 99258, 99363, 99416, 99441, 99510, 99559, 99688, 99703, 99713, 99726, 99754,
        99770, 99804, 99831, 99889, 99890, 99918, 99934, 99962, 100150, 100247, 100291, 100359,
        100502, 100526, 100538, 100654, 100745, 101323, 101335, 101392, 101438, 101799, 102531, 102562,
        102573, 102585, 102586, 102623, 102629, 102630, 102633, 102710, 102711, 102726, 102727, 103007,
        103292, 103819, 103952, 104012, 104040, 104044, 104045, 104049, 104219, 104309, 104313, 104395,
        104397, 104409, 104415, 104441, 104449, 104455, 104510, 104524, 104578, 104585, 104591, 104598,
        104738, 104739, 104793, 104798, 104832, 104866, 104869, 104880, 105852, 105854, 105912, 105937,
        105953, 105993, 106005, 106025, 106065, 106069, 106080, 107227, 107279, 107401, 107452, 107716,
        107966, 108006, 108660, 108698, 108726, 108740, 108788, 108817, 108846, 108931, 108933, 108945,
        108958, 108960, 109040, 109042, 109046, 109047, 109049, 109060, 109071, 109072, 109085, 109096,
        109126, 109129, 109136, 109142, 109143, 109183, 109278, 109302, 109345, 109351, 109377, 109408,
        109410, 109448, 109502, 109579, 109580, 109619, 109635, 109643, 109649, 109664, 109758, 109761,
        109769, 109775, 109776, 109809, 109811, 109814, 109849, 113728, 113736, 113746, 113810, 113822,
        113845, 113857, 113858, 113931, 113932, 113953, 113987, 113988, 114018, 114019, 114025, 114029,
        114049, 114050, 114066, 114069, 114081, 114150, 114212, 114233, 117297, 117487, 117537, 117543,
        117550, 117555, 117603, 117644, 117673, 117697, 117716, 117812, 117831, 117935, 117965, 117969,
        117973, 117975, 117977, 117985, 118016, 118041, 118054, 118066, 118070, 118103, 118245, 118248,
        118323, 118372, 118374, 118405, 118406, 118430, 118432, 118434, 118468, 118479, 118484, 118493,
        118531, 118548, 118564, 118572, 118574, 118579, 118607, 118609, 118614, 118644, 118712, 118761,
        118790, 118888, 119008, 119148, 119161, 119166, 119169, 119176, 119180, 119186, 119188, 119192,
        119198, 119209, 119216, 119217, 119221, 119223, 119224, 119225, 119228, 119235, 119241, 119249,
        119262, 119263, 119264, 119269, 119272, 119276, 119277, 119280, 119286, 119291, 119293, 119300,
        119308, 119312, 119322, 119331, 119333, 119340, 119363, 119383, 119386, 119392, 119398, 119418,
        119430, 119438, 119454, 119456, 119481, 119634, 120755, 120758, 120771, 121076, 121196, 121221,
        121229, 121659, 121673, 121684, 121959, 121960, 121994, 122022, 122030, 122070, 122102, 122104,
        122109, 122110, 122120, 122138, 122163, 122180, 122184, 122194, 122201, 122206, 122251, 122252,
        122257, 122262, 122282, 122283, 122296, 122337, 122341, 122395, 122401, 122411, 122455, 122461,
        122551, 122555, 122564, 122595, 122608, 122618, 122631, 122658, 122667, 122672, 122674, 122679,
        122705, 122709, 122740, 122783, 122791, 122804, 122806, 122844, 122853, 122870, 122874, 122876,
        122896, 122911, 122936, 122944, 122950, 122960, 122976, 122982, 122986, 123056, 123126, 123147,
        123200, 123202, 123251, 123274, 123398, 123400, 123445, 123486, 123497, 123550, 123560, 123582,
        123593, 123595, 123602, 123605, 123697, 123700, 123706, 123761, 123784, 123786, 123810, 123816,
        123853, 123875, 123887, 123899
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Wan curation 2026-10-21: cites or compares against Wan without using it'
FROM wan_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING wan_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING wan_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
