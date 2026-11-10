-- Method gap fill (2026-11-10 audit), group F: interpretability and AI safety.
-- Seven widely used techniques were missing from the catalog. None has a single
-- uncontested introducing paper, so source_paper_id stays NULL, source_url
-- points to a canonical reference or explainer (a local /paper/ page where one
-- exists), and no "Introduced" banner is added. The hourly reference backfill
-- skips methods without a source paper.
--
-- Provenance notes:
-- * activation-patching: causal tracing was named by ROME (2202.05262), but
--   interchange interventions (Geiger et al.) and causal mediation analysis of
--   neurons (Vig et al., 2020) came earlier, so ROME is credited, not sourced.
-- * logit-lens: introduced in a 2020 LessWrong post by nostalgebraist; the Tuned
--   Lens (2303.08112) is a learned refinement, kept as a keyword and credited in
--   the description rather than as an alias.
-- * model-editing: ENN (2004.00345), KnowledgeEditor, MEND, ROME and MEMIT all
--   shaped the area; no single source.
-- * red-teaming / jailbreak: broad practices predating any paper; Perez et al.
--   (2202.03286), Ganguli et al. (2209.07858) and Wei et al. (2307.02483) are
--   credited. The existing `gcg` method is one specific jailbreak attack.
-- * prompt-injection: named by Simon Willison (Sep 2022) after Riley Goodside's
--   demonstrations; Perez & Ribeiro (2211.09527) and Greshake et al.
--   (2302.12173, indirect prompt injection) are credited.
-- No task covers jailbreak, red teaming or prompt injection; the explainable-ai
-- task lists "mechanistic interpretability" as a task keyword, which is a
-- different taxonomy and is left unchanged.
--
-- Keywords tag papers through the daily keyword backfill, so they are limited to
-- exact long-form names. Paper links were curated from every local
-- title/abstract candidate of a broader regex than the keywords; true positives
-- get 'manual' evidence and reviewed negatives (passing mentions, benchmark or
-- organization names, other senses such as 3D-model editing or soft-prompt
-- injection) become durable exclusions. Hero images were imported separately
-- with import_entity_image.py; this file records their credits.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES
(
    'mechanistic-interpretability',
    'Mechanistic Interpretability',
    'Mechanistic Interpretability',
    'Mechanistic interpretability aims to reverse-engineer the computations a trained neural network performs into human-understandable algorithms, expressed in terms of its internal components: features (directions in activation space), the neurons and attention heads that compute them, and the circuits that connect them. The program grew out of circuits work on vision models by Olah et al. (Distill, 2020) and the Transformer Circuits thread at Anthropic, which described induction heads ([In-context Learning and Induction Heads](/paper/2209.11895)) and polysemanticity through [Toy Models of Superposition](/paper/2209.10652). Its toolkit includes [Activation Patching](/methods/activation-patching) and path patching for causal localization, the [Logit Lens](/methods/logit-lens), [Probing](/methods/probing), automated circuit discovery such as [ACDC](/paper/2304.14997), and dictionary learning with a [Sparse Autoencoder](/methods/sparse-autoencoder) or transcoders to resolve superposition. Landmark case studies include the indirect-object-identification circuit in GPT-2 small ([Interpretability in the Wild](/paper/2211.00593)) and the modular-arithmetic algorithm of grokked Transformers ([Progress measures for grokking](/paper/2301.05217)), and [Causal Abstraction](/paper/2301.04709) offers a formal foundation. Mechanistic findings feed model editing, [Representation Engineering](/methods/representation-engineering) and steering, and AI-safety auditing.',
    'mechanistic interpretability',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    NULL,
    'https://distill.pub/2020/circuits/zoom-in/',
    'Zoom In: An Introduction to Circuits (Olah et al., 2020)',
    NULL,
    NULL,
    '[Interpretability in the Wild: a Circuit for Indirect Object Identification in GPT-2 small](/paper/2211.00593)',
    'always',
    ARRAY[]::text[]
),
(
    'activation-patching',
    'Activation Patching',
    'Activation Patching',
    'Activation patching localizes the model components responsible for a behavior by running the network on a clean input and a corrupted input that differ only in a key detail, then copying (patching) the activation of a chosen component from one run into the other and measuring how much of the clean behavior, such as the logit of the correct answer, is restored or destroyed. Sweeping the patch over layers, token positions, attention heads and MLPs gives a causal map of where the relevant information is stored and processed. [ROME](/paper/2202.05262) popularized the technique as causal tracing, using noise-corrupted subject tokens to locate factual recall in mid-layer MLPs; closely related interchange interventions come from causal abstraction ([Causal Abstraction](/paper/2301.04709)) and causal mediation analysis. Path patching restricts the intervention to specific paths between components and was used to recover the indirect-object-identification circuit ([Interpretability in the Wild](/paper/2211.00593)), and attribution patching ([AtP*](/paper/2403.00745)) approximates patching with gradients to scale it. [Towards Best Practices of Activation Patching](/paper/2309.16042) and [How to use and interpret activation patching](/paper/2404.15255) discuss corruption methods and metrics. It is a core tool of [Mechanistic Interpretability](/methods/mechanistic-interpretability) and of [Model Editing](/methods/model-editing) methods that locate before they edit.',
    'activation patching, path patching, attribution patching, causal tracing, interchange intervention',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    NULL,
    NULL,
    '/paper/2404.15255',
    'How to use and interpret activation patching (Heimersheim & Nanda, 2024)',
    NULL,
    NULL,
    '[Locating and Editing Factual Associations in GPT](/paper/2202.05262)',
    'always',
    ARRAY['Causal Tracing', 'Interchange Intervention']
),
(
    'logit-lens',
    'Logit Lens',
    'Logit Lens',
    'The logit lens decodes the hidden state of an intermediate Transformer layer directly into a distribution over the vocabulary by applying the model''s final layer norm and unembedding matrix, as if the residual stream at that layer were the last one. Reading these distributions layer by layer shows how a prediction forms and is refined across depth. It was introduced by nostalgebraist in a 2020 LessWrong post on GPT-2. Because intermediate representations drift from the output basis, the plain logit lens is unreliable for some models; the [Tuned Lens](/paper/2303.08112) learns an affine translator per layer to fix this, and related variants decode attention outputs or use a model''s own later layers. The logit lens is a staple of [Mechanistic Interpretability](/methods/mechanistic-interpretability), used to study factual recall, latent multi-hop and chain-of-thought reasoning, whether multilingual models think in English, steering vectors and early exiting, alongside [Activation Patching](/methods/activation-patching) and [Probing](/methods/probing).',
    'logit lens, logit-lens, tuned lens',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2020,
    NULL,
    'https://www.lesswrong.com/posts/AcKRB8wDpdaN6v6ru/interpreting-gpt-the-logit-lens',
    'interpreting GPT: the logit lens (nostalgebraist, 2020)',
    NULL,
    NULL,
    '[Eliciting Latent Predictions from Transformers with the Tuned Lens](/paper/2303.08112)',
    'always',
    ARRAY[]::text[]
),
(
    'model-editing',
    'Model Editing',
    'Model Editing',
    'Model editing, or knowledge editing, changes a trained model''s behavior on a narrow set of inputs, typically updating, inserting or deleting a factual association, without retraining and while leaving unrelated behavior intact. Edits are evaluated for reliability (the edit holds), generalization (it holds for paraphrases and implications) and locality (other knowledge is unchanged). Early work framed it for neural networks generally ([Editable Neural Networks](/paper/2004.00345)); for language models, approaches include hypernetworks that predict weight updates ([MEND](/paper/2110.11309)), locate-then-edit methods that use causal tracing to find and rewrite mid-layer MLP weights ([ROME](/paper/2202.05262), [MEMIT](/paper/2210.07229), [AlphaEdit](/paper/2410.02355)), memory- and adaptor-based editors ([GRACE](/paper/2211.11031)), and in-context editing. Benchmarks such as CounterFact, ZsRE and [MQuAKE](/paper/2305.14795) probe multi-hop ripple effects, and studies report that sequential or lifelong editing can degrade general abilities. [Editing Large Language Models: Problems, Methods, and Opportunities](/paper/2305.13172) surveys the area. Model editing relies on [Activation Patching](/methods/activation-patching) for localization and is related to machine unlearning, [Representation Engineering](/methods/representation-engineering) and [Fine-Tuning](/methods/fine-tuning).',
    'model editing, knowledge editing, editing large language models',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    NULL,
    NULL,
    '/paper/2305.13172',
    'Editing Large Language Models: Problems, Methods, and Opportunities (Yao et al., 2023)',
    NULL,
    NULL,
    '[Editing Large Language Models: Problems, Methods, and Opportunities](/paper/2305.13172)',
    'always',
    ARRAY['Knowledge Editing']
),
(
    'red-teaming',
    'Red Teaming',
    'Red Teaming',
    'Red teaming is the practice of adversarially probing an AI system to discover harmful, unsafe or otherwise undesired behavior before deployment, borrowing the term from military and computer-security exercises in which a red team plays the attacker. For language models, human red teamers write prompts that try to elicit toxic content, dangerous instructions, privacy leaks, bias or policy violations, and the failures they find inform safety training and evaluation; [Red Teaming Language Models to Reduce Harms](/paper/2209.07858) describes a large human effort and released its attack data. Automated red teaming uses a red language model to generate test cases at scale ([Red Teaming Language Models with Language Models](/paper/2202.03286)), optimized with reinforcement learning, curiosity or diversity objectives ([Curiosity-driven Red-teaming](/paper/2402.19464)), multi-round adversarial training ([MART](/paper/2311.07689)) or agentic attackers, and is standardized by benchmarks such as [HarmBench](/paper/2402.04249). Red teaming covers [Jailbreak](/methods/jailbreak) and [Prompt Injection](/methods/prompt-injection) attacks, text-to-image and multimodal models, and tool-using agents, and it is a standard part of frontier-model system cards and AI-control evaluations.',
    'red teaming, red-teaming',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    NULL,
    NULL,
    '/paper/2404.00629',
    'Against The Achilles'' Heel: A Survey on Red Teaming for Generative Models (Lin et al., 2024)',
    NULL,
    NULL,
    '[Red Teaming Language Models with Language Models](/paper/2202.03286)',
    'always',
    ARRAY['Red-Teaming']
),
(
    'jailbreak',
    'Jailbreak',
    'Jailbreak Attack',
    'A jailbreak is an input crafted to make a safety-aligned language model produce content its developers trained it to refuse, such as instructions for dangerous activities. Early jailbreaks were hand-written role-play and persona prompts shared online, such as "Do Anything Now" ([DAN](/paper/2308.03825)). [Jailbroken: How Does LLM Safety Training Fail?](/paper/2307.02483) attributes their success to competing objectives between helpfulness and harmlessness and to mismatched generalization of safety training, for example to Base64 or low-resource languages. Automated attacks include gradient-based adversarial suffixes such as [GCG](/methods/gcg), LLM-driven iterative refinement ([PAIR](/paper/2310.08419), [Tree of Attacks](/paper/2312.02119)), random search and adaptive prompting ([Simple Adaptive Attacks](/paper/2404.02151)), [Best-of-N](/paper/2412.03556) sampling, many-shot and multi-turn attacks, fine-tuning attacks, and white-box methods such as ablating the [refusal direction](/paper/2406.11717) ([Abliteration](/methods/abliteration)). Visual and audio jailbreaks target multimodal models. Defenses include adversarial and safety training, input/output classifiers and guardrails, perplexity filtering and representation-level interventions; benchmarks such as [HarmBench](/paper/2402.04249) and JailbreakBench measure attack success rates. Jailbreaking is a central activity of [Red Teaming](/methods/red-teaming) and is related to [Prompt Injection](/methods/prompt-injection).',
    'jailbreak, jailbreaking, jailbroken, jailbreak attack',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    NULL,
    NULL,
    '/paper/2307.02483',
    'Jailbroken: How Does LLM Safety Training Fail? (Wei et al., 2023)',
    NULL,
    NULL,
    '[Jailbroken: How Does LLM Safety Training Fail?](/paper/2307.02483)',
    'always',
    ARRAY['Jailbreaking']
),
(
    'prompt-injection',
    'Prompt Injection',
    'Prompt Injection',
    'Prompt injection is an attack on applications built around language models in which adversarial text causes the model to follow the attacker''s instructions instead of the developer''s or user''s, exploiting the fact that LLMs process instructions and data in the same token stream. In direct prompt injection the user writes the malicious instruction (for example "ignore previous instructions"), enabling goal hijacking and system-prompt leaking ([Ignore Previous Prompt](/paper/2211.09527)). In indirect prompt injection the instruction is planted in content the model later retrieves, such as web pages, emails, documents or tool outputs, so a third party can steer an LLM-integrated application or agent to exfiltrate data or take unwanted actions ([Not what you''ve signed up for](/paper/2302.12173)). The term was coined by Simon Willison in September 2022 after demonstrations by Riley Goodside. Benchmarks such as [AgentDojo](/paper/2406.13352) and InjecAgent evaluate tool-using agents. Defenses include training models to respect an [instruction hierarchy](/paper/2404.13208) or structured queries ([StruQ](/paper/2402.06363)), detection classifiers and guardrails, and system-level designs that isolate untrusted data. Prompt injection is distinct from but related to [Jailbreak](/methods/jailbreak) attacks and is a focus of [Red Teaming](/methods/red-teaming) for [Agent](/methods/agent) and [RAG](/methods/rag) systems.',
    'prompt injection, prompt-injection, indirect prompt injection',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2022,
    NULL,
    'https://simonwillison.net/2022/Sep/12/prompt-injection/',
    'Prompt injection attacks against GPT-3 (Willison, 2022)',
    NULL,
    NULL,
    '[Not what you''ve signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection](/paper/2302.12173)',
    'always',
    ARRAY['Indirect Prompt Injection']
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
    image_credit = EXCLUDED.image_credit,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

-- mechanistic-interpretability: 265 reviewed true positives of 283 title/abstract candidates.
CREATE TEMP TABLE mi_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'mechanistic-interpretability'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2504.19475', -- Prisma: An Open Source Toolkit for Mechanistic Interpretability in Vision a
          '2602.05859', -- DLM-Scope: Mechanistic Interpretability of Diffusion Language Models via Sp
          '2301.04709', -- Causal Abstraction: A Theoretical Foundation for Mechanistic Interpretabili
          '2501.16496', -- Open Problems in Mechanistic Interpretability
          '2503.06269', -- Using Mechanistic Interpretability to Craft Adversarial Attacks against Lar
          '2505.03368', -- Geospatial Mechanistic Interpretability of Large Language Models
          '2505.20254', -- Position: Mechanistic Interpretability Should Prioritize Feature Consistenc
          '2603.22295', -- Whether, Not Which: Mechanistic Interpretability Reveals Dissociable Affect
          '2601.03047', -- When the Coffee Feature Activates on Coffins: An Analysis of Feature Extrac
          '2308.14179', -- Towards Vision-Language Mechanistic Interpretability: A Causal Tracing Tool
          '2504.13151', -- MIB: A Mechanistic Interpretability Benchmark
          '2301.05217', -- Progress measures for grokking via mechanistic interpretability
          '2304.14997', -- Towards Automated Circuit Discovery for Mechanistic Interpretability
          '2402.05110', -- Opening the AI black box: program synthesis via mechanistic interpretabilit
          '2402.12201', -- Dictionary Learning Improves Patch-Free Circuit Discovery in Mechanistic In
          '2405.10927', -- Using Degeneracy in the Loss Landscape for Mechanistic Interpretability
          '2406.16320', -- What Do VLMs NOTICE? A Mechanistic Interpretability Pipeline for Gaussian-N
          '2407.14494', -- InterpBench: Semi-Synthetic Transformers for Evaluating Mechanistic Interpr
          '2409.10504', -- DILA: Dictionary Label Attention for Mechanistic Interpretability in High-d
          '2411.10950', -- Understanding Multimodal LLMs: the Mechanistic Interpretability of Llava in
          '2503.12730', -- TinySQL: A Progressive Text-to-SQL Dataset for Mechanistic Interpretability
          '2503.20483', -- Dissecting and Mitigating Diffusion Bias via Mechanistic Interpretability
          '2504.07898', -- How do Large Language Models Understand Relevance? A Mechanistic Interpreta
          '2505.14352', -- Towards eliciting latent knowledge from LLMs with mechanistic interpretabil
          '2509.00328', -- Mechanistic interpretability for steering vision-language-action models
          '2601.14004', -- Locate, Steer, and Improve: A Practical Survey of Actionable Mechanistic In
          '2602.16823', -- Formal Mechanistic Interpretability: Automated Circuit Discovery with Prova
          '2603.09988', -- Causally Grounded Mechanistic Interpretability for LLMs with Faithful Natur
          '2602.04902', -- Momentum Attention: The Physics of In-Context Learning and Spectral Forensi
          '2511.05923', -- Causal Tracing of Object Representations in Large Vision Language Models: M
          '2507.08802', -- The Non-Linear Representation Dilemma: Is Causal Abstraction Enough for Mec
          '2507.02559', -- Transformers Don''t Need LayerNorm at Inference Time: Scaling LayerNorm Remo
          '2407.02646', -- A Practical Review of Mechanistic Interpretability for Transformer-Based La
          '2503.10894', -- HyperDAS: Towards Automating Mechanistic Interpretability with Hypernetwork
          '2502.20914', -- Everything, Everywhere, All at Once: Is Mechanistic Interpretability Identi
          '2605.17504', -- A Distributional View for Visual Mechanistic Interpretability: KL-Minimal S
          '2510.00845', -- Mechanistic Interpretability as Statistical Estimation: A Variance Analysis
          '2606.00033', -- Make Mechanistic Interpretability Auditable: A Call to Develop Guidelines v
          '2604.14477', -- Seeing Through Circuits: Faithful Mechanistic Interpretability for Vision T
          '2608.14922', -- SpIn-ViT: Designing a Sparsity-Induced Vision Transformer That Is Mechanist
          '2410.08417', -- Bilinear MLPs enable weight-based mechanistic interpretability
          '2410.11414', -- ReDeEP: Detecting Hallucination in Retrieval-Augmented Generation via Mecha
          '2503.12734', -- In-Context Linear Regression Demystified: Training Dynamics and Mechanistic
          '2508.15882', -- Beyond Transcription: Mechanistic Interpretability in ASR
          '2601.02989', -- Mechanistic Interpretability of Large-Scale Counting in LLMs through a Syst
          '2510.25674', -- Mechanistic Interpretability of RNNs emulating Hidden Markov Models
          '2502.17516', -- A Survey on Mechanistic Interpretability for Multi-Modal Foundation Models
          '2601.19208', -- How Do Transformers Learn to Associate Tokens: Gradient Leading Terms Bring
          '2606.12629', -- Bag of Dims: Training-Free Mechanistic Interpretability via Dimension-Level
          '2507.22928', -- How Does Chain of Thought Think? Mechanistic Interpretability of Chain-of-T
          '2609.35210', -- Understanding On-Policy Distillation: A Mechanistic Interpretability Perspe
          '2605.12639', -- OceanCBM: A Concept Bottleneck Model for Mechanistic Interpretability in Oc
          '2605.13930', -- Mechanistic Interpretability of EEG Foundation Models via Sparse Autoencode
          '2409.13710', -- You can remove GPT2''s LayerNorm by fine-tuning
          '2306.01128', -- Learning Transformer Programs
          '2405.17425', -- From Neurons to Neutrons: A Case Study in Interpretability
          '2410.07656', -- Mechanistic Permutability: Match Features Across Layers
          '2412.04139', -- Monet: Mixture of Monosemantic Experts for Transformers
          '2506.19382', -- Measuring and Guiding Monosemanticity
          '2503.05613', -- A Survey on Sparse Autoencoders: Interpreting the Internal Mechanisms of La
          '2407.08734', -- Transformer Circuit Faithfulness Metrics are not Robust
          '2606.22673', -- Agent MechSuits : Mechanistic Subspace Safety Steering for Multi-Turn CLI A
          '2205.10487', -- Scaling Laws and Interpretability of Learning from Repeated Data
          '2209.10652', -- Toy Models of Superposition
          '2211.00593', -- Interpretability in the Wild: a Circuit for Indirect Object Identification
          '2302.03025', -- A Toy Model of Universality: Reverse Engineering How Networks Learn Group O
          '2305.03452', -- A technical note on bilinear layers for interpretability
          '2309.08600', -- Sparse Autoencoders Find Highly Interpretable Features in Language Models
          '2309.16042', -- Towards Best Practices of Activation Patching in Language Models: Metrics a
          '2310.08744', -- Circuit Component Reuse Across Tasks in Transformer Language Models
          '2310.18969', -- Analyzing Vision Transformers for Image Classification in Class Embedding S
          '2311.12786', -- Mechanistically analyzing the effects of fine-tuning on procedurally define
          '2311.17030', -- Is This the Subspace You Are Looking for? An Interpretability Illusion for
          '2312.09230', -- Successor Heads: Recurring, Interpretable Attention Heads In The Wild
          '2312.16291', -- Observable Propagation: Uncovering Feature Vectors in Transformers
          '2401.12181', -- Universal Neurons in GPT2 Language Models
          '2402.10688', -- Towards Uncovering How Large Language Model Works: An Explainability Perspe
          '2404.07129', -- What needs to go right for an induction head? A mechanistic study of in-con
          '2404.15255', -- How to use and interpret activation patching
          '2405.03205', -- Anchored Answers: Unravelling Positional Bias in GPT-2''s Multiple-Choice Qu
          '2405.10928', -- The Local Interaction Basis: Identifying Computationally-Relevant and Spars
          '2405.12241', -- Identifying Functionally Important Features with End-to-End Sparse Dictiona
          '2405.12522', -- Sparse Autoencoders Enable Scalable and Reliable Circuit Identification in
          '2405.13816', -- Getting More from Less: Large Language Models are Good Spontaneous Multilin
          '2405.13868', -- Automatically Identifying Local and Global Circuits with Linear Computation
          '2406.11944', -- Transcoders Find Interpretable LLM Feature Circuits
          '2406.16235', -- Preference Tuning For Toxicity Mitigation Generalizes Across Languages
          '2406.17759', -- Interpreting Attention Layer Outputs with Sparse Autoencoders
          '2407.00886', -- Efficient Automated Circuit Discovery in Transformers using Contextual Deco
          '2407.14499', -- Discover-then-Name: Task-Agnostic Concept Bottlenecks via Automated Concept
          '2410.06981', -- Quantifying Feature Space Universality Across Large Language Models via Spa
          '2410.09223', -- The Same But Different: Structural Similarities and Differences in Multilin
          '2410.12949', -- Mechanistic Unlearning: Robust Knowledge Unlearning and Editing via Mechani
          '2410.13708', -- On the Role of Attention Heads in Large Language Model Safety
          '2410.20526', -- Llama Scope: Extracting Millions of Features from Llama-3.1-8B with Sparse
          '2412.04703', -- Transformers Struggle to Learn to Search
          '2412.12841', -- Benchmarking and Understanding Compositional Relational Reasoning of LLMs
          '2412.14133', -- Performance Gap in Entity Knowledge Extraction Across Modalities in Vision
          '2412.17626', -- Tracking the Feature Dynamics in LLM Training: A Mechanistic Study
          '2501.02362', -- Easing Optimization Paths: a Circuit Perspective
          '2501.15740', -- Propositional Interpretability in Artificial Intelligence
          '2501.18838', -- Partially Rewriting a Transformer in Natural Language
          '2502.09135', -- Interpreting and Steering Protein Language Models through Sparse Autoencode
          '2502.12131', -- Transformer Dynamics: A neuroscientific approach to interpretability of lar
          '2503.01773', -- Why Is Spatial Reasoning Hard for VLMs? An Attention Mechanism Perspective
          '2504.04264', -- Lost in Multilinguality: Dissecting Cross-lingual Factual Inconsistency in
          '2504.08016', -- Emergence of psychopathological computations in large language models
          '2504.12585', -- Identifying and Mitigating the Influence of the Prior Distribution in Large
          '2504.14218', -- Understanding the Repeat Curse in Large Language Models from a Feature Pers
          '2505.16538', -- Mechanistic Understanding and Mitigation of Language Confusion in English-C
          '2505.19440', -- The Birth of Knowledge: Emergent Features across Time, Space, and Scale in
          '2506.07985', -- Rethinking Crowd-Sourced Evaluation of Neuron Explanations
          '2506.10423', -- PAL: Probing Audio Encoders via LLMs -- A Study of Information Transfer fro
          '2506.10920', -- Decomposing MLP Activations into Interpretable Features via Semi-Nonnegativ
          '2506.14002', -- Taming Polysemanticity in LLMs: Provable Feature Recovery via Sparse Autoen
          '2506.20790', -- Stochastic Parameter Decomposition
          '2507.12990', -- Teach Old SAEs New Domain Tricks with Boosting
          '2510.13251', -- Map the Flow: Revealing Hidden Pathways of Information in VideoLLMs
          '2601.10825', -- Reasoning Models Generate Societies of Thought
          '2601.21996', -- Mechanistic Data Attribution: Tracing the Training Origins of Interpretable
          '2602.07080', -- CodeCircuit: Toward Inferring LLM-Generated Code Correctness via Attributio
          '2602.22600', -- Transformers converge to invariant algorithmic cores
          '2603.06854', -- Are Audio-Language Models Listening? Audio-Specialist Heads for Adaptive Au
          '2604.02605', -- Do Audio-Visual Large Language Models Really See and Hear?
          '2604.21691', -- There Will Be a Scientific Theory of Deep Learning
          '2604.11061', -- Pando: Do Interpretability Methods Work When Models Won''t Explain Themselve
          '2604.06005', -- Disentangling MLP Neuron Weights in Vocabulary Space
          '2603.25052', -- Closing the Confidence-Faithfulness Gap in Large Language Models
          '2603.19460', -- GeoLAN: Geometric Learning of Latent Explanatory Directions in Large Langua
          '2603.14923', -- Directional Routing in Transformers
          '2603.08234', -- The Struggle Between Continuation and Refusal: A Mechanistic Analysis of th
          '2602.22253', -- AR&D: A Framework for Retrieving and Describing Concepts for Interpreting A
          '2602.18262', -- Simplifying Outcomes of Language Model Component Analyses with ELIA
          '2602.14759', -- Inner Loop Inference for Pretrained Transformers: Unlocking Latent Capabili
          '2602.12026', -- Protein Circuit Tracing via Cross-layer Transcoders
          '2602.10437', -- Control Reinforcement Learning: Interpretable Token-Level Steering of LLMs
          '2602.10168', -- EVA: Towards a universal model of the immune system
          '2602.04613', -- Disentangling meaning from language in LLM-based machine translation
          '2602.00924', -- Supervised sparse auto-encoders as unconstrained feature models for semanti
          '2601.12879', -- Hierarchical Sparse Circuit Extraction from Billion-Parameter Language Mode
          '2512.10805', -- Interpretable and Steerable Concept Bottleneck Sparse Autoencoders
          '2512.08892', -- Toward Faithful Retrieval-Augmented Generation with Sparse Autoencoders
          '2511.20798', -- Physics Steering: Causal Control of Cross-Domain Concepts in a Physics Foun
          '2511.13653', -- Weight-sparse transformers have interpretable circuits
          '2511.08379', -- SOM Directions are Better than One: Multi-Directional Refusal Suppression i
          '2511.07002', -- Automated Circuit Interpretation via Probe Prompting
          '2510.25776', -- StreetMath: Study of LLMs'' Approximation Behaviors
          '2510.18900', -- Foundation Models for Discovery and Exploration in Chemical Space
          '2510.14936', -- Circuit Insights: Towards Interpretability Beyond Activations
          '2510.03366', -- Disentangling Recall and Reasoning in Transformer Models through Layer-wise
          '2510.02629', -- Evaluation Framework for Highlight Explanations of Context Utilisation in L
          '2402.02619', -- Understanding Addition and Subtraction in Transformers
          '2510.01048', -- Interpreting Language Models Through Concept Descriptions: A Survey
          '2509.20784', -- Towards Atoms of Large Language Models
          '2509.18136', -- From Parameters to Performance: A Data-Driven Study on LLM Structure and De
          '2509.03738', -- Sparse Autoencoder Neural Operators: Model Recovery in Function Spaces
          '2508.21258', -- RelP: Faithful and Efficient Circuit Discovery via Relevance Patching
          '2508.16652', -- Do VLMs Have Bad Eyes? Diagnosing Compositional Failures via Mechanistic In
          '2508.15807', -- KL-based self-distillation for large language models
          '2508.09019', -- Activation Steering for Bias Mitigation: An Interpretable Approach to Safer
          '2507.12950', -- Insights into a radiology-specialised multimodal large language model with
          '2506.07691', -- Training Superior Sparse Autoencoders for Instruct Models
          '2505.13737', -- Causal Head Gating: A Framework for Interpreting Roles of Attention Heads i
          '2503.24277', -- Evaluating and Designing Sparse Autoencoders by Approximating Quasi-Orthogo
          '2502.17514', -- SAE-V: Interpreting Multimodal Models for Enhanced Alignment
          '2502.04878', -- Sparse Autoencoders Do Not Find Canonical Units of Analysis
          '2406.13564', -- HumorDB: Can AI understand graphical humor?
          '2605.19908', -- Where Does Authorship Signal Emerge in Encoder-Based Language Models?
          '2605.27354', -- Guiding LLM Post-training Data Engineering with Model Internals from Sparse
          '2511.17699', -- Understanding Counting Mechanisms in Large Language and Vision-Language Mod
          '2601.06338', -- Circuit Mechanisms for Spatial Relation Generation in Diffusion Transformer
          '2509.23323', -- LLM Interpretability with Identifiable Temporal-Instantaneous Representatio
          '2411.04105', -- A Implies B: Circuit Analysis in LLMs for Propositional Logical Reasoning
          '2505.22411', -- Mitigating Overthinking in Large Reasoning Models via Manifold Steering
          '2504.15473', -- Emergence and Evolution of Interpretable Concepts in Diffusion Models
          '2502.03618', -- The Logical Implication Steering Method for Conditional Interventions on Tr
          '2407.13594', -- Validating Mechanistic Interpretations: An Axiomatic Approach
          '2410.06331', -- Locate-then-edit for Multi-hop Factual Recall under Knowledge Editing
          '2502.11812', -- Towards Understanding Fine-Tuning Mechanisms of LLMs via Circuit Analysis
          '2506.05774', -- Evaluating Neuron Explanations: A Unified Framework with Sanity Checks
          '2502.01954', -- Constrained Belief Updates Explain Geometric Structures in Transformer Repr
          '2503.02080', -- Linear Representations of Political Perspective Emerge in Large Language Mo
          '2410.07476', -- Towards a Unified and Verified Understanding of Group-Operation Networks
          '2511.04638', -- Addressing divergent representations from causal interventions on neural ne
          '2603.30002', -- Tracking Equivalent Mechanistic Interpretations Across Neural Networks
          '2509.23684', -- Hedonic Neurons: A Mechanistic Mapping of Latent Coalitions in Transformer
          '2605.14075', -- Rethinking Layer Relevance in Large Language Models Beyond Cosine Similarit
          '2501.17727', -- Automated Interpretability Metrics Do Not Distinguish Trained and Random Tr
          '2506.16975', -- Latent Concept Disentanglement in Transformer-based Language Models
          '2603.09972', -- From Data Statistics to Feature Geometry: How Correlations Shape Superposit
          '2508.01916', -- Decomposing Representation Space into Interpretable Subspaces with Unsuperv
          '2507.12553', -- Is This Just Fantasy? Language Model Representations Reflect Human Judgment
          '2509.20977', -- CLUE: Conflict-guided Localization for LLM Unlearning Framework
          '2606.06664', -- Inside the Visual Mind: Neuroscience-Motivated Concept Circuits for Interpr
          '2505.18441', -- DB-KSVD: Scalable Alternating Optimization for Disentangling High-Dimension
          '2603.23268', -- SafeSeek: Universal Attribution of Safety Circuits in Language Models
          '2602.13524', -- Singular Vectors of Attention Heads Align with Features
          '2602.15183', -- Seeing to Generalize: How Visual Data Corrects Binding Shortcuts
          '2602.01605', -- Universal Redundancies in Time Series Foundation Models
          '2602.07050', -- Interpreting Physics in Video World Models
          '2506.15199', -- Interpretability and Generalization Bounds for Learning Spatial Physics
          '2602.23164', -- MetaOthello: A Controlled Study of Multiple World Models in Transformers
          '2601.13548', -- Patterning: The Dual of Interpretability
          '2604.08764', -- Revisiting Anisotropy in Language Transformers: The Geometry of Learning Dy
          '2602.16740', -- Quantifying LLM Attention-Head Stability: Implications for Circuit Universa
          '2601.22818', -- Hide and Seek in Embedding Space: Geometry-based Steganography and Detectio
          '2602.22968', -- Certified Circuits: Stability Guarantees for Mechanistic Circuits
          '2606.08236', -- Shared Semantics, Divergent Mechanisms: Unsupervised Feature Discovery by A
          '2602.22719', -- Interpreting and Steering State-Space Models via Activation Subspace Bottle
          '2606.19353', -- Quantifying Aleatoric Uncertainty of In-Context Learning for Robust Measure
          '2604.25167', -- From Insight to Action: A Novel Framework for Interpretability-Guided Data
          '2602.07930', -- Patches of Nonlinearity: Instruction Vectors in Large Language Models
          '2606.01243', -- Unlocking the Black Box of Latent Reasoning: An Interpretability-Guided App
          '2604.22345', -- Preference Heads in Large Language Models: A Mechanistic Framework for Inte
          '2607.10034', -- MLPs are Hebbians: Constructing Efficient Fact-Storing MLPs for Transformer
          '2603.23301', -- Steering LLMs for Culturally Localized Generation
          '2602.04718', -- Towards Isolated Interventions via Almost Orthogonal Features in Language M
          '2604.13950', -- Causal Drawbridges: Characterizing Gradient Blocking of Syntactic Islands i
          '2604.24302', -- Differentiable Faithfulness Alignment for Cross-Model Circuit Transfer
          '2509.05309', -- ProtSAE: Disentangling and Interpreting Protein Language Models via Semanti
          '2608.19338', -- Mechanistic Tomography: Designed Measurement for Control-Oriented Interpret
          '2608.22614', -- What AstroPT knows about galaxies, and what that can teach us about LLMs
          '2503.08200', -- Route Sparse Autoencoder to Interpret Large Language Models
          '2509.18792', -- Beyond the Leaderboard: Understanding Performance Disparities in Large Lang
          '2609.03026', -- ObserverBench: Testing Mechanistic Estimates for Intervention and Control
          '2609.09113', -- SAEScientist-Bench: Can AI Agents Conduct Autonomous SAE Interpretability R
          '2511.22697', -- Mechanistic Finetuning of Vision-Language-Action Models via Few-Shot Demons
          '2607.02494', -- Towards Robustness against Typographic Attack with Training-free Concept Lo
          '2605.19792', -- Mechanisms of Object Localization in Vision-Language Models
          '2610.09087', -- U-Space: Uncovering When and Why Uncertainty Arises in Language Models
          '2605.14694', -- The Rate-Distortion-Polysemanticity Tradeoff in SAEs
          '2605.08298', -- What Cohort INRs Encode, and Where to Freeze Them
          '2601.15441', -- CASL: Concept-Aligned Sparse Latents for Interpreting Diffusion Models
          '2605.21849', -- Geometry-Adaptive Explainer for Faithful Dictionary-Based Interpretability
          '2606.15796', -- DifFRACT: Diffusion Feature Reconstruction and Attribution for Circuit Trac
          '2602.13483', -- Finding Interpretable Prompt-Specific Circuits in Language Models
          '2610.20851', -- Complete or Sparse: A Tale of Two Identifiabilities
          '2610.04905', -- ScopeSAE: Model-Scope Feature Discovery with Interpretable Layer Selection
          '2608.26419', -- Interpreting Latent Protein Language Model Features with Geometric Annotati
          '2605.06076', -- Navigating by Old Maps: The Pitfalls of Static Mechanistic Localization in
          '2605.17204', -- Event-Grounded Sparse Autoencoders for Vision-Language-Action Policies
          '2606.09899', -- When Attribution Patching Lies: Diagnosis and a Second-Order Correction
          '2608.05158', -- Safe Evolution with Circuit Anchors
          '2608.24065', -- Mechanistic Circuit Identification for Controllable Data Generation
          '2606.27510', -- The Curse of Multiple Mediators: Hidden Interaction Effects in Activation P
          '2609.07681' -- On the Recall Scaling Laws in Mamba: A Theoretical and Mechanistic Study vi
      )
      OR
      (p.source = 'external' AND p.id IN (
          128690, -- SASA: Subspace-Aware Sparse Autoencoders for Effective Mechanistic Interpre
          127593, -- A Mechanistic Interpretability Study of an Astronomical Foundation Model
          120782, -- Global Information Thresholding for Sufficient and Necessary Circuits
          124367, -- From Outcome to Representation: Tracing Reasoning Mechanisms through Integr
          125728, -- Mechanistic Insights into LoRA: Layer Sparsity for Adaptive Fine-Tuning via
          128627, -- Parasite Features: Causal Abstraction Through Spurious Pathways
          83337, -- Transformers Linearly Represent Highly Structured World Models
          110900, -- Toward Efficient Sparse Autoencoder-Guided Steering for Improved In-Context
          111110, -- A Simple Yet Effective Method for Non-Refusing Context Relevant Fine-graine
          125369, -- Towards Multi-Human-Value Alignment via Value Localization in LLMs
          126045, -- The PFAD Not Taken: Measuring Polysemanticity via Feature Affine Decomposit
          127436, -- What Do SAE Features Encode? Evidence from Human Neural Activity
          128344, -- Circuit-Level Knowledge Distillation for Large Language Models
          129843, -- How do Small Transformer Models Learn Hard Math Tasks?
          130017, -- Matryoshka Transcoders and Hierarchy Misalignment: When SAE Absorption Prot
          130220, -- Is a Linear Probe Evidence of a Linear Representation?
          130223, -- Do You CARE to Generalize? Extracting Robust Concept Directions from LLMs
          130667, -- What Arranges Features in Activation Space? Non-Classical Predictive Geomet
          131044 -- The parameters in weight-sparse transformers are interpretable
      ))
  );

