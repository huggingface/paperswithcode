-- Add Continuous Language Model method (continuous diffusion and flow language models).
-- Umbrella method for the field mapped by the survey site
-- https://continuous-lm.github.io/ (Tang, Lee, Eijkelboom, Kim, 2026). There is no
-- single introducing paper: embedding, simplex, bit and latent-space variants appeared
-- in parallel in 2022, so source_paper_id stays NULL (no reference backfill, no
-- Introduced banner). source_url links the field survey's local paper page
-- instead (an external paper whose PDF is hosted on alphaXiv).
-- It replaces the narrower continuous-diffusion-language-model method (removed in
-- remove_continuous_diffusion_language_model_method.sql).
--
-- Paper links: every arXiv paper on https://continuous-lm.github.io/map/ plus papers
-- reviewed from keyword matches and local citers of seminal continuous LM papers.
-- Run with a raw DBAPI cursor (titles in comments).

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'continuous-language-model',
    'Continuous Language Model',
    'Continuous Diffusion and Flow Language Model',
    'Continuous language models generate text by transforming noise into continuous representations of tokens (vocabulary embeddings, simplex or one-hot vectors, bits, or autoencoder latents) and decoding the result into tokens, instead of predicting one token at a time or corrupting tokens directly like discrete [Diffusion Language Models](/methods/diffusion-language-model-dlm). They are trained with Gaussian [diffusion](/methods/diffusion) or [Flow Matching](/methods/flow-matching), and their deterministic trajectories allow few-step distillation and gradient-based guidance.',
    'continuous language model, continuous diffusion and flow language model, continuous flow language model, flow matching language model, flow map language model, continuous text diffusion, embedding diffusion language model, simplex diffusion language model, latent diffusion language model',
    (SELECT id FROM areas WHERE name IN ('Language', 'Natural Language Processing')
     ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END LIMIT 1),
    NULL,
    NULL,
    (SELECT '/paper/' || id FROM papers WHERE source = 'external'
     AND source_url = 'https://www.alphaxiv.org/abs/2611.continuous-diffusion-flow-language-models.pdf'
     ORDER BY id DESC LIMIT 1),
    'A Survey on Continuous Diffusion and Flow Language Models',
    NULL,
    NULL,
    '[Flow Map Language Models: One-step Language Modeling via Continuous Denoising](/paper/2602.16813)',
    'judge',
    ARRAY['Continuous Diffusion Language Model', 'Continuous Flow Language Model', 'Flow Language Model', 'Flow Map Language Model']
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

