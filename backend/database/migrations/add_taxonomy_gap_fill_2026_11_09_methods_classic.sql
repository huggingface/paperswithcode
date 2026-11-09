-- Chat lookup-miss taxonomy gap fill (2026-11-09 audit): six classic methods.
-- None has an arXiv introducing paper, so source_paper_id stays NULL, source_url
-- points to a canonical reference, and no "Introduced" banner is added. The
-- hourly reference backfill skips methods without a source paper.
--
-- Keywords tag papers through the daily keyword backfill, so they are limited to
-- exact long-form technique names; bare acronyms (ICA, SOM, MPC, OLS) collide
-- with other senses and live only in full_name/aliases, where the Jev judge
-- decides each abstract mention.
--
-- Paper links were curated by hand from every local title/abstract candidate
-- (long forms plus the bare acronyms); true positives get 'manual' evidence and
-- reviewed negatives become durable exclusions. Hero images were imported
-- separately with import_entity_image.py; this file records their credits.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, abstract_linking, aliases
)
VALUES
(
    'linear-regression',
    'Linear Regression',
    'Linear Regression',
    'Linear regression models a continuous target as a weighted sum of input features plus an intercept, y = Xβ + ε, and fits the weights β by minimizing the squared error between predictions and targets. The ordinary least squares (OLS) solution has the closed form β = (XᵀX)⁻¹Xᵀy, rooted in the least-squares method of Legendre (1805) and Gauss; it can also be found iteratively with [Gradient Descent](/methods/gradient-descent) or [SGD](/methods/sgd). Ridge and lasso regression add L2 and L1 penalties to control variance and select features, and Bayesian linear regression places a prior on β. Linear regression remains a standard baseline, a linear probe on learned representations, and a tractable model for theory: much of the analysis of benign overfitting, scaling laws and in-context learning in Transformers is carried out on linear regression tasks. Its classification counterpart is [Logistic Regression](/methods/logistic-regression).',
    'linear regression, ordinary least squares',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://scikit-learn.org/stable/modules/linear_model.html#ordinary-least-squares',
    'Linear Models: Ordinary Least Squares (scikit-learn)',
    NULL,
    NULL,
    'judge',
    ARRAY['Ordinary Least Squares (OLS)']
),
(
    'conjugate-gradient',
    'Conjugate Gradient',
    'Conjugate Gradient (CG)',
    'The conjugate gradient (CG) method, introduced by Hestenes and Stiefel (1952), solves symmetric positive-definite linear systems Ax = b, or equivalently minimizes the quadratic ½xᵀAx − bᵀx. Each iteration moves along a search direction that is A-conjugate to all previous ones, so in exact arithmetic CG converges in at most n steps and in practice far sooner when the eigenvalues of A are clustered. It only needs matrix-vector products, which makes it the standard Krylov-subspace solver for large sparse systems, usually combined with a preconditioner (PCG). Nonlinear variants such as Fletcher–Reeves and Polak–Ribière extend it to general unconstrained optimization, between [Gradient Descent](/methods/gradient-descent) and Newton methods. In machine learning CG computes Hessian-free and Gauss–Newton updates, natural-gradient and TRPO steps, implicit gradients, Gaussian process inference and data-consistency steps in MRI reconstruction and diffusion-based inverse problem solvers.',
    'conjugate gradient, conjugate-gradient',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    1952,
    NULL,
    'https://nvlpubs.nist.gov/nistpubs/jres/049/jresv49n6p409_a1b.pdf',
    'Methods of Conjugate Gradients for Solving Linear Systems (Hestenes & Stiefel, 1952)',
    NULL,
    NULL,
    'always',
    ARRAY[]::text[]
),
(
    'independent-component-analysis',
    'Independent Component Analysis',
    'Independent Component Analysis (ICA)',
    'Independent Component Analysis (ICA) separates a multivariate signal into additive components that are statistically independent and non-Gaussian. It assumes the observations are linear mixtures x = As of unknown sources and estimates an unmixing matrix W ≈ A⁻¹ by maximizing non-Gaussianity (kurtosis or negentropy, as in FastICA) or by maximum likelihood (Infomax). Unlike [PCA](/methods/pca), which only decorrelates the data, ICA recovers the sources up to permutation and scale, which makes it the classic solution to blind source separation (the cocktail party problem). It grew out of work by Hérault and Jutten in the 1980s and was formalized by Comon (1994). ICA is widely used to remove artifacts from EEG and MEG recordings, in rPPG and EMG decomposition, and in causal discovery (ICA-LiNGAM). Nonlinear ICA and its identifiability theory underpin much of causal and disentangled representation learning, and ICA has been revived to find interpretable directions in language model representations.',
    'independent component analysis',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1016/S0893-6080(00)00026-5',
    'Independent Component Analysis: Algorithms and Applications (Hyvärinen & Oja, 2000)',
    NULL,
    NULL,
    'judge',
    ARRAY[]::text[]
),
(
    'self-organizing-map',
    'Self-Organizing Map',
    'Self-Organizing Map (SOM)',
    'A self-organizing map (SOM), or Kohonen map, is an unsupervised neural network introduced by Teuvo Kohonen (1982) that maps high-dimensional data onto a low-dimensional, usually two-dimensional, grid of units while preserving its topology. Each unit holds a weight vector. For every input the best-matching unit (BMU) is found, and the BMU and its grid neighbours are pulled towards the input with a learning rate and neighbourhood radius that shrink over training. The trained grid works as a clustering, a nonlinear dimensionality reduction and a visualization (for example via the U-matrix), and is related to [k-means clustering](/methods/k-means-clustering) and [Vector Quantization (VQ)](/methods/vector-quantization-vq). SOMs are used for document and word-embedding clustering, astronomy (photometric redshift calibration, radio-source morphology), medical imaging and interpretability, and as components inside deep models.',
    'self-organizing map, self-organising map, self-organizing feature map, kohonen map',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    1982,
    NULL,
    'https://doi.org/10.1007/BF00337288',
    'Self-Organized Formation of Topologically Correct Feature Maps (Kohonen, 1982)',
    NULL,
    NULL,
    'judge',
    ARRAY['Kohonen Map', 'Self-Organizing Feature Map']
),
(
    'random-projection',
    'Random Projection',
    'Random Projection',
    'Random projection reduces dimensionality by multiplying data with a random matrix, for example with Gaussian, sign or very sparse entries, instead of a matrix learned from the data. By the Johnson–Lindenstrauss lemma (1984), n points can be projected to O(log n / ε²) dimensions while all pairwise distances are preserved within a factor 1 ± ε, independent of the original dimension. Random projection is data-oblivious, needs no training and costs far less than [PCA](/methods/pca); fast and sparse Johnson–Lindenstrauss transforms speed it up further. It underlies sketching in randomized numerical linear algebra, locality-sensitive hashing and approximate nearest neighbor search, random features for kernel and attention approximation, and compressed sensing. In deep learning it compresses gradients for training-data attribution, optimizer states and activations for memory-efficient training (Flora, APOLLO, CompAct), KV caches (QJL), and serves as a fixed tokenizer for self-supervised speech and audio models such as BEATs.',
    'random projection, johnson-lindenstrauss transform',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1145/502512.502546',
    'Random Projection in Dimensionality Reduction: Applications to Image and Text Data (Bingham & Mannila, 2001)',
    NULL,
    NULL,
    'always',
    ARRAY['Johnson-Lindenstrauss Transform']
),
(
    'model-predictive-control',
    'Model Predictive Control',
    'Model Predictive Control (MPC)',
    'Model Predictive Control (MPC), also called receding horizon control, chooses actions by repeatedly solving a finite-horizon optimal control problem. At each step it uses a dynamics model to predict the system over the next H steps, optimizes the control sequence against a cost subject to state and input constraints, applies only the first action, and re-plans from the new measured state. Explicit constraint handling and feedback through re-planning made MPC the standard advanced controller in the process industries from the late 1970s, and it is now widely used for legged locomotion, drones, autonomous driving and manipulation, with linear, nonlinear (NMPC), robust, stochastic and sampling-based variants such as MPPI and the cross-entropy method. In learning-based control, MPC plans with learned dynamics or latent world models, as in PETS, [TD-MPC](/paper/2203.04955) and [TD-MPC2](/paper/2310.16828), and is combined with reinforcement learning, value functions and differentiable optimization layers.',
    'model predictive control, model-predictive control, model predictive controller, model-predictive controller',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://doi.org/10.1016/S0005-1098(99)00214-9',
    'Constrained Model Predictive Control: Stability and Optimality (Mayne et al., 2000)',
    NULL,
    NULL,
    'judge',
    ARRAY['Receding Horizon Control']
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

-- linear-regression: 212 reviewed true positives of 252 title/abstract candidates.
CREATE TEMP TABLE lr_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'linear-regression'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1711.07831', -- On Breast Cancer Detection: An Application of Machine Learning Algorithm
          '1904.10622', -- Objective Assessment of Social Skills Using Automated Language Analysis
          '1905.02072', -- Characterizing the invariances of learning algorithms using category the
          '2010.08168', -- A Generalizable and Accessible Approach to Machine Learning with Global
          '2010.14672', -- How Does the Task Landscape Affect MAML Performance?
          '2106.05024', -- Contamination Bias in Linear Regressions
          '2106.10466', -- TS2Vec: Towards Universal Representation of Time Series
          '2106.13956', -- Solar Irradiation Forecasting using Genetic Algorithms
          '2111.03861', -- What augmentations are sensitive to hyper-parameters and why?
          '2111.15397', -- NeuralProphet: Explainable Forecasting at Scale
          '2202.01470', -- Towards 3D Scene Reconstruction from Locally Scale-Aligned Monocular Vid
          '2202.10670', -- From Optimization Dynamics to Generalization Bounds via ?ojasiewicz Grad
          '2207.09259', -- Adaptive Testing for Connected and Automated Vehicles with Sparse Contro
          '2209.14881', -- Sequential Attention for Feature Selection
          '2211.12743', -- Efficient List-Decodable Regression using Batches
          '2211.15661', -- What learning algorithm is in-context learning? Investigations with line
          '2212.00517', -- Adaptive Safety Evaluation for Connected and Automated Vehicles with Spa
          '2301.11342', -- A Robust Optimisation Perspective on Counterexample-Guided Repair of Neu
          '2301.11647', -- Learning the Dynamics of Sparsely Observed Interacting Systems
          '2301.13304', -- Understanding Self-Distillation in the Presence of Label Noise
          '2301.13778', -- Differentially Private Distributed Bayesian Linear Regression with MCMC
          '2302.00257', -- Implicit Regularization Leads to Benign Overfitting for Sparse Linear Re
          '2302.01088', -- Sketched Ridgeless Linear Regression: The Role of Downsampling
          '2302.01855', -- From Robustness to Privacy and Back
          '2302.11172', -- Impact of a Batter in ODI Cricket Implementing Regression Models from Ma
          '2303.15634', -- Learning Rate Schedules in the Presence of Distribution Shift
          '2304.00451', -- Re-IQA: Unsupervised Learning for Image Quality Assessment in the Wild
          '2304.02478', -- Exploring AI-Generated Text in Student Writing: How Does AI Help?
          '2305.11560', -- Brain Captioning: Decoding human brain activity into images and text
          '2305.16704', -- A Closer Look at In-Context Learning under Distribution Shifts
          '2306.01854', -- Reinforcement Learning with General Utilities: Simpler Variance Reductio
          '2306.04891', -- In-Context Learning through the Bayesian Prism
          '2306.09927', -- Trained Transformers Learn Linear Models In-Context
          '2306.15063', -- Pretraining task diversity and the emergence of non-Bayesian in-context
          '2307.03576', -- One Step of Gradient Descent is Provably the Optimal In-Context Learner
          '2308.02796', -- OBESEYE: Interpretable Diet Recommender for Obesity Management using Mac
          '2308.06912', -- CausalLM is not optimal for in-context learning
          '2308.12280', -- Extended Linear Regression: A Kalman Filter Approach for Minimizing Loss
          '2309.03409', -- Large Language Models as Optimizers
          '2310.04652', -- Oracle Efficient Algorithms for Groupwise Regret
          '2310.06771', -- Correlated Noise Provably Beats Independent Noise for Differentially Pri
          '2310.07367', -- Improved Analysis of Sparse Linear Regression in Local Differential Priv
          '2310.08391', -- How Many Pretraining Tasks Are Needed for In-Context Learning of Linear
          '2310.17086', -- Transformers Learn to Achieve Second-Order Convergence Rates for In-Cont
          '2311.08362', -- Transformers can optimally learn regression mixture models
          '2311.14222', -- Risk Bounds of Accelerated SGD for Overparameterized Linear Regression
          '2311.15961', -- Maximum Likelihood Estimation is All You Need for Well-Specified Covaria
          '2401.11081', -- Learning from Aggregate responses: Instance Level versus Bag Level Loss
          '2401.12617', -- The Joint Effect of Task Similarity and Overparameterization on Catastro
          '2401.13034', -- Locality Sensitive Sparse Encoding for Learning World Models Online
          '2402.14180', -- Linear Transformers are Versatile In-Context Learners
          '2402.17327', -- Data-Efficient Learning via Clustering-Based Sensitivity Sampling: Found
          '2403.00686', -- A Bit of a Problem: Measurement Disparities in Dataset Sizes Across Lang
          '2404.07544', -- From Words to Numbers: Your Large Language Model Is Secretly A Capable R
          '2405.15115', -- Towards Better Understanding of In-Context Learning Ability from In-Cont
          '2405.16845', -- On Mesa-Optimization in Autoregressively Trained Transformers: Emergence
          '2408.05288', -- The impact of internal variability on benchmarking deep learning climate
          '2409.13854', -- More Consideration for the Perceptron
          '2410.03240', -- Beyond Film Subtitles: Is YouTube the Best Approximation of Spoken Vocab
          '2412.18134', -- Learning Randomized Reductions and Program Properties
          '2501.17836', -- Matrix Product Sketching via Coordinated Sampling
          '2502.14123', -- Understanding SGD with Exponential Moving Average: A Case Study in Linea
          '2503.12528', -- Investigating Human-Aligned Large Language Model Uncertainty
          '2503.12734', -- In-Context Linear Regression Demystified: Training Dynamics and Mechanis
          '2503.17538', -- A Statistical Theory of Contrastive Learning via Approximate Sufficient
          '2505.14414', -- Diving into the Fusion of Monocular Priors for Generalized Stereo Matchi
          '2506.00999', -- An Empirical Analysis of Tiff''s Impact on American Business Formation
          '2510.00184', -- Why Can''t Transformers Learn Multiplication? Reverse-Engineering Reveal
          '2602.10870', -- FedPS: Federated data Preprocessing via aggregated Statistics
          '2410.05882', -- Frame forecasting in cine MRI using the PCA respiratory motion model: co
          '2603.28274', -- Statistics 101, 201, and 202: Three Shiny Apps for Teaching Probability
          '2602.13278', -- NP-hardness of p-adic linear regression
          '2512.19905', -- Demystifying LLM-as-a-Judge: Analytically Tractable Model for Inference-
          '2512.17639', -- Linear Personality Probing and Steering in LLMs: A Big Five Study
          '2512.04268', -- The Initialization Determines Whether In-Context Learning Is Gradient De
          '2511.12129', -- A Practical Machine Learning Approach for Dynamic Stock Recommendation
          '2511.06211', -- Sparse Linear Regression is Easy on Random Supports
          '2510.00043', -- Linear Regression in p-adic metric spaces
          '2508.11372', -- Stealing Accuracy: Predicting Day-ahead Electricity Prices with Temporal
          '2508.03121', -- RegMean++: Enhancing Effectiveness and Generalization of Regression Mean
          '2508.02686', -- Adaptive Market Intelligence: A Mixture of Experts Framework for Volatil
          '2507.02442', -- The Gauss-Markov Adjunction: Categorical Semantics of Residuals in
          '2504.02915', -- Brewing Discontent: How U.S. Reciprocal Tariffs on Coffee Could Echo the
          '2502.21212', -- Transformers Learn to Implement Multi-step Gradient Descent with Chain o
          '2502.06800', -- Analyzing Geospatial and Socioeconomic Disparities in Breast Cancer Scre
          '2408.03733', -- Bayes-optimal learning of an extensive-width neural network from quadrat
          '2407.04600', -- Understanding the Gains from Repeated Self-Distillation
          '2406.16437', -- Theory on Mixture-of-Experts in Continual Learning
          '2406.12145', -- Minimax Linear Regression under the Quantile Risk
          '2405.06725', -- On the Shape of Brainscores for Large Language Models (LLMs)
          '2404.07849', -- Overparameterized Multiple Linear Regression as Hyper-Curve Fitting
          '2312.15494', -- Variable Selection in High Dimensional Linear Regressions with Parameter
          '2309.10986', -- Research on the Impact of Executive Shareholding on New Investment in
          '2301.10942', -- Divide and Conquer Dynamic Programming: An Almost Linear Time Change
          '2301.02200', -- Impact, Attention, Influence: Early Assessment of Autonomous Driving
          '2211.13124', -- Number Theory Meets Linguistics: Modelling Noun Pluralisation Across 149
          '2011.03443', -- Is Transfer Learning Necessary for Protein Landscape Prediction?
          '2009.05241', -- Improving Robustness to Model Inversion Attacks via Mutual Information R
          '1906.08509', -- Online A-Optimal Design and Active Linear Regression
          '1807.06510', -- Modernizing use of regression models in physics education research: a re
          '1612.09506', -- Smart Content Recognition from Images Using a Mixture of Convolutional N
          '2605.21468', -- You Only Need Minimal RLVR Training: Extrapolating LLMs via Rank-1 Traje
          '2507.05478', -- Dynamic Regret Reduces to Kernelized Static Regret
          '2506.11849', -- Regression-adjusted Monte Carlo Estimators for Shapley Values and Probab
          '2502.18710', -- Bridging Critical Gaps in Convergent Learning: How Representational Alig
          '2502.04204', -- Short-length Adversarial Training Helps LLMs Defend Long-length Jailbrea
          '2505.24603', -- The Gaussian Mixing Mechanism: Differential Privacy via Gaussian Sketche
          '2507.04194', -- Mixed-Sample SGD: an End-to-end Analysis of Supervised Transfer Learning
          '2409.15582', -- Generalization vs Specialization under Concept Shift
          '2506.06501', -- Optimal Rates in Continual Linear Regression via Increasing Regularizati
          '2506.05188', -- Counterfactual reasoning: an analysis of in-context emergence
          '2510.15337', -- Transfer Learning for Benign Overfitting in High-Dimensional Linear Regr
          '2509.25536', -- Optimal Nuisance Function Tuning for Doubly Robust Functional Estimation
          '2502.18475', -- Least squares variational inference
          '2508.15051', -- Robust Estimation Under Heterogeneous Corruption Rates
          '2505.17863', -- The emergence of sparse attention: impact of data distribution and benef
          '2509.23779', -- Trained Mamba Emulates Online Gradient Descent in In-Context Linear Regr
          '2412.17749', -- Bivariate Matrix-valued Linear Regression (BMLR): Finite-sample performa
          '2506.08415', -- Improved Scaling Laws in Linear Regression via Data Reuse
          '2510.10665', -- Information-Computation Tradeoffs for Noiseless Linear Regression with O
          '2505.22689', -- SlimLLM: Accurate Structured Pruning for Large Language Models
          '2411.12665', -- Regression for the Mean: Auto-Evaluation and Inference with Few Labels t
          '2503.09802', -- Batch List-Decodable Linear Regression via Higher Moments
          '2506.05101', -- Privacy Amplification Through Synthetic Data: Insights from Linear Regre
          '2412.18140', -- An Instrumental Value for Data Production and its Application to Data Pr
          '2506.07595', -- Exploiting Curvature in Online Convex Optimization with Delayed Feedback
          '2502.01347', -- Spurious Correlations in High Dimensional Regression: The Roles of Regul
          '2502.09534', -- Fast Tensor Completion via Approximate Richardson Iteration
          '2506.14673', -- Uniform Mean Estimation for Heavy-Tailed Distributions via Median-of-Mea
          '2505.03923', -- SAND: One-Shot Feature Selection with Additive Noise Distortion
          '2501.16265', -- Training Dynamics of In-Context Learning in Linear Attention
          '2407.07059', -- Differentiable Optimization of Similarity Scores Between Models and Brai
          '2410.07916', -- Robustness Auditing for Linear Regression: To Singularity and Beyond
          '2410.01265', -- Transformers Handle Endogeneity in In-Context Linear Regression
          '2408.09966', -- Mask in the Mirror: Implicit Sparsification
          '2410.07870', -- Gradient correlation is a key ingredient to accelerate SGD with momentum
          '2603.02069', -- Scaling Laws of SignSGD in Linear Regression: When Does It Outperform SG
          '2510.16657', -- Escaping Model Collapse via Synthetic Data Verification: Near-term Impro
          '2509.22341', -- Preventing Model Collapse Under Overparametrization: Optimal Mixing Rati
          '2509.21181', -- Closed-form $\ell_r$ norm scaling with data for overparameterized linear
          '2510.03605', -- Understanding the Role of Training Data in Test-Time Scaling
          '2505.03736', -- Decentralized Nonconvex Optimization under Heavy-Tailed Noise: Normaliza
          '2510.18259', -- Learning under Quantization for High-Dimensional Linear Regression
          '2511.13421', -- Larger Datasets Can Be Repeated More: A Theoretical Analysis of Multi-Ep
          '2509.26551', -- Pretrain?Test Task Alignment Governs Generalization in In-Context Learni
          '2509.23488', -- Mapping Overlaps in Benchmarks through Perplexity in the Wild
          '2504.04039', -- Memory-Statistics Tradeoff in Continual Learning with Structural Regular
          '2506.07022', -- AlphaSteer: Learning Refusal Steering with Principled Null-Space Constra
          '2510.14717', -- Seesaw: Accelerating Training by Balancing Batch Size and Learning Rate
          '2510.01098', -- Theory of Scaling Laws for In-Context Regression: Depth, Width, Context
          '2604.12817', -- Understanding and Improving Continuous LLM Adversarial Training via In-c
          '2506.02630', -- Hyperbolic Aware Minimization: Implicit Bias for Sparsity
          '2510.01414', -- Risk Phase Transitions in Spiked Regression: Alignment Driven Benign and
          '2602.23341', -- Mean Estimation from Coarse Data: Characterizations and Efficient Algori
          '2602.15684', -- Estimating Human Muscular Fatigue in Dynamic Collaborative Robotic Tasks
          '2606.10617', -- SSR-Merge: Subspace Signal Routing for Training-Free LoRA Merging in Dif
          '2512.11784', -- Softmax as Linear Attention in the Large-Prompt Regime: a Measure-based
          '2602.08372', -- Dynamic Regret via Discounted-to-Dynamic Reduction with Applications to
          '2601.07545', -- Near-Optimal Private Linear Regression via Iterative Hessian Mixing
          '2606.18773', -- Private Learning with Public Feature Conditioning
          '2509.12689', -- Loss-Aware Distributionally Robust Optimization via Trainable Optimal Tr
          '2603.01293', -- Theoretical Perspectives on Data Quality and Synergistic Effects in Pre-
          '2508.07571', -- Towards Theoretical Understanding of Transformer Test-Time Computing: In
          '2601.19791', -- To Grok Grokking: Provable Grokking in Ridge Regression
          '2606.01292', -- What Makes a Strong Model? A Unified Spectral Analysis of Knowledge Tran
          '2606.25745', -- Gaussian Mean Field Variational Inference can Overestimate Predictive Va
          '2605.17126', -- Multi-task Linear Regression without Eigenvalue Lower Bounds: Adaptivity
          '2602.14029', -- Why Self-Distillation Helps and Hurts: Denoising vs. Signal Forgetting
          '2602.07218', -- Collaborative and Efficient Fine-tuning: Leveraging Task Similarity
          '2602.19241', -- Scaling Laws for Precision in High-Dimensional Linear Regression
          '2602.12534', -- Linear Regression with Unknown Truncation Beyond Gaussian Features
          '2604.18712', -- Probing for Reading Times
          '2507.19155', -- RegScore: Scoring Systems for Regression Tasks
          '2511.10809', -- Near-optimal Linear Predictive Clustering in Non-separable Spaces via MI
          '2511.08073', -- Online Linear Regression with Paid Stochastic Features
          '2608.20061', -- Let''s Scale Step by Step: Compute-Efficient Hyperparameter Transfer for
          '2512.03336', -- Single-Round Scalable Analytic Federated Learning
          '2603.06462', -- Bayesian Additive Distribution Regression
          '2610.19573', -- On Inherent Privacy of Posterior Sampling: A Unified R\''enyi-Divergence
          '2609.09572', -- Learning with Synthetic Data via SGD in High-Dimensional Linear Regressi
          '2605.18537', -- Probing for Representation Manifolds in Superposition
          '2607.23388', -- Constraint-Aware Influence Estimation in Deep Constrained Learning
          '2606.19179', -- Compute Efficiency and Serial Runtime Tradeoffs for Stochastic Momentum
          '2605.20105', -- Optimal Representation Size: High-Dimensional Analysis of Pretraining an
          '2304.04308', -- Ensemble Modeling for Time Series Forecasting: an Adaptive Robust Optimi
          '2603.26954', -- High dimensional theory of two-phase optimizers
          '2410.12740', -- Just Ramp-Up: Debiasing Regression-based Estimator for A/B Tests under N
          '2602.16531', -- Transfer Learning of Linear Regression with Multiple Pretrained Models:
          '2504.09663' -- Ordinary Least Squares as an Attention Mechanism
      )
      OR       (p.source = 'external' AND p.id IN (
          96727, -- Integration and Continual Learning-Based Modeling of a Soft Robotic Sens
          111622, -- PERCEPT-US: A Multimodal American English Child Speech Corpus Specialize
          115437, -- Test-Time Linear Out-of-Distribution Detection
          124280, -- Markovian Experimental Design under Concept Drift
          124395, -- A Solvable Model of Chain-of-Thought in In-Context Learning
          125386, -- Loss is Not Behavior: A Unified Output-Space Analysis of Gradient-Based
          125545, -- In-Context Benign Overfitting: A Feature-Selection Model in Linear Regre
          126286, -- Improved Leverage Score Sampling for Constrained Active Linear Regressio
          126300, -- A Transformer-Derived Iterative Preconditioner
          126421, -- Statistical Mixing Guarantees for Contractive Echo State Networks
          126513, -- Sup-Norm Error under Proportional Asymptotics: Phase Transitions under L
          126541, -- Regret-Optimal Wasserstein-Robust Regression
          126693, -- Optimal Linear Regression Without a Variance
          127945, -- Spectral Representations for Provably Robust Offline Meta-Reinforcement
          128651, -- Sample Complexity of Linear Regression under Random-Location Coordinate
          129042, -- The Price of Locality in Label Privacy: Optimal Rates for Classification
          130056, -- Efficient algorithms for linear regression with heteroskedastic errors
          130073, -- How Can SignSGD Outperform SGD? A Functional Scaling Law Perspective
          130608, -- Positional Encoding and Prompt-Order Sensitivity in In-Context Learning
          130645, -- Understanding Randomization in Greedy Model Search
          130938, -- On Differentially Private Mechanisms for Linear Regression
          131068, -- Linear Regression Under Misalignment: Algorithms and Theoretical Results
          131119 -- Riemannian Ordinary Least Squares
      ))
  );

