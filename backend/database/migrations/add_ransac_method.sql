-- RANSAC was introduced by Fischler & Bolles (CACM 1981), which has no local
-- paper row, so the source is the paper's DOI and papers are linked from a
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
    'ransac',
    'RANSAC',
    'Random Sample Consensus (RANSAC)',
    'Random Sample Consensus (RANSAC) is an iterative algorithm for robustly fitting a model to data that contain a large fraction of outliers. Each iteration draws a minimal random subset of points, such as four correspondences for a homography, fits a model hypothesis to it, and counts the inliers whose error falls below a threshold; the hypothesis with the largest consensus set is kept and re-estimated from all of its inliers. The number of iterations follows from the desired confidence and the expected inlier ratio. Introduced by Fischler and Bolles for the location determination problem in image analysis and automated cartography, RANSAC is a standard component of geometric computer vision, used for homography, fundamental- and essential-matrix estimation, camera pose (PnP), point cloud registration and [SLAM](/methods/slam). Variants include MSAC, PROSAC, LO-RANSAC, MAGSAC and the differentiable DSAC.',
    'RANSAC, random sample consensus',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    1981,
    NULL,
    'https://doi.org/10.1145/358669.358692',
    'Random Sample Consensus: A Paradigm for Model Fitting with Applications to Image Analysis and Automated Cartography',
    'https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/linear_model/_ransac.py',
    NULL,
    '[Fitted line](https://commons.wikimedia.org/wiki/File:Fitted_line.svg) by Msm, CC BY-SA 3.0'
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

-- Curated 2026-10-15 from every title/abstract mention of RANSAC: each paper below uses, extends or builds solvers for RANSAC-based robust estimation.
CREATE TEMP TABLE ransac_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ransac'
  AND p.id IN (
        4012, -- Automatic assembly of aero engine low pressure turbine shaft based on
        5558, -- Robust 360-8PA: Redesigning The Normalized 8-point Algorithm for 360-F
        6528, -- You Only Hypothesize Once: Point Cloud Registration with Rotation-equi
        12227, -- Generalized Differentiable RANSAC
        20499, -- BANSAC: A dynamic BAyesian Network for adaptive SAmple Consensus
        24160, -- FreeZe: Training-free zero-shot 6D pose estimation with geometric and
        24449, -- Correspondences of the Third Kind: Camera Pose Estimation from Object
        31702, -- DiffCalib: Reformulating Monocular Camera Calibration as Diffusion-Bas
        40499, -- Boost 3D Reconstruction using Diffusion-based Monocular Camera Calibra
        45961, -- Monte Carlo Diffusion for Generalizable Learning-Based RANSAC
        60383, -- Generative 6D Pose Estimation via Conditional Flow Matching
        62846, -- ImLoc: Revisiting Visual Localization with Image-based Representation
        67628, -- GeLoc3r: Enhancing Relative Camera Pose Regression with Geometric Cons
        74449, -- BEV-LIO(LC): BEV Image Assisted LiDAR-Inertial Odometry with Loop Clos
        79753, -- Inference and Learning for Generative Capsule Models
        84087, -- DualReg: Dual-Space Filtering and Reinforcement for Rigid Registration
        87877, -- Unified Category-Level Object Detection and Pose Estimation from RGB I
        90384, -- SPARS3R: Semantic Prior Alignment and Regularization for Sparse 3D Rec
        94576, -- Articulation in Motion: Prior-free Part Mobility Analysis for Articula
        94580, -- Loc$^{2}$: Interpretable Cross-View Localization via Depth-Lifted Loca
        96104, -- Efficient Minimal Solvers for Visual-Inertial Relative Pose Estimation
        97004, -- ForestVO: Enhancing Visual Odometry in Forest Environments through For
        97245, -- GeVI-SLAM: Gravity-Enhanced Stereo VI SLAM for Underwater Robots
        98066, -- BEV-SLD (AutoSOTA)
        109803, -- Accurate Measurement of 3D and 2D Circular Centers With Application to
        112914, -- Semicalibrated Relative Pose from an Affine Correspondence and Monodep
        113515, -- RANRAC: Robust Neural Scene Representations via Random Ray Consensus
        113604, -- Revisit Self-supervision with Local Structure-from-Motion
        116106, -- Robust Self-calibration of Focal Lengths from the Fundamental Matrix
        116719, -- Noisy One-point Homographies are Surprisingly Good
        118257, -- Rolling Shutter Relative Pose Estimation Made Practical
        118321, -- Gravity-aware partially calibrated absolute pose estimation from affin
        119972, -- Dense Match Summarization for Faster Two-view Estimation
        120399, -- Implicit Correspondence Learning for Image-to-Point Cloud Registration
        121658 -- Sparse-View Localization via Online Neural 3D Regression
  );

DELETE FROM paper_method_exclusions x
USING ransac_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ransac_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ransac_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed false positives: RANSAC is mentioned only as the pipeline the paper replaces or as a baseline.
CREATE TEMP TABLE ransac_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ransac'
  AND p.id IN (
        5088, -- GDRNPP: A Geometry-guided and Fully Learning-based Object Pose Estimat
        8921, -- End2End Multi-View Feature Matching with Differentiable Pose Optimizat
        14005, -- RegFormer: An Efficient Projection-Aware Transformer Network for Large
        17816, -- PoseDiffusion: Solving Pose Estimation via Diffusion-aided Bundle Adju
        20487, -- Robust Frame-to-Frame Camera Rotation Estimation in Crowded Scenes
        27804, -- Towards Seamless Adaptation of Pre-trained Models for Visual Place Rec
        77761, -- Deep Homography Estimation for Visual Place Recognition
        108827, -- BIMStruct3D: A Fully Automated Hybrid Learning Scan-to-BIM Pipeline wi
        117302, -- Marginalized Bundle Adjustment: Multi-View Camera Pose from Monocular
        117739, -- SHReg: Strictly Rotation-Equivariant Point Cloud Registration via Sphe
        119786, -- Q-REG: End-to-End Trainable Point Cloud Registration with Surface Curv
        121939 -- $R^{2}$Former: Unified $R$etrieval and $R$eranking Transformer for Pla
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'RANSAC curation 2026-10-15: mentions RANSAC without using it'
FROM ransac_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING ransac_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING ransac_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