DELETE FROM paper_method_exclusions x
USING mi_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM mi_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM mi_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- mechanistic-interpretability: 18 reviewed negatives.
CREATE TEMP TABLE mi_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'mechanistic-interpretability'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2311.08360', -- The Transient Nature of Emergent In-Context Learning in Transformers
          '2402.12219', -- Reformatted Alignment
          '2410.09637', -- ReLU''s Revival: On the Entropic Overload in Normalization-Free Large Langua
          '2504.17017', -- Neural Theorem Proving: Generating and Structuring Proofs for Formal Verifi
          '2601.22203', -- Beyond Conditional Computation: Retrieval-Augmented Genomic Foundation Mode
          '2509.20935', -- GALAX: Graph-Augmented Language Model for Explainable Reinforcement-Guided
          '2507.10624', -- Comprehension Without Competence: Architectural Limits of LLMs in Symbolic
          '2603.17809', -- Fine-Grained Post-Training Quantization for Large Vision Language Models wi
          '2412.20292', -- An analytic theory of creativity in convolutional diffusion models
          '2509.19988', -- BioBO: Biology-informed Bayesian Optimization for Perturbation Design
          '2602.05532', -- Split Personality Training: Revealing Latent Knowledge Through Alternate Pe
          '2605.30635', -- CellBRIDGE: Learning Cellular Trajectories via Interaction-Aware Alignment
          '2506.22740', -- Explanations are a Means to an End: Decision Theoretic Explanation Evaluati
          '2604.12806' -- Interpretable Relational Inference with LLM-Guided Symbolic Dynamics Modeli
      )
      OR
      (p.source = 'external' AND p.id IN (
          126136, -- The Neural Race Model
          126524, -- PIGRAM: An Interpretable Patch--Motif Interaction Grammar for Protein--Nucl
          129379, -- Mechanism-Level Chemical Reaction Simulation with Electron Bookkeeping Tran
          130236 -- BASIL-DCM: Biophysical Amortized Scalable Inference for Latent Dynamic Caus
      ))
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'safety methods curation 2026-11-10: passing mention, or mechanistic interpretability in the sense of mechanistic scientific models (biology, chemistry, neuroscience)'
FROM mi_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING mi_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING mi_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- activation-patching: 95 reviewed true positives of 99 title/abstract candidates.
CREATE TEMP TABLE ap_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'activation-patching'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2309.16042', -- Towards Best Practices of Activation Patching in Language Models: Metrics a
          '2310.10348', -- Attribution Patching Outperforms Automated Circuit Discovery
          '2311.17030', -- Is This the Subspace You Are Looking for? An Interpretability Illusion for
          '2404.15255', -- How to use and interpret activation patching
          '2308.14179', -- Towards Vision-Language Mechanistic Interpretability: A Causal Tracing Tool
          '2606.09899', -- When Attribution Patching Lies: Diagnosis and a Second-Order Correction
          '2606.27510', -- The Curse of Multiple Mediators: Hidden Interaction Effects in Activation P
          '2603.13768', -- Causal Tracing of Audio-Text Fusion in Large Audio Language Models
          '2602.05234', -- Faithful Bi-Directional Model Steering via Distribution Matching and Distri
          '2511.05923', -- Causal Tracing of Object Representations in Large Vision Language Models: M
          '2605.24614', -- Measuring the Depth of LLM Unlearning via Activation Patching
          '2606.03085', -- Multi-component Causal Tracing in Large Language Models
          '2410.14155', -- Towards Faithful Natural Language Explanations: A Study Using Activation Pa
          '2603.13652', -- Causal Attribution via Activation Patching
          '2601.00267', -- ActErase: A Training-Free Paradigm for Precise Concept Erasure via Activati
          '2508.21258', -- RelP: Faithful and Efficient Circuit Discovery via Relevance Patching
          '2403.00745', -- AtP*: An efficient and scalable method for localizing LLM behaviour to comp
          '2301.04213', -- Does Localization Inform Editing? Surprising Differences in Causality-Based
          '2301.04709', -- Causal Abstraction: A Theoretical Foundation for Mechanistic Interpretabili
          '2404.03646', -- Locating and Editing Factual Associations in Mamba
          '2411.06424', -- Beyond Toxic Neurons: A Mechanistic Analysis of DPO for Toxicity Reduction
          '2603.22295', -- Whether, Not Which: Mechanistic Interpretability Reveals Dissociable Affect
          '2505.08265', -- LLM Enhancers for GNNs: An Analysis from the Perspective of Causal Mechanis
          '2604.22166', -- Fine-Grained Analysis of Shared Syntactic Mechanisms in Language Models
          '2304.14997', -- Towards Automated Circuit Discovery for Mechanistic Interpretability
          '2307.09458', -- Does Circuit Analysis Interpretability Scale? Evidence from Multiple Choice
          '2401.12631', -- A Reply to Makelov et al. (2023)''s "Interpretability Illusion" Arguments
          '2402.12201', -- Dictionary Learning Improves Patch-Free Circuit Discovery in Mechanistic In
          '2402.18154', -- Cutting Off the Head Ends the Conflict: A Mechanism for Interpreting and Mi
          '2403.00824', -- Information Flow Routes: Automatically Interpreting Language Models at Scal
          '2403.17806', -- Have Faith in Faithfulness: Going Beyond Circuit Overlap When Finding Model
          '2407.00886', -- Efficient Automated Circuit Discovery in Transformers using Contextual Deco
          '2407.14494', -- InterpBench: Semi-Synthetic Transformers for Evaluating Mechanistic Interpr
          '2410.14405', -- Fact Recall, Heuristics or Pure Guesswork? Precise Interpretations of Langu
          '2412.12841', -- Benchmarking and Understanding Compositional Relational Reasoning of LLMs
          '2502.04577', -- Position-aware Automatic Circuit Discovery
          '2502.09935', -- Precise Parameter Localization for Textual Generation in Diffusion Models
          '2502.20475', -- Promote, Suppress, Iterate: How Language Models Answer One-to-Many Factual
          '2503.12730', -- TinySQL: A Progressive Text-to-SQL Dataset for Mechanistic Interpretability
          '2504.07898', -- How do Large Language Models Understand Relevance? A Mechanistic Interpreta
          '2504.12996', -- SHA256 at SemEval-2025 Task 4: Selective Amnesia -- Constrained Unlearning
          '2505.16002', -- Causal Interventions Reveal Shared Structure Across English Filler-Gap Cons
          '2508.15882', -- Beyond Transcription: Mechanistic Interpretability in ASR
          '2601.11061', -- Spurious Rewards Paradox: Mechanistically Understanding How RLVR Activates
          '2602.11910', -- TADA! Tuning Audio Diffusion Models through Activation Steering
          '2604.19117', -- LLMs Know They''re Wrong and Agree Anyway: The Shared Sycophancy-Lying Circu
          '2602.16698', -- Causality is Key for Interpretability Claims to Generalise
          '2603.09988', -- Causally Grounded Mechanistic Interpretability for LLMs with Faithful Natur
          '2602.10382', -- Triggers Hijack Language Circuits: A Mechanistic Analysis of Backdoor Behav
          '2602.00449', -- Do Latent-CoT Models Think Step-by-Step? A Mechanistic Study on Sequential
          '2601.17086', -- SonoEdit: Null-Space Constrained Knowledge Editing for Pronunciation Correc
          '2510.03366', -- Disentangling Recall and Reasoning in Transformer Models through Layer-wise
          '2509.22674', -- Pathological Truth Bias in Vision-Language Models
          '2507.09875', -- Function Induction and Task Generalization: An Interpretability Study with
          '2507.02559', -- Transformers Don''t Need LayerNorm at Inference Time: Scaling LayerNorm Remo
          '2506.12044', -- Why Do Some Inputs Break Low-Bit LLM Quantization?
          '2502.00726', -- Perspectives for Direct Interpretability in Multi-Agent Deep Reinforcement
          '2404.03623', -- Unveiling LLMs: The Evolution of Latent Representations in a Dynamic Knowle
          '2402.18344', -- Focus on Your Question! Interpreting and Mitigating Toxic CoT Problems in C
          '2412.02542', -- Unveiling Concept Attribution in Diffusion Models
          '2502.11806', -- Exploring Translation Mechanism of Large Language Models
          '2504.13151', -- MIB: A Mechanistic Interpretability Benchmark
          '2503.01090', -- Precise Localization of Memories: A Fine-grained Neuron-level Knowledge Edi
          '2407.15018', -- Answer, Assemble, Ace: Understanding How LMs Answer Multiple Choice Questio
          '2509.21044', -- Reinforcement Learning Fine-Tuning Enhances Activation Intensity and Divers
          '2506.20746', -- Dynamic Weight Grafting: Localizing Finetuned Factual Knowledge in Transfor
          '2510.11390', -- Medical Interpretability and Knowledge Maps of Large Language Models
          '2605.02958', -- Tracing the Dynamics of Refusal: Exploiting Latent Refusal Trajectories for
          '2510.00845', -- Mechanistic Interpretability as Statistical Estimation: A Variance Analysis
          '2604.10031', -- CoSToM: Causal-oriented Steering for Intrinsic Theory-of-Mind Alignment in
          '2508.02360', -- Understanding and Mitigating Political Stance Cross-topic Generalization in
          '2604.19052', -- Cell-Based Representation of Relational Binding in Language Models
          '2604.09364', -- Arbitration Failure, Not Perceptual Blindness: How Vision-Language Models R
          '2508.02087', -- When Truth Is Overridden: Uncovering the Internal Origins of Sycophancy in
          '2507.22928', -- How Does Chain of Thought Think? Mechanistic Interpretability of Chain-of-T
          '2607.26326', -- Seeing or Knowing? Visual Context Sensitivity in Multimodal Large Language
          '2509.23676', -- From Reasoning to Answer: Empirical, Attention-Based and Mechanistic Insigh
          '2510.11210', -- Discursive Circuits: How Do Language Models Understand Discourse Relations?
          '2610.22169', -- Lexical Reference Frames: Interpreting LM Residual Streams in Native Semant
          '2608.10430', -- Actionable Hallucination Detection: Translating Latent Uncertainty into Age
          '2606.05403', -- Trust, but Don’t Verify: Epistemic Blind Spots in LLM Source Evaluation
          '2607.04846', -- Pretraining Curricula Enable Selective Fine-tuning
          '2602.08548', -- How Do Language Models Understand Tables? A Mechanistic Analysis of Cell Lo
          '2605.13156' -- Dual-Pathway Circuits of Object Hallucination in Vision-Language Models
      )
      OR
      (p.source = 'external' AND p.id IN (
          125728, -- Mechanistic Insights into LoRA: Layer Sparsity for Adaptive Fine-Tuning via
          124795, -- Module Specialization in Transformer Factual Recall under Correlated Fact D
          109994, -- Interpretability Analysis of Arithmetic In-Context Learning in Large Langua
          125290, -- State Copying Crowds Out Reasoning: Mechanistic Evidence for Delta Planning
          126806, -- Locating and Repairing Domain Shift in VLM Trajectory Planning
          126951, -- TIGER: Bridging the Multimodal Reasoning-Access Gap via Modality Counterfac
          127220, -- From Groups to Rings: Causal Evidence for Algebraic Decomposition in Grokke
          127536, -- A Unifying Perspective on Language Model Interpretability
          127593, -- A Mechanistic Interpretability Study of an Astronomical Foundation Model
          131096, -- Localizing and Repairing Sparse-Prompt Failure in SAM Decoders via Box-to-P
          131206 -- Specialist Mediators: Causal Localization of Dense Fine-Tuning
      ))
  );

DELETE FROM paper_method_exclusions x
USING ap_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ap_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ap_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- activation-patching: 4 reviewed negatives.
CREATE TEMP TABLE ap_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'activation-patching'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2603.14688', -- AgentTrace: Causal Graph Tracing for Root Cause Analysis in Deployed Multi-
          '2409.00119', -- 3-in-1: 2D Rotary Adaptation for Efficient Finetuning, Efficient Batching a
          '2602.19631', -- Localized Concept Erasure in Text-to-Image Diffusion Models via High-Level
          '2509.08592' -- Interpretability as Alignment: Making Internal Understanding a Design Princ
      )
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'safety methods curation 2026-11-10: passing mention, or causal tracing / interchange intervention in another sense'
FROM ap_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING ap_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING ap_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- logit-lens: 50 reviewed true positives of 51 title/abstract candidates.
CREATE TEMP TABLE ll_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'logit-lens'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2303.08112', -- Eliciting Latent Predictions from Transformers with the Tuned Lens
          '2604.02608', -- Steerable but Not Decodable: Function Vectors Operate Beyond the Logit Lens
          '2411.19187', -- Beyond Logit Lens: Contextual Embeddings for Robust Hallucination Detection
          '2602.13567', -- DistillLens: Symmetric Knowledge Distillation Through Logit Lens
          '2609.01936', -- Sparse Readout Prism: Explaining Logit-Lens Scores in Features Instead of T
          '2606.07617', -- Query Lens: Interpreting Sparse Key-Value Features with Indirect Effects
          '2404.05971', -- Does Transformer Interpretability Transfer to RNNs?
          '2405.03205', -- Anchored Answers: Unravelling Positional Bias in GPT-2''s Multiple-Choice Qu
          '2406.11193', -- MMNeuron: Discovering Neuron-Level Domain-Specific Interpretation in Multim
          '2409.04185', -- Residual Stream Analysis with Multi-Layer SAEs
          '2411.04986', -- The Semantic Hub Hypothesis: Language Models Share Semantic Representations
          '2412.04537', -- Understanding Hidden Computations in Chain-of-Thought Reasoning
          '2502.15007', -- LLM-Microscope: Uncovering the Hidden Role of Punctuation in Context Memory
          '2502.15603', -- Do Multilingual LLMs Think In English?
          '2503.12730', -- TinySQL: A Progressive Text-to-SQL Dataset for Mechanistic Interpretability
          '2505.14352', -- Towards eliciting latent knowledge from LLMs with mechanistic interpretabil
          '2507.02199', -- Latent Chain-of-Thought? Decoding the Depth-Recurrent Transformer
          '2508.15882', -- Beyond Transcription: Mechanistic Interpretability in ASR
          '2510.01070', -- Eliciting Secret Knowledge from Language Models
          '2601.11061', -- Spurious Rewards Paradox: Mechanistically Understanding How RLVR Activates
          '2604.02486', -- VLMs Need Words: Vision Language Models Ignore Visual Detail In Favor of Se
          '2604.15557', -- Predicting Where Steering Vectors Succeed
          '2604.11061', -- Pando: Do Interpretability Methods Work When Models Won''t Explain Themselve
          '2602.00449', -- Do Latent-CoT Models Think Step-by-Step? A Mechanistic Study on Sequential
          '2602.15038', -- Indic-TunedLens: Interpreting Multilingual Models in Indian Languages
          '2510.01685', -- How Do Language Models Compose Functions?
          '2509.06608', -- Small Vectors, Big Effects: A Mechanistic Study of RL-Induced Reasoning via
          '2506.22724', -- The Translation Barrier Hypothesis: Multilingual Generation with Large Lang
          '2505.18706', -- Steering LLM Reasoning Through Bias-Only Adaptation
          '2502.16570', -- Entropy-Lens: Uncovering Decision Strategies in LLMs
          '2511.19972', -- Boosting Reasoning in Large Multimodal Models via Activation Replay
          '2601.20009', -- LinguaMap: Which Layers of LLMs Speak Your Language and How to Tune Them?
          '2606.25182', -- What Intermediate Layers Know: Detecting Jailbreaks from Entropy Dynamics
          '2606.22473', -- Interleaved Speech Language Models Latently Work In Text
          '2604.18712', -- Probing for Reading Times
          '2605.10622', -- Vocabulary Hijacking in LVLMs: Unveiling Critical Attention Heads by Exclud
          '2604.06374', -- The Illusion of Superposition? A Principled Analysis of Latent Thinking in
          '2604.09364', -- Arbitration Failure, Not Perceptual Blindness: How Vision-Language Models R
          '2604.09885', -- What do your logits know? (The answer may surprise you!)
          '2508.02087', -- When Truth Is Overridden: Uncovering the Internal Origins of Sycophancy in
          '2609.11085', -- Beyond Solver Verdicts: Generative Reward Models for Autoformalization
          '2602.20031', -- Latent Introspection: Models Can Detect Prior Concept Injections
          '2508.21380', -- The Algorithm Is Not the Behavior: Learned Priors Override Look-Ahead in a
          '2609.38810', -- CRAFT: Causal Responsibility and Failure Tracing in Medical Vision Language
          '2607.03502' -- Reading Between the Dots: Decoding Hidden Computation across Filler Tokens
      )
      OR
      (p.source = 'external' AND p.id IN (
          121088, -- Same Attention, Different Truths: Put Logit-Lens over Visual Attention to D
          109994, -- Interpretability Analysis of Arithmetic In-Context Learning in Large Langua
          110004, -- Unveiling Internal Reasoning Modes in LLMs: A Deep Dive into Latent Reasoni
          125992, -- Bypassing PC1 Makes SAEs More Reproducible
          126135 -- Inside the Loop: A Mechanistic Study of Weight-Tied Transformers on Depth-B
      ))
  );