DELETE FROM paper_method_exclusions x
USING lr_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM lr_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM lr_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- linear-regression: 40 reviewed negatives.
CREATE TEMP TABLE lr_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'linear-regression'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1802.06509', -- On the Optimization of Deep Networks: Implicit Acceleration by Overparam
          '2002.03419', -- The Alzheimer''s Disease Prediction Of Longitudinal Evolution (TADPOLE)
          '2002.07651', -- Listwise Learning to Rank with Deep Q-Networks
          '2202.13603', -- Optimal Online Generalized Linear Regression with Stochastic Noise and I
          '2210.08196', -- Deep Regression Unlearning
          '2212.07677', -- Transformers learn in-context by gradient descent
          '2212.11279', -- Annotated History of Modern AI and Deep Learning
          '2304.13276', -- The Closeness of In-Context Learning and Weight Shifting for Softmax Reg
          '2310.04918', -- SWAP: Sparse Entropic Wasserstein Regression for Robust Network Pruning
          '2401.12973', -- In-Context Language Learning: Architectures and Algorithms
          '2403.06328', -- Distributional Successor Features Enable Zero-Shot Policy Optimization
          '2412.00800', -- A Comprehensive Guide to Explainable AI: From Classical Models to LLMs
          '2502.15813', -- Stock Price Prediction Using a Hybrid LSTM-GNN Model: Integrating Time-S
          '2512.24193', -- PointRAFT: 3D deep learning for high-throughput prediction of potato tub
          '2403.01607', -- Real-time respiratory motion forecasting with online learning of recurre
          '2207.05951', -- Prediction of the motion of chest internal points using a recurrent neur
          '2106.01100', -- Prediction of the Position of External Markers Using a Recurrent Neural
          '1911.07135', -- The Secret Revealer: Generative Model-Inversion Attacks Against Deep Neu
          '2605.08423', -- Queryable LoRA: Instruction-Regularized Routing Over Shared Low-Rank Upd
          '2507.11274', -- Fast Last-Iterate Convergence of SGD in the Smooth Interpolation Regime
          '2405.19162', -- Does learning the right latent variables necessarily improve in-context
          '2412.12156', -- Deep Distributed Optimization for Large-Scale Quadratic Programming
          '2410.01774', -- Trained Transformer Classifiers Generalize and Exhibit Benign Overfittin
          '2506.05059', -- NIMO: a Nonlinear Interpretable MOdel
          '2508.17550', -- In-Context Algorithm Emulation in Fixed-Weight Transformers
          '2509.24757', -- Accelerating Regression Tasks with Quantum Algorithms
          '2606.12840', -- CLARITree: Cholesky and Lookahead Accelerations for Regression with Inte
          '2604.19033', -- Intentional Updates for Streaming Reinforcement Learning
          '2602.02431', -- Full-Batch Gradient Descent Outperforms One-Pass SGD: Sample Complexity
          '2605.26067', -- Conditional KRR: Injecting Unpenalized Features into Kernel Methods with
          '2504.11304', -- Differentially Private Geodesic Regression
          '2605.01082', -- Networked Information Aggregation for Binary Classification
          '2503.03023', -- Quantum Non-Linear Bandit Optimization
          '2410.12763', -- Gravity-aligned Rotation Averaging with Circular Regression
          '2605.27912', -- Privately Estimating Monotone Statistics in Polynomial Time
          '2609.07868' -- SGD in Multiclass Logistic Regression: Sequential Learning and Scaling L
      )
      OR       (p.source = 'external' AND p.id IN (
          111435, -- Robust Vocal Intensity Prediction: Overcoming Dataset Bias with Pretrain
          111627, -- On Enhancing the Performance of Children''s ASR Task in Limited Data Sce
          124774, -- DeltaMomentum: A Key-Value based Anisotropic Momentum Update via Delta R
          125938 -- Uncertainty as an Underconstrained Axis in Lossy Compression
      ))
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'classic methods curation 2026-11-09: passing mention, baseline only, or another sense (non-linear/generalized regression, fMLLR)'
FROM lr_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING lr_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING lr_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- conjugate-gradient: 29 reviewed true positives of 34 title/abstract candidates.
CREATE TEMP TABLE cg_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'conjugate-gradient'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1908.05884', -- GODS: Generalized One-class Discriminative Subspaces for Anomaly Detecti
          '1910.12680', -- FD-Net with Auxiliary Time Steps: Fast Prediction of PDEs using Hessian-
          '2205.10763', -- A Deep Conjugate Direction Method for Iteratively Solving Linear Systems
          '2209.07219', -- Training Neural Networks in Single vs Double Precision
          '2303.05754', -- Decomposed Diffusion Sampler for Accelerating Large-Scale Inverse Proble
          '2308.10547', -- Decentralized Riemannian Conjugate Gradient Method on the Stiefel Manifo
          '2312.04339', -- Merging by Matching Models in Task Parameter Subspaces
          '2401.12004', -- NLCG-Net: A Model-Based Zero-Shot Learning Framework for Undersampled Qu
          '2406.07831', -- ALPS: Improved Optimization for Highly Sparse One-Shot Pruning for Large
          '2408.17252', -- A Homogeneous Graph Neural Network for Precoding and Power Allocation in
          '2509.06285', -- DCReg: Decoupled Characterization for Efficient Degenerate LiDAR Registr
          '2509.08155', -- Contributions to Robust and Efficient Methods for Analysis of High Dimen
          '2505.13621', -- Bayesian Hierarchical Models for Quantitative Estimates for Performance
          '2305.16432', -- Learning Preconditioner for Conjugate Gradient PDE Solvers
          '1310.1967', -- Comparative Analysis of Numerical Methods for Parameter Determination
          '2603.21528', -- PEARL: Geometry Aligns Semantics for Training-Free Open-Vocabulary Seman
          '2605.09477', -- Outlier-Robust Diffusion Solvers for Inverse Problems
          '2502.04799', -- A Regularized Newton Method for Nonconvex Optimization with Global and L
          '2412.03489', -- Stochastic Gradient Estimation for Higher-Order Differentiable Rendering
          '2310.01766', -- Learning Causal Alignment for Reliable Disease Diagnosis
          '2506.05233', -- MesaNet: Sequence Modeling by Locally Optimal Test-Time Training
          '2510.06179', -- Differentiable Model Predictive Control on the GPU
          '2605.24395', -- AvAtar: Learning to Align via Active Optimal Transport
          '2606.03391', -- When Model Merging Breaks Routing: Training-Free Calibration for MoE
          '2504.12905', -- Matrix-free Second-order Optimization of Gaussian Splats with Residual S
          '2603.28475', -- Tac2Real: Reliable and GPU Visuotactile Simulation for Online Reinforcem
          '2605.06081' -- Fast Gauss-Newton for Multiclass Cross-Entropy
      )
      OR       (p.source = 'external' AND p.id IN (
          126300, -- A Transformer-Derived Iterative Preconditioner
          128688 -- GCD: GCM-consistent Diffusion for Zero-shot Downscaling across Heterogen
      ))
  );