CREATE TEMP TABLE clm_papers ON COMMIT DROP AS
SELECT DISTINCT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'continuous-language-model'
  AND p.is_latest_version
  AND (
      p.source_url = 'https://www.alphaxiv.org/abs/2611.continuous-diffusion-flow-language-models.pdf'
      OR p.arxiv_id IN (
        '2205.14217', -- Diffusion-lm improves controllable text generation
        '2208.00638', -- Composable Text Controls in Latent Space with ODEs
        '2208.04202', -- Analog bits: Generating discrete data using diffusion models with self-condition
        '2210.08933', -- Diffuseq: Sequence to sequence text generation with diffusion models
        '2210.17432', -- Ssd-lm: Semi-autoregressive simplex-based diffusion language model for text gene
        '2211.04236', -- Self-conditioned embedding diffusion for text generation
        '2211.15089', -- Continuous diffusion for categorical data
        '2212.09412', -- Empowering Diffusion Models on the Embedding Space for Text Generation
        '2212.09462', -- Latent diffusion for language generation
        '2212.10325', -- Seqdiffuseq: Text diffusion with encoder-decoder transformers
        '2212.11685', -- Text generation with diffusion language models: A pre-training approach with con
        '2302.10025', -- DINOISER: Diffused Conditional Sequence Learning by Manipulating Noises
        '2304.04746', -- A Cheaper and Better Diffusion Language Model with Soft-Masked Noise
        '2304.12519', -- GlyphDiffusion: Text Generation as Image Generation
        '2305.08379', -- Tess: Text-to-text self-conditioned simplex diffusion
        '2305.09515', -- AR-diffusion: Auto-regressive diffusion model for text generation
        '2305.10699', -- Dirichlet diffusion score model for biological sequence generation
        '2305.10818', -- Diffusion Language Models Generation Can Be Halted Early
        '2305.11517', -- DiffuSIA: A Spiral Interaction Architecture for Encoder-Decoder Text Diffusion
        '2305.14771', -- David helps goliath: Inference-time collaboration between small specialized and
        '2305.18619', -- Likelihood-Based Diffusion Language Models
        '2306.02531', -- Planner: Generating diversified paragraph via latent language diffusion model
        '2308.07037', -- Bayesian Flow Networks
        '2308.15459', -- ParaGuide: Guided Diffusion Paraphrasers for Plug-and-Play Textual Style Transfe
        '2310.05793', -- DiffuSeq-v2: Bridging Discrete and Continuous Text Spaces for Accelerated Seq2Se
        '2310.11976', -- InfoDiffusion: Information Entropy Aware Diffusion Process for Non-Autoregressiv
        '2310.17680', -- CodeFusion: A Pre-trained Diffusion Model for Code Generation
        '2402.05841', -- Dirichlet Flow Matching with Applications to DNA Sequence Design
        '2402.07754', -- Diffusion of Thoughts: Chain-of-Thought Reasoning in Diffusion Language Models
        '2402.14843', -- Text Diffusion with Reinforced Conditioning
        '2402.19097', -- Tencdm: Understanding the properties of the diffusion model in the space of lang
        '2403.03726', -- Diffusion on Language Model Encodings for Protein Sequence Generation
        '2403.16995', -- LanguageFlow: Advancing Diffusion Language Generation with Probabilistic Flows
        '2404.10763', -- LaDiC: Are Diffusion Models Really Inferior to Autoregressive Counterparts for I
        '2405.14664', -- Fisher Flow Matching for Generative Modeling over Discrete Data
        '2406.04843', -- Variational flow matching for graph generation
        '2408.04220', -- Diffusion guided language modeling
        '2411.16821', -- Logit-KL Flow Matching: Non-Autoregressive Text Generation
        '2411.17248', -- DiffSLT: Enhancing Diversity in Sign Language Translation via Diffusion Model
        '2412.08821', -- Large Concept Models: Language Modeling in a Sentence Representation Space
        '2412.11333', -- Segment-Level Diffusion: A Framework for Controllable Long-Form Generation with
        '2502.11564', -- Continuous Diffusion Model for Language Modeling
        '2502.13917', -- TESS 2: A Large-Scale Generalist Diffusion Language Model
        '2503.17361', -- Gumbel-Softmax Flow Matching with Straight-Through Guidance for Controllable Bio
        '2504.10983', -- ProtFlow: Fast Protein Sequence Design via Flow Matching on Compressed Protein L
        '2505.18853', -- Smoothie: Smoothing Diffusion on Token Embeddings for Text Generation
        '2505.22165', -- Unifying Continuous and Discrete Text Diffusion with Non-simultaneous Diffusion
        '2506.00290', -- DLM-One: Diffusion Language Models for One-Step Sequence Generation
        '2506.10892', -- The Diffusion Duality
        '2506.21170', -- Cosmos: Compressed and smooth latent space for text diffusion modeling
        '2507.00425', -- Flexible Language Modeling in Continuous Space with Transformer-based Autoregres
        '2510.01329', -- Continuously Augmented Discrete Diffusion Model for Categorical Generative Model
        '2510.03206', -- Coevolutionary Continuous Discrete Diffusion: Make Your Diffusion Language Model
        '2510.04573', -- LaDiR: Latent Diffusion Enhances LLMs for Text Reasoning
        '2510.22510', -- CANDI: Hybrid Discrete-Continuous Diffusion Models
        '2510.27688', -- Continuous Autoregressive Language Models
        '2512.15923', -- A Unification of Discrete, Gaussian, and Simplicial Diffusion
        '2512.21323', -- Parallel Token Prediction for Language Models
        '2602.01705', -- Beyond Mode Elicitation: Diversity-Preserving RL via Latent Diffusion Reasoner
        '2602.02425', -- Repurposing Protein Language Models for Latent Flow-Based Fitness Optimization
        '2602.12233', -- Categorical flow maps
        '2602.12468', -- Continuous Diffusion Models Can Obey Formal Syntax
        '2602.16169', -- Discrete Stochastic Localization for Non-autoregressive Generation
        '2602.16813', -- Flow map language models: One-step language modeling via continuous denoising
        '2602.18647', -- Noise Scheduling as Information-Guided Allocation in Diffusion Training
        '2603.02547', -- Codar: Continuous diffusion language models are more powerful than you think
        '2603.20210', -- CRoCoDiL: Continuous and Robust Conditioned Diffusion for Language
        '2603.20589', -- Generating from Discrete Distributions Using Diffusions: Insights from Random Co
        '2603.22216', -- Gumbel Distillation for Parallel Text Generation
        '2604.02028', -- Why Gaussian Diffusion Models Fail on Discrete Data and How to Prevent It?
        '2604.02718', -- Generative frontiers: Why evaluation matters for diffusion language models
        '2604.05551', -- FastDiSS: Few-step Match Many-step Diffusion Language Model on Sequence-to-Seque
        '2604.09784', -- Discrete flow maps
        '2604.11748', -- LangFlow: Continuous Diffusion Rivals Discrete in Language Modeling
        '2604.27147', -- How to guide your flow: Few-step alignment via flow map reward guidance
        '2605.05629', -- Spherical Flows for Sampling Categorical Data
        '2605.06548', -- Continuous latent diffusion language model
        '2605.06885', -- Don''t Retrain, Align: Adapting Autoregressive LMs to Diffusion LMs via Represen
        '2605.07013', -- CoBit: Language Modeling with Bitstream Diffusion
        '2605.07193', -- Coupling Models for One-Step Discrete Generation
        '2605.07748', -- TextLDM: Language Modeling with Continuous Latent Diffusion
        '2605.07820', -- Scaling Categorical Flow Maps
        '2605.07933', -- How to train your latent diffusion language model jointly with the latent space
        '2605.10938', -- Elf: Embedded language flows
        '2605.11125', -- Language modeling with hyperspherical flows
        '2605.11577', -- BitLM: Unlocking Multi-Token Language Generation with Bitwise Continuous Diffusi
        '2605.14368', -- Where Should Diffusion Enter a Language Model?
        '2605.14531', -- Language Generation as Optimal Control: Closed-Loop Diffusion in Latent Control
        '2605.18530', -- Continuous diffusion scales competitively with discrete diffusion for language
        '2605.19376', -- Generative recursive reasoning
        '2605.20199', -- FlowLM: Few-Step Language Modeling via Diffusion-to-Flow Adaptation
        '2605.23605', -- DiLaDiff: Distilled Latent-Augmented Diffusion for Language Modeling
        '2606.01024', -- DSL-LLaDA: Scaling Continuous Denoising to 8B Masked Diffusion LMs
        '2606.08417', -- Hacking Generative Perplexity: Why Unconditional Text Evaluation Needs New Metri
        '2606.08810', -- Continuous Language Diffusion as a Decoder-Interface Problem
        '2606.24773', -- Posterior Refinement: Fast Language Generation via Any-Order Flow Maps
        '2606.27617', -- Masked Language Flow Models
        '2606.29066', -- $x$-Prediction Flow: Efficient Continuous Decoding for Masked Diffusion Language
        '2606.29150', -- Flow Reasoning Models: Turning Flows Into Efficient Recurrent Reasoners
        '2607.00588', -- A Dominant Self-Conditioning Direction Drives Repetition in Unconditional Contin
        '2607.00714', -- Self-conditioned Flow Map Language Models via Fixed-point Flows
        '2607.10951', -- Sticky Jump Diffusions: A Unifying Framework for Discrete, Continuous, and Hybri
        '2607.14106', -- Token Time Continuous Diffusion for Language Modeling
        '2607.21585', -- Expanding Flow Maps
        '2608.01240', -- DeltaFlow: Noise-Adaptive Bidirectional Gated Delta Networks for Embedded Langua
        '2608.01692', -- Beckmann Transport Models: From Autonomous Flows to One-Step Maps
        '2608.02602', -- AURORA-LM: Autoencoding Unified Representation for Continuous-Latent Diffusion L
        '2608.10615', -- Simplex Relaxation for Discrete Diffusion
        '2608.22244', -- Improving Few-Step Language Flows with Untied Self-Conditioning
        '2608.23551', -- Convergeflow: Language flow with provable convergence to token embeddings
        '2609.11801', -- Thinking with Looped Flows
        '2609.15903', -- Discrete Beckmann Transport Models for One-Step Language Modeling and Reasoning
        '2609.19356', -- How to Guide Your Language Flow
        '2609.29102', -- ELF-REG: Scaling Continuous Diffusion Language Models to Reasoning Tasks
        '2609.33698', -- One Latent, Many Tokens: Jointly Learning Compressed Embeddings for Efficient La
        '2609.35553', -- Simplex Diffusion Models
        '2609.40235', -- Distribution Matching Distillation for Continuous Diffusion Language Models
        '2609.40362', -- Multimodal Flow: Unified Flow Modeling of Language and Vision in Embedding Space
        '2610.00497', -- Gumbel Straight Flow: Distilling Autoregressive Models into One-step Flow Maps
        '2610.00894', -- Clock Diffusion: Efficient Semi-Autoregressive Continuous Diffusion Language Mod
        '2610.01016', -- Scaling and Distilling Text Embeddings for Better Diffusibility
        '2610.02193', -- Hierarchical Continuous Diffusion Language Models
        '2610.02665', -- Large Language Continuous Diffusion Models
        '2610.04454', -- One-Step Generation via Riemannian Wasserstein Gradient Flows
        '2610.06513', -- SOL: Measuring Gaps between Text Distributions by Double Sliced Wasserstein Metr
        '2610.06648', -- Representation-Space MMD for Diffusion Language Models
        '2610.06666', -- What Matters for Latent Reasoning with Flow Matching
        '2610.08738', -- Denoising Hierarchical Representations: Joint Continuous Diffusion for Language
        '2610.09311', -- Denoising Blocks, Not Tokens: Efficient Compressed Continuous Diffusion with Bra
        '2610.09416', -- Efficient Reasoning with Flow Language Models
        '2610.12879', -- One-Step Text Generation by Seq-Drifting
        '2610.12898', -- Rethinking the Roles of Diffusion and Decoding: Predictive-State Flows for Paral
        '2610.13834', -- On the Design Space of Continuous Diffusion Language Models
        '2610.14349', -- Multimodal Co-Generation With Continuous Bitstream Diffusion
        '2610.19080', -- Backpropagating Verifier Rewards Through Continuous Flow Language Models
        '2610.22330', -- Designing Transformers for Continuous Diffusion Language Models
        '2610.24365', -- FlashMap: Flow Map Speculative Decoding
        '2610.26693', -- Parallel Language Models via Variational Decoding
        '2610.27641', -- BCT: Bayes-Consistent Tempering for Flow Language Models
        '2610.28559', -- Large Flow Language Models
        '2610.28801', -- JUICE: Unified Multimodal Modeling in Pretrained Representation Spaces
        '2610.28905', -- Hidden Messages Between Diffusion Language Model Agents
        '2610.29136', -- GRAFT: Restoring the Missing Sampling Interface in Continuous Diffusion Language
        '2610.31305', -- Cola2: Co-Adaptive Hierarchical Language Modeling with Continuous Semantic Compr
        '2610.32604', -- LLaCO: Continuous Diffusion for Large Language Models with Competition-Aware Sem
        '2610.33811', -- Rectified Language Flow
        '2610.35101', -- Spherical Brownian Diffusion for Language Modeling
        '2610.37115', -- Self-Regularized Flow Language Models
        '2610.42018', -- Asynchronous Flow Map Language Models
        '2610.42084' -- RangeSWA: Training-Free Length Extrapolation for Continuous Diffusion Language M
      )
  );

DELETE FROM paper_method_exclusions x
USING clm_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM clm_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM clm_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO NOTHING;