DELETE FROM paper_method_exclusions x
USING ll_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ll_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ll_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- logit-lens: 1 reviewed negatives.
CREATE TEMP TABLE ll_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'logit-lens'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2610.17495' -- A Sense of Proprioception in Language Models
      )
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'safety methods curation 2026-11-10: passing mention of the logit lens'
FROM ll_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING ll_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING ll_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- model-editing: 228 reviewed true positives of 265 title/abstract candidates.
CREATE TEMP TABLE me_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'model-editing'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2308.07269', -- EasyEdit: An Easy-to-use Knowledge Editing Framework for Large Language Mod
          '2410.16251', -- Can Knowledge Editing Really Correct Hallucinations?
          '2401.07453', -- Model Editing at Scale leads to Gradual and Catastrophic Forgetting
          '2411.12790', -- Visual-Oriented Fine-Grained Knowledge Editing for MultiModal Large Languag
          '2405.00664', -- Is Bigger Edit Batch Size Always Better? -- An Empirical Study on Model Edi
          '2411.06638', -- Model Editing for LLMs4Code: How Far are We?
          '2508.01302', -- Aligning Language Models with Real-time Knowledge Editing
          '2505.01343', -- BalancEdit: Dynamically Balancing the Generality-Locality Trade-off in Mult
          '2310.02129', -- Unveiling the Pitfalls of Knowledge Editing for Large Language Models
          '2401.01286', -- A Comprehensive Study of Knowledge Editing for Large Language Models
          '2402.13462', -- Potential and Challenges of Model Editing for Social Debiasing
          '2403.05330', -- Consecutive Batch Model Editing with HooK Layers
          '2503.05683', -- Understanding the Limits of Lifelong Knowledge Editing in LLMs
          '2503.05212', -- Knowledge Updating? No More Model Editing! Just Selective Contextual Reason
          '2402.09394', -- Long-form evaluation of model editing
          '2401.04700', -- Model Editing Harms General Abilities of Large Language Models: Regularizat
          '2402.11905', -- Learning to Edit: Aligning LLMs with Knowledge Editing
          '2405.14768', -- WISE: Rethinking the Knowledge Memory for Lifelong Model Editing of Large L
          '2502.11177', -- The Mirage of Model Editing: Revisiting Evaluation in the Wild
          '2405.16821', -- Perturbation-Restrained Sequential Model Editing
          '2509.24502', -- SUIT: Knowledge Editing with Subspace-Aware Key-Value Mappings
          '2506.13772', -- MobiEdit: Resource-efficient Knowledge Editing for Personalized On-device L
          '2512.00881', -- Hybrid-DMKG: A Hybrid Reasoning Framework over Dynamic Multimodal Knowledge
          '2508.05083', -- MedMKEB: A Comprehensive Knowledge Editing Benchmark for Medical Multimodal
          '2607.05310', -- Evaluating and Understanding Model Editing for Medical Vision Language Mode
          '2308.08742', -- PMET: Precise Model Editing in a Transformer
          '2402.09656', -- The Butterfly Effect of Model Editing: Few Edits Can Trigger Large Language
          '2402.16123', -- InstructEdit: Instruction-based Knowledge Editing for Large Language Models
          '2403.07175', -- Rebuilding ROME : Resolving Model Collapse during Sequential Model Editing
          '2403.14236', -- A Unified Framework for Model Editing
          '2403.14472', -- Detoxifying Large Language Models via Knowledge Editing
          '2404.13752', -- Adversarial Representation Engineering: A General Model Editing Framework f
          '2405.19086', -- MEMoE: Enhancing Model Editing with Mixture of Experts Adaptors
          '2406.04496', -- Time Sensitive Knowledge Editing through Efficient Finetuning
          '2406.20030', -- LEMoE: Advanced Mixture of Experts Adaptor for Lifelong Model Editing of La
          '2407.06249', -- CodeUpdateArena: Benchmarking Knowledge Editing on API Updates
          '2409.10132', -- StruEdit: Structured Outputs Enable the Fast and Accurate Knowledge Editing
          '2410.07819', -- Uncovering Overfitting in Large Language Model Editing
          '2412.17727', -- Knowledge Editing through Chain-of-Thought
          '2502.10626', -- K-Edit: Language Model Editing with Contextual Knowledge Awareness
          '2502.15826', -- CoME: An Unlearning-based Approach to Conflict-free Model Editing
          '2503.02701', -- MindBridge: Scalable and Cross-Model Knowledge Editing via Memory-Augmented
          '2503.20756', -- ADS-Edit: A Multimodal Knowledge Editing Dataset for Autonomous Driving Sys
          '2509.22072', -- Fine-tuning Done Right in Model Editing
          '2512.04753', -- EtCon: Edit-then-Consolidate for Reliable Knowledge Editing
          '2602.03696', -- Conflict-Resolving and Sharpness-Aware Minimization for Generalized Knowled
          '2510.22139', -- Edit Less, Achieve More: Dynamic Sparse Neuron Masking for Lifelong Knowled
          '2510.21059', -- Dynamic Retriever for In-Context Knowledge Editing via Policy Optimization
          '2502.14838', -- Revealing and Mitigating Over-Attention in Knowledge Editing
          '2408.10411', -- Resolving Lexical Bias in Model Editing
          '2405.15349', -- Everything is Editable: Extend Knowledge Editing to Unstructured Data in La
          '2602.10965', -- MoEEdit: Efficient and Routing-Stable Knowledge Editing for Mixture-of-Expe
          '2606.00477', -- Do Text Edits Generalize to Visual Generation? Benchmarking Cross-Modal Kno
          '2502.19953', -- GeoEdit: Geometric Knowledge Editing for Large Language Models
          '2505.14393', -- Editing Across Languages: A Survey of Multilingual Knowledge Editing
          '2110.11309', -- Fast Model Editing at Scale
          '2202.05262', -- Locating and Editing Factual Associations in GPT
          '2305.13172', -- Editing Large Language Models: Problems, Methods, and Opportunities
          '2312.11795', -- MELO: Enhancing Model Editing with Neuron-Indexed Dynamic LoRA
          '2401.10647', -- Sowing the Wind, Reaping the Whirlwind: The Impact of Editing Language Mode
          '2402.05827', -- On the Robustness of Editing Large Language Models
          '2402.06155', -- Model Editing with Canonical Examples
          '2402.11324', -- EVEDIT: Event-based Knowledge Editing with Deductive Editing Boundaries
          '2406.10777', -- RoseLoRA: Row and Column-wise Sparse Low-rank Adaptation of Pre-trained Lan
          '2406.17764', -- BMIKE-53: Investigating Cross-Lingual Knowledge Editing with In-Context Lea
          '2409.05806', -- CKnowEdit: A New Chinese Knowledge Editing Dataset for Linguistics, Facts,
          '2410.14276', -- EcomEdit: An Automated E-commerce Knowledge Editing Framework for Enhanced
          '2502.01636', -- Lifelong Knowledge Editing requires Better Regularization
          '2504.01196', -- $μ$KE: Matryoshka Unstructured Knowledge Editing of Large Language Models
          '2505.11876', -- NAMET: Robust Massive Model Editing via Noise-Aware Memory Optimization
          '2505.23291', -- ScEdit: Script-based Assessment of Knowledge Editing
          '2510.07896', -- ACE: Attribution-Controlled Knowledge Editing for Multi-hop Factual Recall
          '2603.15518', -- Beyond the Covariance Trap: Unlocking Generalization in Same-Subject Knowle
          '2510.01172', -- Energy-Regularized Sequential Model Editing on Hyperspheres
          '2602.08550', -- GOT-Edit: Geometry-Aware Generic Object Tracking via Online Model Editing
          '2510.25798', -- MemEIC: A Step Toward Continual and Compositional Knowledge Editing
          '2509.21993', -- Bilinear relational structure fixes reversal curse and enables consistent m
          '2410.09508', -- CollabEdit: Towards Non-destructive Collaborative Knowledge Editing
          '2502.03748', -- Rethinking Residual Distribution in Locate-then-Edit Model Editing
          '2411.15432', -- Lifelong Knowledge Editing for Vision Language Models with Low-Rank Mixture
          '2503.01090', -- Precise Localization of Memories: A Fine-grained Neuron-level Knowledge Edi
          '2503.00306', -- Unlocking Efficient, Scalable, and Continual Knowledge Editing with Basis-L
          '2505.18774', -- Disentangling Knowledge Representations for Large Language Model Editing
          '2606.00570', -- Revisiting Parameter-Based Knowledge Editing in Large Language Models: Theo
          '2604.19089', -- Towards Scalable Lifelong Knowledge Editing with Selective Knowledge Suppre
          '2601.11042', -- Spectral Characterization and Mitigation of Sequential Knowledge Editing Co
          '2511.13243', -- Uncovering and Mitigating Transient Blindness in Multimodal Model Editing
          '2508.07022', -- MultiMedBench: A Scenario-Aware Benchmark for Evaluating Knowledge Editing
          '2506.20606', -- Model Editing as a Double-Edged Sword: Steering Agent Behavior Toward Benef
          '2505.15702', -- LyapLock: Bounded Knowledge Preservation in Sequential Large Language Model
          '2505.18933', -- REACT: Representation Extraction And Controllable Tuning to Overcome Overfi
          '2602.20207', -- Golden Layers and Where to Find Them: Improved Knowledge Editing for Large
          '2211.11031', -- Aging with GRACE: Lifelong Model Editing with Discrete Key-Value Adaptors
          '2301.04213', -- Does Localization Inform Editing? Surprising Differences in Causality-Based
          '2305.14795', -- MQuAKE: Assessing Knowledge Editing in Language Models via Multi-Hop Questi
          '2307.12976', -- Evaluating the Ripple Effects of Knowledge Editing in Language Models
          '2402.08631', -- Knowledge Editing on Black-box Large Language Models
          '2403.07350', -- VLKEB: A Large Vision-Language Model Knowledge Editing Benchmark
          '2403.13355', -- BadEdit: Backdooring large language models by model editing
          '2404.03646', -- Locating and Editing Factual Associations in Mamba
          '2405.13967', -- Model Editing as a Robust and Denoised variant of DPO: A Case Study on Toxi
          '2406.11139', -- Breaking Boundaries: Investigating the Effects of Model Editing on Cross-li
          '2406.11263', -- Understanding the Collapse of LLMs in Model Editing
          '2410.02355', -- AlphaEdit: Null-Space Constrained Knowledge Editing for Language Models
          '2410.03122', -- RIPPLECOT: Amplifying Ripple Effect of Knowledge Editing in Language Models
          '2503.08588', -- BiasEdit: Debiasing Stereotyped Language Models via Model Editing
          '2505.12345', -- UniEdit: A Unified Knowledge Editing Benchmark for Large Language Models
          '2505.23026', -- Context Robust Knowledge Editing for Language Models
          '2602.02543', -- Toward Ultra-Long-Horizon Sequential Model Editing
          '2601.17086', -- SonoEdit: Null-Space Constrained Knowledge Editing for Pronunciation Correc
          '2510.06627', -- POME: Post Optimization Model Edit via Muon-style Projection
          '2506.09672', -- Is Fine-Tuning an Effective Solution? Reassessing Knowledge Editing for Uns
          '2505.22156', -- InComeS: Integrating Compression and Selection Mechanisms into LLMs for Eff
          '2502.00602', -- Mitigating Heterogeneous Token Overfitting in LLM Knowledge Editing
          '2506.07899', -- MEMOIR: Lifelong Model Editing with Minimal Overwrite and Informed Retentio
          '2410.06331', -- Locate-then-edit for Multi-hop Factual Recall under Knowledge Editing
          '2410.17194', -- Representation Shattering in Transformers: A Synthetic Study with Knowledge
          '2510.02392', -- KnowledgeSmith: Uncovering Knowledge Updating in LLMs with Model Editing an
          '2606.01053', -- AnyEdit++: Adaptive Long-Form Knowledge Editing via Bayesian Surprise
          '2605.11836', -- More Edits, More Stable: Understanding the Lifelong Normalization in Sequen
          '2602.10134', -- Reverse-Engineering Model Editing on Language Models
          '2604.11214', -- HiEdit: Lifelong Model Editing with Hierarchical Reinforcement Learning
          '2505.07899', -- On the Superimposed Noise Accumulation Problem in Sequential Knowledge Edit
          '2605.06096', -- Uncovering Entity Identity Confusion in Multimodal Knowledge Editing
          '2608.11660', -- Hybrid-Policy Self-Editing for Composable Unstructured Knowledge Editing
          '2507.03377', -- Eigenvoice Synthesis based on Model Editing for Speaker Generation
          '2610.02772', -- Improving Atomic-Fact Recall via Focused Views in Unstructured Knowledge Ed
          '2606.23276', -- Exposing the Illusion of Erasure in Knowledge Editing for LLMs
          '2603.12677', -- MetaKE: Meta-Learning for Knowledge Editing Toward a Better Accuracy-Editab
          '2402.17811', -- TruthX: Alleviating Hallucinations by Editing Large Language Models in Trut
          '2403.17431', -- Robust and Scalable Model Editing for Large Language Models
          '2504.15133', -- EasyEdit2: An Easy-to-use Steering Framework for Editing Large Language Mod
          '2507.18028', -- NeuralDB: Scaling Knowledge Editing in LLMs to 100,000 Facts with Neural KV
          '2606.09707', -- BrainSurgery: Reproducible and Reliable Declarative Weight Manipulations fo
          '2605.26670', -- The Labyrinth and the Thread: Rethinking Regularizations in Sequential Know
          '2502.19870', -- MMKE-Bench: A Multimodal Editing Benchmark for Diverse Visual Knowledge
          '2310.11958', -- Emptying the Ocean with a Spoon: Should We Edit Models?
          '2407.20224', -- Can Editing LLMs Inject Harm?
          '2305.15529', -- Editable Graph Neural Network for Node Classifications
          '2303.08084', -- Editing Implicit Assumptions in Text-to-Image Diffusion Models
          '2505.14679', -- UltraEdit: Training-, Subject-, and Memory-Free Lifelong Editing in Large L
          '2512.14395', -- Massive Editing for Large Language Models Based on Dynamic Weight Generatio
          '2604.05540', -- Learning to Edit Knowledge via Instruction-based Chain-of-Thought Prompting
          '2511.14018', -- ALEX:A Light Editing-knowledge Extractor
          '2609.09054', -- Training-Free Task Vectors for LLM Behavioral Control
          '2305.12740', -- Can We Edit Factual Knowledge by In-Context Learning?
          '2305.17553', -- Detecting Edit Failures In Large Language Models: An Improved Specificity B
          '2310.08475', -- Can We Edit Multimodal Large Language Models?
          '2311.16087', -- DUnE: Dataset for Unified Editing
          '2401.10521', -- Cross-lingual Editing in Multilingual Language Models
          '2405.17969', -- Knowledge Circuits in Pretrained Transformers
          '2406.12670', -- Stealth edits to large language models
          '2502.05628', -- AnyEdit: Edit Any Knowledge Encoded in Language Models
          '2503.07392', -- SPEED: Scalable, Precise, and Efficient Concept Erasure for Diffusion Model
          '2503.16356', -- CaKE: Circuit-aware Editing Enables Generalizable Knowledge Learners
          '2510.19457', -- MINED: Probing and Updating with Multimodal Time-Sensitive Knowledge for La
          '2510.16917', -- SAKE: Towards Editing Auditory Attribute Knowledge of Large Audio-Language
          '2604.07965', -- DSCA: Dynamic Subspace Concept Alignment for Lifelong VLM Editing
          '2603.15656', -- Attribution-Guided Model Rectification of Unreliable Neural Network Behavio
          '2506.13285', -- DualEdit: Mitigating Safety Fallback in LLM Backdoor Editing via Affirmatio
          '2510.13500', -- MedREK: Retrieval-Based Editing for Medical LLMs with Key-Aware Prompts
          '2602.02408', -- ReasonEdit: Editing Vision--Language Models using Human Reasoning
          '2601.07873', -- Multiplicative Orthogonal Sequential Editing for Language Models
          '2206.15465', -- Interpretability, Then What? Editing Machine Learning Models to Reflect Hum
          '2301.10405', -- Editing Language Model-based Knowledge Graph Embeddings
          '2309.17410', -- Can Sensitive Information Be Deleted From LLMs? Objectives for Defending Ag
          '2310.02168', -- Editing Personality for Large Language Models
          '2310.10378', -- Cross-Lingual Consistency of Factual Knowledge in Multilingual Language Mod
          '2310.13730', -- Localizing and Editing Knowledge in Text-to-Image Generative Models
          '2311.04661', -- Massive Editing for Large Language Models via Meta Learning
          '2312.04364', -- DemoCaricature: Democratising Caricature Generation with a Rough Sketch
          '2402.04624', -- MEMORYLLM: Towards Self-Updatable Large Language Models
          '2402.15302', -- How (un)ethical are instruction-centric responses of LLMs? Unveiling the vu
          '2403.06259', -- Editing Conceptual Knowledge for Large Language Models
          '2403.13807', -- Editing Massive Concepts in Text-to-Image Diffusion Models
          '2404.00486', -- Dialectical Alignment: Resolving the Tension of 3H and Security Threats of
          '2404.11534', -- Decomposing and Editing Predictions by Modeling Model Computation
          '2406.09325', -- REVS: Unlearning Sensitive Information in Language Models via Rank Editing
          '2406.11194', -- In-Context Editing: Learning Knowledge from Self-Induced Distributions
          '2407.06483', -- Composable Interventions for Language Models
          '2409.00617', -- Does Knowledge Localization Hold True? Surprising Differences Between Entit
          '2409.14144', -- Interpreting Arithmetic Mechanism in Large Language Models through Comparat
          '2410.12949', -- Mechanistic Unlearning: Robust Knowledge Unlearning and Editing via Mechani
          '2410.18785', -- Should We Really Edit Language Models? On the Evaluation of Edited Language
          '2412.08201', -- Model-Editing-Based Jailbreak against Safety-aligned Large Language Models
          '2506.08920', -- PropMEND: Hypernetworks for Knowledge Propagation in LLMs
          '2603.24653', -- From Weights to Concepts: Data-Free Interpretability of CLIP via Singular V
          '2602.10021', -- Decoupled Reasoning with Implicit Fact Tokens (DRIFT): A Dual-Model Framewo
          '2601.15686', -- Beyond Hard Writes and Rigid Preservation: Soft Recursive Least-Squares for
          '2601.10639', -- STEM: Scaling Transformers with Embedding Modules
          '2510.27400', -- Balancing Knowledge Updates: Toward Unified Modular Editing in LLMs
          '2509.18868', -- Memory in Large Language Models: Mechanisms, Evaluation and Evolution
          '2605.16865', -- MixSD: Mixed Contextual Self-Distillation for Knowledge Injection
          '2605.18879', -- ZeroUnlearn: Few-Shot Knowledge Unlearning in Large Language Models
          '2604.10032', -- Closed-Form Concept Erasure via Double Projections
          '2510.11268', -- Exploring and Leveraging Class Vectors for Classifier Editing
          '2412.02542', -- Unveiling Concept Attribution in Diffusion Models
          '2505.18832', -- Localizing Knowledge in Diffusion Transformers
          '2502.05759', -- Reinforced Lifelong Editing for Language Models
          '2502.10438', -- Injecting Universal Jailbreak Backdoors into LLMs in Minutes
          '2404.00216', -- Is Factuality Enhancement a Free Lunch For LLMs? Better Factuality Can Lead
          '2405.16720', -- Large Scale Knowledge Washing
          '2505.20819', -- Tracing and Reversing Edits in LLMs
          '2605.20273', -- Modality-Decoupled Online Recursive Editing
          '2603.15117', -- MMKU-Bench: A Multimodal Update Benchmark for Diverse Visual Knowledge
          '2606.17057', -- Correct When Paired, Wrong When Split: Decoupling and Editing Modality-Spec
          '2606.03096', -- Can Factual Opinions Be Edited (Manipulated) in Large Language Models?
          '2508.02092', -- FPEdit: Robust LLM Fingerprinting through Localized Parameter Editing
          '2511.12828', -- Catastrophic Forgetting in Kolmogorov-Arnold Networks
          '2509.08778', -- Do All Autoregressive Transformers Remember Facts the Same Way? A Cross-Arc
          '2603.12598', -- Neural Gate: Mitigating Privacy Risks in LVLMs via Neuron-Level Gradient Ga
          '2609.00184' -- Synthetic Worlds for Temporal Evaluation and Knowledge Updating in LLMs
      )
      OR
      (p.source = 'external' AND p.id IN (
          110387, -- Think and Recall: Layer-Level Prompting for Lifelong Model Editing
          111063, -- MicroEdit: Neuron-level Knowledge Disentanglement and Localization in Lifel
          121907, -- SAME: Sparse and Anchored Model Editing for Heterogeneous Incremental Learn
          130983, -- The Illusion of Forgetting: Rank Leakage in Knowledge Editing and Its Mitig
          110053, -- Multimedia Event Extraction with LLM Knowledge Editing
          113556, -- PFedEdit: Personalized Federated Learning via Automated Model Editing
          127048, -- The Fractured Interlingua: Geometric Bottlenecks in Cross-Lingual Knowledge
          127562, -- ROSE: Risk-Aware Orthogonal Subspace Navigation for Lifelong Knowledge Edit
          129037, -- Capacity Allocation at the Source: Sparse Target Optimization for LLM Knowl
          129861, -- Editing Large Language Models with Geometry-Aware Regularization
          130955, -- Memoir: Let the Model Direct Its Own Story for Robust Cross-Domain Knowledg
          110903, -- M2Edit: Locate and Edit Multi-Granularity Knowledge in Multimodal Large Lan
          125909, -- DynEdit: Dynamic Entropy-Guided Sequential Editing for Large Language Model
          110525, -- Towards a Unified Paradigm of Concept Editing in Large Language Models
          127095, -- Generalized Influence Functions for Better Model Change Estimates
          128357 -- Gradient-Free Editing for Attribute Invariance in Graph Neural Networks
      ))
  );