DELETE FROM paper_method_exclusions x
USING cg_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM cg_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM cg_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- conjugate-gradient: 5 reviewed negatives.
CREATE TEMP TABLE cg_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'conjugate-gradient'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2310.20581', -- Stochastic Gradient Descent for Gaussian Processes Done Right
          '2505.13723', -- Turbocharging Gaussian Process Inference with Approximate Sketch-and-Pro
          '2406.05938', -- Expressive Power of Graph Neural Networks for (Mixed-Integer) Quadratic
          '2605.18591' -- Randomized Advantage Transformation (RAT): Computing Natural Policy Grad
      )
      OR       (p.source = 'external' AND p.id IN (
          105110 -- Direct Inversion Formula of the Multi-coil MR Operator under Arbitrary T
      ))
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'classic methods curation 2026-11-09: mentions conjugate gradient only as a baseline or alternative'
FROM cg_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING cg_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING cg_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- independent-component-analysis: 23 reviewed true positives of 46 title/abstract candidates.
CREATE TEMP TABLE ica_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'independent-component-analysis'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2209.05578', -- Cocktail Party Attack: Breaking Aggregation-Based Privacy in Federated L
          '2311.04056', -- Multi-View Causal Representation Learning with Partial Observability
          '2403.00777', -- Combating Financial Crimes with Unsupervised Learning Techniques: Cluste
          '2406.09556', -- $S^3$ -- Semantic Signal Separation
          '2409.07326', -- ART: Artifact Removal Transformer for Reconstructing Noise-Free Multicha
          '2409.19813', -- Transforming Hidden States into Binary Semantic Features
          '2512.19399', -- Brain-Grounded Axes for Reading and Steering LLM States
          '2602.10893', -- Deep and Sparse Denoising Benchmarks for Spectral Data Cubes of High-z G
          '2303.09336', -- Image Enhancement for Remote Photoplethysmography in a Low-Light Environ
          '2508.03102', -- Causal Disentanglement and Cross-Modal Alignment for Enhanced Few-Shot L
          '2503.23896', -- Feature learning from non-Gaussian inputs: the case of Independent Compo
          '2406.14302', -- Identifiable Exchangeable Mechanisms for Causal Structure and Representa
          '2510.13583', -- On the Identifiability of Causal Graphs with the Invariance Principle
          '2603.11970', -- Statistical and structural identifiability in representation learning
          '2606.11722', -- ICA Lens: Interpreting Language Models Without Training Another Dictiona
          '2605.03517', -- Understanding Self-Supervised Learning via Latent Distribution Matching
          '2601.21696', -- Independent Component Discovery in Temporal Count Data
          '2607.23182', -- Beyond ICA: Identifiability by Symmetry Breaking
          '2610.20851', -- Complete or Sparse: A Tale of Two Identifiabilities
          '2406.19581' -- Quasi-Linear ICA for Motor Unit Decomposition during Dynamic Contraction
      )
      OR       (p.source = 'external' AND p.id IN (
          111485, -- Heart Rate as a Proxy Measure to Assess Human Confidence in Spoken Speec
          124216, -- Exact Recovery of Lipschitz Orthogonal Coordinate Transformations via Co
          129297 -- Causal Discovery from Unseen Environments
      ))
  );

DELETE FROM paper_method_exclusions x
USING ica_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ica_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ica_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- independent-component-analysis: 23 reviewed negatives.
CREATE TEMP TABLE ica_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'independent-component-analysis'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1511.06281', -- Density Modeling of Images using a Generalized Normalization Transformat
          '1908.06843', -- ProSper -- A Python Library for Probabilistic Sparse Coding with Non-Sta
          '2302.13334', -- Knowledge Restore and Transfer for Multi-label Class-Incremental Learnin
          '2305.19582', -- Causal Discovery with Latent Confounders Based on Higher-Order Cumulants
          '2308.07737', -- Identity-Consistent Aggregation for Video Object Detection
          '2310.06387', -- Jailbreak and Guard Aligned Language Models with Only Few In-Context Dem
          '2402.00570', -- CADICA: a new dataset for coronary artery disease detection by using inv
          '2409.15179', -- MIMAFace: Face Animation via Motion-Identity Modulated Appearance Featur
          '2412.01254', -- EmojiDiff: Advanced Facial Expression Control with High Identity Preserv
          '2510.11000', -- ContextGen: Contextual Layout Anchoring for Identity-Consistent
          '2602.10863', -- ICA: Information-Aware Credit Assignment for Visually Grounded Long-Hori
          '1803.10172', -- Distributed Adaptive Sampling for Kernel Matrix Approximation
          '0903.1979', -- Semantic learning in autonomously active recurrent neural networks
          '2508.10133', -- MANGO: Multimodal Attention-based Normalizing Flow Approach to Fusion Le
          '2410.21869', -- Cross-Entropy Is All You Need To Invert the Data Generating Process
          '2406.03337', -- Identifying latent state transitions in non-linear dynamical systems
          '2510.14459', -- Holdout-Loss-Based Data Selection for LLM Finetuning via In-Context Lear
          '2509.13832', -- UltraHiT: A Hierarchical Transformer Architecture for Generalizable Inte
          '2502.20115', -- Multi-View Causal Discovery without Non-Gaussianity: Identifiability and
          '2507.16679', -- PICACO: Pluralistic In-Context Value Alignment via Total Correlation Opt
          '2610.09457', -- DSReg: Provably Recovering Individual World Latents without Reconstructi
          '2606.18509' -- Concept Modulation Models: A Unified Framework for Identifiability and E
      )
      OR       (p.source = 'external' AND p.id IN (
          120620 -- ABC-Former: Auxiliary Bimodal Cross-domain Transformer with Interactive
      ))
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'classic methods curation 2026-11-09: passing ICA mention, or ICA abbreviates something else'
FROM ica_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING ica_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING ica_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- self-organizing-map: 9 reviewed true positives of 11 title/abstract candidates.
CREATE TEMP TABLE som_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'self-organizing-map'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1810.09597', -- Biomedical Document Clustering and Visualization based on the Concepts o
          '2101.04197', -- Clustering Word Embeddings with Self-Organizing Maps. Application on LaR
          '2104.14870', -- Action in Mind: A Neural Network Approach to Action Recognition and Segm
          '2601.02005', -- Euclid: Improving redshift distribution reconstruction using a deep-to-w
          '2511.08379', -- SOM Directions are Better than One: Multi-Directional Refusal Suppressio
          '2412.10183', -- A catalogue of complex radio sources in the Rapid ASKAP Continuum Survey
          '2407.05800', -- FedMRL: Data Heterogeneity Aware Federated Multi-agent Deep Reinforcemen
          '2606.29403' -- Self-Organized Conformal Prediction: Reducing Regional Coverage Gaps wit
      )
      OR       (p.source = 'external' AND p.id IN (
          115304 -- SOM2LM: Self-Organized Multi-Modal Longitudinal Maps
      ))
  );