DELETE FROM paper_method_exclusions x
USING me_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM me_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM me_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- model-editing: 37 reviewed negatives.
CREATE TEMP TABLE me_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'model-editing'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2205.12374', -- Learning to Model Editing Processes
          '2608.01973', -- Roomer: Reflective Object-Grounded Model Editing and Repair for 3D Indoor L
          '2311.18166', -- A-Scan2BIM: Assistive Scan to Building Information Modeling
          '2205.15480', -- Post-hoc Concept Bottleneck Models
          '2211.09800', -- InstructPix2Pix: Learning to Follow Image Editing Instructions
          '2307.03941', -- Right to be Forgotten in the Era of Large Language Models: Implications, Ch
          '2311.11908', -- Continual Learning: Applications and the Road Forward
          '2401.12874', -- From Understanding to Utilization: A Survey on Explainability for Large Lan
          '2402.01364', -- Continual Learning for Large Language Models: A Survey
          '2402.08787', -- Rethinking Machine Unlearning for Large Language Models
          '2402.10688', -- Towards Uncovering How Large Language Model Works: An Explainability Perspe
          '2402.14522', -- Towards Unified Task Embeddings Across Multiple Models: Bridging the Gap fo
          '2403.07809', -- pyvene: A Library for Understanding and Improving PyTorch Models via Interv
          '2404.11672', -- MemLLM: Finetuning LLMs to Use An Explicit Read-Write Memory
          '2407.15549', -- Latent Adversarial Training Improves Robustness to Persistent Harmful Behav
          '2410.19427', -- Expose Before You Defend: Unifying and Enhancing Backdoor Defenses via Expo
          '2501.18887', -- Building Bridges, Not Walls -- Advancing Interpretability by Unifying Featu
          '2502.06755', -- Sparse Autoencoders for Scientifically Rigorous Interpretation of Vision Mo
          '2504.05523', -- Pretraining Language Models for Diachronic Linguistic Change Discovery
          '2504.15585', -- A Comprehensive Survey in LLM(-Agent) Full Stack Safety: Data, Training and
          '2506.09227', -- SoK: Machine Unlearning for Large Language Models
          '2509.10708', -- SearchInstruct: Enhancing Domain Adaptation via Retrieval-Based Instruction
          '2602.21499', -- Easy3E: Feed-Forward 3D Asset Editing via Rectified Voxel Flow
          '2507.20930', -- FRED: Financial Retrieval-Enhanced Detection and Editing of Hallucinations
          '2406.10868', -- Identifying Query-Relevant Neurons in Large Language Models for Long-Form T
          '2512.01329', -- TagSplat: Topology-Aware Gaussian Splatting for Dynamic Mesh Modeling and T
          '2510.13462', -- Who Speaks for the Trigger? Dynamic Expert Routing in Backdoored Mixture-of
          '2505.17721', -- SeaLion: Semantic Part-Aware Latent Point Diffusion Models for 3D Generatio
          '2410.00487', -- Self-Updatable Large Language Models by Integrating Context into Model Para
          '2505.24262', -- On Fairness of Task Arithmetic: The Role of Task Vectors
          '2605.24906', -- Where Detectors Fail: Probing Generative Space for Generalizable AI-Generat
          '2603.03335', -- Compressed Sensing for Capability Localization in Large Language Models
          '2601.21601', -- Dynamics Reveals Structure: Challenging the Linear Propagation Assumption
          '2507.18178', -- Decoupling Knowledge and Reasoning in LLMs: An Exploration Using Cognitive
          '2608.16328', -- GRNEdit: Efficient General Video Editing from a New Binary-Evidence Perspec
          '2505.24428' -- Model Unlearning via Sparse Autoencoder Subspace Guided Projections
      )
      OR
      (p.source = 'external' AND p.id IN (
          130718 -- Can Hybrid-Parallel Planning Support Alternating Model–Strategy Design? Dep
      ))
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'safety methods curation 2026-11-10: passing mention in a list, or editing of images, 3D/BIM models or text rather than of a trained model'
FROM me_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING me_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING me_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- red-teaming: 264 reviewed true positives of 300 title/abstract candidates.
CREATE TEMP TABLE rt_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'red-teaming'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2501.07238', -- Lessons From Red Teaming 100 Generative AI Products
          '2506.00781', -- CoP: Agentic Red-teaming for Large Language Models using Composition of Pri
          '2209.07858', -- Red Teaming Language Models to Reduce Harms: Methods, Scaling Behaviors, an
          '2401.12915', -- Red Teaming Visual Language Models
          '2408.11851', -- SAGE-RT: Synthetic Alignment data Generation for Safety Evaluation and Red
          '2510.02677', -- ARMs: Adaptive Red-Teaming Agent against Multimodal Models with Plug-and-Pl
          '2311.07689', -- MART: Improving LLM Safety with Multi-round Automatic Red-Teaming
          '2401.16656', -- Gradient-Based Language Model Red Teaming
          '2504.03174', -- Multi-lingual Multi-turn Automated Red Teaming for LLMs
          '2505.20162', -- Capability-Based Scaling Laws for LLM Red-Teaming
          '2601.13518', -- AgenticRed: Optimizing Agentic Systems for Automated Red-teaming
          '2510.02609', -- RedCodeAgent: Automatic Red-teaming Agent against Diverse Code Agents
          '2607.26115', -- GPT-Red: Automated Red Teaming via Self-Play at Scale
          '2306.09442', -- Explore, Establish, Exploit: Red Teaming Language Models from Scratch
          '2311.06237', -- Summon a Demon and Bind it: A Grounded Theory of LLM Red Teaming
          '2402.04249', -- HarmBench: A Standardized Evaluation Framework for Automated Red Teaming an
          '2402.19464', -- Curiosity-driven Red-teaming for Large Language Models
          '2405.18540', -- Learning diverse attacks on large language models for robust red-teaming an
          '2505.21936', -- RedTeamCUA: Realistic Adversarial Testing of Computer-Use Agents in Hybrid
          '2602.02164', -- Co-RedTeam: Orchestrated Security Discovery and Exploitation with LLM Agent
          '2407.16667', -- RedAgent: Red Teaming Large Language Models with Context-aware Autonomous L
          '2510.18131', -- BlueCodeAgent: A Blue Teaming Agent Powered by Automated Red Teaming for Co
          '2308.04265', -- FLIRT: Feedback Loop In-context Red Teaming
          '2310.14303', -- Language Model Unalignment: Parametric Red-Teaming to Expose Hidden Harms a
          '2404.03411', -- Red Teaming GPT-4V: Are GPT-4V Safe Against Uni/Multi-Modal Jailbreak Attac
          '2406.15481', -- Code-Switching Red-Teaming: LLM Evaluation for Safety and Multilingual Unde
          '2407.14937', -- Operationalizing a Threat Model for Red-Teaming Large Language Models (LLMs
          '2410.02828', -- PyRIT: A Framework for Security Risk Identification and Red Teaming in Gene
          '2411.18676', -- Embodied Red Teaming for Auditing Robotic Foundation Models
          '2503.15754', -- AutoRedTeamer: Autonomous Red Teaming with Lifelong Attack Integration
          '2601.01592', -- OpenRT: An Open-Source Red Teaming Framework for Multimodal LLMs
          '2605.00553', -- Stable-GFlowNet: Toward Diverse and Robust LLM Red-Teaming via Contrastive
          '2512.20677', -- Automated Red-Teaming Framework for Large Language Model Security Assessmen
          '2509.21011', -- Automatic Red Teaming LLM-based Agents with Model Context Protocol Tools
          '2508.00923', -- Beyond Benchmarks: Dynamic, Automatic And Systematic Red-Teaming Agents For
          '2507.16329', -- DREAM: Scalable Red Teaming for Text-to-Image Generative Systems via Distri
          '2507.22063', -- RedCoder: Automated Multi-Turn Red Teaming for Code LLMs
          '2410.01606', -- Automated Red Teaming with GOAT: the Generative Offensive Agent Tester
          '2605.04808', -- DecodingTrust-Agent Platform (DTap): A Controllable and Interactive Red-Tea
          '2509.15551', -- PolyJuice Makes It Real: Black-Box, Universal Red-Teaming for Synthetic Ima
          '2606.05101', -- FoeGlass: Simple In-Context Learning Is Enough for Red Teaming Audio Deepfa
          '2510.09689', -- When Search Goes Wrong: Red-Teaming Web-Augmented Large Language Models
          '2608.05108', -- Agent Against Agent: An Agentic System for Automatic Prompt Injection Red T
          '2509.19143', -- Anecdoctoring: Automated Red-Teaming Across Language and Place
          '2202.03286', -- Red Teaming Language Models with Language Models
          '2308.09662', -- Red-Teaming Large Language Models using Chain of Utterances for Safety-Alig
          '2310.12505', -- Attack Prompt Generation for Red Teaming and Defending Large Language Model
          '2311.08592', -- AART: AI-Assisted Red-Teaming with Diverse Data Generation for New LLM-powe
          '2404.00629', -- Against The Achilles'' Heel: A Survey on Red Teaming for Generative Models
          '2404.06664', -- CulturalTeaming: AI-Assisted Interactive Red-Teaming for Challenging LLMs''
          '2405.12604', -- Tiny Refinements Elicit Resilience: Toward Efficient Prefix-Model Against L
          '2405.19026', -- DiveR-CT: Diversity-enhanced Red Teaming Large Language Model Assistants wi
          '2405.19360', -- ART: Automatic Red-teaming for Text-to-Image Models to Protect Benign Users
          '2501.18837', -- Constitutional Classifiers: Defending against Universal Jailbreaks across T
          '2505.06913', -- RedTeamLLM: an Agentic AI framework for offensive security
          '2604.28157', -- FlashRT: Towards Computationally and Memory Efficient Red-Teaming for Promp
          '2602.19948', -- Assessing Risks of Large Language Models in Mental Health Support: A Framew
          '2601.10971', -- AJAR: Adaptive Jailbreak Architecture for Red-teaming
          '2601.10589', -- Be Your Own Red Teamer: Safety Alignment via Self-Play and Reflective Exper
          '2507.07248', -- Medical Red Teaming Protocol of Language Models: On the Importance of User
          '2506.22523', -- Red Teaming for Generative AI, Report on a Copyright-Focused Exercise Compl
          '2506.14682', -- AIRTBench: Measuring Autonomous AI Red Teaming Capabilities in Language Mod
          '2504.01278', -- Strategize Globally, Adapt Locally: A Multi-Turn Red Teaming Agent with Dua
          '2605.22880', -- How Far Will They Go? Red-Teaming Online Influence with Large Language Mode
          '2506.10047', -- GenBreak: Red Teaming Text-to-Image Generation Using Large Language Models
          '2603.22882', -- TreeTeaming: Autonomous Red-Teaming of Vision-Language Models via Hierarchi
          '2505.21074', -- Red-Teaming Text-to-Image Systems by Rule-based Preference Modeling
          '2602.20170', -- CAGE: A Framework for Culturally Adaptive Red-Teaming Benchmark Generation
          '2605.00699', -- STARE: Step-wise Temporal Alignment and Red-teaming Engine for Multi-modal
          '2506.11083', -- RedDebate: Safer Responses Through Multi-Agent Red Teaming Debates
          '2606.31227', -- Securing the AI Agent: A Unified Framework for Multi-Layer Agent Red Teamin
          '2509.10546', -- Learning to Conceal Risk: Controllable Multi-turn Red Teaming for LLMs in t
          '2510.07239', -- Red-Bandit: Test-Time Adaptation for LLM Red-Teaming via Bandit-Guided LoRA
          '2607.21735', -- What AI Red-Team Evaluations Can and Cannot Prove
          '2609.34920', -- RISE: Red-teaming via Iterative Strategy Evolution for Modern Text-to-Image
          '2301.12867', -- Red teaming ChatGPT via Jailbreaking: Bias, Robustness, Reliability and Tox
          '2309.06135', -- Prompting4Debugging: Red-Teaming Text-to-Image Diffusion Models by Finding
          '2309.10253', -- GPTFUZZER: Red Teaming Large Language Models with Auto-Generated Jailbreak
          '2310.09624', -- ASSERT: Automated Safety Scenario Red Teaming for Evaluating the Robustness
          '2402.13946', -- AttackGNN: Red-Teaming GNNs in Hardware Security Using Reinforcement Learni
          '2404.08676', -- ALERT: A Comprehensive Benchmark for Assessing Large Language Models'' Safet
          '2407.12784', -- AgentPoison: Red-teaming LLM Agents via Poisoning Memory or Knowledge Bases
          '2408.10701', -- Ferret: Faster and Effective Automated Red Teaming with Reward-Based Scorin
          '2409.15398', -- Attack Atlas: A Practitioner''s Perspective on Challenges and Pitfalls in Re
          '2410.17401', -- AdvAgent: Controllable Blackbox Red-teaming on Web Agents
          '2501.01830', -- Auto-RT: Automatic Jailbreak Strategy Exploration for Red-Teaming Large Lan
          '2503.01908', -- UDora: A Unified Red Teaming Framework against LLM Agents by Dynamically Hi
          '2506.09600', -- Effective Red-Teaming of Policy-Adherent Agents
          '2508.03936', -- ASTRA: Autonomous Spatial-Temporal Red-teaming for AI Software Assistants
          '2510.02286', -- Tree-based Dialogue Reinforced Policy Optimization for Red-Teaming Attacks
          '2601.03699', -- RedBench: A Universal Dataset for Comprehensive Red Teaming of Large Langua
          '2603.22341', -- T-MAP: Red-Teaming LLM Agents with Trajectory-aware Evolutionary Search
          '2603.18762', -- ClawTrap: A MITM-Based Red-Teaming Framework for Real-World OpenClaw Securi
          '2602.10148', -- Red-teaming the Multimodal Reasoning: Jailbreaking Vision-Language Models v
          '2603.20198', -- Visual Exclusivity Attacks: Automatic Multimodal Red Teaming via Agentic Pl
          '2601.22569', -- Whispers of Wealth: Red-Teaming Google''s Agent Payments Protocol via Prompt
          '2509.15478', -- Red Teaming Multimodal Language Models: Evaluating Harm Across Prompt Modal
          '2510.18314', -- Genesis: Evolving Attack Strategies for LLM Web Agent Red-Teaming
          '2509.23694', -- SafeSearch: Automated Red-Teaming for the Safety of LLM-Based Search Agents
          '2504.19855', -- The Automation Advantage in AI Red Teaming
          '2511.21145', -- TEAR: Temporal-aware Automated Red-teaming for Text-to-Video Models
          '2509.21947', -- Active Attacks: Red-teaming LLMs via Adaptive Environments
          '2605.08876', -- OTora: A Unified Red Teaming Framework for Reasoning-Level Denial-of-Servic
          '2604.05549', -- Stop Fixating on Prompts: Reasoning Hijacking and Constraint Tightening for
          '2604.18789', -- ARES: Adaptive Red-Teaming and End-to-End Repair of Policy-Reward System
          '2601.03265', -- Jailbreak-Zero: A Path to Pareto Optimal Red Teaming for Large Language Mod
          '2604.21159', -- Adaptive Instruction Composition for Automated LLM Red-Teaming
          '2411.16769', -- Red-Teaming Text-to-Image Models via In-Context Experience Replay and Seman
          '2603.13026', -- PISmith: Reinforcement Learning-based Red Teaming for Prompt Injection Defe
          '2606.20408', -- NRT-Bench: Benchmarking Multi-Turn Red-Teaming of LLM Operator Agents in Sa
          '2608.00677', -- OpenART: Scaling Agent Red Teaming via Open-Ended Environment Evolution
          '2509.15260', -- Toxicity Red-Teaming: Benchmarking LLM Safety in Singapore’s Low-Resource L
          '2609.32400', -- SkillDRE: Dual-Stage Red-Team Evolution of Agent Skills via Pre-Execution a
          '2210.04610', -- Red-Teaming the Stable Diffusion Safety Filter
          '2305.19713', -- Red Teaming Language Model Detectors with Language Models
          '2311.09433', -- Trojan Activation Attack: Red-Teaming Large Language Models using Activatio
          '2406.11654', -- Ruby Teaming: Improving Quality Diversity Search with Memory for Automated
          '2505.05849', -- AgentVigil: Generic Black-Box Red-teaming for Indirect Prompt Injection aga
          '2505.24672', -- TRIDENT: Enhancing Large Language Model Safety with Tri-Dimensional Diversi
          '2509.14651', -- MUSE: MCTS-Driven Red Teaming Framework for Enhanced Multi-Turn Dialogue Sa
          '2502.14847', -- Red-Teaming LLM Multi-Agent Systems via Communication Attacks
          '2512.00412', -- Red Teaming Large Reasoning Models
          '2610.22722', -- LLM-Attack Suite: A Unified Red-Team Framework for Privacy Evaluation of Sp
          '2506.00782', -- Jailbreak-R1: Exploring the Jailbreak Capabilities of LLMs via Reinforcemen
          '2408.02632', -- SEAS: Self-Evolving Adversarial Safety Optimization for Large Language Mode
          '2410.13886', -- Refusal-Trained LLMs Are Easily Jailbroken As Browser Agents
          '2502.09638', -- Jailbreaking to Jailbreak
          '2504.15047', -- RainbowPlus: Enhancing Adversarial Prompt Generation via Evolutionary Quali
          '2508.10108', -- Amazon Nova AI Challenge -- Trusted AI: Advancing secure, AI-assisted softw
          '2511.14195', -- N-GLARE: An Non-Generative Latent Representation-Efficient LLM Safety Evalu
          '2310.02446', -- Low-Resource Languages Jailbreak GPT-4
          '2401.10647', -- Sowing the Wind, Reaping the Whirlwind: The Impact of Editing Language Mode
          '2405.21018', -- Improved Techniques for Optimization-Based Jailbreaking on Large Language M
          '2406.18510', -- WildTeaming at Scale: From In-the-Wild Jailbreaks to (Adversarially) Safer
          '2407.13833', -- Phi-3 Safety Post-Training: Aligning Language Models with a "Break-Fix" Cyc
          '2409.11445', -- Jailbreaking Large Language Models with Symbolic Mathematics
          '2601.11516', -- Building Production-Ready Probes For Gemini
          '2603.15714', -- How Vulnerable Are AI Agents to Indirect Prompt Injections? Insights from a
          '2512.07810', -- Auditing Games for Sandbagging
          '2510.17017', -- SafeSearch: Do Not Trade Safety for Utility in LLM Search Agents
          '2507.20526', -- Security Challenges in AI Agent Deployment: Insights from a Large Scale Pub
          '2506.07468', -- Chasing Moving Targets with Online Self-Play Reinforcement Learning for Saf
          '2602.16346', -- Helpful to a Fault: Measuring Illicit Assistance in Multi-Turn, Multilingua
          '2608.17067', -- DiSCO: Defending text-to-image generation through distribution-guided contr
          '2604.07831', -- Are GUI Agents Focused Enough? Automated Distraction via Semantic-level UI
          '2607.11070', -- MJ: Multi-turn LLM Jailbreaking via Decomposed Credit Assignment
          '2310.02224', -- Can Language Models be Instructed to Protect Personal Information?
          '2310.03693', -- Fine-tuning Aligned Language Models Compromises Safety, Even When Users Do
          '2310.06987', -- Catastrophic Jailbreak of Open-source LLMs via Exploiting Generation
          '2310.15140', -- AutoDAN: Interpretable Gradient-Based Adversarial Attacks on Large Language
          '2311.09641', -- RLHFPoison: Reward Poisoning Attack for Reinforcement Learning with Human F
          '2312.05187', -- Seamless: Multilingual Expressive and Streaming Speech Translation
          '2312.06942', -- AI Control: Improving Safety Despite Intentional Subversion
          '2312.14302', -- Exploiting Novel GPT-4 APIs
          '2401.12509', -- Digital cloning of online social networks for language-sensitive agent-base
          '2402.08567', -- Agent Smith: A Single Image Can Jailbreak One Million Multimodal LLM Agents
          '2403.01038', -- AutoAttacker: A Large Language Model Guided System to Implement Automatic C
          '2403.08424', -- Distract Large Language Models for Automatic Jailbreak Attack
          '2404.00399', -- Aurora-M: Open Source Continual Pre-training for Multilingual Language and
          '2404.16873', -- AdvPrompter: Fast Adaptive Adversarial Prompting for LLMs
          '2406.07594', -- MLLMGuard: A Multi-dimensional Safety Evaluation Suite for Multimodal Large
          '2406.11036', -- garak: A Framework for Security Probing Large Language Models
          '2406.11978', -- Dialogue Action Tokens: Steering Language Models in Goal-Directed Dialogue
          '2406.14393', -- Jailbreaking as a Reward Misspecification Problem
          '2406.18682', -- The Multilingual Alignment Prism: Aligning Global and Local Preferences to
          '2407.16318', -- PrimeGuard: Safe and Helpful LLMs through Tuning-Free Routing
          '2408.00761', -- Tamper-Resistant Safeguards for Open-Weight LLMs
          '2408.15221', -- LLM Defenses Are Not Robust to Multi-Turn Human Jailbreaks Yet
          '2409.00138', -- PrivacyLens: Evaluating Privacy Norm Awareness of Language Models in Action
          '2409.00551', -- Testing and Evaluation of Large Language Models: Correctness, Non-Toxicity,
          '2409.11276', -- Hackphyr: A Local Fine-Tuned LLM Agent for Network Security Environments
          '2409.17458', -- RED QUEEN: Safeguarding Large Language Models against Concealed Multi-Turn
          '2410.05295', -- AutoDAN-Turbo: A Lifelong Agent for Strategy Self-Exploration to Jailbreak
          '2411.14133', -- GASP: Efficient Black-Box Generation of Adversarial Suffixes for Jailbreaki
          '2411.17693', -- Adaptive Deployment of Untrusted LLMs Reduces Distributed Threats
          '2412.16720', -- OpenAI o1 System Card
          '2501.00069', -- Adversarial Negotiation Dynamics in Generative Language Models
          '2501.04931', -- Jailbreaking Multimodal Large Language Models via Shuffle Inconsistency
          '2501.07927', -- Gandalf the Red: Adaptive Security for LLMs
          '2501.17433', -- Virus: Harmful Fine-tuning Attack for Large Language Models Bypassing Guard
          '2502.03052', -- Understanding and Enhancing the Transferability of Jailbreaking Attacks
          '2503.14827', -- MMDT: Decoding the Trustworthiness and Safety of Multimodal Foundation Mode
          '2503.18929', -- Trajectory Balance with Asynchrony: Decoupling Exploration and Learning for
          '2504.13203', -- X-Teaming: Multi-Turn Jailbreaks and Defenses with Adaptive Multi-Agents
          '2505.10838', -- LARGO: Latent Adversarial Reflection through Gradient Optimization for Jail
          '2506.17299', -- LLM Jailbreak Oracle
          '2507.05980', -- RabakBench: Scaling Human Annotations to Construct Localized Multilingual S
          '2507.06260', -- Evaluating the Critical Risks of Amazon''s Nova Premier under the Frontier M
          '2508.10390', -- Jailbreaking Commercial Black-Box LLMs with Explicitly Harmful Prompts
          '2508.19500', -- Servant, Stalker, Predator: How An Honest, Helpful, And Harmless (3H) Agent
          '2509.17938', -- D-REX: A Benchmark for Detecting Deceptive Reasoning in Large Language Mode
          '2511.12710', -- Evolve the Method, Not the Prompts: Evolutionary Synthesis of Jailbreak Att
          '2512.10675', -- Evaluating Gemini Robotics Policies in a Veo World Simulator
          '2602.06854', -- SEMA: Simple yet Effective Learning for Multi-Turn Jailbreak Attacks
          '2602.14689', -- Exposing the Systematic Vulnerability of Open-Weight Models to Prefill Atta
          '2602.20021', -- Agents of Chaos
          '2603.02482', -- MUSE: A Run-Centric Platform for Multimodal Unified Safety Evaluation of La
          '2601.02670', -- Break Me If You Can: Self-Jailbreaking of Aligned LLMs via Lexical Insertio
          '2603.25176', -- Prompt Attack Detection with LLM-as-a-Judge and Mixture-of-Models
          '2603.24935', -- SABER: A Stealthy Agentic Black-Box Attack Framework for Vision-Language-Ac
          '2603.17305', -- Contrastive Reasoning Alignment: Reinforcement Learning from Hidden Represe
          '2603.16576', -- REFORGE: Multi-modal Attacks Reveal Vulnerable Concept Unlearning in Image
          '2602.07391', -- NAAMSE: Framework for Evolutionary Security Evaluation of Agents
          '2602.05746', -- Learning to Inject: Automated Prompt Injection via Reinforcement Learning
          '2603.06594', -- A Coin Flip for Safety: LLM Judges Fail to Reliably Measure Adversarial Rob
          '2601.15331', -- RECAP: A Resource-Efficient Method for Adversarial Prompting in Large Langu
          '2509.05367', -- Between a Rock and a Hard Place: The Tension Between Ethical Reasoning and
          '2512.20806', -- Safety Alignment of LMs via Non-cooperative Games
          '2512.13526', -- Async Control: Stress-testing Asynchronous Control Measures for LLM Agents
          '2511.21990', -- A Safety and Security Framework for Real-World Agentic Systems
          '2511.20686', -- AssurAI: Experience with Constructing Korean Socio-cultural Datasets to Dis
          '2511.16709', -- AutoBackdoor: Automating Backdoor Attacks via LLM Agents
          '2511.10222', -- Speech-Audio Compositional Attacks on Multimodal LLMs and Their Mitigation
          '2511.01375', -- Align to Misalign: Automatic LLM Jailbreak with Meta-Optimized LLM Judges
          '2511.00203', -- Diffusion LLMs are Natural Adversaries for any LLM
          '2510.17947', -- PLAGUE: Plug-and-play framework for Lifelong Adaptive Generation of Multi-t
          '2509.25896', -- LLaVAShield: Safeguarding Multimodal Multi-Turn Dialogues in Vision-Languag
          '2509.21029', -- FORCE: Transferable Visual Jailbreaking Attacks via Feature Over-Reliance C
          '2509.08729', -- X-Teaming Evolutionary M2S: Automated Discovery of Multi-turn to Single-tur
          '2508.19461', -- Reliable Weak-to-Strong Monitoring of LLM Agents
          '2508.14904', -- Efficient Switchable Safety Control in LLMs via Magic-Token-Guided Co-Train
          '2508.08243', -- Jinx: Unlimited LLMs for Probing Alignment Failures
          '2508.04196', -- Eliciting and Analyzing Emergent Misalignment in State-of-the-Art Large Lan
          '2508.00555', -- Activation-Guided Local Editing for Jailbreaking Attacks
          '2507.22564', -- Exploiting Synergistic Cognitive Biases to Bypass Safety in LLMs
          '2507.19060', -- PurpCode: Reasoning for Safer Code Generation
          '2506.24068', -- STACK: Adversarial Attacks on LLM Safeguard Pipelines
          '2506.00359', -- Keeping an Eye on LLM Unlearning: The Hidden Risk and Remedy
          '2411.00827', -- IDEATOR: Jailbreaking and Benchmarking Large Vision-Language Models Using T
          '2505.06843', -- Benign Samples Matter! Fine-tuning On Outlier Benign Samples Severely Break
          '2408.04811', -- h4rm3l: A Language for Composable Jailbreak Attack Synthesis
          '2406.09179', -- Towards Effective Evaluations and Comparisons for LLM Unlearning Methods
          '2601.04603', -- Constitutional Classifiers++: Efficient Production-Grade Defenses against U
          '2606.23496', -- TROPT: An Open Framework for Unifying and Advancing Discrete Text Optimizat
          '2605.10067', -- Metis: Learning to Jailbreak LLMs via Self-Evolving Metacognitive Policy Op
          '2510.17759', -- VERA-V: Variational Inference Framework for Jailbreaking Vision-Language Mo
          '2601.04740', -- StealthGraph: Exposing Domain-Specific Risks in LLMs through Knowledge-Grap
          '2510.17687', -- CrossGuard: Safeguarding MLLMs against Joint-Modal Implicit Malicious Attac
          '2605.24883', -- Inverting the Shield: Systematically Generating Safety Tests from Policy Sp
          '2607.26314', -- StealthBench: Measuring Operational Stealth in Autonomous Offensive-Securit
          '2602.06440', -- TrailBlazer: History-Guided Reinforcement Learning for Black-Box LLM Jailbr
          '2505.14300', -- Beyond Black-Box Obfuscation: Mechanistic Analysis and Defense of White-Box
          '2508.06194', -- SceneJailEval: A Scenario-Adaptive Multi-Dimensional Framework for Jailbrea
          '2509.08000', -- AntiDote: Bi-level Adversarial Training for Tamper-Resistant LLMs
          '2608.09158', -- From Inaudible Inputs to Model Failures: Low-Frequency Safety Risks in LALM
          '2605.17380', -- ADR: An Agentic Detection System for Enterprise Agentic AI Security
          '2605.12673', -- Do Androids Dream of Breaking the Game? Systematically Auditing AI Agent Be
          '2310.10012', -- Ring-A-Bell! How Reliable are Concept Removal Methods for Diffusion Models?
          '2609.30383', -- Stealth Apart, Harm Together: Skill Cascading Attacks on Skill-Based Agent
          '2606.04027', -- MaskForge: Structure-Aware Adaptive Attacks for Jailbreaking Diffusion Larg
          '2610.22124', -- PROBE: Learning to Audit Policy Compliance in Tool-Using LLM Agents
          '2605.08427' -- The Attacker in the Mirror: Breaking Self-Consistency in Safety via Anchore
      )
      OR
      (p.source = 'external' AND p.id IN (
          128448, -- There are Levels to It: Red Teaming LLMs with Hierarchical Reinforcement Le
          110627, -- Nullspace Disentanglement for Red Teaming Language Models
          128704, -- Who Watches the Watchers? Semantically-Constrained Reinforcement Learning f
          109971, -- Refusal-Aware Red Teaming: Exposing Inconsistency in Safety Evaluations
          128588, -- PROTEUS: A Self-Evolving Red Team with Surface Expansion for Agent Skill Ec
          129879, -- Auditing Instruction Robustness in Vision-Language-Action Models via Divers
          121047, -- Red-teaming Retrieval-Augmented Diffusion Models via Poisoning Knowledge Ba
          127047, -- AI Control for Sandbagging on Fuzzy Tasks
          128146, -- Stress Testing Chain-of-Thought Monitoring Against Covert Misalignment
          110123, -- DAMON: A Dialogue-Aware MCTS Framework for Jailbreaking Large Language Mode
          120852, -- Adversarial Style Optimization: Enhancing VLM Jailbreaks by GRPO-based Styl
          127443 -- Improving Audit Realism with Inference-Time Compute and Deployment Scaffold
      ))
  );