DELETE FROM paper_method_exclusions x
USING som_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM som_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM som_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- self-organizing-map: 2 reviewed negatives.
CREATE TEMP TABLE som_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'self-organizing-map'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2412.04418', -- ACE2-SOM: Coupling to a slab ocean and learning the sensitivity of
          '2506.22696' -- Residual Matrix Transformers: Scaling the Size of the Residual Stream
      )
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'classic methods curation 2026-11-09: SOM/Kohonen names something else (slab ocean model, associative memory)'
FROM som_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING som_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING som_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- random-projection: 54 reviewed true positives of 72 title/abstract candidates.
CREATE TEMP TABLE rp_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'random-projection'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1806.10805', -- Beyond One-hot Encoding: lower dimensional target embedding
          '1908.11512', -- Fast and Accurate Network Embeddings via Very Sparse Random Projection
          '2106.15307', -- Deep Random Projection Outlyingness for Unsupervised Anomaly Detection
          '2204.01800', -- The Fast Johnson-Lindenstrauss Transform is Even Faster
          '2208.08503', -- Learning with Local Gradients at the Edge
          '2212.09058', -- BEATs: Audio Pre-Training with Acoustic Tokenizers
          '2305.14585', -- Faithful and Efficient Explanations for Neural Networks via Neural Tange
          '2310.14481', -- Efficient Heterogeneous Graph Learning via Random Projection
          '2402.03293', -- Flora: Low-Rank Adapters Are Secretly Gradient Compressors
          '2410.15352', -- CompAct: Compressed Activations for Memory-Efficient LLM Training
          '2412.05270', -- APOLLO: SGD-like Memory, AdamW-level Performance
          '2502.20293', -- Scalable Graph Attention-based Instance Selection via Mini-Batch Samplin
          '2504.07448', -- LoRI: Reducing Cross-Task Interference in Multi-Task Low-Rank Adaptation
          '2510.26491', -- Data-Efficient RLVR via Off-Policy Influence Guidance
          '2603.26110', -- TurboESM: Ultra-Efficient 3-Bit KV Cache Quantization for Protein Langua
          '2603.19145', -- Enhancing Pretrained Model-based Continual Representation Learning via G
          '2601.16651', -- Select or Project? Evaluating Lower-dimensional Vectors for LLM Training
          '2511.18519', -- CHIPS: Efficient CLIP Adaptation via Curvature-aware Hybrid Influence-ba
          '2510.08396', -- FlyLoRA: Boosting Task Decoupling and Parameter Efficiency via Implicit
          '2507.08254', -- Raptor: Scalable Train-Free Embeddings for 3D Medical Volumes Leveraging
          '2505.22042', -- Estimating the Effects of Sample Training Orders for Large Language
          '2505.00105', -- Optimization of embeddings storage for RAG systems using quantization
          '2408.13106', -- NEST: Self-supervised Fast Conformer as All-purpose Seasoning to Speech
          '2406.03482', -- QJL: 1-Bit Quantized JL Transform for KV Cache Quantization with Zero Ov
          '2303.05786', -- Vertical Federated Graph Neural Network for Recommender System
          '2506.05398', -- 2ndMatch: Finetuning Pruned Diffusion Models via Second-Order Jacobian M
          '2605.28034', -- Clark Hash: Stateless Sparse Johnson-Lindenstrauss Quantization for Neur
          '2506.08645', -- Fusing Cross-modal and Uni-modal Representations: A Kronecker Product Ap
          '2505.14083', -- Computational Efficiency under Covariate Shift in Kernel Ridge Regressio
          '2507.16345', -- The Cost of Compression: Tight Quadratic Black-Box Attacks on Sketches f
          '2502.13583', -- Fundamental Bias in Inverting Random Sampling Matrices with Application
          '2506.19220', -- Private Model Personalization Revisited
          '2212.06605', -- Dimensionality Reduction on Complex Vector Spaces for Euclidean Distance
          '2410.08003', -- More Experts Than Galaxies: Conditionally-Overlapping Experts with Biolo
          '2410.17263', -- An Effective Theory of Bias Amplification
          '2404.10148', -- Node Similarities under Random Projections: Limits and Pathological Case
          '2503.01720', -- Quality Measures for Dynamic Graph Generative Models
          '2410.04840', -- Strong Model Collapse
          '2510.04008', -- RACE Attention: A Strictly Linear-Time Attention Layer for Training on O
          '2410.04922', -- Random-projection ensemble dimension reduction
          '2509.22307', -- Johnson-Lindenstrauss Lemma Guided Network for Efficient 3D Medical Segm
          '2606.04180', -- KODA: Contrastive Representation Comparison and Alignment for Vision-Lan
          '2602.14761', -- Universal Algorithm-Implicit Learning
          '2602.06071', -- FlashSketch: Sketch-Kernel Co-Design for Fast Sparse Sketching on GPUs
          '2511.16575', -- ECPv2: Fast, Efficient, and Scalable Global Optimization of Lipschitz Fu
          '1708.00630', -- ProjectionNet: Learning Efficient On-Device Deep Networks Using Neural P
          '2606.10406', -- FOGO: Forgetting-aware Orthogonalization Optimizer
          '2605.15571', -- MaxSketch: Robust Distinct Counting in Streams via Random Projections
          '2605.13810' -- Provable Quantization with Randomized Hadamard Transform
      )
      OR       (p.source = 'external' AND p.id IN (
          124258, -- Rubato: Signature Attention for Irregular Multivariate Time Series Forec
          125030, -- Deployment-Time Online Imitation Learning from Corrective Demonstrations
          127011, -- Fast Approximate $\ell_p$ Chamfer Distance via Lopsided Embeddings and S
          129182, -- Random-Projection Tree Stein Variational Gradient Descent
          130091 -- High-Dimensional Conditional Independence Testing via Random Projection
      ))
  );

DELETE FROM paper_method_exclusions x
USING rp_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM rp_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM rp_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- random-projection: 18 reviewed negatives.
CREATE TEMP TABLE rp_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'random-projection'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2006.01475', -- Light-in-the-loop: using a photonics co-processor for scalable training
          '2006.08812', -- Augmented Sliced Wasserstein Distances
          '2012.06373', -- Hardware Beyond Backpropagation: a Photonic Co-Processor for Direct Feed
          '2101.02115', -- Adversarial Robustness by Design through Analog Computing and Synthetic
          '2106.03645', -- Photonic Differential Privacy with Direct Feedback Alignment
          '2106.11168', -- From Unsupervised to Semi-supervised Anomaly Detection Methods for HRRP
          '2301.13856', -- Simplex Random Features
          '2412.00071', -- COAP: Memory-Efficient Training with Correlation-Aware Gradient Projecti
          '2501.01108', -- MuQ: Self-Supervised Music Representation Learning with Mel Residual Vec
          '2501.17836', -- Matrix Product Sketching via Coordinated Sampling
          '2501.18901', -- Lightspeed Geometric Dataset Distance via Sliced Optimal Transport
          '2410.01316', -- Fast Summation of Radial Kernels via QMC Slicing
          '2505.20274', -- Probabilistic Kernel Function for Fast Angle Testing
          '2510.19382', -- A Derandomization Framework for Structure Discovery: Applications in Neu
          '2605.03373', -- Learning Dynamics of Zeroth-Order Optimization: A Kernel Perspective
          '2601.22784', -- Approximating f -Divergences with Rank Statistics
          '2601.21929', -- LoRIF: Low-Rank Influence Functions for Scalable Training Data Attributi
          '2609.07681' -- On the Recall Scaling Laws in Mamba: A Theoretical and Mechanistic Study
      )
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'classic methods curation 2026-11-09: passing mention, sliced 1-D projections, or random feedback matrices rather than random-projection dimensionality reduction'
FROM rp_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING rp_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING rp_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- model-predictive-control: 203 reviewed true positives of 264 title/abstract candidates.
CREATE TEMP TABLE mpc_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'model-predictive-control'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1812.00568', -- Visual Foresight: Model-Based Deep Reinforcement Learning for Vision-Bas
          '2009.11997', -- Continual Model-Based Reinforcement Learning with Hypernetworks
          '2104.11478', -- Inductive biases and Self Supervised Learning in modelling a physical he
          '2109.04821', -- KNODE-MPC: A Knowledge-based Data-driven Predictive Control Framework fo
          '2203.04955', -- Temporal Difference Learning for Model Predictive Control
          '2203.08072', -- Neural Solvers for Fast and Accurate Numerical Optimal Control
          '2205.10940', -- Toward smart composites: small-scale, untethered prediction and control
          '2209.08073', -- Case Studies for Computing Density of Reachable States for Safe Autonomo
          '2209.12016', -- Mastering the Unsupervised Reinforcement Learning Benchmark from Pixels
          '2304.00069', -- On stochastic MPC formulations with closed-loop guarantees: Analysis and
          '2306.08205', -- Agile Catching with Whole-Body MPC and Blackbox Policy Learning
          '2306.08647', -- Language to Rewards for Robotic Skill Synthesis
          '2306.16700', -- Dynamic-Resolution Model Learning for Object Pile Manipulation
          '2309.05131', -- Signal Temporal Logic Neural Predictive Control
          '2310.07220', -- COPlanner: Plan to Roll Out Conservatively but to Explore Optimistically
          '2310.13258', -- ManiCast: Collaborative Manipulation with Cost-Aware Human Forecasting
          '2310.16659', -- Multi-Agent Reinforcement Learning-Based UAV Pathfinding for Obstacle Av
          '2310.16723', -- Harmonic model predictive control for tracking sinusoidal references and
          '2310.16828', -- TD-MPC2: Scalable, Robust World Models for Continuous Control
          '2312.05332', -- MPC-Inspired Reinforcement Learning for Verifiable Model-Free Control
          '2312.17227', -- Gradient-based Planning with World Models
          '2402.01116', -- Scalable Multi-modal Model Predictive Control via Duality-based Interact
          '2402.11450', -- Learning to Learn Faster from Human Feedback with Language Model Predict
          '2407.01418', -- RoboPack: Learning Tactile-Informed Dynamics Models for Dense Packing
          '2407.16680', -- A Simulation Benchmark for Autonomous Racing with Large-Scale Human Data
          '2410.07484', -- WALL-E: World Alignment by Rule Learning Improves World Model-based LLM
          '2410.17195', -- Non-myopic Generation of Language Models for Reasoning and Planning
          '2412.16346', -- SOUS VIDE: Cooking Visual Drone Navigation Policies in a Gaussian Splatt
          '2501.02486', -- LLMPC: Large Language Model Predictive Control
          '2502.01366', -- Trajectory World Models for Heterogeneous Environments
          '2503.18871', -- Bootstrapped Model Predictive Control
          '2504.11514', -- Enhancing Autonomous Driving Systems with On-Board Deployed Large Langua
          '2504.15785', -- WALL-E 2.0: World Alignment by NeuroSymbolic Learning improves World Mod
          '2602.23259', -- Risk-Aware World Model Predictive Control for Generalizable End-to-End A
          '2604.03208', -- Hierarchical Planning with Latent World Models
          '2603.26697', -- Physicochemical-Neural Fusion for Semi-Closed-Circuit Respiratory Autono
          '2603.10878', -- RL-Augmented MPC for Non-Gaited Legged and Hybrid Locomotion
          '2602.12794', -- SafeFlowMPC: Predictive and Safe Trajectory Planning for Robot Manipulat
          '2602.01780', -- DDP-WM: Disentangled Dynamics Prediction for Efficient World Models
          '2601.11426', -- Learning-Based Shrinking Disturbance-Invariant Tubes for State- and Inpu
          '2601.03782', -- PointWorld: Scaling 3D World Models for In-The-Wild Robotic Manipulation
          '2512.09929', -- Closing the Train-Test Gap in World Models for Gradient-Based Planning
          '2510.15626', -- Adaptive Legged Locomotion via Online Learning for Model Predictive
          '2509.22441', -- UnderwaterVLA: Dual-brain Vision-Language-Action architecture for
          '2510.03241', -- Efficient MPC-Based Energy Management System for Secure and Cost-Effecti
          '2508.16474', -- Reinforcement Learning-based Control via Y-wise Affine Neural Networks
          '2508.07686', -- Risk Map As Middleware: Towards Interpretable Cooperative End-to-end
          '2506.17184', -- Judo: A User-Friendly Open-Source Package for Sampling-Based Model Predi
          '2506.15249', -- Context-Aware Deep Lagrangian Networks for Model Predictive Control
          '2504.05727', -- SAP-CoPE: Social-Aware Planning using Cooperative Pose Estimation with
          '2411.13983', -- Learning Two-agent Motion Planning Strategies from Generalized Nash
          '2409.15633', -- Intent Prediction-Driven Model Predictive Control for UAV Planning and N
          '2403.18149', -- Code Generation and Conic Constraints for Model-Predictive Control on Mi
          '2401.05057', -- BoundMPC: Cartesian Trajectory Planning with Error Bounds based on Model
          '2310.16985', -- TinyMPC: Model-Predictive Control on Resource-Constrained Microcontrolle
          '2304.07794', -- Nonlinear MPC for Quadrotors in Close-Proximity Flight with Neural Netwo
          '2203.10910', -- Quad2Plane: An Intermediate Training Procedure for Online Exploration in
          '2103.04301', -- DMotion: Robotic Visuomotor Control with Unsupervised Forward Model
          '2102.12124', -- Safe Learning-based Gradient-free Model Predictive Control Based on
          '2604.08031', -- Open-Ended Instruction Realization with LLM-Enabled Multi-Planner Schedu
          '2502.02921', -- Robust Reward Alignment via Hypothesis Space Batch Cutting
          '2507.09177', -- Continual Reinforcement Learning by Planning with Online World Models
          '2410.10253', -- Feedback Favors the Generalization of Neural ODEs
          '2410.04553', -- Bisimulation Metric for Model Predictive Control
          '2503.00653', -- Discrete Codebook World Models for Continuous Control
          '2510.06179', -- Differentiable Model Predictive Control on the GPU
          '2507.21533', -- Model Predictive Adversarial Imitation Learning for Planning from Observ
          '2502.06760', -- Infinite-Horizon Value Function Approximation for Model Predictive Contr
          '2410.20267', -- Learning Maximal Safe Sets Using Hypernetworks for MPC-Based Local Traje
          '2509.19168', -- A Multimodal Stochastic Planning Approach for Navigation and Multi-Robot
          '2605.19209', -- Graph Neural Planning and Predictive Control for Multi-Robot Communicati
          '2603.17632', -- Real-Time Online Learning for Model Predictive Control Using a Spatio-Te
          '2604.06133', -- Learning-Guided Force-Feedback Model Predictive Control with Obstacle Av
          '2602.12095', -- Pack It In: Packing into Partially Filled Containers through Contact
          '2603.17802', -- An HMDP-MPC Decision-Making Framework with Adaptive Safety Margins and H
          '2602.15357', -- Fluoroscopy-Constrained Magnetic Robot Control Via Zernike-Based Field M
          '2410.15946', -- Neural Predictor for Flight Control with Payload
          '2505.13350', -- Approximating Global Contact-Implicit MPC Via Sampling and Local Complem
          '2605.18373', -- Dynamic Robotic Cloth Folding with Efficient Koopman Operator-Based Mode
          '2411.03481', -- Chance-Constrained Convex MPC for Robust Quadruped Locomotion under Para
          '2503.14656', -- Safety-Critical and Distributed Nonlinear Predictive Controllers for Tea
          '2409.01144', -- Adaptive Non-Linear Centroidal MPC with Stability Guarantees for Robust
          '2505.00237', -- Future-Oriented Navigation: Dynamic Obstacle Avoidance with One-Shot Ene
          '2603.00103', -- Autonomous Block Assembly for Boom Cranes with Passive Joint Dynamics: I
          '2604.12149', -- Uncertainty Guided Exploratory Trajectory Optimization for Sampling-Base
          '2603.13733', -- Implicit Maximum Likelihood Estimation for Real-Time Generative Model Pr
          '2510.07725', -- Probabilistically-Safe Bipedal Navigation Over Uncertain Terrain Via Con
          '2506.18689', -- NOVA: Navigation Via Object-Centric Visual Autonomy for High-Speed Targe
          '2508.07387', -- MonoMPC: Monocular Vision Based Navigation with Learned Collision Model
          '2602.16187', -- SIT-LMPC: Safe Information-Theoretic Learning Model Predictive Control f
          '2503.05792', -- Ro-To-Go! Robust Reactive Control with Signal Temporal Logic
          '2510.04278', -- Integrated Planning and Control on Manifolds: Factor Graph Representatio
          '2602.17199', -- Nonlinear Predictive Control of the Continuum and Hybrid Dynamics of a S
          '2603.13732', -- LPV-MPC for Lateral Control in Full-Scale Autonomous Racing
          '2503.08858', -- SICNav-Diffusion: Safe and Interactive Crowd Navigation with Diffusion T
          '2409.10283', -- ASMA: An Adaptive Safety Margin Algorithm for Vision-Language Drone Navi
          '2602.10035', -- A Collision-Free Sway Damping Model Predictive Controller for Safe and R
          '2511.07761', -- High-Altitude Balloon Station-Keeping with First Order Model Predictive
          '2510.11682', -- Ego-Vision World Model for Humanoid Contact Planning
          '2603.23044', -- Learning Actuator-Aware Spectral Submanifolds for Precise Control of Con
          '2510.18845', -- MADR: MPC-Guided Adversarial Deepreach
          '2410.06819', -- Dynamic Neural Potential Field: Online Trajectory Optimization in Presen
          '2506.14855', -- Feedback-MPPI: Fast Sampling-Based MPC Via Rollout Differentiation ? Adi
          '2510.19974', -- Push Anything: Single and Multi-Object Pushing from First Sight with Con
          '2510.04234', -- Flexible Locomotion Learning with Diffusion Model Predictive Control
          '2603.28581', -- A Self-Rotating Tri-Rotor UAV for Field-Of-View Expansion and Autonomous
          '2509.06201', -- Grasp-MPC: Closed-Loop Visual Grasping Via Value-Guided Model Predictive
          '2603.29315', -- IMPASTO: Integrating Model-Based Planning with Learned Dynamics Models f
          '2509.18760', -- Guaranteed Robust Nonlinear MPC Via Disturbance Feedback
          '2603.18400', -- Graph-Of-Constraints Model Predictive Control for Reactive Multi-Agent T
          '2510.16953', -- Safe Payload Transfer with Ship-Mounted Cranes: A Robust Model Predictiv
          '2511.17798', -- SM^2ITH: Safe Mobile Manipulation with Interactive Human Prediction Via
          '2504.08841', -- ES-HPC-MPC: Exponentially Stable Hybrid Perception Constrained MPC for Q
          '2506.07823', -- Primal-Dual iLQR for GPU-Accelerated Learning and Control in Legged Robo
          '2506.01046', -- STATE-NAV: Stability-Aware Traversability Estimation for Bipedal Navigat
          '2502.01916', -- Generalizable and Fast Surrogates: Model Predictive Control of Articulat
          '2506.14341', -- Barrier Method for Inequality Constrained Factor Graph Optimization with
          '2511.19709', -- Whole-Body Inverse Dynamics MPC for Legged Loco-Manipulation
          '2603.08860', -- SEP-NMPC: Safety Enhanced Passivity-Based Nonlinear Model Predictive Con
          '2406.11506', -- Embedded Hierarchical MPC for Autonomous Navigation
          '2507.18138', -- A Modular Residual Learning Framework to Enhance Model-Based Approach fo
          '2511.19204', -- Reference-Free Sampling-Based Model Predictive Control
          '2508.01192', -- Unified Generation-Refinement Planning: Bridging Guided Flow Matching an
          '2509.13109', -- Model Predictive Control with Reference Learning for Soft Robotic Intrac
          '2503.04613', -- Whole-Body Model-Predictive Control of Legged Robots with MuJoCo
          '2509.18466', -- RL-Augmented Adaptive Model Predictive Control for Bipedal Locomotion Ov
          '2602.17601', -- Graph Neural Model Predictive Control for High-Dimensional Systems
          '2603.01898', -- SaferPath: Hierarchical Visual Navigation with Learned Guidance and Safe
          '2506.16565', -- Reimagination with Test-Time Observation Interventions: Distractor-Robus
          '2411.00107', -- First, Learn What You Don''t Know: Active Information Gathering for Driv
          '2407.17013', -- Towards Indirect Data-Driven Predictive Control for Heating Phase of The
          '2409.12374', -- Real-Time Linear MPC for Quadrotors on SE(3): An Analytical Koopman-Base
          '2502.11375', -- Robot Deformable Object Manipulation Via NMPC-Generated Demonstrations i
          '2507.05710', -- DRO-EDL-MPC: Evidential Deep Learning-Based Distributionally Robust Mode
          '2503.04563', -- Occlusion-Aware Consistent Model Predictive Control for Robot Navigation
          '2510.07625', -- GATO: GPU-Accelerated and Batched Trajectory Optimization for Scalable E
          '2511.03077', -- WorldPlanner: Monte Carlo Tree Search and MPC with Action-Conditioned Vi
          '2511.17777', -- See, Plan, Cut: MPC-Based Autonomous Volumetric Robotic Laser Surgery wi
          '2602.05608', -- HiCrowd: Hierarchical Crowd Flow Alignment for Dense Human Environments
          '2502.01924', -- DualGuard MPPI: Safe and Performant Optimal Control by Combining Samplin
          '2408.10450', -- RUMI: Rummaging Using Mutual Information
          '2510.21369', -- Load-Bearing Assessment for Safe Locomotion of Quadruped Robots on Colla
          '2512.03639', -- Context-Triggered Contingency Games for Strategic Multi-Agent Interactio
          '2607.00917', -- Valdi: Value Diffusion World Models
          '2605.04568', -- Dream-MPC: Gradient-Based Model Predictive Control with Latent Imaginati
          '2601.23231', -- Solving Inverse Problems with Flow-based Models via Model Predictive Con
          '2510.04280', -- A KL-regularization framework for learning to plan with adaptive priors
          '2605.10624', -- Hierarchical Causal Abduction: A Foundation Framework for Explainable Mo
          '2606.07974', -- PRISM: PRior-guided Imagination Sampling in world Models
          '2607.25236', -- VisualPatchWorld: Code World Models as Latent Structured Representations
          '2607.25337', -- Temporal-Distance JEPA: Plan-Aware Representation Learning for Latent Wo
          '2512.00375', -- DPNet: Doppler LiDAR Motion Planning for Highly-Dynamic Environments
          '2608.18746', -- Decision-Metric Alignment in Latent World Models: Diagnostics and Action
          '2010.12598', -- A Software Architecture for Autonomous Vehicles: Team LRM-B Entry in the
          '2408.04821', -- VLM-MPC: Vision Language Foundation Model (VLM)-Guided Model Predictive
          '2610.27851', -- LaLa-World: Scaling Latent World Models with Natural Language Actions
          '2505.01353', -- Differentiable Nonlinear Model Predictive Control
          '2601.10418', -- Reinforcement Learning with Multi-Step Lookahead Information Via Adaptiv
          '2608.21175' -- SRL-MPC: Shape-Aware Reinforcement Learned Model Predictive Control
      )
      OR       (p.source = 'external' AND p.id IN (
          95178, -- Distributed NMPC for Cooperative Aerial Manipulation of Cable-Suspended
          95260, -- DexTele: A Dual-Arm Dexterous Teleoperation System Based on Motion Retar
          95286, -- Turning Disturbances into Actuation: Hierarchical Environment-Assisted M
          95384, -- Real-Time Model Predictive Control of Nonlinear Coupled Joints Using MPP
          95462, -- Structure-Exploiting Sequential Quadratic Programming for Model-Predicti
          95478, -- Single-Instance Sampling for Computationally Efficient and Accurate Real
          95492, -- L-BIRD: Lightweight Bio-Inspired Rotary-Wing Drone
          95558, -- Learning What Matters: Task Tailored Dynamics Models through Differentia
          95617, -- Nonlinear Model Predictive Control for Robotic Pushing of Planar Objects
          95630, -- Plantar Compensation Via Dynamic Control of Pneumatic Insoles for Flatfo
          95660, -- A Nonlinear MPC for Physical Human-Aerial Robot Interaction in Collabora
          95691, -- Path Tracking Control for a Transformable Wheel-Legged Robot Using Model
          95696, -- Approximated Collision Detection for Contact-Rich Dexterous Manipulation
          95736, -- Viper: Verifiable Imitation Learning Policy for Efficient Robotic Manipu
          95902, -- Fully Distributed Real-Time MPC for Cooperative Mobile Manipulation Via
          95914, -- Multi-Robot Segregation Using Finite-Time MPC with Chernoff Bound-Based
          95976, -- Risk-Aware and Scalable Hierarchical Motion Planning for Large-Scale Rob
          95987, -- Actuator Dynamics-Aware Model Predictive Control of a Wheeled Inverted P
          96010, -- Manipulator-Effort-Aware MPC for Body Motion Coordination of an Underwat
          96019, -- Disturbance-Adaptive Differentiable MPC for Underwater Structure Inspect
          96044, -- CoorGrasp: Coordinated Contact Control for Adaptive Dexterous Grasping u
          96436, -- SLOT-MPC: A Hierarchical Whole-Body Model Predictive Controller to Enhan
          96462, -- Receding Horizon Control for Signal Temporal Logic Using Robustness-Cons
          96921, -- Vertical-Plane Locomotion Control of a High-Speed Robotic Tuna Via NMPC
          96932, -- Time-Series Data-Driven Three Dimensional Shape Control of Deformable Li
          96982, -- Robust Bipedal Walking with Closed-Loop MPC: Adios Stabilizers
          97076, -- In-Situ Automated Robotic Crown Preparation with MPC-Based Adaptive Cont
          97260, -- Obstacle-Aware IBVS Target Tracking Via Feature-Space Projection and Vir
          97358, -- A Neuro-Inspired Control Architecture to Enhance Robot Self-Preservation
          97367, -- Predictive Admittance Control for Aerial Physical Interaction
          97415, -- Risk-Aware Control of Tendon-Driven Continuum Robots Via CVaR-MPPI with
          97475, -- Robust Sensitivity-Aware Chance-Constrained MPC for Efficient Handling o
          97479, -- Time-Optimal Trajectory Planning and Model Predictive Control of Morphin
          97484, -- SM-NMPC: Sliding Mode-Based Nonlinear Model Predictive Control for UAVs
          97505, -- Prompt-To-State Stable Vision-Language MPC for Approximated Neural Netwo
          97553, -- Receding Horizon Reinforcement Learning with Autoregressive Model for Mo
          97630, -- A Model Predictive Control Approach to Blending in Shared Control
          97666, -- Optimizing Vehicle Trajectories at a Signalized Intersection in Mixed Tr
          97728, -- SA-MPPI: Sensitivity-Aware Model Predictive Path Integral Control for Ro
          97871, -- Inverse Reachability Map Guided Motion Planning of Mobile Manipulator
          124505, -- Neural Compression of Long ADMM Trajectory for Multiparametric Quadratic
          124899, -- Hierarchical World Models with Implicit Dynamics
          125421, -- Predicting What Changes: Causal Delta World Models for Risk-Aware LLM Ag
          128910 -- From POMDP Theory to Deep RL with Particle Filters
      ))
  );