DELETE FROM paper_method_exclusions x
USING rt_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM rt_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM rt_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- red-teaming: 36 reviewed negatives.
CREATE TEMP TABLE rt_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'red-teaming'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2307.02483', -- Jailbroken: How Does LLM Safety Training Fail?
          '2401.05998', -- Combating Adversarial Attacks with Multi-Agent Debate
          '2404.17546', -- Probabilistic Inference in Language Models via Twisted Sequential Monte Car
          '2405.01886', -- Aloe: A Family of Fine-tuned Open Healthcare LLMs
          '2407.15549', -- Latent Adversarial Training Improves Robustness to Persistent Harmful Behav
          '2501.15570', -- ARWKV: Pretrain is not what we need, an RNN-Attention-Based Language Model
          '2305.07153', -- Towards best practices in AGI safety and governance: A survey of expert opi
          '2308.01263', -- XSTest: A Test Suite for Identifying Exaggerated Safety Behaviours in Large
          '2308.06463', -- GPT-4 Is Too Smart To Be Safe: Stealthy Chat with LLMs via Cipher
          '2310.20624', -- LoRA Fine-tuning Efficiently Undoes Safety Training in Llama 2-Chat 70B
          '2311.11202', -- Unmasking and Improving Data Credibility: A Study with Datasets for Trainin
          '2312.00027', -- Stealthy and Persistent Unalignment on Large Language Models via Backdoor I
          '2403.04224', -- Aligners: Decoupling LLMs and Alignment
          '2403.05030', -- Defending Against Unforeseen Failure Modes with Latent Adversarial Training
          '2407.12383', -- Reliable and Efficient Concept Erasure of Text-to-Image Diffusion Models
          '2410.09421', -- VLFeedback: A Large-Scale AI Feedback Dataset for Large Vision-Language Mod
          '2504.03289', -- RWKVTTS: Yet another TTS based on RWKV-7
          '2504.12553', -- ELAB: Extensive LLM Alignment Benchmark in Persian Language
          '2506.02479', -- BitBypass: A New Direction in Jailbreaking Aligned Large Language Models wi
          '2512.04124', -- When AI Takes the Couch: Psychometric Jailbreaks Reveal Internal Conflict i
          '2511.05865', -- CGCE: Classifier-Guided Concept Erasure in Generative Models
          '2509.08592', -- Interpretability as Alignment: Making Internal Understanding a Design Princ
          '2506.00062', -- SafeCOMM: What about Safety Alignment in Fine-Tuned Telecom Large Language
          '2409.19476', -- Overriding Safety protections of Open-source Models
          '2404.05880', -- Eraser: Jailbreaking Defense in Large Language Models via Unlearning Harmfu
          '2308.00862', -- Confidence-Building Measures for Artificial Intelligence: Workshop Proceedi
          '2505.12677', -- CURE: Concept Unlearning via Orthogonal Representation Editing in Diffusion
          '2406.14595', -- Adversaries Can Misuse Combinations of Safe Models
          '2503.06550', -- BingoGuard: LLM Content Moderation Tools with Risk Levels
          '2410.19406', -- An Auditing Test to Detect Behavioral Shift in Language Models
          '2410.20971', -- BlueSuffix: Reinforced Blue Teaming for Vision-Language Models Against Jail
          '2602.08621', -- Sparse Models, Sparse Safety: Unsafe Routes in Mixture-of-Experts LLMs
          '2606.14351', -- ForceForget: Reinforcement Concept Removal for Enhancing Safety in Text-to-
          '2610.00960' -- Video-Index: A Curated Meta-Benchmark for Video Understanding
      )
      OR
      (p.source = 'external' AND p.id IN (
          106032, -- Qwen-CUA: Native Computer Use for (almost) Everything
          131941 -- Introducing Inkling 2 Small
      ))
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'safety methods curation 2026-11-10: passing mention, dataset/benchmark or organization name (RWKV-Red-Team, RedTeam-2K), or robustness claim only'
FROM rt_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING rt_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING rt_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- jailbreak: 757 reviewed true positives of 785 title/abstract candidates.
CREATE TEMP TABLE jb_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'jailbreak'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2502.07557', -- JBShield: Defending Large Language Models from Jailbreak Attacks through Ac
          '2504.10694', -- The Jailbreak Tax: How Useful are Your Jailbreak Outputs?
          '2502.10438', -- Injecting Universal Jailbreak Backdoors into LLMs in Minutes
          '2603.17372', -- Understanding and Defending VLM Jailbreaks via Jailbreak-Related Representa
          '2406.11682', -- Knowledge-to-Jailbreak: Investigating Knowledge-driven Jailbreaking Attacks
          '2504.19440', -- JailbreaksOverTime: Detecting Jailbreak Attacks Under Distribution Shift
          '2411.01565', -- SQL Injection Jailbreak: a structural disaster of large language models
          '2405.20015', -- Efficient LLM-Jailbreaking via Multimodal-LLM Jailbreak
          '2308.03825', -- "Do Anything Now": Characterizing and Evaluating In-The-Wild Jailbreak Prom
          '2402.10260', -- A StrongREJECT for Empty Jailbreaks
          '2605.24535', -- Steering Beyond the Support: Adversarial Training on Unsupervised Jailbroke
          '2305.13860', -- Jailbreaking ChatGPT via Prompt Engineering: An Empirical Study
          '2404.03027', -- JailBreakV: A Benchmark for Assessing the Robustness of MultiModal Large La
          '2409.14866', -- PAPILLON: Efficient and Stealthy Fuzz Testing-Powered Jailbreaks for LLMs
          '2408.04811', -- h4rm3l: A Language for Composable Jailbreak Attack Synthesis
          '2402.03299', -- GUARD: Role-playing to Generate Natural-language Jailbreakings to Test Guid
          '2404.01318', -- JailbreakBench: An Open Robustness Benchmark for Jailbreaking Large Languag
          '2405.20653', -- Enhancing Jailbreak Attack Against Large Language Models through Silent Tok
          '2406.18122', -- Poisoned LangChain: Jailbreak LLMs by LangChain
          '2411.07494', -- Rapid Response: Mitigating LLM Jailbreaks with a Few Examples
          '2502.09638', -- Jailbreaking to Jailbreak
          '2601.03600', -- ALERT: Zero-shot LLM Jailbreak Detection via Internal Discrepancy Amplifica
          '2404.01833', -- Great, Now Write an Article About That: The Crescendo Multi-Turn LLM Jailbr
          '2411.00827', -- IDEATOR: Jailbreaking and Benchmarking Large Vision-Language Models Using T
          '2505.23839', -- GeneBreaker: Jailbreak Attacks against DNA Language Models with Pathogenici
          '2312.02119', -- Tree of Attacks: Jailbreaking Black-Box LLMs Automatically
          '2406.18510', -- WildTeaming at Scale: From In-the-Wild Jailbreaks to (Adversarially) Safer
          '2410.09804', -- BlackDAN: A Black-Box Multi-Objective Approach for Effective and Contextual
          '2501.13772', -- Jailbreak-AudioBench: In-Depth Evaluation and Analysis of Jailbreak Threats
          '2502.11084', -- Rewrite to Jailbreak: Discover Learnable and Transferable Implicit Harmfuln
          '2506.17299', -- LLM Jailbreak Oracle
          '2508.20848', -- JADES: A Universal Framework for Jailbreak Assessment via Decompositional S
          '2406.05498', -- SelfDefend: LLMs Can Defend Themselves against Jailbreaking in a Practical
          '2402.02309', -- Jailbreaking Attack against Multimodal Large Language Model
          '2307.08715', -- MasterKey: Automated Jailbreak Across Multiple Large Language Model Chatbot
          '2601.03005', -- JPU: Bridging Jailbreak Defense and Unlearning via On-Policy Path Rectifica
          '2309.10253', -- GPTFUZZER: Red Teaming Large Language Models with Auto-Generated Jailbreak
          '2310.04451', -- AutoDAN: Generating Stealthy Jailbreak Prompts on Aligned Large Language Mo
          '2310.08419', -- Jailbreaking Black Box Large Language Models in Twenty Queries
          '2311.09096', -- Defending Large Language Models Against Jailbreaking Attacks Through Goal P
          '2402.08567', -- Agent Smith: A Single Image Can Jailbreak One Million Multimodal LLM Agents
          '2402.08983', -- SafeDecoding: Defending against Jailbreak Attacks via Safety-Aware Decoding
          '2402.13494', -- GradSafe: Detecting Jailbreak Prompts for LLMs via Safety-Critical Gradient
          '2403.12171', -- EasyJailbreak: A Unified Framework for Jailbreaking Large Language Models
          '2404.02151', -- Jailbreaking Leading Safety-Aligned LLMs with Simple Adaptive Attacks
          '2404.03411', -- Red Teaming GPT-4V: Are GPT-4V Safe Against Uni/Multi-Modal Jailbreak Attac
          '2409.19149', -- Multimodal Pragmatic Jailbreak on Text-to-image Models
          '2411.18688', -- Immune: Improving Safety Against Jailbreaks in Multi-modal LLMs via Inferen
          '2412.03556', -- Best-of-N Jailbreaking
          '2502.16903', -- GuidedBench: Equipping Jailbreak Evaluation with Guidelines
          '2505.17598', -- One Model Transfer to All: On Robust Jailbreak Prompts Generation against L
          '2601.02670', -- Break Me If You Can: Self-Jailbreaking of Aligned LLMs via Lexical Insertio
          '2603.08234', -- The Struggle Between Continuation and Refusal: A Mechanistic Analysis of th
          '2602.01025', -- Toward Universal and Transferable Jailbreak Attacks on Vision-Language Mode
          '2506.00782', -- Jailbreak-R1: Exploring the Jailbreak Capabilities of LLMs via Reinforcemen
          '2503.20823', -- Playing the Fool: Jailbreaking LLMs and Multimodal LLMs with Out-of-Distrib
          '2502.04204', -- Short-length Adversarial Training Helps LLMs Defend Long-length Jailbreak A
          '2407.15211', -- Failures to Find Transferable Image Jailbreaks Between Vision-Language Mode
          '2510.21910', -- Adversarial Déjà Vu: Jailbreak Dictionary Learning for Stronger Generalizat
          '2510.20956', -- Self-Jailbreaking: Language Models Can Reason Themselves Out of Safety Alig
          '2605.18915', -- DMN: A Compositional Framework for Jailbreaking Multimodal LLMs with Multi-
          '2602.06440', -- TrailBlazer: History-Guided Reinforcement Learning for Black-Box LLM Jailbr
          '2311.08268', -- A Wolf in Sheep''s Clothing: Generalized Nested Jailbreak Prompts can Fool L
          '2401.10862', -- Pruning for Protection: Increasing Jailbreak Resistance in Aligned LLMs Wit
          '2401.17263', -- Robust Prompt Optimization for Defending Language Models Against Jailbreaki
          '2402.16459', -- Defending LLMs against Jailbreaking Attacks via Backtranslation
          '2403.08424', -- Distract Large Language Models for Automatic Jailbreak Attack
          '2405.21018', -- Improved Techniques for Optimization-Based Jailbreaking on Large Language M
          '2406.01288', -- Improved Few-Shot Jailbreaking Can Circumvent Aligned Language Models and T
          '2408.15221', -- LLM Defenses Are Not Robust to Multi-Turn Human Jailbreaks Yet
          '2412.05892', -- PBI-Attack: Prior-Guided Bimodal Interactive Black-Box Jailbreak Attack for
          '2412.05934', -- Heuristic-Induced Multimodal Risk Distribution Jailbreak Attack for Multimo
          '2412.17522', -- DiffusionAttacker: Diffusion-Driven Prompt Manipulation for LLM Jailbreak
          '2501.02629', -- Layer-Level Self-Exposure and Patch: Affirmative Token Mitigation for Jailb
          '2504.03770', -- JailDAM: Jailbreak Detection with Adaptive Memory for Vision-Language Model
          '2505.15406', -- Audio Jailbreak: An Open Comprehensive Benchmark for Jailbreaking Large Aud
          '2506.02479', -- BitBypass: A New Direction in Jailbreaking Aligned Large Language Models wi
          '2510.05025', -- Imperceptible Jailbreaking against Large Language Models
          '2412.18171', -- Token Highlighter: Inspecting and Mitigating Jailbreak Prompts for Large La
          '2411.11496', -- Safe + Safe = Unsafe? Exploring How Safe Images Can Be Exploited to Jailbre
          '2410.20971', -- BlueSuffix: Reinforced Blue Teaming for Vision-Language Models Against Jail
          '2602.22983', -- Obscure but Effective: Classical Chinese Jailbreak Prompt Optimization via
          '2506.12913', -- Jailbreak Transferability Emerges from Shared Representations
          '2605.07414', -- OrchJail: Jailbreaking Tool-Calling Text-to-Image Agents by Orchestration-G
          '2508.16406', -- Retrieval-Augmented Defense: Adaptive and Controllable Jailbreak Prevention
          '2607.11070', -- MJ: Multi-turn LLM Jailbreaking via Decomposed Credit Assignment
          '2610.34074', -- Identically Trained Language Models Break on Different Jailbreaks
          '2311.05608', -- FigStep: Jailbreaking Large Vision-Language Models via Typographic Visual P
          '2311.14455', -- Universal Jailbreak Backdoors from Poisoned Human Feedback
          '2401.06373', -- How Johnny Can Persuade LLMs to Jailbreak Them: Rethinking Persuasion to Ch
          '2401.06561', -- Intention Analysis Makes LLMs A Good Jailbreak Defender
          '2401.06824', -- Revisiting Jailbreaking for Large Language Models: A Representation Enginee
          '2401.17256', -- Weak-to-Strong Jailbreaking on Large Language Models
          '2402.08679', -- COLD-Attack: Jailbreaking LLMs with Stealthiness and Controllability
          '2403.00867', -- Gradient Cuff: Detecting Jailbreak Attacks on Large Language Models by Expl
          '2403.04783', -- AutoDefense: Multi-Agent LLM Defense against Jailbreak Attacks
          '2406.05644', -- How Alignment and Jailbreak Work: Explain LLM Safety through Intermediate H
          '2408.11313', -- Unlocking Adversarial Suffix Optimization Without Affirmative Phrases: Effi
          '2410.13334', -- BiasJailbreak:Analyzing Ethical Biases and Jailbreak Vulnerabilities in Lar
          '2411.06426', -- SequentialBreak: Large Language Models Can be Fooled by Embedding Jailbreak
          '2412.01547', -- Improved Large Language Model Jailbreak Detection via Pretrained Embeddings
          '2501.18837', -- Constitutional Classifiers: Defending against Universal Jailbreaks across T
          '2502.04322', -- Speak Easy: Eliciting Harmful Jailbreaks from LLMs with Simple Interactions
          '2502.19820', -- Foot-In-The-Door: A Multi-turn Jailbreak for LLMs
          '2511.04707', -- Jailbreaking in the Haystack
          '2512.06589', -- OmniSafeBench-MM: A Unified Benchmark and Toolbox for Multimodal Jailbreak
          '2603.19127', -- On Optimizing Multimodal Jailbreaks for Spoken Language Models
          '2602.18154', -- FENCE: A Financial and Multimodal Jailbreak Detection Dataset
          '2502.11090', -- SafeDialBench: A Fine-Grained Safety Evaluation Benchmark for Large Languag
          '2512.18244', -- Breaking Minds, Breaking Systems: Jailbreaking Large Language Models via Hu
          '2511.10519', -- Say It Differently: Linguistic Styles as Jailbreak Vectors
          '2511.01375', -- Align to Misalign: Automatic LLM Jailbreak with Meta-Optimized LLM Judges
          '2510.02833', -- Attack via Overfitting: 10-shot Benign Fine-tuning to Jailbreak LLMs
          '2508.13246', -- Involuntary Jailbreak
          '2508.01741', -- Simulated Ensemble Attack: Transferring Jailbreaks Across Fine-tuned Vision
          '2501.10639', -- Latent-space adversarial training with post-aware calibration for defending
          '2505.21556', -- Benign-to-Toxic Jailbreaking: Inducing Harmful Responses from Harmless Prom
          '2504.08104', -- Geneshift: Impact of different scenario shift on Jailbreaking LLM
          '2503.06519', -- Can Small Language Models Reliably Resist Jailbreak Attacks? A Comprehensiv
          '2410.02298', -- Jailbreak Antidote: Runtime Safety-Utility Balance via Sparse Representatio
          '2405.20099', -- Defensive Prompt Patch: A Robust and Interpretable Defense of LLMs against
          '2404.05880', -- Eraser: Jailbreaking Defense in Large Language Models via Unlearning Harmfu
          '2402.16914', -- DrAttack: Prompt Decomposition and Reconstruction Makes Powerful LLM Jailbr
          '2402.09091', -- Play Guessing Game with LLM: Indirect Jailbreak Attack with Implicit Clues
          '2603.21208', -- JANUS: A Lightweight Framework for Jailbreaking Text-to-Image Models via Di
          '2506.22666', -- VERA: Variational Inference Framework for Jailbreaking Large Language Model
          '2507.01513', -- SafePTR: Token-Level Jailbreak Defense in Multimodal LLMs via Prune-then-Re
          '2603.00565', -- MIDAS: Multi-Image Dispersion and Semantic Reconstruction for Jailbreaking
          '2509.23281', -- Preventing Robotic Jailbreaking Via Multimodal Domain Adaptation
          '2605.24497', -- Reasoning as an Attack Surface: Adaptive Evolutionary CoT Jailbreaks for LL
          '2605.01687', -- MultiBreak: A Scalable and Diverse Multi-turn Jailbreak Benchmark for Evalu
          '2605.17128', -- New Wide-Net-Casting Jailbreak Attacks Risk Large Models
          '2508.06194', -- SceneJailEval: A Scenario-Adaptive Multi-Dimensional Framework for Jailbrea
          '2508.13048', -- MAJIC: Markovian Adaptive Jailbreaking via Iterative Composition of Diverse
          '2504.09466', -- AdaSteer: Your Aligned LLM is Inherently an Adaptive Jailbreak Defender
          '2603.11149', -- Systematic Scaling Analysis of Jailbreak Attacks in Large Language Models
          '2305.12082', -- SneakyPrompt: Jailbreaking Text-to-image Generative Models
          '2307.02483', -- Jailbroken: How Does LLM Safety Training Fail?
          '2307.14539', -- Jailbreak in pieces: Compositional Adversarial Attacks on Multi-Modal Langu
          '2310.03684', -- SmoothLLM: Defending Large Language Models Against Jailbreaking Attacks
          '2310.06987', -- Catastrophic Jailbreak of Open-source LLMs via Exploiting Generation
          '2311.03348', -- Scalable and Transferable Black-Box Jailbreaks for Language Models via Pers
          '2402.09177', -- Leveraging the Context through Multi-Round Interactions for Jailbreaking At
          '2402.10601', -- When "Competency" in Reasoning Opens the Door to Vulnerability: Jailbreakin
          '2404.16369', -- Don''t Say No: Jailbreaking LLM by Suppressing Refusal
          '2406.07188', -- Merging Improves Self-Critique Against Jailbreak Attacks
          '2406.18495', -- WildGuard: Open One-Stop Moderation Tools for Safety Risks, Jailbreaks, and
          '2407.02855', -- From Theft to Bomb-Making: The Ripple Effect of Unlearning in Defending Aga
          '2409.00137', -- Emerging Vulnerabilities in Frontier Models: Multi-Turn Jailbreak Attacks
          '2409.17458', -- RED QUEEN: Safeguarding Large Language Models against Concealed Multi-Turn
          '2410.05295', -- AutoDAN-Turbo: A Lifelong Agent for Strategy Self-Exploration to Jailbreak
          '2410.18469', -- Iterative Self-Tuning LLMs for Enhanced Jailbreaking Capabilities
          '2411.08410', -- The VLLM Safety Paradox: Dual Ease in Jailbreak Attack and Defense
          '2411.14133', -- GASP: Efficient Black-Box Generation of Adversarial Suffixes for Jailbreaki
          '2412.08201', -- Model-Editing-Based Jailbreak against Safety-aligned Large Language Models
          '2412.08615', -- Exploiting the Index Gradients for Optimization-Based Jailbreaking on Large
          '2501.04931', -- Jailbreaking Multimodal Large Language Models via Shuffle Inconsistency
          '2502.01925', -- PANDAS: Improving Many-shot Jailbreaking via Positive Affirmation, Negative
          '2502.09990', -- X-Boundary: Establishing Exact Safety Boundary to Shield LLMs from Multi-Tu
          '2502.12970', -- Reasoning-to-Defend: Safety-Aware Reasoning Can Defend Large Language Model
          '2503.01865', -- Guiding not Forcing: Enhancing the Transferability of Jailbreaking Attacks
          '2505.10838', -- LARGO: Latent Adversarial Reflection through Gradient Optimization for Jail
          '2505.11790', -- JULI: Jailbreak Large Language Models by Self-Introspection
          '2505.22037', -- Jailbreak Distillation: Renewable Safety Benchmarking
          '2507.02844', -- Visual Contextual Attack: Jailbreaking MLLMs with Image-Driven Context Inje
          '2508.10390', -- Jailbreaking Commercial Black-Box LLMs with Explicitly Harmful Prompts
          '2511.12710', -- Evolve the Method, Not the Prompts: Evolutionary Synthesis of Jailbreak Att
          '2602.06854', -- SEMA: Simple yet Effective Learning for Multi-Turn Jailbreak Attacks
          '2509.25843', -- ASGuard: Activation-Scaling Guard to Mitigate Targeted Jailbreaking Attack
          '2602.24009', -- Jailbreak Foundry: From Papers to Runnable Attacks for Reproducible Benchma
          '2603.01291', -- JailNewsBench: Multi-Lingual and Regional Benchmark for Fake News Generatio
          '2505.17568', -- JALMBench: Benchmarking Jailbreak Vulnerabilities in Audio Language Models
          '2511.18933', -- Defending Large Language Models Against Jailbreak Exploits with Responsible
          '2511.02356', -- An Automated Framework for Strategy Discovery, Retrieval, and Evolution in
          '2509.21029', -- FORCE: Transferable Visual Jailbreaking Attacks via Feature Over-Reliance C
          '2509.14297', -- A Simple and Efficient Jailbreak Method Exploiting LLMs'' Helpfulness
          '2508.05087', -- JPS: Jailbreak Multimodal Large Language Models with Collaborative Visual P
          '2508.03054', -- Beyond Surface-Level Detection: Towards Cognitive-Driven Defense Against Ja
          '2508.00555', -- Activation-Guided Local Editing for Jailbreaking Attacks
          '2506.16760', -- Cross-Modal Obfuscation for Jailbreak Attacks on Large Vision-Language Mode
          '2504.21307', -- The Dual Power of Interpretable Token Embeddings: Jailbreaking Attacks and
          '2503.17987', -- Reason2Attack: Jailbreaking Text-to-Image Models via LLM Reasoning
          '2503.12339', -- A Closer Look at Adversarial Suffix Learning for Jailbreaking LLMs: Augment
          '2502.18504', -- TurboFuzzLLM: Turbocharging Mutation-based Fuzzing for Effectively Jailbrea
          '2501.12210', -- You Can''t Eat Your Cake and Have It Too: The Performance Degradation of LLM
          '2412.08608', -- AdvWave: Stealthy Adversarial Jailbreak Attack against Large Audio-Language
          '2410.09040', -- AttnGCG: Enhancing Jailbreaking Attacks on LLMs with Attention Manipulation
          '2403.02910', -- ImgTrojan: Jailbreaking Vision-Language Models with ONE Image
          '2512.06674', -- RunawayEvil: Jailbreaking the Image-to-Video Generative Models
          '2412.10321', -- AdvPrefix: An Objective for Nuanced LLM Jailbreaks
          '2505.19610', -- JailBound: Jailbreaking Internal Safety Boundaries of Vision-Language Model
          '2410.19937', -- RobustKV: Defending Large Language Models against Jailbreak Attacks via KV
          '2604.10326', -- Jailbreaking the Matrix: Nullspace Steering for Controlled Model Subversion
          '2606.11817', -- Grammar-Constrained Decoding Can Jailbreak LLMs into Generating Malicious C
          '2606.25182', -- What Intermediate Layers Know: Detecting Jailbreaks from Entropy Dynamics
          '2605.24550', -- Jailbreak to Protect: Buffering and Reinforcing via Temporary Jailbreaking
          '2605.04700', -- Sparse Tokens Suffice: Jailbreaking Audio Language Models via Token-Aware G
          '2601.03265', -- Jailbreak-Zero: A Path to Pareto Optimal Red Teaming for Large Language Mod
          '2512.23173', -- EquaCode: A Multi-Strategy Jailbreak Approach for Large Language Models via
          '2503.12931', -- MirrorShield: Towards Dynamic Adaptive Defense Against Jailbreaks via Entro
          '2605.27932', -- When Think-with-Image Meets Safety: What Determines Multimodal Jailbreak Ro
          '2605.10582', -- Guaranteed Jailbreaking Defense via Disrupt-and-Rectify Smoothing
          '2310.06474', -- Multilingual Jailbreak Challenges in Large Language Models
          '2311.03191', -- DeepInception: Hypnotize Large Language Model to Be Jailbreaker
          '2402.11753', -- ArtPrompt: ASCII Art-based Jailbreak Attacks against Aligned LLMs
          '2402.13457', -- A Comprehensive Study of Jailbreak Attack versus Defense for Large Language
          '2402.15180', -- Break the Breakout: Reinventing LM Defense Against Jailbreak Attacks with S
          '2403.09792', -- Images are Achilles'' Heel of Alignment: Exploiting Visual Vulnerabilities f
          '2404.07921', -- AmpleGCG: Learning a Universal and Transferable Generative Model of Adversa
          '2406.18118', -- SafeAligner: Safety Alignment against Jailbreak Attacks via Response Dispar
          '2410.02832', -- FlipAttack: Jailbreak LLMs via Flipping
          '2410.04190', -- Harnessing Task Overload for Scalable Jailbreak Attacks on Large Language M
          '2410.12855', -- JAILJUDGE: A Comprehensive Jailbreak Judge Benchmark with Multi-Agent Enhan
          '2410.22143', -- AmpleGCG-Plus: A Strong Generative Model of Adversarial Suffixes to Jailbre
          '2501.18632', -- Towards Safe AI Clinicians: A Comprehensive Study on Large Language Model J
          '2502.01154', -- Jailbreaking with Universal Multi-Prompts
          '2502.03052', -- Understanding and Enhancing the Transferability of Jailbreaking Attacks
          '2502.14486', -- How Jailbreak Defenses Work and Ensemble? A Mechanistic Investigation
          '2502.14744', -- HiddenDetect: Detecting Jailbreak Attacks against Large Vision-Language Mod
          '2502.16750', -- Guardians of the Agentic System: Preventing Many Shots Jailbreak with Agent
          '2502.19883', -- Beyond the Tip of Efficiency: Uncovering the Submerged Threats of Jailbreak
          '2503.01839', -- Jailbreaking Safeguarded Text-to-Image Models via Large Language Models
          '2503.10619', -- Tempest: Autonomous Multi-Turn Jailbreaking of Large Language Models with T
          '2504.11168', -- Bypassing Prompt Injection and Jailbreak Detection in LLM Guardrails
          '2504.13203', -- X-Teaming: Multi-Turn Jailbreaks and Defenses with Adaptive Multi-Agents
          '2505.13862', -- PandaGuard: Systematic Evaluation of LLM Safety against Jailbreaking Attack
          '2505.16446', -- Implicit Jailbreak Attacks via Cross-Modal Information Concealment on Visio
          '2506.07402', -- Beyond Jailbreaks: Revealing Stealthier and Broader LLM Security Risks Stem
          '2506.10597', -- SoK: Evaluating Jailbreak Guardrails for Large Language Models
          '2506.12880', -- Universal Jailbreak Suffixes Are Strong Attention Hijackers
          '2602.10179', -- When the Prompt Becomes Visual: Vision-Centric Jailbreak Attacks for Large
          '2604.19274', -- HarDBench: A Benchmark for Draft-Based Co-Authoring Jailbreak Attacks for S
          '2603.07028', -- Two Frames Matter: A Temporal Attack for Text-to-Video Model Jailbreaking
          '2511.13127', -- SPARK: Jailbreaking T2V Models by Synergistically Prompting Auditory and Re
          '2602.10148', -- Red-teaming the Multimodal Reasoning: Jailbreaking Vision-Language Models v
          '2602.07107', -- ShallowJail: Steering Jailbreaks against Large Language Models
          '2601.20903', -- ICON: Intent-Context Coupling for Efficient Multi-Turn Jailbreak Attack
          '2601.05445', -- Knowledge-Driven Multi-Turn Jailbreaking on Large Language Models
          '2511.15304', -- Adversarial Poetry as a Universal Single-Turn Jailbreak Mechanism in Large
          '2511.11784', -- NegBLEURT Forest: Leveraging Inconsistencies for Detecting Jailbreak Attack
          '2511.07315', -- JPRO: Automated Multimodal Jailbreaking via Multi-Agent Collaboration Frame
          '2510.21285', -- When Models Outthink Their Safety: Mitigating Self-Jailbreak in Large Reaso
          '2510.17904', -- BreakFun: Jailbreaking LLMs via Schema Exploitation
          '2510.03417', -- NEXUS: Network Exploration for eXploiting Unsafe Sequences in Multi-Turn LL
          '2509.11629', -- Reasoned Safety Alignment: Ensuring Jailbreak Defense via Answer-Then-Check
          '2508.09218', -- Towards Effective MLLM Jailbreaking Through Balanced On-Topicness and OOD-I
          '2508.10029', -- Latent Fusion Jailbreak: Blending Harmful and Harmless Representations to E
          '2507.21540', -- PRISM: Programmatic Reasoning with Image Sequence Manipulation for LVLM Jai
          '2507.22171', -- Enhancing Jailbreak Attacks on LLMs via Persona Prompts
          '2507.02332', -- PII Jailbreaking in LLMs via Activation Steering Reveals Personal Informati
          '2505.06679', -- T2V-OptJail: Discrete Prompt Optimization for Text-to-Video Jailbreak Attac
          '2502.15806', -- A Mousetrap: Fooling Large Reasoning Models for Jailbreak with Chain of Ite
          '2502.09723', -- QueryAttack: Jailbreaking Aligned Large Language Models Using Structured No
          '2501.18638', -- Graph of Attacks with Pruning: Optimizing Stealthy Jailbreak Prompt Generat
          '2402.18104', -- Making Them Ask and Answer: Jailbreaking Large Language Models in Few Queri
          '2502.00653', -- Towards Robust Multimodal Large Language Models Against Jailbreak Attacks
          '2603.22094', -- Principled Steering via Null-space Projection for Jailbreak Defense in Visi
          '2411.01077', -- Emoji Attack: Enhancing Jailbreak Attacks Against Judge LLM Detection
          '2502.01633', -- Adversarial Reasoning at Jailbreaking Time
          '2504.05838', -- Mind the Trojan Horse: Image Prompt Adapter Enabling Scalable and Deceptive
          '2502.10794', -- Distraction is All You Need for Multimodal Large Language Model Jailbreakin
          '2411.16721', -- Steering Away from Harm: An Adaptive Approach to Defending Vision Language
          '2410.01294', -- Endless Jailbreaks with Bijection Learning
          '2601.04603', -- Constitutional Classifiers++: Efficient Production-Grade Defenses against U
          '2603.03081', -- TAO-Attack: Toward Advanced Optimization-Based Jailbreak Attacks for Large
          '2509.22292', -- Jailbreaking on Text-to-Video Models via Scene Splitting Strategy
          '2510.17759', -- VERA-V: Variational Inference Framework for Jailbreaking Vision-Language Mo
          '2601.09321', -- SpatialJB: How Text Distribution Art Becomes The "Jailbreak Key" for LLM Gu
          '2605.18168', -- Acoustic Interference: A New Paradigm Weaponizing Acoustic Latent Semantic
          '2606.02640', -- D-Judge: Disrupting Multi-Turn Jailbreaks using Semantics-Preserving Output
          '2601.19487', -- LLM-VA: Resolving the Jailbreak-Overrefusal Trade-off via Vector Alignment
          '2601.03416', -- GAMBIT: A Gamified Jailbreak Framework for Multimodal Large Language Models
          '2512.12069', -- Rethinking Jailbreak Detection of Large Vision Language Models with Represe
          '2604.09748', -- Backdoors in RLVR: Jailbreak Backdoors in LLMs From Verifiable Reward
          '2506.15734', -- SafetyReminder: Reviving Delayed Safety Awareness of Vision-Language Models
          '2507.05248', -- Response Attack: Exploiting Contextual Priming to Jailbreak Large Language
          '2505.19684', -- VisCRA: A Visual Chain Reasoning Attack for Jailbreaking Multimodal Large L
          '2507.11630', -- Jailbreak-Tuning: Models Efficiently Learn Jailbreak Susceptibility
          '2509.10931', -- Harmful Prompt Laundering: Jailbreaking LLMs with Abductive Styles and Symb
          '2605.10779', -- LITMUS: Benchmarking Behavioral Jailbreaks of LLM Agents in Real OS Environ
          '2306.13213', -- Visual Adversarial Examples Jailbreak Aligned Large Language Models
          '2310.02446', -- Low-Resource Languages Jailbreak GPT-4
          '2310.06387', -- Jailbreak and Guard Aligned Language Models with Only Few In-Context Demons
          '2402.06255', -- Fight Back Against Jailbreaking via Prompt Adversarial Tuning
          '2405.01229', -- Boosting Jailbreak Attack with Momentum
          '2405.20775', -- Medical MLLM is Vulnerable: Cross-Modality Jailbreak and Mismatched Attacks
          '2407.08441', -- Are Large Language Models Really Bias-Free? Jailbreak Prompts for Assessing
          '2409.11445', -- Jailbreaking Large Language Models with Symbolic Mathematics
          '2410.03857', -- You Know What I''m Saying: Jailbreak Attack via Implicit Reference
          '2410.13886', -- Refusal-Trained LLMs Are Easily Jailbroken As Browser Agents
          '2501.19180', -- Enhancing Model Defense Against Jailbreaks with Proactive Safety Reasoning
          '2502.13162', -- ShieldLearner: A New Paradigm for Jailbreak Attack Defense in LLMs
          '2502.13603', -- Efficient Safety Retrofitting Against Jailbreaking for LLMs
          '2505.13541', -- SPIRIT: Patching Speech Language Models against Jailbreak Attacks
          '2507.13474', -- Paper Summary Attack: Jailbreaking LLMs through LLM Safety Papers
          '2510.09023', -- The Attacker Moves Second: Stronger Adaptive Attacks Bypass Defenses Agains
          '2602.08741', -- Large Language Lobotomy: Jailbreaking Mixture-of-Experts via Expert Silenci
          '2512.07761', -- TROJail: Trajectory-Level Optimization for Multi-Turn Large Language Model
          '2604.07835', -- Silencing the Guardrails: Inference-Time Jailbreaking via Dynamic Contextua
          '2602.20999', -- VII: Visual Instruction Injection for Jailbreaking Image-to-Video Generatio
          '2601.10971', -- AJAR: Adaptive Jailbreak Architecture for Red-teaming
          '2512.05485', -- TeleAI-Safety: A comprehensive LLM jailbreaking benchmark towards attacks,
          '2511.17874', -- Beyond Jailbreak: Unveiling Risks in LLM Applications Arising from Blurred
          '2510.05379', -- AutoDAN-Reasoning: Enhancing Strategies Exploration based Jailbreak Attacks
          '2508.16889', -- ObjexMT: Objective Extraction and Metacognitive Calibration for LLM-as-a-Ju
          '2508.12072', -- Mitigating Jailbreaks with Intent-Aware LLMs
          '2502.12893', -- H-CoT: Hijacking the Chain-of-Thought Safety Reasoning Mechanism to Jailbre
          '2411.18000', -- Exploring Visual Vulnerabilities via Multi-Loss Adversarial Search for Jail
          '2410.04234', -- Functional Homotopy: Smoothing Discrete Optimization via Continuous Paramet
          '2605.20286', -- Adaptive Probe-based Steering for Robust LLM Jailbreaking
          '2605.10067', -- Metis: Learning to Jailbreak LLMs via Self-Evolving Metacognitive Policy Op
          '2605.20654', -- Reflector: Internalizing Step-wise Reflection against Indirect Jailbreaks
          '2605.02958', -- Tracing the Dynamics of Refusal: Exploiting Latent Refusal Trajectories for
          '2605.00583', -- Jailbreaking Vision-Language Models Through the Visual Modality
          '2606.02111', -- Jailbreaking Multimodal Large Language Models using Multi-Clip Video
          '2606.04027', -- MaskForge: Structure-Aware Adaptive Attacks for Jailbreaking Diffusion Larg
          '2602.04896', -- Steering Externalities: Benign Activation Steering Unintentionally Increase
          '2609.30841', -- Why Jailbreaks Succeed in Diffusion Language Models: An Energy Landscape An
          '2605.26409', -- Jailbreak susceptibility prediction and mitigation via the behavioral geome
          '2605.05709', -- Conceal, Reconstruct, Jailbreak: Exploiting the Reconstruction--Concealment
          '2301.12867', -- Red teaming ChatGPT via Jailbreaking: Bias, Robustness, Reliability and Tox
          '2304.05197', -- Multi-step Jailbreaking Privacy Attacks on ChatGPT
          '2404.14461', -- Competition Report: Finding Universal Jailbreak Backdoors in Aligned LLMs
          '2406.14393', -- Jailbreaking as a Reward Misspecification Problem
          '2408.16163', -- FRACTURED-SORRY-Bench: Framework for Revealing Attacks in Conversational Tu
          '2410.10700', -- Derail Yourself: Multi-turn LLM Jailbreak Attack through Self-discovered Cl
          '2501.01830', -- Auto-RT: Automatic Jailbreak Strategy Exploration for Red-Teaming Large Lan
          '2508.03365', -- When Good Sounds Go Adversarial: Jailbreaking Audio-Language Models with Be
          '2512.04124', -- When AI Takes the Couch: Psychometric Jailbreaks Reveal Internal Conflict i
          '2509.08729', -- X-Teaming Evolutionary M2S: Automated Discovery of Multi-turn to Single-tur
          '2505.08804', -- TokenProber: Jailbreaking Text-to-image Models via Fine-grained Word Impact
          '2402.16006', -- ASETF: A Novel Method for Jailbreak Attack on LLMs through Translate Suffix
          '2603.29038', -- Trojan-Speak: Bypassing Constitutional Classifiers with No Jailbreak Tax vi
          '2601.07141', -- MacPrompt: Maraconic-Guided Jailbreak Against Text-to-Image Models
          '2605.10998', -- Few-Shot Truly Benign DPO Attack for Jailbreaking LLMs
          '2407.16667', -- RedAgent: Red Teaming Large Language Models with Context-aware Autonomous L
          '2410.09024', -- AgentHarm: A Benchmark for Measuring Harmfulness of LLM Agents
          '2501.01335', -- CySecBench: Generative AI-based CyberSecurity-focused Prompt Dataset for Be
          '2507.06282', -- The bitter lesson of misuse detection
          '2412.03235', -- Does Safety Training of LLMs Generalize to Semantically Related Natural Pro
          '2508.19292', -- Stand on The Shoulders of Giants: Building JailExpert from Previous Attack
          '2310.15140', -- AutoDAN: Interpretable Gradient-Based Adversarial Attacks on Large Language
          '2502.15427', -- Adversarial Prompt Evaluation: Systematic Benchmarking of Guardrails Agains
          '2601.04034', -- HoneyTrap: Deceiving Large Language Model Attackers to Honeypot Traps with
          '2606.16242', -- Rapid Poison: Practical Poisoning Attacks Against the Rapid Response Framew
          '2502.15334', -- Attention Eclipse: Manipulating Attention to Bypass LLM Safety-Alignment
          '2605.12128', -- Metaphor Is Not All Attention Needs
          '2405.08317', -- SpeechGuard: Exploring the Adversarial Robustness of Multimodal Large Langu
          '2407.11969', -- Does Refusal Training in LLMs Generalize to the Past Tense?
          '2505.20259', -- Lifelong Safety Alignment for Language Models
          '2506.07452', -- When Style Breaks Safety: Defending Language Models Against Superficial Sty
          '2507.11097', -- The Devil behind the mask: An emergent safety vulnerability of Diffusion LL
          '2601.01747', -- Crafting Adversarial Inputs for Large Vision-Language Models Using Black-Bo
          '2510.26096', -- ALMGuard: Safety Shortcuts and Where to Find Them as Guardrails for Audio-L
          '2507.11500', -- ARMOR: Aligning Secure and Safe Large Language Models via Meticulous Reason
          '2506.05346', -- Why LLM Safety Guardrails Collapse After Fine-tuning: A Similarity Analysis
          '2604.12817', -- Understanding and Improving Continuous LLM Adversarial Training via In-cont
          '2606.23496', -- TROPT: An Open Framework for Unifying and Advancing Discrete Text Optimizat
          '2602.11096', -- Safety Recovery in Reasoning Models Is Only a Few Early Steering Steps Away
          '2403.09513', -- AdaShield: Safeguarding Multimodal Large Language Models from Structure-bas
          '2605.21834', -- On-Policy Consistency Training Improves LLM Safety with Minimal Capability
          '2402.15570', -- Fast Adversarial Attacks on Language Models In One GPU Minute
          '2407.02551', -- Breach By A Thousand Leaks: Unsafe Information Leakage in `Safe'' AI Respons
          '2407.08770', -- Model Surgery: Modulating LLM''s Behavior Via Simple Parameter Editing
          '2408.07663', -- Alignment-Enhanced Decoding:Defending via Token-Level Adaptive Refining of
          '2411.09125', -- DROJ: A Prompt-Driven Attack against Large Language Models
          '2502.11411', -- Detecting and Filtering Unsafe Training Data via Data Attribution
          '2502.13946', -- Why Safeguarded Ships Run Aground? Aligned Large Language Models'' Safety Me
          '2503.03710', -- Improving LLM Safety Alignment with Dual-Objective Optimization
          '2503.04856', -- One-Shot is Enough: Consolidating Multi-Turn Attacks into Efficient Single-
          '2505.11413', -- CARES: Comprehensive Evaluation of Safety and Adversarial Robustness in Med
          '2510.11570', -- Bag of Tricks for Subverting Reasoning-based Safety Guardrails
          '2604.18756', -- Towards Understanding the Robustness of Sparse Autoencoders
          '2602.16977', -- Fail-Closed Alignment for Large Language Models
          '2601.03537', -- STAR-S: Improving Safety Alignment through Self-Taught Reasoning on Safety
          '2511.06512', -- EASE: Practical and Efficient Safety Alignment for Small Language Models
          '2510.17947', -- PLAGUE: Plug-and-play framework for Lifelong Adaptive Generation of Multi-t
          '2510.15476', -- SoK: Taxonomy and Evaluation of Prompt Security in Large Language Models
          '2510.01494', -- Understanding Adversarial Transfer: Why Representation-Space Attacks Fail W
          '2509.15202', -- Beyond Surface Alignment: Rebuilding LLMs Safety Mechanism via Probabilisti
          '2508.10031', -- Context Misleads LLMs: The Role of Context Filtering in Maintaining Safe Al
          '2506.00781', -- CoP: Agentic Red-teaming for Large Language Models using Composition of Pri
          '2605.22880', -- How Far Will They Go? Red-Teaming Online Influence with Large Language Mode
          '2510.00565', -- Toward Safer Diffusion Language Models: Discovery and Mitigation of Priming
          '2605.01899', -- Disentangling Intent from Role: Adversarial Self-Play for Persona-Invariant
          '2604.25921', -- One Word at a Time: Incremental Completion Decomposition Breaks LLM Safety
          '2501.02018', -- SAFENUDGE: Safeguarding Large Language Models in Real-time with Tunable Saf
          '2510.13698', -- Attention Misses Visual Risk: Risk-Adaptive Steering for Multimodal Safety
          '2609.39902', -- CodeMimicry: Exploiting Safety Generalization Lag in Large Language Models
          '2512.06655', -- Graph-Regularized Sparse Autoencoders for LLM Safety Steering
          '2401.05998', -- Combating Adversarial Attacks with Multi-Agent Debate
          '2402.03303', -- Nevermind: Instruction Override and Moderation in Large Language Models
          '2402.14020', -- Coercing LLMs to do and reveal (almost) anything
          '2404.13968', -- Protecting Your LLMs with Information Bottleneck
          '2404.16020', -- Universal Adversarial Triggers Are Not Universal
          '2404.16873', -- AdvPrompter: Fast Adaptive Adversarial Prompting for LLMs
          '2406.03589', -- Ranking Manipulation for Conversational Search Engines
          '2407.15549', -- Latent Adversarial Training Improves Robustness to Persistent Harmful Behav
          '2408.11006', -- Security Attacks on LLM-based Code Completion Tools
          '2408.11851', -- SAGE-RT: Synthetic Alignment data Generation for Safety Evaluation and Red
          '2409.00598', -- Automatic Pseudo-Harmful Prompt Generation for Evaluating False Refusals in
          '2410.02163', -- Adversarial Decoding: Generating Readable Documents for Adversarial Objecti
          '2411.17075', -- Don''t Command, Cultivate: An Exploratory Study of System-2 Alignment
          '2412.07724', -- Granite Guardian
          '2501.01872', -- Turning Logic Against Itself : Probing Model Defenses Through Contrastive Q
          '2501.14073', -- LLMs are Vulnerable to Malicious Prompts Disguised as Scientific Language
          '2501.16534', -- Targeting Alignment: Extracting Safety Classifiers of Aligned LLMs
          '2501.18628', -- Indiana Jones: There Are Always Some Useful Ancient Relics
          '2502.02384', -- STAIR: Improving Safety Alignment with Introspective Reasoning
          '2504.07113', -- How Robust Are Router-LLMs? Analysis of the Fragility of LLM Routing Capabi
          '2505.04388', -- The Aloe Family Recipe for Open and Specialized Healthcare LLMs
          '2505.06538', -- Think in Safety: Unveiling and Mitigating Safety Alignment Collapse in Mult
          '2505.14607', -- sudoLLM : On Multi-role Alignment of Language Models
          '2505.14667', -- SAFEPATH: Preventing Harmful Reasoning in Chain-of-Thought via Early Alignm
          '2505.16186', -- SafeKey: Amplifying Aha-Moment Insights for Safety Reasoning
          '2505.20162', -- Capability-Based Scaling Laws for LLM Red-Teaming
          '2505.21784', -- Towards Safety Reasoning in LLMs: AI-agentic Deliberation for Policy-embedd
          '2506.12299', -- QGuard:Question-based Zero-shot Guard for Multi-modal LLM Safety
          '2506.13901', -- Alignment Quality Index (AQI) : Beyond Refusals: AQI as an Intrinsic Alignm
          '2507.03167', -- Adversarial Manipulation of Reasoning Models using Internal Representations
          '2507.11878', -- LLMs Encode Harmfulness and Refusal Separately
          '2509.18058', -- Strategic Dishonesty Can Undermine AI Safety Evaluations of Frontier LLM
          '2510.01586', -- AdvEvo-MARL: Shaping Internalized Safety through Adversarial Co-Evolution i
          '2510.11851', -- Deep Research Brings Deeper Harm
          '2604.05179', -- Gradient-Controlled Decoding: A Safety Guardrail for LLMs with Dual-Anchor
          '2603.23509', -- Internal Safety Collapse in Frontier Large Language Models
          '2602.14161', -- When Benchmarks Lie: Evaluating Malicious Prompt Classifiers Under True Dis
          '2602.04448', -- RASA: Routing-Aware Safety Alignment for Mixture-of-Experts Models
          '2602.03402', -- Risk Awareness Injection: Calibrating Vision-Language Models for Safety wit
          '2602.01600', -- Expected Harm: Rethinking Safety Evaluation of (Mis)Aligned LLMs
          '2601.10589', -- Be Your Own Red Teamer: Safety Alignment via Self-Play and Reflective Exper
          '2512.07141', -- Think-Reflect-Revise: A Policy-Guided Reflective Framework for Safety Align
          '2512.01353', -- The Trojan Knowledge: Bypassing Commercial LLM Guardrails via Harmless Prom
          '2511.16229', -- Q-MLLM: Vector Quantization for Robust Multimodal Large Language Model Secu
          '2510.20129', -- SAID: Empowering Large Language Models with Self-Activating Internal Defens
          '2509.09708', -- Beyond I''m Sorry, I Can''t: Dissecting Large Language Model Refusal
          '2509.16060', -- SABER: Uncovering Vulnerabilities in Safety Alignment via Cross-Layer Resid
          '2509.14651', -- MUSE: MCTS-Driven Red Teaming Framework for Enhanced Multi-Turn Dialogue Sa
          '2508.19697', -- Safety Alignment Should Be Made More Than Just A Few Attention Heads
          '2508.17739', -- Speculative Safety-Aware Decoding
          '2505.17089', -- Trust Me, I Can Handle It: Self-Generated Adversarial Scenario Extrapolatio
          '2504.01278', -- Strategize Globally, Adapt Locally: A Multi-Turn Red Teaming Agent with Dua
          '2502.18935', -- JailBench: A Comprehensive Chinese Security Assessment Benchmark for Large
          '2501.08814', -- SAIF: A Comprehensive Framework for Evaluating the Risks of Generative AI i
          '2605.05662', -- XL-SafetyBench: A Country-Grounded Cross-Cultural Benchmark for LLM Safety
          '2605.24834', -- Reflect-Guard: Enhancing LLM Safeguards against Adversarial Prompts via Log
          '2505.17132', -- Dynamic Token Reweighting for Robust Vision-Language Models
          '2502.13329', -- Language Models Can Predict Their Own Behavior
          '2505.19911', -- Attention! You Vision Language Model Could Be Maliciously Manipulated
          '2603.30034', -- EnsembleSHAP: Faithful and Certifiably Robust Attribution for Random Subspa
          '2510.02609', -- RedCodeAgent: Automatic Red-teaming Agent against Diverse Code Agents
          '2602.21346', -- Alignment-Weighted DPO: A principled reasoning approach to improve safety a
          '2506.07022', -- AlphaSteer: Learning Refusal Steering with Principled Null-Space Constraint
          '2509.23362', -- Dual-Space Smoothness for Robust and Balanced LLM Unlearning
          '2509.24296', -- DiffuGuard: How Intrinsic Safety is Lost and Found in Diffusion Large Langu
          '2606.11409', -- Risk Under Pressure: Compute-Aware Evaluation of Adversarial Robustness in
          '2602.16346', -- Helpful to a Fault: Measuring Illicit Assistance in Multi-Turn, Multilingua
          '2605.08930', -- Internalizing Safety Understanding in Large Reasoning Models via Verificati
          '2604.22134', -- SHAPE: Unifying Safety, Helpfulness and Pedagogy for Educational LLMs
          '2604.12359', -- Compiling Activation Steering into Weights via Null-Space Constraints for S
          '2607.07918', -- Efficient Safety Alignment of Language Models via Latent Personality Traits
          '2605.27823', -- Disentangling Adversarial Prompts: A Semantic-Graph Defense for Robust LLM
          '2608.09867', -- Stealing Reasoning Traces from Proprietary LLM APIs
          '2508.15648', -- SDGO: Self-Discrimination-Guided Optimization for Consistent Safety in Larg
          '2512.02973', -- Contextual Image Attack: How Visual Context Exposes Multimodal Safety Vulne
          '2603.14825', -- Two Birds, One Projection: Harmonizing Safety and Utility in LVLMs via Infe
          '2609.36956', -- Controlled Decoding Attacks on Black-Box LLMs
          '2510.02194', -- UpSafe℃: Upcycling for Controllable Safety in Large Language Models
          '2605.02971', -- Multilingual Safety Alignment via Self-Distillation
          '2603.24511', -- Claudini: Autoresearch Discovers State-of-the-Art Adversarial Attack Algori
          '2305.03495', -- Automatic Prompt Optimization with "Gradient Descent" and Beam Search
          '2306.11698', -- DecodingTrust: A Comprehensive Assessment of Trustworthiness in GPT Models
          '2307.15043', -- Universal and Transferable Adversarial Attacks on Aligned Language Models
          '2308.09662', -- Red-Teaming Large Language Models using Chain of Utterances for Safety-Alig
          '2308.10741', -- On the Adversarial Robustness of Multi-Modal Foundation Models
          '2309.00614', -- Baseline Defenses for Adversarial Attacks Against Aligned Language Models
          '2310.01386', -- Who is ChatGPT? Benchmarking LLMs'' Psychological Portrayal Using PsychoBenc
          '2310.02224', -- Can Language Models be Instructed to Protect Personal Information?
          '2310.03693', -- Fine-tuning Aligned Language Models Compromises Safety, Even When Users Do
          '2310.10844', -- Survey of Vulnerabilities in Large Language Models Revealed by Adversarial
          '2310.14303', -- Language Model Unalignment: Parametric Red-Teaming to Expose Hidden Harms a
          '2310.19181', -- From Chatbots to PhishBots? -- Preventing Phishing scams created using Chat
          '2311.04235', -- Can LLMs Follow Simple Rules?
          '2311.05915', -- Fake Alignment: Are LLMs Really Aligned Well?
          '2311.06899', -- Flames: Benchmarking Value Alignment of LLMs in Chinese
          '2311.16101', -- How Many Unicorns Are in This Image? A Safety Evaluation Benchmark for Visi
          '2311.16119', -- Ignore This Title and HackAPrompt: Exposing Systemic Vulnerabilities of LLM
          '2401.01967', -- A Mechanistic Understanding of Alignment Algorithms: A Case Study on DPO an
          '2401.10647', -- Sowing the Wind, Reaping the Whirlwind: The Impact of Editing Language Mode
          '2401.11206', -- InferAligner: Inference-Time Alignment for Harmlessness through Cross-Model
          '2401.18018', -- On Prompt-Driven Safeguarding for Large Language Models
          '2402.02207', -- Safety Fine-Tuning at (Almost) No Cost: A Baseline for Vision Large Languag
          '2402.05162', -- Assessing the Brittleness of Safety Alignment via Pruning and Low-Rank Modi
          '2402.10196', -- A Trembling House of Cards? Mapping Adversarial Attacks against Language Ag
          '2402.12991', -- TRAP: Targeted Random Adversarial Prompt Honeypot for Black-Box Identificat
          '2402.15302', -- How (un)ethical are instruction-centric responses of LLMs? Unveiling the vu
          '2402.15911', -- PRP: Propagating Universal Perturbations to Attack Large Language Model Gua
          '2403.09037', -- The First to Know: How Token Distributions Reveal Hidden Knowledge in Large
          '2403.13031', -- RigorLLM: Resilient Guardrails for Large Language Models against Undesired
          '2404.13208', -- The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructi
          '2405.06823', -- PLeak: Prompt Leaking Attacks against Large Language Model Applications
          '2405.09055', -- A safety realignment framework via subspace-oriented model fusion for large
          '2405.11647', -- Hummer: Towards Limited Competitive Preference Dataset
          '2405.12523', -- Single Image Unlearning: Efficient Machine Unlearning in Multimodal Large L
          '2405.14577', -- Representation Noising: A Defence Mechanism Against Harmful Finetuning
          '2405.19360', -- ART: Automatic Red-teaming for Text-to-Image Models to Protect Benign Users
          '2406.05946', -- Safety Alignment Should Be Made More Than Just a Few Tokens Deep
          '2406.07057', -- MultiTrust: A Comprehensive Benchmark Towards Trustworthy Multimodal Large
          '2406.11717', -- Refusal in Language Models Is Mediated by a Single Direction
          '2406.12935', -- ChatBug: A Common Vulnerability of Aligned LLMs Induced by Chat Templates
          '2407.00075', -- Logicbreaks: A Framework for Understanding Subversion of Rule-based Inferen
          '2407.01376', -- Badllama 3: removing safety finetuning from Llama 3 in minutes
          '2407.05965', -- T2VSafetyBench: Evaluating the Safety of Text-to-Video Generative Models
          '2407.09121', -- Refuse Whenever You Feel Unsafe: Improving Safety in LLMs via Decoupled Ref
          '2407.16318', -- PrimeGuard: Safe and Helpful LLMs through Tuning-Free Routing
          '2407.16637', -- Course-Correction: Safety Alignment Using Synthetic Preferences
          '2407.16997', -- Revisiting Who''s Harry Potter: Towards Targeted Unlearning from a Causal In
          '2408.11727', -- Efficient Detection of Toxic Prompts in Large Language Models
          '2410.01524', -- HarmAug: Effective Data Augmentation for Knowledge Distillation of Safety G
          '2410.02828', -- PyRIT: A Framework for Security Risk Identification and Red Teaming in Gene
          '2410.03769', -- SciSafeEval: A Comprehensive Benchmark for Safety Alignment of Large Langua
          '2410.13236', -- SPIN: Self-Supervised Prompt INjection
          '2410.13722', -- Persistent Pre-Training Poisoning of LLMs
          '2410.13785', -- PopAlign: Diversifying Contrasting Patterns for a More Comprehensive Alignm
          '2410.18210', -- Towards Understanding the Fragility of Multilingual LLMs against Fine-Tunin
          '2411.11296', -- Steering Language Model Refusal with Sparse Autoencoders
          '2411.12946', -- A Flexible Large Language Models Guardrail Development Methodology Applied
          '2412.00357', -- Safety Alignment Backfires: Preventing the Re-emergence of Suppressed Conce
          '2412.02626', -- Time-Reversal Provides Unsupervised Feedback to LLMs
          '2412.09565', -- Obfuscated Activations Bypass LLM Latent-Space Defenses
          '2412.11041', -- Separate the Wheat from the Chaff: A Post-Hoc Approach to Safety Re-Alignme
          '2412.16720', -- OpenAI o1 System Card
          '2412.19792', -- InfAlign: Inference-aware language model alignment
          '2501.15446', -- Token Democracy: The Architectural Limits of Alignment in Transformer-Based
          '2501.16497', -- Smoothed Embeddings for Robust Language Models
          '2502.05206', -- Safety at Scale: A Comprehensive Survey of Large Model Safety
          '2502.05374', -- Towards LLM Unlearning Resilient to Relearning Attacks: A Sharpness-Aware M
          '2502.07985', -- MetaSC: Test-Time Safety Specification Optimization for Language Models
          '2502.12202', -- To Think or Not to Think: Exploring the Unthinking Vulnerability in Large R
          '2502.12659', -- The Hidden Risks of Large Reasoning Models: A Safety Assessment of R1
          '2502.17424', -- Emergent Misalignment: Narrow finetuning can produce broadly misaligned LLM
          '2502.19537', -- No, of course I can! Refusal Mechanisms Can Be Exploited Using Harmless Fin
          '2503.00224', -- À la recherche du sens perdu: your favourite LLM might have more to say tha
          '2503.03502', -- CURVALID: Geometrically-guided Adversarial Prompt Detection
          '2503.06269', -- Using Mechanistic Interpretability to Craft Adversarial Attacks against Lar
          '2503.16861', -- In-House Evaluation Is Not Enough: Towards Robust Third-Party Flaw Disclosu
          '2503.18991', -- HAIR: Hardness-Aware Inverse Reinforcement Learning with Introspective Reas
          '2504.01308', -- Safeguarding Vision-Language Models: Mitigating Vulnerabilities to Gaussian
          '2504.01550', -- Representation Bending for Large Language Model Safety
          '2504.02193', -- More is Less: The Pitfalls of Multi-Model Synthetic Preference Data in DPO
          '2504.07887', -- Benchmarking Adversarial Robustness to Bias Elicitation in Large Language M
          '2504.10081', -- RealSafe-R1: Safety-Aligned DeepSeek-R1 without Compromising Reasoning Capa
          '2504.12562', -- ZeroSumEval: Scaling LLM Evaluation with Inter-Model Competition
          '2505.05619', -- LiteLMGuard: Seamless and Lightweight On-Device Prompt Filtering for Safegu
          '2505.14536', -- Breaking Bad Tokens: Detoxification of LLMs Using Sparse Autoencoders
          '2505.20809', -- Improved Representation Steering for Language Models
          '2505.24621', -- Benchmarking Large Language Models for Cryptanalysis and Mismatched-General
          '2505.24672', -- TRIDENT: Enhancing Large Language Model Safety with Tri-Dimensional Diversi
          '2506.06444', -- Saffron-1: Towards an Inference Scaling Paradigm for LLM Safety Assurance
          '2506.07645', -- Evaluating LLMs Robustness in Less Resourced Languages with Proxy Models
          '2506.07736', -- RSafe: Incentivizing proactive reasoning to build robust and adaptive LLM s
          '2506.08885', -- AdversariaL attacK sAfety aLIgnment(ALKALI): Safeguarding LLMs through GRAC
          '2506.09600', -- Effective Red-Teaming of Policy-Adherent Agents
          '2506.22957', -- Agent-to-Agent Theory of Mind: Testing Interlocutor Awareness among Large L
          '2508.02063', -- TRACEALIGN -- Tracing the Drift: Attributing Alignment Failures to Training
          '2508.12535', -- CorrSteer: Steering Improves Task Performance and Safety in LLMs through Co
          '2509.22067', -- The Rogue Scalpel: Activation Steering Compromises LLM Safety
          '2510.00938', -- Large Reasoning Models Learn Better Alignment from Flawed Thinking
          '2601.01592', -- OpenRT: An Open-Source Red Teaming Framework for Multimodal LLMs
          '2601.11516', -- Building Production-Ready Probes For Gemini
          '2601.10387', -- The Assistant Axis: Situating and Stabilizing the Default Persona of Langua
          '2601.08441', -- YaPO: Learnable Sparse Activation Steering Vectors for Domain Adaptation
          '2601.07853', -- FinVault: Benchmarking Financial Agent Safety in Execution-Grounded Environ
          '2601.22636', -- Statistical Estimation of Adversarial Risk in Large Language Models under B
          '2602.04581', -- Trust The Typical
          '2602.14689', -- Exposing the Systematic Vulnerability of Open-Weight Models to Prefill Atta
          '2602.14364', -- A Trajectory-Based Safety Audit of Clawdbot (OpenClaw)
          '2602.16729', -- Intent Laundering: AI Safety Datasets Are Not What They Seem
          '2604.09544', -- Large Language Models Generate Harmful Content Using a Distinct, Unified Me
          '2604.16659', -- Benign Fine-Tuning Breaks Safety Alignment in Audio LLMs
          '2604.23775', -- Vision-Language-Action Safety: Threats, Challenges, Evaluations, and Mechan
          '2604.27818', -- MASCing: Configurable Mixture-of-Experts Behavior via Activation Steering M
          '2604.18487', -- Adversarial Humanities Benchmark: Results on Stylistic Robustness in Fronti
          '2603.27918', -- Adversarial Attacks on Multimodal Large Language Models: A Comprehensive Su
          '2603.25176', -- Prompt Attack Detection with LLM-as-a-Judge and Mixture-of-Models
          '2603.17305', -- Contrastive Reasoning Alignment: Reinforcement Learning from Hidden Represe
          '2603.15800', -- Evolving Contextual Safety in Multi-Modal Large Language Models via Inferen
          '2506.15751', -- Sysformer: Safeguarding Frozen Large Language Models with Adaptive System P
          '2603.04355', -- Efficient Refusal Ablation in LLM through Optimal Transport
          '2603.13292', -- Pragma-VL: Towards a Pragmatic Arbitration of Safety and Helpfulness in MLL
          '2508.20570', -- Dyslexify: A Mechanistic Defense Against Typographic Attacks in CLIP
          '2602.06911', -- TamperBench: Systematically Stress-Testing LLM Safety Under Fine-Tuning and
          '2603.20198', -- Visual Exclusivity Attacks: Automatic Multimodal Red Teaming via Agentic Pl
          '2603.06594', -- A Coin Flip for Safety: LLM Judges Fail to Reliably Measure Adversarial Rob
          '2602.02600', -- Step-Wise Refusal Dynamics in Autoregressive and Diffusion Language Models
          '2601.15331', -- RECAP: A Resource-Efficient Method for Adversarial Prompting in Large Langu
          '2601.05739', -- PII-VisBench: Evaluating Personally Identifiable Information Safety in Visi
          '2601.03868', -- What Matters For Safety Alignment?
          '2512.20293', -- AprielGuard
          '2601.03273', -- GuardEval: A Multi-Perspective Benchmark for Evaluating Safety, Fairness, a
          '2512.16602', -- Refusal Steering: Fine-grained Control over LLM Refusal Behaviour for Sensi
          '2512.15712', -- Predictive Concept Decoders: Training Scalable End-to-End Interpretability
          '2511.22047', -- Evaluating the Robustness of Large Language Model Safety Guardrails Against
          '2511.18921', -- BackdoorVLM: A Benchmark for Backdoor Attacks on Vision-Language Models
          '2511.12497', -- SGuard-v1: Safety Guardrail for Large Language Models
          '2511.09880', -- EnchTable: Unified Safety Alignment Transfer in Fine-tuned Large Language M
          '2511.08379', -- SOM Directions are Better than One: Multi-Directional Refusal Suppression i
          '2511.06852', -- Differentiated Directional Intervention A Framework for Evading LLM Safety
          '2511.00203', -- Diffusion LLMs are Natural Adversaries for any LLM
          '2510.26847', -- Broken-Token: Filtering Obfuscated Prompts by Counting Characters-Per-Token
          '2510.25941', -- RECAP: Reproducing Copyrighted Data from LLMs Training with an Agentic Pipe
          '2510.19169', -- OpenGuardrails: An Open-Source Context-Aware AI Guardrails Platform
          '2510.16794', -- Black-box Optimization of LLM Outputs by Asking for Directions
          '2510.12133', -- SafeMT: Multi-turn Safety for Multimodal Language Models
          '2510.11837', -- Countermind: A Multi-Layered Security Architecture for Large Language Model
          '2510.01088', -- Safety Instincts: LLMs Learn to Trust Their Internal Compass for Self-Defen
          '2509.24393', -- Towards Safe Reasoning in Large Reasoning Models via Corrective Interventio
          '2509.24319', -- Dual Mechanisms of Value Expression: Intrinsic vs. Prompted Values in LLMs
          '2509.24269', -- AdvChain: Adversarial Chain-of-Thought Tuning for Robust Safety Alignment o
          '2509.21768', -- PSRT: Accelerating LRM-based Guard Models via Prefilled Safe Reasoning Trac
          '2509.09660', -- Steering MoE LLMs via Expert (De)Activation
          '2509.05883', -- Multimodal Prompt Injection Attacks: Risks and Defenses for Modern LLMs
          '2509.04781', -- The LLM Has Left The Chat: Evidence of Bail Preferences in Large Language M
          '2509.01909', -- Oyster-I: Beyond Refusal -- Constructive Safety Alignment for Responsible L
          '2508.19980', -- Evaluating Language Model Reasoning about Confidential Information
          '2508.18649', -- PRISM: Robust VLM Alignment with Principled Reasoning for Integrated Safety
          '2508.17540', -- Activation Transport Operators
          '2508.04196', -- Eliciting and Analyzing Emergent Misalignment in State-of-the-Art Large Lan
          '2508.00935', -- Measuring Harmfulness of Computer-Using Agents
          '2507.22564', -- Exploiting Synergistic Cognitive Biases to Bypass Safety in LLMs
          '2507.14987', -- AlphaAlign: Incentivizing Safety Alignment with Extremely Simplified Reinfo
          '2507.00971', -- Reasoning as an Adaptive Defense for Safety
          '2506.22523', -- Red Teaming for Generative AI, Report on a Copyright-Focused Exercise Compl
          '2506.19563', -- PrivacyXray: Detecting Privacy Breaches in LLMs through Semantic Consistenc
          '2506.19140', -- Command-V: Pasting LLM Behaviors via Activation Profiles
          '2506.16078', -- Probing the Robustness of Large Language Models Safety to Latent Perturbati
          '2506.04704', -- HoliSafe: Holistic Safety Benchmarking and Modeling with Safety Meta Token
          '2505.23556', -- Understanding Refusal in Language Models with Sparse Autoencoders
          '2505.19773', -- What Really Matters in Many-Shot Attacks? An Empirical Study of Long-Contex
          '2505.19766', -- SGM: A Framework for Building Specification-Guided Moderation Filters
          '2505.17306', -- Refusal Direction is Universal Across Safety-Aligned Languages
          '2505.03574', -- LlamaFirewall: An open source guardrail system for building secure AI agent
          '2504.19521', -- Security Steerability is All You Need
          '2504.15241', -- MrGuard: A Multilingual Reasoning Guardrail for Universal LLM Safety
          '2503.20279', -- sudo rm -rf agentic_security
          '2503.05021', -- Safety is Not Only About Refusal: Reasoning-Enhanced Fine-tuning for Interp
          '2502.00406', -- Agents Are All You Need for LLM Unlearning
          '2412.16339', -- Deliberative Alignment: Reasoning Enables Safer Language Models
          '2410.01606', -- Automated Red Teaming with GOAT: the Generative Offensive Agent Tester
          '2406.00045', -- Personalized Steering of Large Language Models: Versatile Steering Vectors
          '2308.14132', -- Detecting Language Model Attacks with Perplexity
          '2605.12290', -- Targeted Neuron Modulation via Contrastive Pair Search
          '2605.22984', -- Test-Time Training Undermines Safety Guardrails
          '2511.11301', -- EcoAlign: An Economically Rational Framework for Efficient LVLM Alignment
          '2603.07590', -- Models as Lego Builders: Assembling Malice from Benign Blocks via Semantic
          '2603.22882', -- TreeTeaming: Autonomous Red-Teaming of Vision-Language Models via Hierarchi
          '2604.08846', -- Dictionary-Aligned Concept Control for Safeguarding Multimodal LLMs
          '2507.06489', -- On the Robustness of Verbal Confidence of LLMs in Adversarial Attacks
          '2502.13095', -- Understanding and Rectifying Safety Perception Distortion in VLMs
          '2502.00669', -- Safety Depth in Large Language Models: A Markov Chain Perspective
          '2502.17578', -- How Do Large Language Monkeys Get Their Power (Laws)?
          '2503.01926', -- Unnatural Languages Are Not Bugs but Features for LLMs
          '2502.17254', -- REINFORCE Adversarial Attacks on Large Language Models: An Adaptive, Distri
          '2502.09674', -- The Hidden Dimensions of LLM Alignment: A Multi-Dimensional Analysis of Ort
          '2502.04040', -- Safety Reasoning with Guidelines
          '2407.18213', -- Scaling Trends in Language Model Robustness
          '2410.10414', -- On Calibration of LLM-based Guard Models for Reliable Content Moderation
          '2405.19237', -- ConceptPrune: Concept Editing in Diffusion Models via Skilled Neuron Prunin
          '2409.20089', -- Robust LLM safeguarding via refusal feature adversarial training
          '2506.06975', -- Auditing Black-Box LLM APIs with a Rank-Based Uniformity Test
          '2510.07985', -- Fewer Weights, More Problems: A Practical Attack on LLM Pruning
          '2505.16567', -- Watch your steps: Dormant Adversarial Behaviors that Activate upon LLM Fine
          '2602.20170', -- CAGE: A Framework for Culturally Adaptive Red-Teaming Benchmark Generation
          '2602.05535', -- Detecting Misbehaviors of Large Vision-Language Models by Evidential Uncert
          '2510.06790', -- Get RICH or Die Scaling: Profitably Trading Inference Compute for Robustnes
          '2507.04531', -- DP-Fusion: Token-Level Differentially Private Inference for Large Language
          '2506.17052', -- From Concepts to Components: Concept-Agnostic Attention Module Discovery in
          '2606.10740', -- When the Chain of Thought Knows Better: Failure Modes in Multi-Turn Reasoni
          '2605.08116', -- The Safety-Aware Denoiser for Text Diffusion Models
          '2510.11834', -- Don''t Walk the Line: Boundary Guidance for Filtered Generation
          '2603.23268', -- SafeSeek: Universal Attribution of Safety Circuits in Language Models
          '2606.19755', -- SafeSpec: Fast and Safe LLM via Dynamic Reflective Sampling
          '2602.08621', -- Sparse Models, Sparse Safety: Unsafe Routes in Mixture-of-Experts LLMs
          '2603.15684', -- State-Dependent Safety Failures in Multi-Turn Language Model Interaction
          '2605.19966', -- Detecting Fluent Optimization-Based Adversarial Prompts via Sequential Entr
          '2606.26396', -- At the Edge of Understanding: Sparse Autoencoders Trace The Limits of Trans
          '2601.22313', -- Hair-Trigger Alignment: Black-Box Evaluation Cannot Guarantee Post-Update A
          '2605.25194', -- Localize and Neutralize: Gradient-Guided Token Suppression Against Visual P
          '2605.26158', -- Furina: Fragmented Uncertainty-Driven Refusal Instability Attack
          '2606.31227', -- Securing the AI Agent: A Unified Framework for Multi-Layer Agent Red Teamin
          '2604.10299', -- Seeing No Evil: Blinding Large Vision-Language Models to Safety Instruction
          '2604.15717', -- Into the Gray Zone: Domain Contexts Can Blur LLM Safety Boundaries
          '2510.17687', -- CrossGuard: Safeguarding MLLMs against Joint-Modal Implicit Malicious Attac
          '2604.15780', -- Pruning Unsafe Tickets: A Resource-Efficient Framework for Safer and More R
          '2604.18660', -- Evaluating Answer Leakage Robustness of LLM Tutors against Adversarial Stud
          '2508.04204', -- ReasoningGuard: Safeguarding Large Reasoning Models with Inference-time Saf
          '2510.08646', -- Mitigating Over-Refusal in Aligned Large Language Models via Inference-Time
          '2604.21159', -- Adaptive Instruction Composition for Automated LLM Red-Teaming
          '2605.01913', -- RefusalGuard: Geometry-Preserving Fine-Tuning for Safety in LLMs
          '2604.07615', -- ADAG: Automatically Describing Attribution Graphs
          '2604.02574', -- Understanding the Effects of Safety Unalignment on Large Language Models
          '2411.16769', -- Red-Teaming Text-to-Image Models via In-Context Experience Replay and Seman
          '2604.19001', -- When Safety Fails Before the Answer: Benchmarking Harmful Behavior Detectio
          '2605.17173', -- Why Do Safety Guardrails Degrade Across Languages?
          '2604.07223', -- TraceSafe: A Systematic Assessment of LLM Guardrails on Multi-Step Tool-Cal
          '2509.08000', -- AntiDote: Bi-level Adversarial Training for Tamper-Resistant LLMs
          '2509.11141', -- When Smiley Turns Hostile: Interpreting How Emojis Trigger LLMs’ Toxicity
          '2508.03986', -- The Emotional Baby Is Truly Deadly: Does Your Multimodal Large Reasoning Mo
          '2511.00509', -- Reimagining Safety Alignment with An Image
          '2505.24428', -- Model Unlearning via Sparse Autoencoder Subspace Guided Projections
          '2509.16088', -- Randomized Smoothing Meets Vision-Language Models
          '2403.09572', -- "Eyes Closed, Safety On: Protecting Multimodal LLMs via Image-to-Text Trans
          '2505.20309', -- Guiding Giants: Lightweight Controllers for Weighted Activation Steering in
          '2609.35291', -- Narrow Multimodal Fine-Tuning Can Induce Emergent Misalignment
          '2606.31876', -- Harnessing Textual Refusal Directions for Multimodal Safety
          '2510.05197', -- Efficient Prediction of Pass@k Scaling in Large Language Models
          '2610.07532', -- Safeguarding LLMs via Model-Agnostic Latent Safety Signals from Dark Knowle
          '2610.01062', -- Kernelized Activation Steering
          '2609.32717', -- LLM Alignment--Utility Asymmetry under Semantic-Preserving Transformations
          '2610.16084', -- The Sharp Directions Are Against You: Curvature Analysis of Activation Stee
          '2609.32602', -- AnchorRep: Defending LLMs Against Cross-Model Adversarial Transfer via Repr
          '2606.22673', -- Agent MechSuits : Mechanistic Subspace Safety Steering for Multi-Turn CLI A
          '2603.15647', -- Steering Frozen LLMs: Adaptive Social Alignment via Online Prompt Routing
          '2605.21706', -- Latent-space Attacks for Refusal Evasion in Language Models
          '2605.26315', -- Curriculum Learning for Safety Alignment
          '2605.08427' -- The Attacker in the Mirror: Breaking Self-Consistency in Safety via Anchore
      )
      OR
      (p.source = 'external' AND p.id IN (
          121679, -- SafeLogo: Turning Your Logos into Jailbreak Shields via Micro-Regional Adve
          129071, -- TraceGuard: Defending Multi-Turn Jailbreak Attacks via Prompt-Response Risk
          110425, -- Jailbreak LLMs through Internal Stance Manipulation
          127990, -- DualSteer: Dual-Space Steering for Robust Jailbreak Mitigation of Large Vis
          129651, -- JailBound: A FOL-Guided Jailbreak Evaluation Framework for Revealing Safety
          120852, -- Adversarial Style Optimization: Enhancing VLM Jailbreaks by GRPO-based Styl
          121258, -- Anchoring the Mind of Multimodal Reasoners: Cognitive Bias as a Vector for
          129430, -- Beyond the Prompt: Leveraging Pre-Decoding States for Jailbreak Detection i
          127992, -- Brute-Force Jailbreaks and Codon-Aware Watermarking for DNA Foundation Mode
          129976, -- Harmless in Pieces, Harmful in Motion: Detecting Multi-Agent Jailbreaks
          130600, -- SelfGuard: Self-Supervised Deviation Modeling for Multi-Modal Jailbreak Det
          110123, -- DAMON: A Dialogue-Aware MCTS Framework for Jailbreaking Large Language Mode
          111492, -- Defending Speech-enabled LLMs Against Adversarial Jailbreak Threats
          120673, -- Jailbreaking Vision-Language Models via Dissonance-Guided Suffix Optimizati
          127042, -- JEDI: Real-Time Jailbreak Defense for LLMs via In-Generation Detection and
          118647, -- Co-Steer: Cross-Modal Collaborative Steering for Jailbreaking MLLMs
          124851, -- Safety-Aware Latent Space Reasoning in Large Language Models
          125790, -- Gradient-Guided Smoothing for LLM Safety Defense
          120973, -- Breaking Multimodal LLM Safety via Video-Driven Prompting
          110164, -- SURE: Safety Understanding and Reasoning Enhancement for Multimodal Large L
          125843, -- HARC: Coupling Harmfulness and Refusal Capabilities for Robust Safety Align
          128738, -- CrossSteer:Cross-Modal Safety Steering for Audio-Language Models
          130708, -- Decomposing One Professional-Framing Pipeline: Which Components Shift LLM S
          110315, -- Gamma-Guard: Lightweight Residual Adapters for Robust Guardrails in Large L
          110376, -- ToolSafety: A Comprehensive Dataset for Enhancing Safety in LLM-Based Agent
          120479, -- SLADE: Shielding against Dual Exploits in Large Vision-Language Models
          125264, -- Bridging the Gap Between Harmfulness Belief and Refusal Behavior for Safety
          126150, -- CURE: Counterfactual Unsafe-token Re-masking for Diffusion Large Language M
          127468, -- Safe in Its Own Words: Self-Guided Safety Alignment for Multimodal Reasonin
          128074, -- Rubric-Align: Safety Alignment through Dynamically Co-Evolving Rubrics
          128207 -- LLM Rheology: Auditing Refusal Geometry in Aligned Language Models
      ))
  );

DELETE FROM paper_method_exclusions x
USING jb_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM jb_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM jb_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- jailbreak: 28 reviewed negatives.
CREATE TEMP TABLE jb_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'jailbreak'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2503.17198', -- Jailbreaking the Non-Transferable Barrier via Test-Time Data Disguising
          '2405.15012', -- Extracting Prompts by Inverting LLM Outputs
          '2410.23687', -- Adversarial Attacks of Vision Tasks in the Past 10 Years: A Survey
          '2502.00299', -- ChunkKV: Semantic-Preserving KV Cache Compression for Efficient Long-Contex
          '2502.00306', -- Riddle Me This! Stealthy Membership Inference for Retrieval-Augmented Gener
          '2504.04717', -- Beyond Single-Turn: A Survey on Multi-Turn Interactions with Large Language
          '2506.04255', -- HASHIRU: Hierarchical Agent System for Hybrid Intelligent Resource Utilizat
          '2511.20494', -- Adversarial Confusion Attack: Disrupting Multimodal Large Language Models
          '2604.06950', -- Making MLLMs Blind: Adversarial Smuggling Attacks in MLLM Content Moderatio
          '2603.21354', -- The Workload-Router-Pool Architecture for LLM Inference Optimization: A Vis
          '2603.04444', -- vLLM Semantic Router: Signal Driven Decision Routing for Mixture-of-Modalit
          '2602.21236', -- @GrokSet: multi-party Human-LLM Interactions in Social Media
          '2601.08490', -- BenchOverflow: Measuring Overflow in Large Language Models via Plain-Text P
          '2512.16962', -- MemoryGraft: Persistent Compromise of LLM Agents via Poisoned Experience Re
          '2505.16888', -- SPECTRE: Conditional System Prompt Poisoning to Hijack LLMs
          '2505.15420', -- Silent Leaks: Implicit Knowledge Extraction Attack on RAG Systems through B
          '2604.09839', -- Steered LLM Activations are Non-Surjective
          '2605.20266', -- A Survey of Large Audio Language Models: Generalization, Trustworthiness, a
          '2506.00794', -- Predicting Empirical AI Research Outcomes with Language Models
          '2502.00921', -- Blink of an eye: a simple theory for feature localization in generative mod
          '2606.21638', -- Toward Open Weight Models Without Risks: Separating Public and Private Capa
          '2606.12716', -- Does AI Reviewer See the Full Picture? Attacking and Defending Multimodal P
          '2603.00029', -- Embracing Anisotropy: Turning Massive Activations into Interpretable Contro
          '2604.14053', -- From Where Words Come: Efficient Regularization of Code Tokenizers Through
          '2609.14803', -- Another Blueprint In The Wall: How to Ask Frontier AI Like a Kid?
          '2609.29429', -- Just Ask Jev: Reinforcement Learning for Calibrated Decisions as a Zero-Sho
          '2610.25060', -- Policy Is Not Capability: Some Safety Benchmarks Measure Which Definition o
          '2605.30040' -- Token Inflation: How Dishonest Providers Can Overcharge for Large Language
      )
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'safety methods curation 2026-11-10: passing mention or contrast, benchmark name only (JailbreakV, JailbreakBench), or jailbreaking in another sense'
FROM jb_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING jb_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING jb_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;

-- prompt-injection: 226 reviewed true positives of 256 title/abstract candidates.
CREATE TEMP TABLE pi_curated_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'prompt-injection'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2310.12815', -- Formalizing and Benchmarking Prompt Injection Attacks and Defenses
          '2409.14729', -- PROMPTFUZZ: Harnessing Fuzzing Techniques for Robust Testing of Prompt Inje
          '2604.01194', -- AgentWatcher: A Rule-based Prompt Injection Monitor
          '2410.23308', -- Systematically Analyzing Prompt Injection Vulnerabilities in Diverse LLM Ar
          '2306.05499', -- Prompt Injection attack against LLM-integrated Applications
          '2311.01011', -- Tensor Trust: Interpretable Prompt Injection Attacks from an Online Game
          '2312.17673', -- Jatmo: Prompt Injection Defense by Task-Specific Finetuning
          '2402.00898', -- An Early Categorization of Prompt Injection Attacks on Large Language Model
          '2602.06268', -- MPIB: A Benchmark for Medical Prompt Injection Attacks and Clinical Safety
          '2409.19521', -- GenTel-Safe: A Unified Benchmark and Shielding Framework for Defending Agai
          '2410.22770', -- InjecGuard: Benchmarking and Mitigating Over-defense in Prompt Injection Gu
          '2411.00348', -- Attention Tracker: Detecting Prompt Injection Attacks in LLMs
          '2506.05446', -- Sentinel: SOTA model to protect against prompt injections
          '2507.02735', -- Meta SecAlign: A Secure Foundation LLM Against Prompt Injection Attacks
          '2604.08499', -- PIArena: A Platform for Prompt Injection Evaluation
          '2603.29418', -- Adversarial Prompt Injection Attack on Multimodal Large Language Models
          '2603.11875', -- The Mirror Design Pattern: Strict Data Geometry over Model Scale for Prompt
          '2601.13612', -- PINA: Prompt Injection Attack against Navigation Agents
          '2511.20597', -- BrowseSafe: Understanding and Preventing Prompt Injection Within AI Browser
          '2504.11358', -- DataSentinel: A Game-Theoretic Detection of Prompt Injection Attacks
          '2508.20890', -- PromptSleuth: Detecting Prompt Injection via Semantic Intent Invariance
          '2505.12368', -- CAPTURE: Context-Aware Prompt Injection Testing and Robustness Enhancement
          '2502.16580', -- Can Indirect Prompt Injection Attacks Be Detected and Removed?
          '2501.15145', -- PromptShield: Deployable Detection for Prompt Injection Attacks
          '2603.12277', -- Prompt Injection as Role Confusion
          '2603.13026', -- PISmith: Reinforcement Learning-based Red Teaming for Prompt Injection Defe
          '2608.05108', -- Agent Against Agent: An Agentic System for Automatic Prompt Injection Red T
          '2608.21500', -- SecOPD: Mitigating Adaptive Prompt Injections by On-Policy Distillation
          '2302.12173', -- Not what you''ve signed up for: Compromising Real-World LLM-Integrated Appli
          '2308.10819', -- Evaluating the Instruction-Following Robustness of Large Language Models to
          '2312.14197', -- Benchmarking and Defending Against Indirect Prompt Injection Attacks on Lar
          '2406.13352', -- AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and D
          '2409.13331', -- Applying Pre-trained Multilingual BERT in Embeddings for Improved Malicious
          '2410.22284', -- Embedding-based classifiers can detect prompt injection attacks
          '2501.09798', -- Fun-tuning: Characterizing the Vulnerability of Proprietary LLMs to Optimiz
          '2503.18813', -- Defeating Prompt Injections by Design
          '2504.11168', -- Bypassing Prompt Injection and Jailbreak Detection in LLM Guardrails
          '2505.05849', -- AgentVigil: Generic Black-Box Red-teaming for Indirect Prompt Injection aga
          '2506.08837', -- Design Patterns for Securing LLM Agents against Prompt Injections
          '2510.01354', -- WAInjectBench: Benchmarking Prompt Injection Detections for Web Agents
          '2604.28157', -- FlashRT: Towards Computationally and Memory Efficient Red-Teaming for Promp
          '2604.03598', -- AttackEval: A Systematic Empirical Study of Prompt Injection Attack Effecti
          '2602.05746', -- Learning to Inject: Automated Prompt Injection via Reinforcement Learning
          '2601.17548', -- Prompt Injection Attacks on Agentic Coding Assistants: A Systematic Analysi
          '2601.11199', -- SD-RAG: A Prompt-Injection-Resilient Framework for Selective Disclosure in
          '2601.04795', -- Defense Against Indirect Prompt Injection via Tool Result Parsing
          '2507.07417', -- May I have your Attention? Breaking Fine-Tuning based Prompt Injection Defe
          '2510.26328', -- Agent Skills Enable a New Class of Realistic and Trivially Simple Prompt In
          '2510.19207', -- Defending Against Prompt Injection with DataFilter
          '2509.22040', -- "Your AI, My Shell": Demystifying Prompt Injection Attacks on Agentic AI Co
          '2509.05883', -- Multimodal Prompt Injection Attacks: Risks and Defenses for Modern LLMs
          '2509.05831', -- Decoding Latent Attack Surfaces in LLMs: Prompt Injection via HTML in Web S
          '2504.19793', -- Prompt Injection Attack to Tool Selection in LLM Agents
          '2506.09956', -- LLMail-Inject: A Dataset from a Realistic Adaptive Prompt Injection Challen
          '2504.18575', -- WASP: Benchmarking Web Agent Security Against Prompt Injection Attacks
          '2502.13141', -- UniGuardian: A Unified Defense for Detecting Prompt Injection, Backdoor Att
          '2410.07283', -- Prompt Infection: LLM-to-LLM Prompt Injection within Multi-Agent Systems
          '2402.06363', -- StruQ: Defending Against Prompt Injection with Structured Queries
          '2605.31042', -- From Prompt Injection to Persistent Control: Defending Agentic Harness Agai
          '2605.30837', -- Send a SCOUT First: Pre-hoc Reasoning for Adaptive Detector Allocation in P
          '2605.25194', -- Localize and Neutralize: Gradient-Guided Token Suppression Against Visual P
          '2602.07104', -- Extended to Reality: Prompt Injection in 3D Environments
          '2509.07617', -- Transferable Direct Prompt Injection via Activation-Guided MCMC Sampling
          '2605.17634', -- AI Agents May Always Fall for Prompt Injections
          '2410.13236', -- SPIN: Self-Supervised Prompt INjection
          '2502.05174', -- MELON: Provable Defense Against Indirect Prompt Injection Attacks in AI Age
          '2510.09023', -- The Attacker Moves Second: Stronger Adaptive Attacks Bypass Defenses Agains
          '2603.15714', -- How Vulnerable Are AI Agents to Indirect Prompt Injections? Insights from a
          '2602.10453', -- The Landscape of Prompt Injection Threats in LLM Agents: From Taxonomy to A
          '2602.07918', -- CausalArmor: Efficient Indirect Prompt Injection Guardrails via Causal Attr
          '2602.03117', -- AgentDyn: A Dynamic Open-Ended Benchmark for Evaluating Prompt Injection At
          '2601.22569', -- Whispers of Wealth: Red-Teaming Google''s Agent Payments Protocol via Prompt
          '2601.17549', -- Breaking the Protocol: Security Analysis of the Model Context Protocol Spec
          '2601.10923', -- Hidden-in-Plain-Text: A Benchmark for Social-Web Indirect Prompt Injection
          '2601.13186', -- Prompt Injection Mitigation with Agentic AI, Nested Learning, and AI Sustai
          '2601.07072', -- Overcoming the Retrieval Barrier: Indirect Prompt Injection in the Wild for
          '2509.22830', -- ChatInject: Abusing Chat Templates for Prompt Injection in LLM Agents
          '2504.14348', -- Manipulating Multimodal Agents via Cross-Modal Prompt Injection
          '2506.23260', -- From Prompt Injections to Protocol Exploits: Threats in LLM-Powered AI Agen
          '2403.02691', -- InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated Larg
          '2512.05745', -- ARGUS: Defending Against Multimodal Indirect Prompt Injection via Steering
          '2506.02456', -- VPI-Bench: Visual Prompt Injection Attacks for Computer-Use Agents
          '2602.01795', -- RedVisor: Reasoning-Aware Prompt Injection Defense via Zero-Copy KV Cache R
          '2604.09024', -- Leave My Images Alone: Preventing Multi-Modal Large Language Models from An
          '2509.25448', -- Fingerprinting LLMs via Prompt Injection
          '2608.16393', -- Security Assessment of DeepSeek Harness with A.I.G: Evaluating Resistance t
          '2505.11717', -- WebInject: Prompt Injection Attack to Web Agents
          '2507.13686', -- TopicAttack: An Indirect Prompt Injection Attack via Topic Transition
          '2609.35932', -- Same Bytes, Different Authority: Reserved-Token Representations in Chat-Tem
          '2503.00061', -- Adaptive Attacks Break Defenses Against Indirect Prompt Injection Attacks o
          '2505.14534', -- Lessons from Defending Gemini Against Indirect Prompt Injections
          '2603.22489', -- Model Context Protocol Threat Modeling and Analyzing Vulnerabilities to Pro
          '2507.15042', -- DeRAG: Black-box Adversarial Attacks on Multiple Retrieval-Augmented Genera
          '2508.15310', -- IPIGuard: A Novel Tool Dependency Graph-Based Defense Against Indirect Prom
          '2610.08773', -- AdvSim2Real : Training Web Agents Against Adaptive Prompt Injection in a We
          '2509.00088', -- AEGIS : Automated Co-Evolutionary Framework for Guarding Prompt Injections
          '2505.21936', -- RedTeamCUA: Realistic Adversarial Testing of Computer-Use Agents in Hybrid
          '2606.07131', -- MalSkillBench: A Runtime-Verified Benchmark of Malicious Agent Skills
          '2603.24511', -- Claudini: Autoresearch Discovers State-of-the-Art Adversarial Attack Algori
          '2404.13161', -- CyberSecEval 2: A Wide-Ranging Cybersecurity Evaluation Suite for Large Lan
          '2406.03589', -- Ranking Manipulation for Conversational Search Engines
          '2506.14866', -- OS-Harm: A Benchmark for Measuring Safety of Computer Use Agents
          '2510.03204', -- FocusAgent: Simple Yet Effective Ways of Trimming the Large Context of Web
          '2510.09462', -- Adaptive Attacks on Trusted Monitors Subvert AI Control Protocols
          '2602.07398', -- AgentSys: Secure and Dynamic LLM Agents Through Explicit Hierarchical Memor
          '2604.05179', -- Gradient-Controlled Decoding: A Safety Guardrail for LLMs with Dual-Anchor
          '2602.20156', -- Skill-Inject: Measuring Agent Vulnerability to Skill File Attacks
          '2602.14161', -- When Benchmarks Lie: Evaluating Malicious Prompt Classifiers Under True Dis
          '2602.05066', -- Bypassing AI Control Protocols via Agent-as-a-Proxy Attacks
          '2601.15528', -- Securing LLM-as-a-Service for Small Businesses: An Industry Case Study of a
          '2511.04508', -- Large Language Models for Cyber Security
          '2510.11837', -- Countermind: A Multi-Layered Security Architecture for Large Language Model
          '2505.03574', -- LlamaFirewall: An open source guardrail system for building secure AI agent
          '2602.11416', -- Optimizing Agent Planning for Security and Autonomy
          '2503.10566', -- ASIDE: Architectural Separation of Instructions and Data in Language Models
          '2512.23128', -- It''s a TRAP! Task-Redirecting Agent Persuasion Benchmark for Web Agents
          '2607.26115', -- GPT-Red: Automated Red Teaming via Self-Play at Scale
          '2610.19118', -- DecisionRobust: Benchmarking Robustness for JEV Style Decision Models Acros
          '2308.03825', -- "Do Anything Now": Characterizing and Evaluating In-The-Wild Jailbreak Prom
          '2311.16119', -- Ignore This Title and HackAPrompt: Exposing Systemic Vulnerabilities of LLM
          '2403.10949', -- SelfIE: Self-Interpretation of Large Language Model Embeddings
          '2404.13208', -- The Instruction Hierarchy: Training LLMs to Prioritize Privileged Instructi
          '2405.20902', -- Preemptive Answer "Attacks" on Chain-of-Thought Reasoning
          '2408.03837', -- WalledEval: A Comprehensive Safety Evaluation Toolkit for Large Language Mo
          '2410.02644', -- Agent Security Bench (ASB): Formalizing and Benchmarking Attacks and Defens
          '2410.09102', -- Instructional Segment Embedding: Improving LLM Safety with Instruction Hier
          '2410.16950', -- Breaking ReAct Agents: Foot-in-the-Door Attack Will Get You In
          '2410.17520', -- MobileSafetyBench: Evaluating Safety of Autonomous Agents in Mobile Device
          '2412.01547', -- Improved Large Language Model Jailbreak Detection via Pretrained Embeddings
          '2502.05206', -- Safety at Scale: A Comprehensive Survey of Large Model Safety
          '2502.12659', -- The Hidden Risks of Large Reasoning Models: A Safety Assessment of R1
          '2503.09334', -- CyberLLMInstruct: A New Dataset for Analysing Safety of Fine-Tuned LLMs Usi
          '2503.11519', -- Exploring Typographic Visual Prompts Injection Threats in Cross-Modality Ge
          '2504.09593', -- ControlNET: A Firewall for RAG-based LLM System
          '2504.20769', -- Chain-of-Defensive-Thought: Structured Reasoning Elicits Robustness in Larg
          '2505.23643', -- Securing AI Agents with Information-Flow Control
          '2506.04202', -- TracLLM: A Generic Framework for Attributing Long Context LLMs
          '2506.15674', -- Leaky Thoughts: Large Reasoning Models Are Not Private Thinkers
          '2508.03793', -- AttnTrace: Attention-based Context Traceback for Long-Context LLMs
          '2509.17938', -- D-REX: A Benchmark for Detecting Deceptive Reasoning in Large Language Mode
          '2510.05025', -- Imperceptible Jailbreaking against Large Language Models
          '2510.01586', -- AdvEvo-MARL: Shaping Internalized Safety through Adversarial Co-Evolution i
          '2510.21057', -- Soft Instruction De-escalation Defense
          '2601.10156', -- ToolSafe: Enhancing Tool Invocation Safety of LLM-based agents via Proactiv
          '2601.10338', -- Agent Skills in the Wild: An Empirical Study of Security Vulnerabilities at
          '2601.09923', -- CaMeLs Can Use Computers Too: System-level Security for Computer Use Agents
          '2601.07853', -- FinVault: Benchmarking Financial Agent Safety in Execution-Grounded Environ
          '2602.08995', -- When Actions Go Off-Task: Detecting and Correcting Misaligned Actions in Co
          '2603.03205', -- Learning When to Act or Refuse: Guarding Agentic Reasoning Models for Safe
          '2604.10577', -- The Blind Spot of Agent Safety: How Benign User Instructions Expose Critica
          '2605.01449', -- VisInject: Disruption != Injection -- A Dual-Dimension Evaluation of Univer
          '2604.15415', -- HarmfulSkillBench: How Do Harmful Skills Weaponize Your Agents?
          '2604.10286', -- STARS: Skill-Triggered Audit for Request-Conditioned Invocation Safety in A
          '2604.02954', -- LogicPoison: Logical Attacks on Graph Retrieval-Augmented Generation
          '2603.27517', -- A Systematic Taxonomy of Security Vulnerabilities in the OpenClaw AI Agent
          '2603.25176', -- Prompt Attack Detection with LLM-as-a-Judge and Mixture-of-Models
          '2603.12644', -- Uncovering Security Threats and Architecting Defenses in Autonomous Agents:
          '2603.11853', -- OpenClaw PRISM: A Zero-Fork, Defense-in-Depth Runtime Security Layer for To
          '2603.11619', -- Taming OpenClaw: Security Analysis and Mitigation of Autonomous LLM Agent T
          '2603.00991', -- Tracking Capabilities for Safer Agents
          '2602.20867', -- SoK: Agentic Skills -- Beyond Tool Use in LLM Agents
          '2602.01129', -- SMCP: Secure Model Context Protocol
          '2601.21083', -- OpenSec: Measuring Incident Response Agent Calibration Under Adversarial Ev
          '2601.12822', -- MirrorGuard: Toward Secure Computer-Use Agents via Simulation-to-Real Reaso
          '2601.12449', -- AgenTRIM: Tool Risk Mitigation for Agentic AI
          '2601.05755', -- VIGIL: Defending LLM Agents Against Tool Stream Injection via Verify-Before
          '2601.01241', -- MCP-SandboxScan: WASM-based Secure Execution and Runtime Analysis for MCP T
          '2512.20293', -- AprielGuard
          '2510.19169', -- OpenGuardrails: An Open-Source Context-Aware AI Guardrails Platform
          '2510.16794', -- Black-box Optimization of LLM Outputs by Asking for Directions
          '2510.13351', -- Protect: Towards Robust Guardrailing Stack for Trustworthy Enterprise LLM S
          '2510.15994', -- MCP Security Bench (MSB): Benchmarking Attacks Against Model Context Protoc
          '2509.23994', -- Policy-as-Prompt: Turning AI Governance Rules into Guardrails for AI Agents
          '2509.23694', -- SafeSearch: Automated Red-Teaming for the Safety of LLM-Based Search Agents
          '2510.05106', -- Rule Encoding and Compliance in Large Language Models: An Information-Theor
          '2509.14295', -- AEGIS: Automated Error Generation and Identification for Multi-Agent System
          '2509.11431', -- Securing AI Agents: Implementing Role-Based Access Control for Industrial A
          '2509.05608', -- Cross-Service Threat Intelligence in LLM Services using Privacy-Preserving
          '2508.19461', -- Reliable Weak-to-Strong Monitoring of LLM Agents
          '2507.22304', -- Invisible Injections: Exploiting Vision-Language Models Through Steganograp
          '2507.20526', -- Security Challenges in AI Agent Deployment: Insights from a Large Scale Pub
          '2506.14682', -- AIRTBench: Measuring Autonomous AI Red Teaming Capabilities in Language Mod
          '2410.13919', -- LLM Agent Honeypot: Monitoring AI Hacking Agents in the Wild
          '2406.05498', -- SelfDefend: LLMs Can Defend Themselves against Jailbreaking in a Practical
          '2309.02926', -- Demystifying RCE Vulnerabilities in LLM-Integrated Apps
          '2605.28617', -- LACUNA: Safe Agents as Recursive Program Holes
          '2605.30189', -- Token-Level Generalization in LoRA Adapter Backdoors: Attack Characterizati
          '2506.12104', -- Dynamic Rule-Based Defense with Injection Isolation for Securing LLM Agents
          '2509.23519', -- ReliabilityRAG: Effective and Provably Robust Defense for RAG-based Web-Sea
          '2505.00626', -- The Illusion of Role Separation: Hidden Shortcuts in LLM Role Learning (and
          '2402.17840', -- Follow My Instruction and Spill the Beans: Scalable Data Extraction from Re
          '2403.06833', -- Can LLMs Separate Instructions From Data? And What Do We Even Mean By That?
          '2406.19501', -- Monitoring Latent World States in Language Models with Propositional Probes
          '2505.20435', -- The Shape of Adversarial Influence: Characterizing LLM Latent Spaces with P
          '2507.04531', -- DP-Fusion: Token-Level Differentially Private Inference for Large Language
          '2505.16934', -- In-Context Watermarks for Large Language Models
          '2606.20636', -- SkillHarness: Harnessing Safe Skills for Computer-Use Agents
          '2606.12716', -- Does AI Reviewer See the Full Picture? Attacking and Defending Multimodal P
          '2510.18131', -- BlueCodeAgent: A Blue Teaming Agent Powered by Automated Red Teaming for Co
          '2606.16242', -- Rapid Poison: Practical Poisoning Attacks Against the Rapid Response Framew
          '2504.21228', -- CachePrune: Teaching LLMs What Not to Follow via KV-Cache Editing
          '2601.07185', -- Defenses Against Prompt Attacks Learn Surface Heuristics
          '2604.11806', -- Detecting Safety Violations Across Many Agent Traces
          '2604.07223', -- TraceSafe: A Systematic Assessment of LLM Guardrails on Multi-Step Tool-Cal
          '2511.12423', -- GraphTextack: A Realistic Black-Box Node Injection Attack on LLM-Enhanced G
          '2605.27823', -- Disentangling Adversarial Prompts: A Semantic-Graph Defense for Robust LLM
          '2508.11733', -- SafeSieve: From Heuristics to Experience in Progressive Pruning for LLM-bas
          '2608.09867', -- Stealing Reasoning Traces from Proprietary LLM APIs
          '2608.11878', -- ToolHazard: Scaling Adversarial Environments for Security Evaluation and Al
          '2608.15888', -- Bounded Agents: Delegation Security for Multi-Agent AI Systems
          '2510.11238', -- Attacks by Content: Automated Fact-checking is an AI Security Issue
          '2605.17380', -- ADR: An Agentic Detection System for Enterprise Agentic AI Security
          '2609.06966', -- MOLE: Detecting Insider Threats in AI Agents
          '2609.05903', -- EvoSafeHarness: Evolving Model- and Domain-Specific Harnesses for Securing
          '2609.17320', -- Emergence World: Adversarial Stress-Testing of Long-Horizon Multi-Agent Sys
          '2609.37040', -- Selecting The Most Informative Tokens in Natural Language Autoencoders
          '2610.19422', -- AgentSafeEvo: Adversarial Co-Evolution for LLM Agent Safety
          '2610.17301', -- The Agent Knew: Internal States Forecast Unauthorized Actions and Stop Them
          '2607.05277', -- Untrusted Content Masking for Web Agents with Security Guarantees
          '2606.15308', -- Forced Deferral: Manipulating Routing Decisions in Multimodal LLM Cascades
          '2603.09781', -- CLIOPATRA: Extracting Private Information from LLM Insights
          '2611.02332' -- LEANGUARD: Lean-Verified Guardrails for Tool-Using Agents
      )
      OR
      (p.source = 'external' AND p.id IN (
          104401, -- Ghosts in the Markup: Techniques to Fight Large Language Model-Powered Web
          127127, -- Breadcrumbing Search Agents: Per-Turn Scheming Over Long-Horizon Trajectori
          127989, -- ChainForge: Tool-Chain Hijacking Attacks against LLM Agents via Execution-G
          129805 -- Cross-User Poisoning: User-Task Boundary Failures in Multi-User Collaborati
      ))
  );

DELETE FROM paper_method_exclusions x
USING pi_curated_papers c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM pi_curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM pi_curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- prompt-injection: 30 reviewed negatives.
CREATE TEMP TABLE pi_excluded_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p CROSS JOIN methods m
WHERE m.slug = 'prompt-injection'
  AND p.is_latest_version
  AND (
      p.arxiv_id IN (
          '2307.16888', -- Backdooring Instruction-Tuned Large Language Models with Virtual Prompt Inj
          '2508.15250', -- EMNLP: Educator-role Moral and Normative Large Language Models Profiling
          '2606.13044', -- No Hidden Prompts Needed! You Can Game AI Peer Review with Presentation-Onl
          '2606.20922', -- Think Twice Before You Act: Protecting LLM Agents Against Tool Description
          '2405.12750', -- Generative AI in Cybersecurity: A Comprehensive Review of LLM Applications
          '2410.23687', -- Adversarial Attacks of Vision Tasks in the Past 10 Years: A Survey
          '2504.10465', -- Pixel-SAIL: Single Transformer For Pixel-Grounded Understanding
          '2510.24801', -- Fortytwo: Swarm Inference with Peer-Ranked Consensus
          '2603.19974', -- Trojan''s Whisper: Stealthy Manipulation of OpenClaw through Injected Bootst
          '2602.01942', -- Human Society-Inspired Approaches to Agentic AI Security: The 4C Framework
          '2601.12560', -- Agentic Artificial Intelligence (AI): Architectures, Taxonomies, and Evalua
          '2601.08490', -- BenchOverflow: Measuring Overflow in Large Language Models via Plain-Text P
          '2601.04583', -- Autonomous Agents on Blockchains: Standards, Execution Models, and Trust Bo
          '2601.03868', -- What Matters For Safety Alignment?
          '2512.16962', -- MemoryGraft: Persistent Compromise of LLM Agents via Poisoned Experience Re
          '2511.19483', -- Z-Space: A Multi-Agent Tool Orchestration Framework for Enterprise-Grade LL
          '2509.15775', -- EmoQ: Speech Emotion Recognition via Speech-Aware Q-Former and Large Langua
          '2506.22183', -- A Different Approach to AI Safety: Proceedings from the Columbia Convening
          '2505.15420', -- Silent Leaks: Implicit Knowledge Extraction Attack on RAG Systems through B
          '2602.23956', -- SwitchCraft: Training-Free Multi-Event Video Generation with Attention Cont
          '2509.17371', -- SilentStriker: Toward Stealthy Bit-Flip Attacks on Large Language Models
          '2508.02110', -- Attractive Metadata Attack: Inducing LLM Agents to Invoke Malicious Tools
          '2407.18213', -- Scaling Trends in Language Model Robustness
          '2604.16966', -- Visual Inception: Compromising Long-term Planning in Agentic Recommenders v
          '2607.21151', -- V-DEAL: Diagnosing Video Safety De-Calibration as an Understanding--Refusal
          '2509.10122', -- Realism Control One-step Diffusion for Real-world Image Super Resolution
          '2604.07831', -- Are GUI Agents Focused Enough? Automated Distraction via Semantic-level UI
          '2609.29647', -- AgentKernel: The Trust-Native Agentic Operating System
          '2609.29429' -- Just Ask Jev: Reinforcement Learning for Calibrated Decisions as a Zero-Sho
      )
      OR
      (p.source = 'external' AND p.id IN (
          127116 -- STEMFly: Enhancing UAV Vision-Language Navigation via Sensor Grounding, Tem
      ))
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'safety methods curation 2026-11-10: passing mention or contrast, survey list, or prompt injection in another sense (soft/visual prompt injection as a modelling technique, virtual prompt injection backdoors)'
FROM pi_excluded_papers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING pi_excluded_papers x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING pi_excluded_papers x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;