DELETE FROM paper_method_exclusions x
USING mpc_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mpc_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM mpc_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- model-predictive-control: 61 reviewed negatives.
CREATE TEMP TABLE mpc_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'model-predictive-control'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '1910.09434', -- Towards a Reinforcement Learning Environment Toolbox for Intelligent Ele
          '2004.02229', -- FALCON: Honest-Majority Maliciously Secure Framework for Private Deep Le
          '2211.01452', -- MPCFormer: fast, performant and private Transformer inference with MPC
          '2211.13955', -- MPCViT: Searching for Accurate and Efficient MPC-Friendly Vision Transfo
          '2303.04212', -- ConBaT: Control Barrier Transformer for Safe Policy Learning
          '2303.10327', -- Hybrid Systems Neural Control with Region-of-Attraction Planner
          '2305.04533', -- Prompted LLMs as Chatbot Modules for Long Open-domain Conversation
          '2305.11290', -- Massively Scalable Inverse Reinforcement Learning in Google Maps
          '2306.07510', -- Require Process Control? LSTMc is all you need!
          '2307.12533', -- PUMA: Secure Inference of LLaMA-7B in Five Minutes
          '2309.03057', -- Hide and Seek (HaS): A Lightweight Framework for Prompt Privacy Protecti
          '2310.00433', -- Active-Perceptive Motion Generation for Mobile Manipulation
          '2311.12955', -- Don''t forget private retrieval: distributed private similarity search f
          '2410.03035', -- SPINE: Online Semantic Planning for Missions with Incomplete Natural Lan
          '2412.00084', -- Unpacking the Individual Components of Diffusion Policy
          '2502.16920', -- SS-MPC: A Sequence-Structured Multi-Party Conversation System
          '2602.06445', -- ECO: Energy-Constrained Optimization with Reinforcement Learning for Hum
          '2511.16297', -- Optimizing Operation Recipes with Reinforcement Learning for Safe and In
          '2509.23960', -- MAD-PINN: A Decentralized Physics-Informed Machine Learning Framework fo
          '2505.21851', -- Streaming Flow Policy: Simplifying diffusion/flow-matching policies by t
          '2502.00560', -- Solving Football by Exploiting Equilibrium Structure of 2p0s
          '2501.06807', -- MPCache: MPC-Friendly KV Cache Eviction for Efficient Private Large
          '2309.00242', -- A Massively Parallel Dynamic Programming for Approximate Rectangle
          '2303.04137', -- Diffusion Policy: Visuomotor Policy Learning via Action Diffusion
          '2302.11601', -- Real-Time Navigation for Autonomous Surface Vehicles In Ice-Covered
          '2509.21729', -- New Parallel and Streaming Algorithms for Directed Densest Subgraph
          '2509.09001', -- Fast attention mechanisms: a tale of parallelism
          '2509.01254', -- What Expressivity Theory Misses: Message Passing Complexity for GNNs
          '2506.15307', -- SecP-Tuning: Efficient Privacy-Preserving Prompt Tuning for Large Langua
          '2509.20917', -- Efficient Differentiable Contact Model with Long-range Influence
          '2508.21065', -- Learning on the Fly: Rapid Policy Adaptation Via Differentiable Simulati
          '2510.20174', -- Reinforcement Learning-Based Robust Wall Climbing Locomotion Controller
          '2507.02438', -- Minimal Intervention Shared Control with Guaranteed Safety under Non-Con
          '2603.25395', -- UMBRELLA: Uncertainty-Aware Multi-Robot Reactive Coordination under Dyna
          '2504.09021', -- A Champion-Level Vision-Based Reinforcement Learning Agent for Competiti
          '2604.09993', -- GPU-Accelerated Continuous-Time Successive Convexification for Contact-I
          '2512.03256', -- KALIKO: Kalman-Implicit Koopman Operator Learning for Prediction of Nonl
          '2507.01125', -- VISTA: Open-Vocabulary, Task-Relevant Robot Exploration with Online Sema
          '2505.00488', -- MULE ? Multi-Terrain and Unknown Load Adaptation for Effective Quadruped
          '2603.05108', -- GaussTwin: Unified Simulation and Correction with Gaussian Splatting for
          '2507.18809', -- Test-time Offline Reinforcement Learning on Goal-related Experience
          '2603.01986', -- Accurate, Private, Secure, Federated U-statistics with Higher Degree
          '2605.03288', -- Neural Control: Adjoint Learning Through Equilibrium Constraints
          '2506.02080', -- Enhancing GOP in CTC-Based Mispronunciation Detection with Phonological
          '2409.05414', -- CipherDM: Secure Three-Party Inference for Diffusion Model Sampling
          '2609.20669', -- Learning Foresight without Explicit Trajectories for 3D Diffusion Polici
          '2603.18624', -- REST: Receding Horizon Explorative Steiner Tree for Zero-Shot Object-Goa
          '2610.25043', -- VLA-Rolling: Fewer Denoising Steps, Better Control via Adaptive Action R
          '2603.01891', -- SEAR: Sample Efficient Action Chunking Reinforcement Learning
          '2606.15359', -- DiRecT: Safe Diffusion-Based Planning via Receding-Horizon Denoising
          '2610.01742' -- World Motion Models: Flexible Sequence Modeling of SE(3) Trajectories
      )
      OR       (p.source = 'external' AND p.id IN (
          96033, -- Closed-Loop Trajectory Optimization of Deformable Linear Objects for Dyn
          96999, -- QP-Based Inner-Loop Control for Constraint-Safe and Robust Trajectory Tr
          97000, -- Overcoming Explicit Environment Representations with Geometric Fabrics
          104247, -- Removing Bottlenecks: Training Generalist Robotics Policies for the BEHA
          112796, -- Phase Concentration and Shortcut Suppression for Weakly Supervised Seman
          120599, -- Noise-Resistant Video Anomaly Detection via RGB Error-Guided Multiscale
          124500, -- CipherFlow: Hardware-Aware Compiler Framework for Low-Latency Hybrid Sec
          124677, -- Learning Digital Twins under Drift: Optimal Tracking Rates for Non-Stati
          126119, -- Q-CoMove: Differentiable Quantum Circuit Priors for Coordinated Motion i
          126159 -- SeqDiCO: Sequence-oriented Diffusion for Scale-Generalizable Neural Comb
      ))
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'classic methods curation 2026-11-09: passing mention or baseline, receding-horizon execution of a learned policy, or MPC abbreviates something else (multi-party computation, massively parallel computation)'
FROM mpc_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING mpc_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING mpc_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
-- Method image credits (figures imported with import_entity_image.py).
UPDATE methods SET image_credit = '[Linear regression](https://commons.wikimedia.org/wiki/File:Linear_regression.svg), Sewaqu, public domain' WHERE slug = 'linear-regression';
UPDATE methods SET image_credit = '[Conjugate gradient illustration](https://commons.wikimedia.org/wiki/File:Conjugate_gradient_illustration.svg), Oleg Alexandrov, public domain' WHERE slug = 'conjugate-gradient';
UPDATE methods SET image_credit = '[BSS-example](https://commons.wikimedia.org/wiki/File:BSS-example.png), Novarank, CC BY-SA 4.0' WHERE slug = 'independent-component-analysis';
UPDATE methods SET image_credit = '[Somtraining](https://commons.wikimedia.org/wiki/File:Somtraining.svg), Mcld, CC BY-SA 3.0' WHERE slug = 'self-organizing-map';
UPDATE methods SET image_credit = '[Deep Random Projection Outlyingness for Unsupervised Anomaly Detection](/paper/2106.15307)' WHERE slug = 'random-projection';
UPDATE methods SET image_credit = '[MPC scheme basic](https://commons.wikimedia.org/wiki/File:MPC_scheme_basic.svg), Martin Behrendt, CC BY-SA 3.0' WHERE slug = 'model-predictive-control';
