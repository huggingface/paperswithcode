-- Method gap fill (2026-11-10 audit), group C: LLM post-training and decoding.
-- 12 new methods, area Language, plus an instruction-tuning alias/keyword
-- update on the existing supervised-fine-tuning-sft row.
--
-- Sourced (source_paper_id set, "Introduced" banner): Self-Instruct
-- (2212.10560), STaR (2203.14465), Constitutional AI and RLAIF (both
-- 2212.08073, which coined "RL from AI feedback"; 2309.00267 is a later
-- RLAIF-vs-RLHF study), KTO (2402.01306), ORPO (2403.07691), SimPO
-- (2405.14734), IPO (2310.12036), nucleus sampling (1904.09751) and contrastive
-- decoding (2210.15097).
--
-- Unsourced (contested or pre-arXiv origins, source_url explainer instead):
-- rejection sampling fine-tuning (STaR, RAFT, Llama 2 and Yuan et al.
-- 2308.01825 all predate or share the name; scoped to LLM fine-tuning, not the
-- classical Monte Carlo sampler, and without the "RFT" abbreviation, which
-- belongs to reinforcement-fine-tuning), and beam search (Harpy, 1976).
--
-- Keywords avoid bare ambiguous abbreviations, which are case-sensitive
-- substrings in the keyword backfill: "KTO" (HECKTOR, PAKTON), "IPO" (initial
-- public offering, other acronyms) and "STaR"/"star". Distinctive ones (ORPO,
-- SimPO, RLAIF) stay. Hero images are imported separately with
-- import_entity_image.py.


INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'rejection-sampling-fine-tuning',
    'Rejection Sampling Fine-Tuning',
    'Rejection Sampling Fine-Tuning',
    'Rejection sampling fine-tuning trains a language model on its own filtered outputs: for each prompt the model samples several candidate responses, a [reward model](/methods/reward-model), verifier or answer checker keeps only the best or the correct ones, and the model is fine-tuned on the kept samples with ordinary [supervised fine-tuning](/methods/supervised-fine-tuning-sft). Repeating the loop gives an iterative, offline alternative to on-policy RL that is simple and stable. [STaR](/methods/self-taught-reasoner) applied the idea to rationales filtered by answer correctness, [RAFT](/paper/2304.06767) ranked samples by reward, [Llama 2](/paper/2307.09288) used rejection sampling with a reward model before PPO in its [RLHF](/methods/rlhf) pipeline, and [Yuan et al.](/paper/2308.01825) named the math-reasoning variant RFT and showed that more distinct correct reasoning paths improve GSM8K accuracy. Related methods include [ReST](/paper/2308.08998) and [ReST-EM](/paper/2312.06585), which frame it as expectation-maximization, and [statistical rejection sampling](/paper/2309.06657) for building preference pairs. It is the training-time counterpart of [Best-of-N](/methods/best-of-n) sampling and should not be confused with [reinforcement fine-tuning](/methods/reinforcement-fine-tuning), which shares the RFT abbreviation, or with classical rejection sampling for drawing Monte Carlo samples.',
    'rejection sampling fine-tuning, rejection-sampling fine-tuning, rejection sampling finetuning, rejection sampling fine tuning, rejection-sampling finetuning, rejection sampling fine-tuned',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    NULL,
    NULL,
    '/paper/2308.01825',
    'Scaling Relationship on Learning Mathematical Reasoning with Large Language Models',
    NULL,
    NULL,
    '[Scaling Relationship on Learning Mathematical Reasoning with Large Language Models](/paper/2308.01825)',
    'always',
    ARRAY['Rejection Sampling Finetuning']
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'self-instruct', 'Self-Instruct', 'Self-Instruct',
    'Self-Instruct bootstraps instruction-tuning data from a language model itself. Starting from 175 human-written seed tasks, the model is prompted to write new instructions, decide whether each is a classification task, and generate input-output instances; near-duplicates (by ROUGE-L) and invalid generations are filtered, and the surviving tasks are added back to the pool for the next round. Applied to vanilla GPT-3, the method produced 52K instructions whose use for [instruction tuning](/methods/supervised-fine-tuning-sft) gave a 33% absolute gain on Super-NaturalInstructions, close to InstructGPT-001, without large human annotation effort. Self-Instruct underlies Stanford Alpaca and many synthetic-data pipelines such as Evol-Instruct in [WizardLM](/paper/2304.12244) and OSS-Instruct in [Magicoder](/paper/2312.02120), and it is a standard way to create [supervised fine-tuning](/methods/supervised-fine-tuning-sft) data for smaller open models.',
    'self-instruct',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2212.10560'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    NULL,
    'https://github.com/yizhongw/self-instruct',
    NULL,
    '[Self-Instruct: Aligning Language Models with Self-Generated Instructions](/paper/2212.10560)',
    'always',
    ARRAY[]::text[]
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'self-taught-reasoner', 'STaR',
    'Self-Taught Reasoner (STaR)',
    'STaR (Self-Taught Reasoner) is an iterative bootstrapping method that teaches a language model to produce [chain-of-thought](/methods/chain-of-thought-cot) rationales from only a few rationale examples and a dataset of question-answer pairs. In each round the model generates rationales with few-shot prompting, keeps those that lead to the correct answer, and for failed problems "rationalizes" by generating a rationale with the correct answer given as a hint; the base model is then fine-tuned on all kept rationales and the loop repeats. With GPT-J, STaR substantially improved over direct-answer fine-tuning on arithmetic, CommonsenseQA and GSM8K, matching a 30x larger model on CommonsenseQA. STaR is an early form of [rejection sampling fine-tuning](/methods/rejection-sampling-fine-tuning) and expert iteration for reasoning, and it influenced [ReST-EM](/paper/2312.06585), Quiet-STaR, V-STaR and reasoning models trained with reinforcement learning such as [DeepSeek-R1](/paper/2501.12948).',
    'self-taught reasoner',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2203.14465'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    NULL,
    'https://github.com/ezelikman/STaR',
    NULL,
    '[STaR: Bootstrapping Reasoning With Reasoning](/paper/2203.14465)',
    'judge',
    ARRAY[]::text[]
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'rlaif', 'RLAIF',
    'Reinforcement Learning from AI Feedback (RLAIF)',
    'Reinforcement Learning from AI Feedback (RLAIF) replaces the human preference labels in [RLHF](/methods/rlhf) with labels from an AI model: an off-the-shelf LLM is prompted, often with a set of principles, to judge which of two responses is better, a [reward model](/methods/reward-model) is trained on these AI preferences, and the policy is optimized against it with RL such as [PPO](/methods/ppo). The term was introduced with [Constitutional AI](/methods/constitutional-ai), which used AI feedback guided by a written constitution to train a harmless assistant. [Lee et al.](/paper/2309.00267) compared RLAIF with RLHF on summarization and dialogue, found similar human-rated quality, and proposed direct RLAIF, which uses the labeler LLM''s scores as the reward without training a reward model. AI feedback is now widely used to build preference datasets such as [UltraFeedback](/paper/2310.01377), for self-rewarding training ([Self-Rewarding Language Models](/paper/2401.10020)), with [DPO](/methods/direct-preference-optimization-dpo) and other offline objectives, and for multimodal alignment ([RLAIF-V](/paper/2405.17220)). It is closely related to [LLM-as-a-judge](/methods/llm-as-a-judge).',
    'RLAIF, reinforcement learning from AI feedback, Reinforcement Learning from AI Feedback, reinforcement learning with AI feedback, RL from AI feedback',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2212.08073'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    NULL,
    NULL,
    NULL,
    '[RLAIF vs. RLHF: Scaling Reinforcement Learning from Human Feedback with AI Feedback](/paper/2309.00267)',
    'always',
    ARRAY['RL from AI Feedback']
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'constitutional-ai',
    'Constitutional AI',
    'Constitutional AI (CAI)',
    'Constitutional AI (CAI) trains a harmless but non-evasive AI assistant using a short list of natural-language principles, the constitution, as the only human oversight instead of human labels of harmful outputs. In a supervised phase the model critiques and revises its own responses to red-teaming prompts according to sampled principles, and is fine-tuned on the revisions. In a reinforcement learning phase the model compares pairs of its responses against the principles, these AI preferences train a preference model, and the policy is optimized against it, which the paper calls RL from AI feedback ([RLAIF](/methods/rlaif)). Chain-of-thought reasoning in the critiques made the model''s judgments more transparent. Constitutional AI produced assistants that were both more helpful and more harmless than RLHF baselines trained on human harmlessness labels ([Bai et al.](/paper/2204.05862)), and it shaped Anthropic''s Claude models and later work on principle-driven alignment, collective constitutions and constitutional classifiers. It extends [RLHF](/methods/rlhf) and relies on a [reward model](/methods/reward-model) trained from AI rather than human comparisons.',
    'constitutional ai',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2212.08073'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    NULL,
    'https://github.com/anthropics/ConstitutionalHarmlessnessPaper',
    NULL,
    '[Constitutional AI: Harmlessness from AI Feedback](/paper/2212.08073)',
    'always',
    ARRAY[]::text[]
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'kto', 'KTO',
    'Kahneman-Tversky Optimization (KTO)',
    'Kahneman-Tversky Optimization (KTO) aligns a language model from binary feedback, a signal that each output is desirable or undesirable, instead of the paired preferences needed by [DPO](/methods/direct-preference-optimization-dpo). Building on prospect theory, the paper argues that alignment losses such as DPO are human-aware losses that implicitly model human biases, and it directly maximizes a Kahneman-Tversky value function of the implicit reward relative to a reference point estimated from the KL divergence to a reference model, with separate weights for desirable and undesirable examples. KTO matched or exceeded DPO at scales from 1B to 30B parameters despite using a weaker signal, tolerated extreme class imbalance, and could sometimes skip [supervised fine-tuning](/methods/supervised-fine-tuning-sft). Because thumbs-up/thumbs-down data is cheap and abundant, KTO is available in libraries such as TRL and is often compared with DPO, [IPO](/methods/ipo), [ORPO](/methods/orpo) and [SimPO](/methods/simpo).',
    'kahneman-tversky optimization, kahneman-tversky optimisation, kahneman tversky optimization',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2024,
    (SELECT id FROM papers WHERE arxiv_id = '2402.01306'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    NULL,
    'https://github.com/ContextualAI/HALOs',
    NULL,
    '[KTO: Model Alignment as Prospect Theoretic Optimization](/paper/2402.01306)',
    'always',
    ARRAY['Kahneman-Tversky Optimisation']
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'orpo', 'ORPO',
    'Odds Ratio Preference Optimization (ORPO)',
    'Odds Ratio Preference Optimization (ORPO) merges [supervised fine-tuning](/methods/supervised-fine-tuning-sft) and preference alignment into a single training stage that needs no reference model. Its loss adds to the usual negative log-likelihood on the chosen response a term that maximizes the log odds ratio between generating the chosen and the rejected response, which weakly penalizes disfavored styles while the model adapts to the domain. The paper shows that SFT alone also raises the likelihood of rejected responses, motivating the extra term. Fine-tuning Phi-2, Llama-2 and Mistral-7B with ORPO on UltraFeedback alone outperformed larger instruction models on AlpacaEval 2.0 and MT-Bench. ORPO saves the memory and compute of a separate SFT run and a frozen reference model, and it is implemented in TRL; it is commonly compared with [DPO](/methods/direct-preference-optimization-dpo), [KTO](/methods/kto) and [SimPO](/methods/simpo).',
    'ORPO, odds ratio preference optimization, odds ratio preference optimisation, odds-ratio preference optimization',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2024,
    (SELECT id FROM papers WHERE arxiv_id = '2403.07691'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    NULL,
    'https://github.com/xfactlab/orpo',
    NULL,
    '[ORPO: Monolithic Preference Optimization without Reference Model](/paper/2403.07691)',
    'always',
    ARRAY[]::text[]
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'simpo', 'SimPO',
    'Simple Preference Optimization (SimPO)',
    'Simple Preference Optimization (SimPO) is an offline preference optimization objective that, unlike [DPO](/methods/direct-preference-optimization-dpo), needs no reference model. It uses the length-normalized average log probability of a response under the policy as the implicit reward, which matches how the model generates and reduces length exploitation, and it adds a target reward margin to the Bradley-Terry objective so that the chosen response must beat the rejected one by a fixed gap. Without a reference model SimPO is cheaper in memory and compute, and across Mistral, Llama 3 and Gemma 2 base and instruct models it outperformed DPO and its variants by up to 6.4 points on AlpacaEval 2 and 7.5 points on Arena-Hard without increasing response length. SimPO is widely used to align open models and is compared with [DPO](/methods/direct-preference-optimization-dpo), [IPO](/methods/ipo), [KTO](/methods/kto) and [ORPO](/methods/orpo).',
    'SimPO, simple preference optimization, simple preference optimisation',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2024,
    (SELECT id FROM papers WHERE arxiv_id = '2405.14734'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    NULL,
    'https://github.com/princeton-nlp/SimPO',
    NULL,
    '[SimPO: Simple Preference Optimization with a Reference-Free Reward](/paper/2405.14734)',
    'always',
    ARRAY[]::text[]
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'ipo',
    'Identity Preference Optimization',
    'Identity Preference Optimization (IPO)',
    'Identity Preference Optimization (IPO) is an offline preference learning objective introduced in a paper that recasts [RLHF](/methods/rlhf) and [DPO](/methods/direct-preference-optimization-dpo) as instances of a general objective, ΨPO, that maximizes a non-decreasing function Ψ of preference probabilities with a KL penalty to a reference policy. The paper shows that DPO and RLHF rely on the Bradley-Terry assumption that pairwise preferences can be replaced by pointwise rewards, and that when preferences are nearly deterministic this lets the KL regularization become ineffective, so the policy overfits the preference data. Choosing Ψ as the identity gives IPO, whose regression-style loss pushes the difference of log-likelihood ratios between preferred and dispreferred responses toward a fixed target set by the regularization strength, which keeps the policy close to the reference even with deterministic preferences. IPO is a standard baseline next to DPO, [KTO](/methods/kto), [ORPO](/methods/orpo) and [SimPO](/methods/simpo) and is implemented in TRL.',
    'identity preference optimization, identity preference optimisation, identity-preference optimization',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2023,
    (SELECT id FROM papers WHERE arxiv_id = '2310.12036'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    NULL,
    NULL,
    NULL,
    '[A General Theoretical Paradigm to Understand Learning from Human Preferences](/paper/2310.12036)',
    'judge',
    ARRAY[]::text[]
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'beam-search',
    'Beam Search',
    'Beam Search',
    'Beam search is a heuristic search algorithm that decodes sequences by keeping only the k highest-scoring partial hypotheses, the beam, at each step: every hypothesis is extended by each candidate next token, the expansions are scored by cumulative log probability, and the best k survive until the hypotheses end. It approximates the most likely output far better than greedy decoding at a cost linear in the beam width, and with width one it reduces to greedy search. It was used in the Harpy speech recognition system (Lowerre, 1976) and became the standard decoder for speech recognition, statistical machine translation and neural [sequence-to-sequence](/methods/seq2seq) models ([Sutskever et al.](/paper/1409.3215)). Practical use adds length normalization and coverage penalties, and variants include [diverse beam search](/paper/1610.02424) and pruning strategies ([Freitag and Al-Onaizan](/paper/1702.01806)). Larger beams can lower output quality, which [Meister et al.](/paper/2010.02650) link to a uniform-information-density bias, and in open-ended generation beam search tends toward bland, repetitive text, which motivated sampling methods such as [nucleus sampling](/methods/nucleus-sampling). Beam search over reasoning steps guided by [process reward models](/methods/process-reward-model) is also used for test-time scaling, alongside [Best-of-N](/methods/best-of-n).',
    'beam search, beam-search, beam search decoding',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    NULL,
    NULL,
    'https://web.stanford.edu/~jurafsky/slp3/',
    'Speech and Language Processing (3rd ed. draft), Jurafsky & Martin',
    NULL,
    NULL,
    '[Beam search](https://commons.wikimedia.org/wiki/File:Beam_search.gif) by BogdanShevchenko, CC BY-SA 4.0',
    'always',
    ARRAY['Beam Search Decoding']
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'nucleus-sampling',
    'Nucleus Sampling',
    'Nucleus Sampling (Top-p Sampling)',
    'Nucleus sampling, also called top-p sampling, is a stochastic decoding method for language models that samples each next token from the smallest set of tokens whose cumulative probability exceeds a threshold p, after renormalizing their probabilities. Unlike top-k sampling, which keeps a fixed number of candidates ([Fan et al.](/paper/1805.04833)), the nucleus grows and shrinks with the model''s confidence, so it truncates the unreliable low-probability tail while keeping diversity when many continuations are plausible. Holtzman et al. introduced it after showing that likelihood-maximizing decoding such as [beam search](/methods/beam-search) produces bland and repetitive text, and that pure sampling drifts into incoherence; nucleus sampling produced text closer to human-written text in perplexity, diversity and human judgments. Top-p, usually combined with temperature, is the default sampling setting in most LLM APIs and generation libraries, and later truncation rules such as typical sampling and min-p are compared against it. It contrasts with search-based decoders and with [contrastive decoding](/methods/contrastive-decoding) and [speculative decoding](/methods/speculative-decoding), which target quality and speed respectively.',
    'nucleus sampling, top-p sampling, top-p decoding, top-p nucleus sampling',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2019,
    (SELECT id FROM papers WHERE arxiv_id = '1904.09751'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    NULL,
    'https://github.com/ari-holtzman/degen',
    NULL,
    '[The Curious Case of Neural Text Degeneration](/paper/1904.09751)',
    'always',
    ARRAY['Top-p Sampling']
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'contrastive-decoding',
    'Contrastive Decoding',
    'Contrastive Decoding (CD)',
    'Contrastive decoding (CD) generates text by searching for tokens that maximize the difference between the log probabilities of a large expert language model and a small amateur model, restricted to tokens to which the expert assigns sufficient probability (an adaptive plausibility constraint). The idea is that failure modes such as repetition and incoherence are even more likely under the amateur, so subtracting it removes them while keeping the expert''s knowledge. Without any training, CD outperformed [nucleus sampling](/methods/nucleus-sampling), top-k sampling and typical decoding in open-ended generation across Wikipedia, news and stories in automatic and human evaluations, and later work found that it also improves reasoning benchmarks such as GSM8K. The idea of contrasting two distributions spread to many variants: [DoLa](/paper/2309.03883) contrasts later and earlier layers of one model to improve factuality, [context-aware decoding](/paper/2305.14739) contrasts outputs with and without the context, and [visual contrastive decoding](/paper/2311.16922) contrasts clean and distorted images to reduce object hallucination in [vision-language models](/methods/vision-language-model-vlm). It differs from [contrastive search](/paper/2202.06417), which penalizes similarity to previous tokens, and is a decoding-time alternative to [beam search](/methods/beam-search).',
    'contrastive decoding',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2210.15097'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    NULL,
    'https://github.com/XiangLi1999/ContrastiveDecoding',
    NULL,
    '[Contrastive Decoding: Open-ended Text Generation as Optimization](/paper/2210.15097)',
    'always',
    ARRAY[]::text[]
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
    image_credit = COALESCE(EXCLUDED.image_credit, methods.image_credit),
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

-- Instruction tuning is not a separate method (user decision 2026-11-10): it is
-- supervised fine-tuning on instruction-formatted tasks, so the existing SFT
-- row gains the name as an alias and keywords, and its description credits
-- FLAN for coining the term.
UPDATE methods SET
    description = 'Supervised fine-tuning (SFT) trains a pretrained model on labeled input-output pairs with the standard [cross-entropy](/methods/cross-entropy-ce) (next-token) loss. For language models these pairs are usually prompts with demonstration responses written by humans or by stronger models, which turns a base model into an instruction-following assistant. SFT on many tasks phrased as natural-language instructions is called instruction tuning, a term coined by [FLAN](/paper/2109.01652), which showed that it improves zero-shot generalization to unseen tasks; such data can also be generated by the model itself, as in [Self-Instruct](/methods/self-instruct). SFT is the first post-training stage of the RLHF pipeline popularized by InstructGPT, run before reward modeling and [RLHF](/methods/rlhf) or [GRPO](/methods/grpo), and also serves as a cold start for reasoning models trained on long chain-of-thought traces. It is the supervised special case of [fine-tuning](/methods/fine-tuning), often combined with parameter-efficient methods such as LoRA.',
    keywords = 'SFT, supervised fine-tuning, supervised finetuning, supervised fine tuning, instruction tuning, instruction-tuning, instruction tuned, instruction-tuned, instruction fine-tuning, instruction finetuning, instruction fine tuning, instruction-finetuned, instruction fine-tuned',
    aliases = ARRAY['Instruction Tuning'],
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'supervised-fine-tuning-sft';


-- Introduced banners for the sourced methods.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug IN ('self-instruct', 'self-taught-reasoner', 'rlaif', 'constitutional-ai', 'kto', 'orpo', 'simpo', 'ipo', 'nucleus-sampling', 'contrastive-decoding') AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug IN ('self-instruct', 'self-taught-reasoner', 'rlaif', 'constitutional-ai', 'kto', 'orpo', 'simpo', 'ipo', 'nucleus-sampling', 'contrastive-decoding') AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Reviewed paper links (2026-11-10). Candidates: local Semantic Scholar
-- citers of each source paper for sourced methods, and bounded title/abstract
-- regex matches for all methods. Positives name, use, extend, analyze or
-- compare against the method in their title or abstract; reviewed negatives
-- (citers that only mention it in passing or not at all) become durable
-- exclusions so the keyword and reference backfills do not re-link them.



-- rejection-sampling-fine-tuning: 115 links, 0 exclusions.

CREATE TEMP TABLE rejection_sampling_fine_tuning_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rejection-sampling-fine-tuning'
  AND p.id IN (
        9987, 16332, 18895, 20347, 22799, 24931, 25919, 27368, 27443, 28159, 29961, 31334, 31399, 32095, 33335, 38600,
        43198, 44184, 44264, 44280, 44337, 44454, 44551, 44614, 45104, 45153, 45441, 45553, 46866, 47037, 47058, 47178,
        47733, 47816, 47865, 48186, 48393, 48439, 48828, 48907, 49574, 50056, 50270, 50960, 51849, 51860, 52202, 52206,
        52325, 52957, 53394, 53430, 53456, 53698, 54124, 55354, 55814, 58269, 59743, 60002, 60653, 61292, 62022, 62364,
        62477, 62517, 62736, 62944, 65627, 65986, 66553, 67619, 68844, 68999, 69055, 69363, 70234, 71203, 71560, 72861,
        82910, 82991, 88942, 94606, 98377, 98911, 99048, 99135, 99553, 100574, 100943, 101403, 103464, 103552, 106398, 108915,
        109520, 109762, 113917, 122191, 122256, 122846, 123061, 123533, 123874, 124615, 124793, 124994, 125140, 125308, 127772, 128098,
        129892, 130297, 130433
  );

DELETE FROM paper_method_exclusions x
USING rejection_sampling_fine_tuning_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM rejection_sampling_fine_tuning_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM rejection_sampling_fine_tuning_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


-- self-instruct: 44 links, 1634 exclusions. S2 local citers reviewed: 1673.

CREATE TEMP TABLE self_instruct_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'self-instruct'
  AND p.id IN (
        12157, 14231, 15830, 16267, 16565, 16787, 17565, 18085, 18189, 19227, 21521, 22321, 22456, 22457, 22642, 22844,
        24644, 26543, 28471, 28796, 31279, 31899, 33591, 34386, 35672, 36513, 36530, 37550, 43628, 47054, 48246, 49490,
        49873, 66668, 67239, 70467, 74560, 75018, 77050, 78437, 78952, 98808, 103675, 111026
  );

DELETE FROM paper_method_exclusions x
USING self_instruct_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM self_instruct_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM self_instruct_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


CREATE TEMP TABLE self_instruct_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'self-instruct'
  AND p.id IN (
        12167, 12269, 12709, 12935, 12946, 12987, 13160, 13869, 13889, 14098, 14150, 14311, 14327, 14330, 14349, 14452,
        14505, 14615, 14627, 14687, 14688, 14701, 14714, 14733, 14734, 14739, 14740, 14743, 14746, 14748, 14752, 14795,
        14838, 14841, 14917, 15015, 15031, 15065, 15201, 15238, 15263, 15276, 15279, 15294, 15337, 15349, 15359, 15383,
        15385, 15444, 15453, 15518, 15548, 15571, 15603, 15655, 15692, 15717, 15739, 15743, 15764, 15770, 15771, 15794,
        15804, 15809, 15816, 15875, 15888, 15960, 15968, 15990, 16007, 16036, 16040, 16041, 16048, 16058, 16063, 16069,
        16080, 16084, 16103, 16118, 16120, 16137, 16160, 16182, 16186, 16191, 16199, 16205, 16237, 16263, 16300, 16315,
        16379, 16559, 16628, 16640, 16751, 16822, 16946, 16953, 17019, 17084, 17100, 17108, 17127, 17128, 17152, 17170,
        17188, 17193, 17200, 17208, 17273, 17311, 17388, 17395, 17421, 17422, 17463, 17471, 17630, 17664, 17716, 17744,
        17766, 17777, 17782, 17807, 17831, 17894, 17901, 17909, 17940, 17966, 18000, 18032, 18038, 18041, 18055, 18128,
        18152, 18169, 18187, 18198, 18201, 18218, 18327, 18334, 18369, 18394, 18470, 18584, 18610, 18617, 18678, 18734,
        18743, 18763, 18802, 18808, 18809, 18810, 18813, 18839, 18873, 18874, 18898, 18903, 18928, 18972, 18979, 18988,
        19002, 19018, 19041, 19084, 19087, 19164, 19169, 19188, 19204, 19223, 19244, 19256, 19316, 19420, 19454, 19459,
        19469, 19502, 19508, 19541, 19543, 19567, 19571, 19598, 19635, 19639, 19680, 19682, 19687, 19736, 19763, 19791,
        19793, 19836, 19840, 19855, 19857, 19930, 19945, 19962, 19993, 20006, 20018, 20053, 20193, 20195, 20196, 20216,
        20233, 20272, 20285, 20286, 20299, 20322, 20325, 20377, 20408, 20411, 20428, 20484, 20496, 20523, 20525, 20537,
        20581, 20589, 20598, 20673, 20677, 20703, 20725, 20807, 20844, 20923, 20933, 20974, 20985, 20998, 21039, 21055,
        21126, 21160, 21162, 21173, 21180, 21181, 21183, 21209, 21212, 21224, 21240, 21261, 21319, 21360, 21390, 21417,
        21427, 21471, 21492, 21518, 21519, 21543, 21558, 21569, 21571, 21589, 21603, 21604, 21620, 21623, 21625, 21635,
        21663, 21664, 21665, 21707, 21713, 21714, 21729, 21740, 21762, 21796, 21807, 21808, 21816, 21882, 21883, 21891,
        21892, 21899, 21930, 21959, 21961, 21964, 21965, 22017, 22024, 22029, 22076, 22088, 22101, 22126, 22133, 22148,
        22178, 22205, 22211, 22221, 22243, 22249, 22273, 22275, 22331, 22338, 22364, 22403, 22430, 22471, 22477, 22517,
        22536, 22553, 22557, 22561, 22577, 22603, 22636, 22649, 22680, 22699, 22730, 22741, 22786, 22807, 22837, 22901,
        22937, 22966, 23041, 23091, 23101, 23144, 23163, 23232, 23253, 23284, 23291, 23333, 23340, 23343, 23354, 23373,
        23379, 23400, 23447, 23450, 23568, 23578, 23627, 23650, 23654, 23656, 23680, 23683, 23723, 23724, 23735, 23746,
        23800, 23804, 23844, 23897, 23951, 24041, 24047, 24049, 24119, 24127, 24132, 24136, 24180, 24188, 24191, 24201,
        24202, 24221, 24227, 24228, 24273, 24331, 24495, 24551, 24592, 24599, 24636, 24655, 24702, 24725, 24876, 24901,
        24925, 24987, 25002, 25022, 25088, 25106, 25127, 25131, 25160, 25185, 25187, 25204, 25206, 25209, 25268, 25270,
        25296, 25366, 25397, 25410, 25423, 25446, 25466, 25561, 25616, 25622, 25626, 25653, 25723, 25751, 25754, 25776,
        25785, 25801, 25836, 25867, 25992, 26007, 26009, 26079, 26193, 26222, 26261, 26302, 26329, 26358, 26374, 26445,
        26452, 26483, 26499, 26542, 26573, 26589, 26600, 26601, 26622, 26656, 26680, 26710, 26723, 26754, 26785, 26815,
        26829, 26907, 26930, 26935, 26945, 26967, 26990, 27011, 27013, 27031, 27035, 27043, 27077, 27097, 27111, 27116,
        27159, 27174, 27184, 27191, 27228, 27231, 27291, 27297, 27300, 27314, 27335, 27346, 27349, 27368, 27372, 27394,
        27400, 27405, 27414, 27426, 27444, 27446, 27451, 27474, 27514, 27534, 27537, 27556, 27558, 27580, 27590, 27592,
        27606, 27647, 27654, 27667, 27670, 27673, 27685, 27688, 27710, 27717, 27721, 27735, 27738, 27747, 27749, 27767,
        27819, 27846, 27852, 27860, 27872, 27877, 27900, 27903, 27910, 27939, 27944, 27947, 27956, 27965, 27979, 28007,
        28049, 28067, 28082, 28133, 28143, 28163, 28186, 28196, 28211, 28289, 28290, 28331, 28383, 28424, 28429, 28435,
        28439, 28456, 28481, 28495, 28498, 28500, 28533, 28538, 28633, 28637, 28639, 28740, 28782, 28819, 28821, 28861,
        28884, 28908, 28931, 28993, 29042, 29096, 29120, 29126, 29312, 29325, 29368, 29383, 29469, 29514, 29540, 29693,
        29705, 29711, 29744, 29855, 29868, 29894, 29977, 29980, 29982, 29988, 30105, 30116, 30124, 30173, 30212, 30240,
        30249, 30259, 30303, 30409, 30438, 30519, 30523, 30527, 30574, 30650, 30654, 30704, 30706, 30738, 30745, 30775,
        30838, 30842, 30865, 30881, 30958, 30966, 31020, 31074, 31090, 31111, 31142, 31158, 31166, 31215, 31217, 31299,
        31309, 31334, 31338, 31349, 31352, 31411, 31423, 31427, 31472, 31506, 31513, 31518, 31542, 31580, 31640, 31666,
        31749, 31779, 31833, 31999, 32036, 32043, 32045, 32071, 32087, 32131, 32133, 32187, 32243, 32373, 32375, 32413,
        32421, 32428, 32439, 32497, 32525, 32564, 32570, 32596, 32604, 32634, 32679, 32683, 32749, 32757, 32782, 32793,
        32809, 32953, 32963, 32984, 33030, 33040, 33062, 33067, 33087, 33105, 33140, 33147, 33160, 33185, 33194, 33204,
        33235, 33251, 33321, 33335, 33356, 33367, 33375, 33379, 33401, 33403, 33434, 33447, 33466, 33471, 33507, 33511,
        33599, 33611, 33729, 33762, 33780, 33794, 33811, 33833, 33838, 33846, 33866, 33877, 33878, 33908, 33952, 33973,
        34000, 34025, 34056, 34073, 34085, 34090, 34181, 34264, 34302, 34324, 34387, 34520, 34529, 34534, 34601, 34614,
        34647, 34707, 34782, 34818, 34860, 34919, 34923, 34978, 35001, 35014, 35021, 35051, 35073, 35222, 35224, 35264,
        35276, 35358, 35446, 35480, 35491, 35521, 35526, 35529, 35538, 35560, 35598, 35603, 35661, 35678, 35734, 35737,
        35833, 35861, 35875, 35908, 35909, 35936, 35961, 36026, 36103, 36127, 36146, 36194, 36223, 36237, 36248, 36277,
        36281, 36286, 36303, 36333, 36335, 36461, 36478, 36480, 36547, 36554, 36563, 36587, 36761, 36778, 36813, 36979,
        36986, 37011, 37018, 37091, 37095, 37108, 37144, 37201, 37229, 37249, 37296, 37347, 37424, 37450, 37492, 37501,
        37533, 37629, 37660, 37762, 37799, 37802, 37806, 37818, 37843, 37845, 37884, 37890, 37896, 37910, 37927, 37973,
        38009, 38021, 38105, 38121, 38125, 38158, 38162, 38214, 38217, 38322, 38410, 38416, 38485, 38488, 38491, 38508,
        38520, 38559, 38638, 38655, 38658, 38708, 38710, 38789, 38809, 38830, 38834, 38844, 38868, 38879, 38890, 38936,
        38982, 39057, 39117, 39131, 39149, 39171, 39189, 39233, 39243, 39282, 39284, 39337, 39417, 39446, 39464, 39475,
        39539, 39556, 39598, 39692, 39880, 39961, 39968, 40030, 40111, 40180, 40184, 40274, 40327, 40383, 40427, 40476,
        40601, 40699, 40755, 40774, 40810, 40871, 40909, 40916, 41009, 41125, 41206, 41526, 41551, 41598, 41600, 41604,
        41634, 41656, 41673, 41749, 41788, 41796, 41802, 41890, 41913, 41967, 42023, 42030, 42049, 42080, 42206, 42232,
        42241, 42244, 42450, 42508, 42559, 42629, 42647, 42653, 42791, 42885, 42902, 42998, 43047, 43049, 43065, 43194,
        43261, 43285, 43299, 43302, 43373, 43374, 43398, 43419, 43420, 43423, 43584, 43620, 43749, 43753, 43796, 43874,
        43879, 44143, 44245, 44280, 44314, 44325, 44331, 44386, 44453, 44468, 44493, 44515, 44549, 44564, 44576, 44598,
        44615, 44646, 44701, 44714, 44774, 44818, 44845, 44858, 44861, 44877, 44879, 44921, 44966, 44974, 45037, 45049,
        45129, 45220, 45231, 45243, 45352, 45404, 45450, 45452, 45497, 45556, 45578, 45583, 45591, 45754, 45755, 45847,
        45916, 45930, 45931, 45972, 45980, 46113, 46123, 46146, 46273, 46306, 46410, 46487, 46520, 46529, 46533, 46543,
        46591, 46717, 46840, 46858, 46866, 46872, 46960, 46968, 47029, 47113, 47184, 47326, 47396, 47459, 47460, 47578,
        47582, 47629, 47637, 47711, 47727, 47832, 47962, 47964, 47966, 47992, 48005, 48027, 48029, 48048, 48116, 48182,
        48221, 48222, 48268, 48432, 48455, 48474, 48532, 48596, 48604, 48636, 48649, 48712, 48735, 48751, 48771, 48864,
        48896, 48903, 48933, 49104, 49118, 49149, 49152, 49229, 49262, 49270, 49297, 49318, 49387, 49500, 49538, 49566,
        49571, 49607, 49649, 49652, 49708, 49931, 49996, 50187, 50230, 50248, 50285, 50401, 50521, 50530, 50546, 50895,
        50979, 51041, 51087, 51099, 51106, 51251, 51296, 51313, 51658, 51744, 51858, 51869, 51940, 51990, 52184, 52206,
        52244, 52265, 52326, 52549, 52588, 52639, 52674, 52709, 52754, 52762, 52808, 52834, 52856, 52870, 52962, 52986,
        53112, 53212, 53258, 53411, 53430, 53472, 53479, 53491, 53527, 53614, 53631, 53678, 53723, 53738, 53893, 53975,
        53982, 54003, 54057, 54126, 54166, 54174, 54226, 54429, 54611, 54614, 54705, 54766, 54851, 54878, 54885, 54922,
        55081, 55175, 55198, 55311, 55404, 55533, 55596, 55619, 55746, 55925, 55952, 56044, 56071, 56156, 56665, 56668,
        56673, 56886, 57154, 57240, 57346, 57413, 57439, 57443, 57544, 57701, 57706, 57775, 57798, 57945, 58187, 58212,
        58312, 58336, 58383, 58394, 58540, 58574, 58690, 59037, 59072, 59175, 59244, 59330, 59366, 59466, 59747, 59751,
        59765, 60035, 60125, 60147, 60320, 60342, 60364, 60406, 60591, 60684, 61350, 61486, 61545, 61722, 61734, 61854,
        61937, 61961, 62028, 62158, 62291, 62336, 62491, 62584, 62966, 63149, 63212, 63300, 64051, 64123, 64178, 64241,
        64392, 64393, 64570, 65004, 65059, 65155, 65735, 65988, 66077, 66187, 66215, 66223, 66272, 66283, 66447, 66510,
        66669, 66830, 66977, 67045, 67141, 67253, 67262, 67268, 67475, 67615, 68060, 68164, 68244, 68247, 68470, 68508,
        68564, 68668, 68674, 68881, 68992, 69024, 69077, 69104, 69109, 69272, 69336, 69363, 69382, 69384, 69537, 69648,
        69822, 70082, 70095, 70189, 70365, 70371, 70487, 70648, 70716, 70754, 70757, 71000, 71008, 71115, 71154, 71299,
        71429, 71553, 71564, 72022, 72061, 72093, 72128, 72264, 72272, 72325, 72417, 72605, 72633, 72661, 73210, 73308,
        73333, 73594, 73699, 73745, 73938, 74233, 74305, 74330, 74619, 74658, 74663, 74665, 74872, 74888, 74891, 74893,
        75009, 75072, 75360, 75842, 76014, 76068, 76072, 76133, 76190, 76336, 76371, 76492, 76510, 76604, 76664, 76789,
        76835, 76865, 76883, 76910, 77025, 77090, 77122, 77137, 77208, 77218, 77317, 77513, 77525, 77643, 77731, 77747,
        77782, 77812, 77870, 77995, 78091, 78214, 78234, 78276, 78428, 78519, 78655, 79260, 79737, 79969, 82862, 82900,
        82974, 82981, 83204, 83396, 83424, 83508, 83763, 84511, 84660, 84734, 84870, 85124, 85532, 85656, 85707, 85780,
        85834, 85921, 86312, 86472, 86601, 86758, 87112, 87252, 87260, 87380, 87478, 87488, 87490, 87503, 88588, 88677,
        88765, 89165, 89604, 89832, 89908, 89918, 90551, 90828, 91011, 91306, 91490, 91534, 91618, 91699, 92026, 92143,
        92353, 92363, 92367, 92477, 92575, 92581, 92613, 92651, 92922, 93148, 93184, 93381, 93688, 93777, 93843, 94269,
        94302, 94421, 94436, 94846, 97538, 98221, 98227, 98706, 99075, 99356, 99881, 100188, 100234, 100308, 100356, 100403,
        100646, 100962, 100977, 101045, 101126, 101360, 101398, 101426, 101569, 101689, 101964, 102382, 102499, 102764, 102818, 102948,
        103129, 103223, 103379, 103395, 103411, 103441, 103446, 103449, 103474, 103508, 103566, 103614, 103649, 103717, 104438, 104518,
        104545, 104554, 106505, 106548, 106686, 106997, 107185, 107216, 107333, 107338, 107560, 107861, 107944, 107945, 108153, 108307,
        108395, 108411, 108757, 109297, 109348, 109507, 109680, 109686, 110061, 110130, 110189, 110267, 110333, 110520, 110583, 110600,
        110613, 110682, 110947, 111057, 111096, 111118, 113199, 113870, 113876, 113909, 113926, 113938, 114877, 115545, 116478, 116598,
        117002, 118396, 119442, 119646, 120449, 122124, 122192, 122294, 122335, 122354, 122398, 122465, 122659, 122814, 123170, 123189,
        123247, 123333, 123361, 123549, 123714, 123951, 123974, 124137, 124206, 124772, 125211, 125468, 125643, 126688, 127000, 127035,
        127143, 127405, 128111, 128394, 128647, 128661, 128723, 129142, 129570, 130031, 130574, 131334, 131584, 131608, 131643, 131665,
        131703, 131820
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the source paper or matches the name without naming, using, extending or comparing against Self-Instruct'
FROM self_instruct_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING self_instruct_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING self_instruct_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- self-taught-reasoner: 29 links, 593 exclusions. S2 local citers reviewed: 611.

CREATE TEMP TABLE self_taught_reasoner_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'self-taught-reasoner'
  AND p.id IN (
        8447, 9856, 24243, 27121, 28875, 29589, 29968, 34332, 34610, 37723, 38049, 38996, 39444, 42011, 42070, 42084,
        45443, 45553, 45897, 55077, 55280, 55477, 59996, 62898, 64225, 67239, 72707, 72861, 108041
  );

DELETE FROM paper_method_exclusions x
USING self_taught_reasoner_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM self_taught_reasoner_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM self_taught_reasoner_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


CREATE TEMP TABLE self_taught_reasoner_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'self-taught-reasoner'
  AND p.id IN (
        7789, 8575, 8874, 8937, 9065, 9109, 9111, 9144, 9368, 9798, 10175, 10318, 10470, 10533, 10575, 10627,
        10771, 10933, 11195, 11203, 11387, 11618, 11858, 11993, 12050, 12076, 12111, 12128, 12142, 12158, 12239, 12241,
        12270, 12300, 12516, 12719, 13058, 13144, 13309, 13533, 13573, 14148, 14301, 14537, 14621, 14897, 14956, 15100,
        15186, 15202, 15312, 15359, 15368, 15644, 15757, 16027, 16068, 16092, 16325, 16379, 16481, 16687, 17070, 17341,
        17372, 17740, 18012, 18776, 18895, 18972, 19283, 19363, 19420, 19431, 19523, 19810, 20130, 20300, 20488, 20547,
        20626, 20794, 20948, 21055, 21082, 21101, 21112, 21337, 21350, 21360, 21433, 21467, 21505, 21554, 21577, 21665,
        21945, 22013, 22387, 22529, 23215, 23589, 23746, 24604, 24704, 24983, 25209, 25535, 26763, 26993, 27031, 27118,
        27377, 27822, 28157, 28581, 28684, 28816, 28861, 28994, 30212, 30523, 30534, 30648, 30678, 30906, 30940, 30968,
        31284, 31654, 31755, 31998, 32202, 32421, 32643, 33147, 33411, 33771, 34044, 34923, 34972, 34981, 35208, 35819,
        35883, 36291, 36366, 36384, 36519, 36564, 37036, 37068, 37089, 37208, 37357, 37830, 38036, 38060, 38162, 38220,
        38255, 38258, 38262, 38266, 38312, 38374, 38398, 38405, 38444, 38491, 38600, 38625, 38637, 38683, 39253, 39392,
        39534, 39578, 39674, 39700, 40445, 40640, 40774, 40870, 40916, 41793, 41947, 41996, 42160, 42200, 42317, 42730,
        43047, 43070, 43169, 43194, 43198, 43353, 43584, 43586, 43663, 43728, 43811, 43823, 43952, 43998, 44277, 44414,
        44502, 44515, 44665, 44790, 44942, 44989, 45183, 45317, 45441, 45456, 45806, 46228, 46323, 46327, 46467, 46671,
        46711, 46909, 46911, 46956, 46988, 47038, 47045, 47088, 47164, 47221, 47230, 47360, 47460, 47512, 47629, 47733,
        47766, 47865, 47910, 47912, 47964, 48002, 48015, 48022, 48086, 48246, 48347, 48393, 48411, 48442, 48472, 48531,
        48888, 48896, 48955, 49071, 49245, 49249, 49337, 49378, 49448, 49546, 49564, 49607, 49645, 49649, 49664, 49752,
        49873, 49886, 50030, 50077, 50130, 50195, 50215, 50273, 50274, 50379, 50453, 50642, 50708, 50739, 50802, 50901,
        51006, 51041, 51069, 51144, 51186, 51413, 51715, 52309, 52345, 52516, 52661, 52674, 52854, 53091, 53161, 53252,
        53270, 53310, 53356, 53479, 53519, 53525, 53695, 53698, 53742, 53771, 53836, 53888, 53893, 54149, 54473, 54614,
        54660, 54831, 54918, 55033, 55374, 55402, 55554, 55792, 55813, 55831, 55872, 56118, 56479, 56617, 56688, 57154,
        57252, 57346, 57489, 57506, 57664, 58042, 58142, 58252, 58336, 58739, 59375, 59458, 59713, 59813, 60022, 60090,
        60445, 60620, 60688, 60746, 60833, 61191, 61266, 61368, 61582, 61587, 61788, 61937, 62022, 62023, 62158, 62165,
        63214, 63488, 63919, 64097, 64408, 64708, 64840, 64933, 65535, 65816, 65947, 66077, 66223, 66266, 67001, 67101,
        67113, 67331, 67388, 67603, 67611, 67754, 68653, 68767, 69077, 69170, 69873, 70178, 70428, 70500, 70648, 70747,
        70817, 70880, 71358, 71472, 71869, 72252, 72272, 72411, 72459, 72568, 72633, 72638, 73306, 73316, 73382, 73384,
        73526, 73598, 73914, 74081, 74502, 74616, 74944, 75009, 75261, 76068, 76454, 82942, 83181, 83205, 83245, 83249,
        83260, 83290, 83291, 83424, 83846, 85706, 86010, 86485, 86493, 86527, 86841, 87026, 87075, 87108, 87252, 88274,
        88590, 88673, 88793, 89643, 90518, 90525, 91039, 91328, 91459, 91490, 91699, 92473, 92581, 92608, 92717, 92831,
        92838, 92866, 92906, 93338, 93590, 93687, 93838, 93870, 93926, 94023, 94102, 94233, 94421, 94606, 94668, 95101,
        95111, 97965, 97982, 98165, 98454, 98689, 98737, 98808, 98887, 98936, 99014, 99031, 99055, 99882, 100733, 100812,
        100943, 101002, 101396, 101632, 101944, 101964, 102177, 102355, 102427, 102526, 102625, 102716, 104305, 104527, 105914, 105933,
        106045, 106047, 106114, 106127, 106276, 106318, 106319, 106324, 106349, 106389, 108711, 108760, 108915, 109064, 109549, 109648,
        109656, 109951, 113383, 113739, 113898, 113899, 113971, 114003, 114089, 114181, 118530, 118756, 121985, 122018, 122145, 122251,
        122254, 122297, 122335, 122444, 122480, 122497, 122519, 122530, 122710, 122737, 122750, 122907, 123039, 123197, 123378, 123403,
        123553, 123623, 123714, 123758, 123970, 123981, 124014, 124957, 125106, 125175, 125643, 126221, 126793, 127090, 127534, 127596,
        127938, 128050, 128462, 129155, 129267, 130110, 130568, 130715, 130773, 131334, 131376, 131511, 131544, 131608, 131754, 131780,
        132060
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the source paper or matches the name without naming, using, extending or comparing against STaR'
FROM self_taught_reasoner_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING self_taught_reasoner_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING self_taught_reasoner_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- rlaif: 86 links, 1188 exclusions. S2 local citers reviewed: 1221.

CREATE TEMP TABLE rlaif_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rlaif'
  AND p.id IN (
        12009, 15104, 15160, 15650, 16205, 18588, 19169, 19930, 20009, 20725, 21244, 22016, 22517, 22577, 23201, 23632,
        24211, 24848, 26715, 26889, 26985, 27239, 27456, 27606, 28821, 28906, 29061, 29705, 30054, 30772, 31421, 31829,
        31978, 32139, 32413, 33066, 33858, 35092, 37848, 38036, 38250, 38358, 38637, 38739, 39162, 39284, 39580, 40034,
        40644, 41188, 41551, 41943, 42048, 44556, 46988, 47661, 48211, 48268, 48882, 49438, 52959, 53743, 55638, 57668,
        59271, 61344, 62317, 63707, 66006, 66830, 66831, 68999, 69394, 70077, 71417, 71644, 75572, 88754, 88806, 89401,
        93870, 94404, 106334, 110975, 127911, 129285
  );

DELETE FROM paper_method_exclusions x
USING rlaif_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM rlaif_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM rlaif_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


CREATE TEMP TABLE rlaif_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'rlaif'
  AND p.id IN (
        8822, 10196, 10705, 11378, 12551, 12709, 12766, 12874, 13122, 13181, 13281, 13438, 13557, 13825, 13926, 13991,
        14150, 14266, 14301, 14303, 14327, 14448, 14505, 14606, 14642, 14688, 14729, 14987, 15026, 15162, 15207, 15238,
        15312, 15417, 15500, 15548, 15577, 15669, 15743, 15788, 15834, 15858, 15919, 15939, 15990, 15992, 16036, 16063,
        16080, 16090, 16120, 16158, 16174, 16267, 16330, 16337, 16379, 16415, 16499, 16739, 16751, 16869, 16901, 16921,
        16967, 17019, 17056, 17108, 17121, 17214, 17223, 17362, 17506, 17624, 17673, 17705, 17825, 17851, 17901, 17909,
        17920, 17940, 17971, 18034, 18055, 18088, 18128, 18144, 18187, 18201, 18334, 18369, 18379, 18470, 18613, 18625,
        18666, 18711, 18727, 18776, 18801, 18862, 18895, 18972, 18996, 19018, 19164, 19174, 19223, 19240, 19420, 19523,
        19567, 19660, 19680, 19687, 19854, 19876, 19912, 20018, 20025, 20026, 20028, 20130, 20141, 20170, 20299, 20377,
        20403, 20428, 20484, 20488, 20562, 20589, 20591, 20598, 20670, 20673, 20722, 20777, 20813, 20848, 20861, 20911,
        20933, 20987, 21000, 21008, 21015, 21039, 21082, 21103, 21104, 21132, 21172, 21261, 21298, 21306, 21336, 21351,
        21357, 21360, 21378, 21462, 21544, 21590, 21596, 21620, 21663, 21697, 21707, 21712, 21734, 21751, 21753, 21778,
        21882, 21883, 21892, 21937, 21982, 22017, 22037, 22043, 22045, 22046, 22133, 22148, 22227, 22244, 22249, 22288,
        22321, 22417, 22503, 22628, 22711, 22816, 22839, 22876, 22890, 22937, 23041, 23054, 23161, 23209, 23258, 23264,
        23265, 23300, 23325, 23333, 23408, 23427, 23554, 23562, 23706, 23723, 23725, 23735, 23828, 23897, 24041, 24047,
        24068, 24148, 24207, 24248, 24655, 24681, 24818, 24824, 24895, 24910, 24931, 25071, 25090, 25107, 25133, 25175,
        25370, 25414, 25458, 25582, 25613, 25616, 25622, 25638, 25645, 25684, 25737, 25776, 25781, 25807, 25881, 25955,
        25992, 26058, 26091, 26129, 26141, 26157, 26195, 26210, 26258, 26495, 26541, 26579, 26589, 26705, 26729, 26732,
        26764, 26843, 26853, 26881, 26921, 26933, 26990, 27006, 27020, 27057, 27103, 27115, 27121, 27173, 27174, 27191,
        27201, 27219, 27246, 27273, 27282, 27287, 27349, 27372, 27379, 27381, 27394, 27420, 27443, 27453, 27474, 27483,
        27501, 27545, 27549, 27625, 27637, 27673, 27763, 27799, 27841, 27915, 28049, 28136, 28156, 28159, 28186, 28219,
        28446, 28456, 28500, 28523, 28536, 28547, 28730, 28749, 28775, 28784, 28792, 28797, 28800, 28861, 28884, 28948,
        28982, 29127, 29148, 29209, 29362, 29557, 29583, 29589, 29597, 29598, 29707, 29711, 29783, 29902, 29950, 29970,
        29980, 29996, 30013, 30114, 30123, 30212, 30238, 30285, 30400, 30434, 30499, 30523, 30597, 30627, 30637, 30648,
        30654, 30697, 30869, 30906, 30968, 31017, 31020, 31131, 31251, 31277, 31284, 31463, 31470, 31487, 31489, 31525,
        31547, 31554, 31704, 31779, 31793, 31899, 31956, 31991, 31998, 32049, 32073, 32086, 32187, 32202, 32250, 32271,
        32332, 32439, 32441, 32468, 32482, 32488, 32561, 32585, 32605, 32617, 32644, 32688, 32690, 32749, 32782, 32810,
        32861, 32872, 32960, 32998, 33050, 33067, 33105, 33207, 33225, 33398, 33471, 33561, 33572, 33592, 33593, 33607,
        33762, 33771, 33811, 33856, 33864, 33872, 33883, 33914, 33930, 34061, 34082, 34116, 34205, 34217, 34363, 34378,
        34499, 34543, 34548, 34647, 34654, 34666, 34693, 34919, 34924, 34942, 34978, 34999, 35001, 35019, 35032, 35064,
        35119, 35208, 35224, 35242, 35278, 35545, 35560, 35755, 35819, 35883, 35961, 35972, 36090, 36091, 36271, 36287,
        36288, 36291, 36303, 36384, 36433, 36480, 36513, 36558, 36602, 36708, 36755, 36756, 36842, 36859, 37105, 37193,
        37222, 37358, 37457, 37676, 37735, 37800, 37884, 37897, 38021, 38060, 38125, 38158, 38159, 38170, 38196, 38286,
        38316, 38323, 38325, 38344, 38498, 38611, 38705, 38757, 38770, 38840, 38881, 38932, 38978, 38986, 38999, 39008,
        39034, 39042, 39056, 39059, 39085, 39227, 39417, 39428, 39500, 39626, 39670, 39765, 39773, 39834, 39968, 39979,
        39988, 40006, 40102, 40111, 40132, 40260, 40327, 40442, 40618, 40916, 40962, 41000, 41020, 41381, 41689, 41987,
        42049, 42200, 42331, 42489, 42490, 42510, 42647, 42692, 42862, 42885, 43070, 43118, 43374, 43398, 43478, 43499,
        43518, 43576, 43617, 43767, 43798, 43815, 43879, 44071, 44129, 44171, 44222, 44399, 44417, 44495, 44568, 44598,
        44603, 44615, 44830, 44862, 44876, 44891, 44945, 45043, 45099, 45182, 45231, 45234, 45427, 45450, 45485, 45502,
        45754, 45796, 45917, 45960, 45981, 46101, 46292, 46425, 46469, 46589, 46633, 46778, 46856, 46917, 46951, 47056,
        47062, 47071, 47134, 47179, 47227, 47372, 47401, 47470, 47491, 47804, 47899, 47940, 47947, 48024, 48099, 48202,
        48291, 48339, 48389, 48391, 48406, 48509, 48780, 48896, 49049, 49092, 49152, 49216, 49217, 49262, 49300, 49371,
        49464, 49513, 49574, 49767, 49873, 49894, 49968, 49976, 50197, 50277, 50462, 50530, 50586, 50646, 50839, 50873,
        51016, 51042, 51105, 51144, 51248, 51333, 51400, 51608, 51641, 51677, 51790, 51849, 51944, 51953, 52064, 52328,
        52404, 52509, 52546, 52663, 52666, 52722, 52901, 53020, 53038, 53143, 53175, 53218, 53232, 53236, 53246, 53338,
        53371, 53421, 53551, 53566, 53610, 53611, 53888, 53893, 54150, 54180, 54223, 54614, 54822, 54935, 55060, 55198,
        55219, 55298, 55335, 55366, 55536, 55542, 55554, 55636, 55798, 55804, 55817, 55830, 55831, 55832, 55929, 56040,
        56078, 56238, 56506, 56601, 56760, 56992, 57154, 57240, 57371, 57429, 57459, 57484, 57543, 57623, 57659, 57706,
        57758, 57984, 57988, 57993, 58026, 58033, 58035, 58085, 58137, 58233, 58235, 58338, 58420, 58430, 58435, 58437,
        58504, 58783, 58906, 59131, 59182, 59192, 59221, 59233, 59374, 59447, 59448, 59641, 59813, 59824, 60022, 60070,
        60332, 60366, 60373, 60426, 60606, 60611, 60643, 60794, 60854, 60875, 60881, 61082, 61096, 61103, 61121, 61143,
        61219, 61296, 61485, 61511, 61562, 61642, 61726, 61736, 61839, 61848, 61908, 61937, 61943, 62031, 62293, 62301,
        62322, 62438, 62579, 62693, 62703, 62876, 62877, 62889, 62937, 62966, 63030, 63108, 63175, 63370, 63411, 63461,
        63506, 63537, 63550, 64009, 64132, 64147, 64446, 64499, 64531, 64665, 64827, 65367, 65431, 65471, 65515, 65640,
        65651, 65722, 65785, 65930, 65935, 65992, 66095, 66161, 66171, 66223, 66259, 66266, 66374, 66416, 66681, 66915,
        66966, 66980, 67133, 67176, 67377, 67593, 67615, 67999, 68162, 68247, 68318, 68358, 68432, 68478, 68519, 68524,
        68553, 68591, 68614, 68844, 68968, 69077, 69106, 69109, 69272, 69384, 69441, 69682, 69822, 69825, 70179, 70240,
        70337, 70500, 70510, 70577, 70579, 70652, 70675, 70754, 70811, 70829, 70854, 70960, 71159, 71539, 71634, 71773,
        71877, 72022, 72144, 72217, 72411, 72551, 72698, 72716, 72745, 72917, 72991, 73014, 73023, 73297, 73366, 73597,
        73873, 74060, 74097, 74269, 74707, 74751, 74764, 74933, 74944, 75022, 75261, 75388, 76084, 76089, 76186, 76358,
        77090, 77131, 77178, 77280, 77328, 77427, 77743, 77759, 77812, 77856, 78076, 78189, 78306, 78346, 78446, 78519,
        78692, 79195, 80788, 82862, 82897, 83253, 83391, 83420, 83642, 83699, 83733, 85652, 85731, 86014, 86100, 86312,
        86405, 86415, 86432, 86456, 86517, 86846, 86982, 86993, 87072, 87252, 87352, 87388, 87478, 87502, 88278, 88599,
        88765, 88863, 88912, 88953, 89069, 89259, 89301, 89307, 89329, 89377, 89633, 89851, 89863, 89864, 89918, 90035,
        91080, 91112, 91208, 91293, 91306, 91423, 91583, 91789, 91815, 92026, 92172, 92381, 92435, 92573, 92645, 92682,
        92822, 92883, 92896, 92912, 93163, 93295, 93327, 93520, 93918, 94093, 94374, 94421, 94433, 94624, 94668, 95134,
        98117, 98887, 99014, 99086, 99107, 99143, 99512, 99560, 99653, 99803, 99832, 100159, 100162, 100228, 100611, 100646,
        100733, 100753, 100818, 100858, 101117, 101121, 101156, 101186, 101196, 101224, 101317, 101441, 101489, 101533, 101733, 101770,
        101800, 101891, 102034, 102183, 102261, 102305, 102393, 102409, 102509, 102516, 102530, 102716, 102756, 102800, 102837, 102899,
        102926, 102955, 102965, 103199, 103222, 103465, 103468, 103611, 103621, 103738, 103746, 103832, 103864, 103874, 104436, 105964,
        106015, 106024, 106079, 106130, 106176, 106213, 106339, 106400, 106601, 106804, 106812, 106860, 106910, 107116, 107154, 107229,
        107332, 108041, 108657, 108689, 108700, 109024, 109101, 109138, 109355, 109844, 109887, 109949, 110024, 110197, 110267, 110296,
        110502, 110607, 110740, 110794, 113813, 113990, 113991, 114017, 114216, 115709, 121143, 121946, 121964, 122123, 122550, 123183,
        123189, 123566, 123571, 124221, 124938, 125031, 125175, 125235, 125370, 126047, 126100, 126595, 126954, 127501, 127549, 127586,
        127700, 127837, 128111, 128114, 128169, 128228, 128397, 128955, 129020, 129197, 129393, 129570, 129604, 129944, 130228, 130503,
        131065, 131202, 131277, 131343
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the source paper or matches the name without naming, using, extending or comparing against RLAIF'
FROM rlaif_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING rlaif_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING rlaif_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- constitutional-ai: 31 links, 1203 exclusions. S2 local citers reviewed: 1221.

CREATE TEMP TABLE constitutional_ai_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'constitutional-ai'
  AND p.id IN (
        12009, 17851, 22310, 22448, 27057, 27219, 28547, 30597, 30648, 32644, 35224, 37787, 40034, 42331, 43440, 45901,
        51333, 52546, 57758, 61642, 62053, 62322, 65471, 68531, 70704, 76186, 92883, 106052, 109101, 110488, 130694
  );

DELETE FROM paper_method_exclusions x
USING constitutional_ai_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM constitutional_ai_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM constitutional_ai_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


CREATE TEMP TABLE constitutional_ai_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'constitutional-ai'
  AND p.id IN (
        8822, 10196, 10705, 11378, 12551, 12709, 12766, 12874, 13122, 13181, 13281, 13438, 13557, 13825, 13926, 13991,
        14150, 14266, 14301, 14303, 14327, 14448, 14505, 14606, 14642, 14688, 14729, 14987, 15026, 15160, 15162, 15207,
        15238, 15312, 15417, 15500, 15548, 15577, 15650, 15669, 15743, 15788, 15834, 15858, 15919, 15939, 15990, 15992,
        16036, 16063, 16080, 16090, 16120, 16158, 16174, 16205, 16267, 16330, 16337, 16379, 16415, 16499, 16739, 16751,
        16869, 16901, 16921, 16967, 17019, 17056, 17108, 17121, 17214, 17223, 17362, 17506, 17624, 17673, 17705, 17825,
        17901, 17909, 17920, 17940, 17971, 18034, 18055, 18088, 18128, 18144, 18187, 18201, 18334, 18369, 18379, 18470,
        18588, 18613, 18625, 18666, 18711, 18727, 18776, 18801, 18862, 18895, 18972, 18996, 19018, 19164, 19169, 19174,
        19223, 19240, 19420, 19523, 19567, 19660, 19680, 19687, 19854, 19876, 19912, 19930, 20009, 20018, 20025, 20026,
        20028, 20130, 20141, 20170, 20299, 20377, 20403, 20428, 20484, 20488, 20562, 20589, 20591, 20598, 20670, 20673,
        20722, 20777, 20813, 20848, 20861, 20911, 20933, 20987, 21000, 21008, 21015, 21039, 21082, 21103, 21104, 21132,
        21172, 21244, 21261, 21298, 21306, 21336, 21351, 21357, 21360, 21378, 21462, 21544, 21590, 21596, 21620, 21663,
        21697, 21707, 21712, 21734, 21751, 21753, 21778, 21882, 21883, 21892, 21937, 21982, 22016, 22017, 22037, 22043,
        22045, 22046, 22133, 22148, 22227, 22244, 22249, 22288, 22321, 22417, 22503, 22517, 22628, 22711, 22816, 22839,
        22876, 22890, 22937, 23041, 23054, 23161, 23209, 23258, 23264, 23265, 23300, 23325, 23333, 23408, 23427, 23554,
        23562, 23632, 23706, 23723, 23725, 23735, 23828, 23897, 24041, 24047, 24068, 24148, 24207, 24248, 24655, 24681,
        24818, 24824, 24895, 24910, 24931, 25071, 25090, 25107, 25133, 25175, 25370, 25414, 25458, 25582, 25613, 25616,
        25622, 25638, 25645, 25684, 25737, 25776, 25781, 25807, 25881, 25955, 25992, 26058, 26091, 26129, 26141, 26157,
        26195, 26210, 26258, 26495, 26541, 26579, 26589, 26705, 26729, 26732, 26764, 26843, 26853, 26881, 26921, 26933,
        26985, 26990, 27006, 27020, 27103, 27115, 27121, 27173, 27174, 27191, 27201, 27239, 27246, 27273, 27282, 27287,
        27349, 27372, 27379, 27381, 27394, 27420, 27443, 27453, 27474, 27483, 27501, 27545, 27549, 27625, 27637, 27673,
        27763, 27799, 27841, 27915, 28049, 28136, 28156, 28159, 28186, 28219, 28446, 28456, 28500, 28523, 28536, 28730,
        28749, 28775, 28784, 28792, 28797, 28800, 28821, 28861, 28884, 28948, 28982, 29061, 29127, 29148, 29209, 29362,
        29557, 29583, 29589, 29597, 29598, 29707, 29711, 29783, 29902, 29950, 29970, 29980, 29996, 30013, 30054, 30114,
        30123, 30212, 30238, 30285, 30400, 30434, 30499, 30523, 30627, 30637, 30654, 30697, 30869, 30906, 30968, 31017,
        31020, 31131, 31251, 31277, 31284, 31463, 31470, 31487, 31489, 31525, 31547, 31554, 31704, 31779, 31793, 31899,
        31956, 31978, 31991, 31998, 32049, 32073, 32086, 32187, 32202, 32250, 32271, 32332, 32439, 32441, 32468, 32482,
        32488, 32561, 32585, 32605, 32617, 32688, 32690, 32749, 32782, 32810, 32861, 32872, 32960, 32998, 33050, 33067,
        33105, 33207, 33225, 33398, 33471, 33561, 33572, 33592, 33593, 33607, 33762, 33771, 33811, 33856, 33858, 33864,
        33872, 33883, 33914, 33930, 34061, 34082, 34116, 34205, 34217, 34363, 34378, 34499, 34543, 34548, 34647, 34654,
        34666, 34693, 34919, 34924, 34942, 34978, 34999, 35001, 35019, 35032, 35064, 35119, 35208, 35242, 35278, 35545,
        35560, 35755, 35819, 35883, 35961, 35972, 36090, 36091, 36271, 36287, 36288, 36291, 36303, 36384, 36433, 36480,
        36513, 36558, 36602, 36708, 36755, 36756, 36842, 36859, 37105, 37193, 37222, 37358, 37457, 37676, 37735, 37800,
        37848, 37884, 37897, 38021, 38036, 38060, 38125, 38158, 38159, 38170, 38196, 38250, 38286, 38316, 38323, 38325,
        38344, 38358, 38498, 38611, 38637, 38705, 38757, 38770, 38840, 38881, 38932, 38978, 38986, 38999, 39008, 39034,
        39042, 39056, 39059, 39085, 39227, 39417, 39428, 39500, 39580, 39626, 39670, 39765, 39773, 39834, 39968, 39979,
        39988, 40006, 40102, 40111, 40132, 40260, 40327, 40442, 40618, 40916, 40962, 41000, 41020, 41188, 41381, 41551,
        41689, 41987, 42049, 42200, 42489, 42490, 42510, 42647, 42692, 42862, 42885, 43070, 43118, 43374, 43398, 43478,
        43499, 43518, 43576, 43617, 43767, 43798, 43815, 43879, 44071, 44129, 44171, 44222, 44399, 44417, 44495, 44556,
        44568, 44598, 44603, 44615, 44830, 44862, 44876, 44891, 44945, 45043, 45099, 45182, 45231, 45234, 45427, 45450,
        45485, 45502, 45754, 45796, 45917, 45960, 45981, 46101, 46292, 46425, 46469, 46633, 46778, 46856, 46917, 46951,
        47056, 47062, 47071, 47134, 47179, 47227, 47372, 47401, 47470, 47491, 47804, 47899, 47940, 47947, 48024, 48099,
        48202, 48268, 48291, 48339, 48389, 48391, 48406, 48509, 48780, 48882, 48896, 49049, 49092, 49152, 49216, 49217,
        49262, 49300, 49371, 49464, 49513, 49574, 49767, 49873, 49894, 49968, 49976, 50197, 50277, 50462, 50530, 50586,
        50646, 50839, 50873, 51016, 51042, 51105, 51144, 51248, 51400, 51608, 51641, 51677, 51790, 51849, 51944, 51953,
        52064, 52328, 52404, 52509, 52663, 52666, 52722, 52901, 53020, 53038, 53143, 53175, 53218, 53232, 53236, 53246,
        53338, 53371, 53421, 53551, 53566, 53610, 53611, 53888, 53893, 54150, 54180, 54223, 54614, 54822, 54935, 55060,
        55198, 55219, 55298, 55335, 55366, 55536, 55542, 55554, 55636, 55798, 55804, 55817, 55830, 55831, 55832, 55929,
        56040, 56078, 56238, 56506, 56601, 56760, 56992, 57154, 57240, 57371, 57429, 57459, 57484, 57543, 57623, 57659,
        57706, 57984, 57988, 57993, 58026, 58033, 58035, 58085, 58137, 58233, 58235, 58338, 58420, 58430, 58435, 58437,
        58504, 58783, 58906, 59131, 59182, 59192, 59221, 59233, 59374, 59447, 59448, 59641, 59813, 59824, 60022, 60070,
        60332, 60366, 60373, 60426, 60606, 60611, 60643, 60794, 60854, 60875, 60881, 61082, 61096, 61103, 61121, 61143,
        61219, 61296, 61485, 61511, 61562, 61726, 61736, 61839, 61848, 61908, 61937, 61943, 62031, 62293, 62301, 62317,
        62438, 62579, 62693, 62703, 62876, 62877, 62889, 62937, 62966, 63030, 63108, 63175, 63370, 63411, 63461, 63506,
        63537, 63550, 64009, 64132, 64147, 64446, 64499, 64531, 64665, 64827, 65367, 65431, 65515, 65640, 65651, 65722,
        65785, 65930, 65935, 65992, 66095, 66161, 66171, 66223, 66259, 66266, 66374, 66416, 66681, 66915, 66966, 66980,
        67133, 67176, 67377, 67593, 67615, 67999, 68162, 68247, 68318, 68358, 68432, 68478, 68519, 68524, 68553, 68591,
        68614, 68844, 68968, 69077, 69106, 69109, 69272, 69384, 69441, 69682, 69822, 69825, 70179, 70240, 70337, 70500,
        70510, 70577, 70579, 70652, 70675, 70754, 70811, 70829, 70960, 71159, 71417, 71539, 71634, 71644, 71773, 71877,
        72022, 72144, 72217, 72411, 72551, 72698, 72716, 72745, 72917, 72991, 73014, 73023, 73297, 73366, 73597, 73873,
        74060, 74097, 74269, 74707, 74751, 74764, 74933, 74944, 75022, 75261, 75388, 76084, 76089, 76358, 77090, 77131,
        77178, 77280, 77328, 77427, 77743, 77759, 77812, 77856, 78076, 78189, 78306, 78346, 78446, 78519, 78692, 79195,
        80788, 82862, 82897, 83253, 83391, 83420, 83642, 83699, 83733, 85652, 85731, 86014, 86100, 86312, 86405, 86415,
        86432, 86456, 86517, 86846, 86982, 86993, 87072, 87252, 87352, 87388, 87478, 87502, 88278, 88599, 88765, 88863,
        88912, 88953, 89069, 89259, 89301, 89307, 89329, 89377, 89633, 89851, 89863, 89864, 89918, 90035, 91080, 91112,
        91208, 91293, 91306, 91423, 91583, 91789, 91815, 92026, 92172, 92381, 92435, 92573, 92645, 92682, 92822, 92896,
        92912, 93163, 93295, 93327, 93520, 93870, 93918, 94093, 94374, 94421, 94433, 94624, 94668, 95134, 98117, 98887,
        99014, 99086, 99107, 99143, 99512, 99560, 99653, 99803, 99832, 100159, 100162, 100228, 100611, 100646, 100733, 100753,
        100818, 100858, 101117, 101121, 101156, 101186, 101196, 101224, 101317, 101441, 101489, 101533, 101733, 101770, 101800, 101891,
        102034, 102183, 102261, 102305, 102393, 102409, 102509, 102516, 102530, 102716, 102756, 102800, 102837, 102899, 102926, 102955,
        102965, 103199, 103222, 103465, 103468, 103611, 103621, 103738, 103746, 103832, 103864, 103874, 104436, 105964, 106015, 106024,
        106079, 106130, 106176, 106213, 106339, 106400, 106601, 106804, 106812, 106860, 106910, 107116, 107154, 107229, 107332, 108041,
        108657, 108689, 108700, 109024, 109138, 109355, 109844, 109887, 109949, 110024, 110197, 110267, 110296, 110502, 110607, 110740,
        110794, 110975, 113813, 113990, 113991, 114017, 114216, 115709, 121143, 121946, 121964, 122123, 122550, 123183, 123189, 123566,
        123571, 124221, 124938, 125031, 125175, 125235, 125370, 126047, 126100, 126595, 126954, 127501, 127549, 127586, 127700, 127837,
        128111, 128114, 128169, 128228, 128397, 128955, 129020, 129197, 129285, 129393, 129570, 129604, 129944, 130228, 130503, 131065,
        131202, 131277, 131343
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the source paper or matches the name without naming, using, extending or comparing against Constitutional AI'
FROM constitutional_ai_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING constitutional_ai_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING constitutional_ai_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- kto: 32 links, 67 exclusions. S2 local citers reviewed: 70.

CREATE TEMP TABLE kto_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'kto'
  AND p.id IN (
        26650, 30014, 30031, 30367, 31787, 31893, 31991, 33777, 36006, 36564, 37676, 39653, 40228, 42985, 43188, 43634,
        49271, 53070, 53208, 56999, 57487, 61110, 64147, 65856, 70711, 71789, 74624, 75342, 89278, 91937, 103108, 103800
  );

DELETE FROM paper_method_exclusions x
USING kto_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM kto_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM kto_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


CREATE TEMP TABLE kto_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'kto'
  AND p.id IN (
        31759, 35833, 37404, 40006, 40919, 42862, 43127, 43512, 44662, 47020, 48041, 48791, 48896, 49283, 52093, 52917,
        52999, 53889, 55198, 57476, 58004, 58094, 59244, 59973, 61560, 67347, 71417, 72431, 73963, 82877, 84411, 86517,
        91653, 99350, 100766, 101121, 101250, 102756, 102939, 103129, 103223, 103282, 103549, 103653, 103657, 103864, 104742, 106398,
        107332, 107632, 108657, 109655, 114069, 114177, 123981, 125512, 125557, 125579, 125643, 127528, 127788, 127939, 128397, 129285,
        129591, 129892, 130441
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the source paper or matches the name without naming, using, extending or comparing against KTO'
FROM kto_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING kto_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING kto_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- orpo: 22 links, 275 exclusions. S2 local citers reviewed: 291.

CREATE TEMP TABLE orpo_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'orpo'
  AND p.id IN (
        28728, 31787, 33694, 33811, 34263, 36614, 36948, 41375, 43347, 43558, 44853, 46541, 51524, 58399, 60653, 67199,
        67409, 94378, 102287, 103653, 110245, 119688
  );

DELETE FROM paper_method_exclusions x
USING orpo_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM orpo_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM orpo_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


CREATE TEMP TABLE orpo_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'orpo'
  AND p.id IN (
        27026, 28456, 29184, 29711, 30413, 31019, 31217, 31427, 31509, 31611, 31766, 31893, 32468, 32631, 33028, 33067,
        33163, 33251, 33464, 33757, 34360, 34502, 34543, 34647, 34913, 34919, 35036, 35833, 35902, 36118, 36430, 36564,
        36579, 37163, 37223, 37356, 37358, 37373, 37840, 37898, 37966, 37996, 38028, 38164, 38250, 38379, 38480, 38500,
        38547, 38600, 38625, 38646, 38658, 38749, 38887, 38912, 39060, 39304, 39475, 39622, 39813, 39825, 39865, 40006,
        40051, 40180, 40228, 40245, 40327, 41102, 41600, 42303, 42556, 42578, 42699, 42745, 42791, 42827, 42922, 42933,
        43188, 43512, 43956, 44143, 44173, 44264, 44571, 44598, 44662, 44891, 45002, 45037, 45231, 45363, 45505, 45530,
        45791, 46589, 46633, 46682, 47205, 47259, 47360, 47437, 47637, 47696, 48041, 48396, 48540, 48791, 48882, 48887,
        48959, 49003, 49012, 49153, 49574, 49646, 50533, 51519, 52093, 52096, 52762, 52893, 52999, 53038, 53070, 53411,
        53679, 53889, 54060, 54653, 54877, 55198, 56192, 56431, 56604, 57417, 57476, 59244, 59743, 60992, 61320, 61582,
        61788, 61856, 63056, 63245, 63707, 63710, 64437, 64742, 64991, 65515, 65629, 65763, 65982, 66596, 66831, 67183,
        67347, 67512, 67566, 67615, 68382, 68786, 69034, 69069, 69156, 69490, 69779, 70077, 70128, 70428, 70711, 71257,
        71402, 71417, 71896, 71976, 71979, 72169, 72431, 72882, 72976, 73038, 73084, 73719, 74135, 74447, 75222, 75363,
        75815, 75965, 76133, 76918, 83130, 83244, 83532, 84105, 86471, 86592, 86763, 86929, 87040, 87075, 88158, 88599,
        88764, 88793, 89140, 89623, 90035, 91106, 91131, 91653, 91786, 91815, 92687, 92831, 92874, 92988, 93250, 93314,
        93856, 94148, 94441, 94510, 94526, 94641, 94871, 94975, 95040, 98329, 98887, 99143, 99560, 99710, 100307, 100379,
        100503, 101221, 101301, 101659, 101670, 102465, 102473, 102939, 103454, 103832, 106398, 106522, 107777, 108067, 108208, 108505,
        108657, 109955, 110217, 110794, 113754, 114177, 121992, 123289, 125361, 125643, 125713, 126416, 127510, 127549, 127788, 127939,
        128703, 129707, 131493
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the source paper or matches the name without naming, using, extending or comparing against ORPO'
FROM orpo_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING orpo_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING orpo_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- simpo: 26 links, 593 exclusions. S2 local citers reviewed: 613.

CREATE TEMP TABLE simpo_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'simpo'
  AND p.id IN (
        31611, 38187, 42578, 44853, 45791, 47437, 48041, 48511, 50270, 52093, 53852, 60755, 67512, 70095, 71257, 72485,
        75017, 89726, 91733, 93314, 94281, 100766, 110982, 129371, 131233, 131273
  );

DELETE FROM paper_method_exclusions x
USING simpo_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM simpo_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM simpo_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


CREATE TEMP TABLE simpo_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'simpo'
  AND p.id IN (
        19420, 26129, 28728, 29711, 30367, 30789, 30900, 30984, 31017, 31217, 31432, 31787, 31978, 32005, 32023, 32073,
        32202, 32259, 32413, 32468, 32497, 32605, 32631, 32703, 32782, 32809, 32829, 32930, 32968, 33039, 33067, 33105,
        33136, 33159, 33163, 33171, 33424, 33561, 33643, 33838, 34181, 34360, 34502, 34639, 34665, 34877, 34919, 34927,
        34972, 35007, 35019, 35036, 35092, 35603, 35721, 35755, 35833, 35854, 36118, 36289, 36303, 36376, 36384, 36564,
        36579, 36622, 36753, 36948, 36989, 37105, 37163, 37186, 37191, 37222, 37223, 37356, 37358, 37360, 37373, 37631,
        37733, 37800, 37840, 37911, 37929, 37966, 37996, 38028, 38158, 38179, 38250, 38316, 38379, 38444, 38449, 38480,
        38500, 38508, 38625, 38749, 38858, 38887, 38916, 39059, 39060, 39108, 39116, 39229, 39253, 39462, 39475, 39500,
        39533, 39569, 39579, 39626, 39834, 39915, 40006, 40180, 40327, 40903, 40919, 41020, 41102, 41124, 41230, 41749,
        41987, 42058, 42104, 42294, 42317, 42455, 42745, 42862, 42922, 42933, 42985, 43047, 43086, 43095, 43105, 43188,
        43237, 43398, 43420, 43423, 43513, 43558, 43683, 43879, 44161, 44162, 44173, 44239, 44264, 44356, 44497, 44571,
        44598, 44662, 44866, 44877, 44891, 44979, 45000, 45002, 45037, 45054, 45056, 45104, 45243, 45295, 45363, 45436,
        45505, 45529, 45530, 45537, 45569, 45755, 45916, 45925, 45975, 46168, 46352, 46463, 46489, 46523, 46711, 46956,
        47045, 47062, 47073, 47133, 47205, 47259, 47360, 47371, 47408, 47411, 47563, 47637, 47646, 47917, 48148, 48211,
        48288, 48336, 48389, 48396, 48406, 48432, 48474, 48540, 48648, 48774, 48791, 48831, 48870, 48882, 48887, 48899,
        48955, 48959, 49012, 49042, 49060, 49075, 49136, 49245, 49461, 49526, 49563, 49611, 49630, 49646, 49676, 49712,
        49758, 49771, 49809, 49876, 49906, 49975, 49993, 50064, 50157, 50183, 50277, 50379, 50417, 50495, 50533, 50721,
        50761, 50797, 50855, 50899, 51016, 51205, 51222, 51814, 51898, 51928, 51953, 52096, 52114, 52181, 52386, 52584,
        52613, 52658, 52810, 52917, 52993, 52999, 53038, 53042, 53044, 53070, 53071, 53081, 53105, 53287, 53374, 53551,
        54003, 54147, 54161, 54624, 54642, 54653, 54877, 54935, 55198, 55584, 55653, 55669, 55804, 55888, 55982, 56221,
        56223, 56399, 56431, 57417, 57431, 57528, 58004, 59115, 59244, 59279, 59448, 59623, 59824, 59891, 60002, 60367,
        60653, 61292, 61296, 61618, 61630, 61689, 61705, 61788, 61812, 62037, 62301, 62317, 62517, 62665, 62852, 63220,
        63245, 63313, 63486, 63707, 63710, 64437, 64817, 65629, 65693, 65763, 65856, 65934, 66002, 66449, 66805, 66831,
        66918, 67223, 67347, 68329, 68668, 68674, 68710, 68730, 68786, 69482, 69779, 69815, 70128, 70618, 70711, 70754,
        71330, 71402, 71478, 71533, 71976, 72082, 72169, 72204, 72252, 72264, 72606, 72785, 72882, 72976, 73038, 73084,
        73297, 73304, 73410, 73618, 73719, 73775, 73963, 74135, 74261, 74404, 74494, 74626, 75222, 75815, 75965, 82926,
        83424, 83532, 83961, 84105, 84411, 85742, 85777, 85789, 85900, 85956, 86071, 86312, 86313, 86517, 86592, 86627,
        86763, 86819, 86929, 87040, 87047, 87075, 87229, 87355, 87421, 88158, 88599, 88672, 88673, 88676, 88764, 88793,
        88804, 88806, 88837, 88877, 89092, 89140, 89232, 89278, 89307, 89623, 89631, 89639, 89672, 89711, 89787, 89864,
        89979, 90035, 90883, 91363, 91364, 91653, 91786, 91815, 91823, 91879, 91912, 92154, 92172, 92399, 92651, 92687,
        92728, 92874, 92903, 92905, 92912, 92982, 92988, 93148, 93190, 93483, 93488, 93802, 93839, 93856, 93920, 93945,
        94089, 94226, 94234, 94302, 94510, 94526, 94574, 94606, 94709, 94731, 94975, 95040, 96907, 98119, 98887, 99021,
        99324, 99350, 99425, 99560, 99710, 100088, 100162, 100307, 100379, 100458, 100503, 100890, 101205, 101221, 101249, 101250,
        101301, 101392, 101670, 101674, 101924, 102034, 102287, 102448, 102462, 102473, 102487, 102756, 102766, 102807, 102939, 103023,
        103129, 103213, 103282, 103439, 103538, 103832, 103864, 105989, 106302, 106398, 106938, 107539, 107632, 108040, 108046, 108505,
        108657, 108873, 109053, 109826, 109955, 110026, 110146, 110158, 110189, 110217, 110559, 111057, 113754, 114177, 114280, 119671,
        121992, 122250, 122452, 122626, 122724, 122886, 123364, 123684, 123829, 124486, 124537, 124642, 125512, 125557, 125643, 125713,
        125904, 125987, 126805, 127549, 127580, 127788, 127939, 128397, 128811, 128955, 129707, 130426, 130441, 131076, 131493, 131973,
        132043
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the source paper or matches the name without naming, using, extending or comparing against SimPO'
FROM simpo_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING simpo_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING simpo_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- ipo: 28 links, 540 exclusions. S2 local citers reviewed: 563.

CREATE TEMP TABLE ipo_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ipo'
  AND p.id IN (
        22172, 28792, 30367, 30984, 31697, 31787, 32138, 32259, 33144, 33777, 33790, 36006, 38547, 39569, 45925, 52093,
        53287, 67512, 75017, 76040, 77831, 89232, 89726, 89821, 100505, 102516, 127550, 131233
  );

DELETE FROM paper_method_exclusions x
USING ipo_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM ipo_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM ipo_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


CREATE TEMP TABLE ipo_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'ipo'
  AND p.id IN (
        20325, 21543, 22243, 22582, 23705, 24157, 24681, 24931, 25270, 25340, 25450, 25582, 25913, 26141, 26157, 26579,
        26585, 26589, 26601, 26650, 26715, 26729, 26769, 26809, 26985, 27001, 27026, 27174, 27246, 27353, 27417, 27451,
        27483, 27545, 27687, 27828, 27846, 28159, 28235, 28303, 28390, 28413, 28456, 28701, 28728, 28730, 28797, 28861,
        28948, 29061, 29449, 29540, 29557, 29711, 29970, 30027, 30031, 30413, 30449, 30527, 30534, 30569, 30648, 30651,
        30681, 30784, 30789, 30900, 30966, 30968, 31017, 31019, 31217, 31251, 31284, 31319, 31421, 31554, 31611, 31669,
        31704, 31759, 31766, 31836, 31893, 31991, 31998, 32005, 32009, 32023, 32025, 32037, 32049, 32086, 32109, 32198,
        32202, 32240, 32346, 32413, 32580, 32631, 32668, 32703, 32746, 32803, 32809, 32810, 32826, 32861, 32873, 32930,
        32998, 33039, 33067, 33105, 33140, 33163, 33171, 33213, 33251, 33288, 33572, 33597, 33643, 33838, 33906, 33914,
        34054, 34062, 34181, 34287, 34310, 34447, 34502, 34543, 34574, 34639, 34642, 34647, 34927, 34972, 35019, 35036,
        35092, 35357, 35755, 35833, 35991, 36090, 36295, 36564, 36579, 36758, 37105, 37223, 37233, 37337, 37356, 37358,
        37373, 37733, 37797, 37803, 37840, 37848, 37898, 37911, 37936, 37966, 37996, 38028, 38113, 38164, 38187, 38250,
        38316, 38345, 38351, 38358, 38379, 38480, 38500, 38625, 38637, 38749, 38857, 38887, 38916, 38999, 39059, 39227,
        39253, 39304, 39398, 39622, 39913, 40006, 40051, 40111, 40180, 40228, 40618, 40725, 40774, 40912, 40919, 41102,
        41188, 41551, 41947, 42104, 42248, 42294, 42303, 42510, 42578, 42791, 42933, 42985, 43026, 43105, 43556, 43558,
        43570, 43634, 43753, 43842, 43858, 44173, 44356, 44471, 44497, 44528, 44598, 44662, 44877, 44879, 44891, 45002,
        45037, 45039, 45056, 45078, 45104, 45243, 45295, 45406, 45436, 45755, 45791, 45862, 45917, 46228, 46323, 46523,
        46633, 46671, 46956, 47045, 47056, 47205, 47563, 47637, 47860, 47863, 48041, 48078, 48139, 48366, 48389, 48393,
        48432, 48540, 48791, 48831, 48882, 48955, 48959, 48992, 49003, 49102, 49283, 49328, 49500, 49526, 49566, 49574,
        49646, 49767, 49771, 49876, 50027, 50168, 50270, 50423, 50468, 50533, 50721, 51537, 51953, 52134, 52386, 52469,
        52854, 52890, 52893, 52978, 52999, 53026, 53038, 53044, 53070, 53679, 53848, 54653, 54877, 55669, 55804, 56133,
        56431, 57295, 57417, 58094, 59169, 59406, 59824, 59891, 59973, 60347, 61296, 61359, 61472, 61618, 61705, 61788,
        62030, 62053, 62937, 63245, 63300, 63369, 63561, 64374, 65856, 65974, 66002, 66113, 66449, 66830, 67183, 67223,
        67347, 68786, 69836, 70128, 71257, 71417, 71644, 71976, 71978, 71979, 72082, 72169, 72264, 72431, 72681, 72976,
        73038, 73084, 73297, 73688, 73719, 73873, 73926, 74135, 74261, 74494, 74624, 75815, 75965, 75982, 76725, 76815,
        76918, 77497, 82877, 83130, 83270, 83532, 84411, 85777, 85900, 86095, 86312, 86313, 86404, 86517, 86592, 86627,
        86763, 86819, 86831, 86929, 87040, 87047, 87073, 87229, 87352, 87355, 87421, 87478, 88158, 88599, 88673, 88676,
        88699, 88793, 88837, 88942, 89087, 89140, 89278, 89301, 89307, 89339, 89393, 89556, 89672, 89724, 89795, 89864,
        90870, 91080, 91297, 91336, 91364, 91653, 91699, 91786, 91815, 91843, 91865, 91932, 92075, 92154, 92334, 92399,
        92682, 92687, 92696, 92838, 92903, 92905, 92988, 93190, 93314, 93488, 93517, 93802, 93856, 94302, 94378, 94404,
        94441, 94510, 94535, 94731, 94975, 95040, 98014, 98887, 99226, 99324, 99350, 99425, 99523, 100379, 100503, 100540,
        100607, 100758, 100766, 100890, 101111, 101163, 101221, 101249, 101540, 101975, 102287, 102462, 102465, 102473, 103023, 103082,
        103584, 103640, 103864, 104527, 106230, 106938, 107229, 107632, 107777, 108448, 108657, 109955, 110026, 110142, 110146, 110217,
        110350, 110794, 110862, 114069, 119671, 121992, 122250, 122305, 122361, 123364, 123981, 124642, 125512, 125557, 125713, 126805,
        127510, 127549, 127788, 127939, 128112, 128397, 129285, 129707, 130426, 130505, 131167, 131973
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the source paper or matches the name without naming, using, extending or comparing against Identity Preference Optimization'
FROM ipo_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING ipo_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING ipo_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- beam-search: 210 links, 0 exclusions.

CREATE TEMP TABLE beam_search_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'beam-search'
  AND p.id IN (
        172, 417, 464, 480, 685, 1227, 1278, 1332, 1654, 2217, 3309, 3584, 3604, 3647, 3869, 4275,
        4814, 5293, 5868, 6047, 6258, 6282, 6702, 6885, 7499, 7538, 7948, 8288, 8493, 8675, 8906, 8980,
        9066, 9921, 10175, 10205, 10421, 10492, 10513, 10625, 11093, 11100, 11342, 11366, 11384, 11427, 11804, 12457,
        13621, 14236, 15090, 15263, 16007, 16136, 16460, 16680, 16989, 18258, 20275, 21350, 22870, 23971, 23985, 24506,
        25764, 25857, 26522, 27148, 27157, 27334, 27748, 27773, 27915, 28237, 28896, 29544, 29833, 30521, 30534, 31091,
        31667, 33346, 33779, 35649, 36357, 36363, 38590, 39160, 39670, 39837, 40050, 40510, 41293, 41896, 43012, 43709,
        44002, 44253, 44540, 45013, 45137, 46791, 47066, 47221, 48888, 49583, 49710, 50716, 52193, 53221, 53680, 53895,
        53941, 56039, 56581, 57397, 57557, 57713, 59128, 59973, 60619, 61835, 62427, 64681, 65389, 66005, 66247, 66449,
        66910, 69577, 69729, 69910, 72099, 72703, 72912, 73336, 74087, 75022, 77231, 78199, 78345, 78803, 79046, 79119,
        79668, 80885, 80894, 81591, 82227, 82228, 82277, 83284, 83560, 86758, 86787, 87007, 88298, 91477, 92050, 93794,
        93827, 94012, 94667, 97572, 98661, 98989, 99498, 100016, 100558, 100773, 100841, 101575, 103133, 104719, 105602, 106097,
        106939, 109186, 109465, 110014, 110060, 110120, 110287, 110398, 110486, 110847, 110976, 111131, 111243, 111244, 111245, 111247,
        113558, 119127, 124168, 125375, 125400, 126309, 126525, 126994, 127547, 127635, 127876, 128562, 128788, 128838, 130265, 130312,
        131033, 131573
  );

DELETE FROM paper_method_exclusions x
USING beam_search_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM beam_search_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM beam_search_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


-- nucleus-sampling: 49 links, 1277 exclusions. S2 local citers reviewed: 1319.

CREATE TEMP TABLE nucleus_sampling_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'nucleus-sampling'
  AND p.id IN (
        2030, 3951, 5827, 6282, 7837, 9066, 10513, 11088, 11091, 11100, 11342, 15870, 16460, 16838, 20529, 21281,
        22571, 28167, 29553, 29833, 31941, 32539, 33937, 37504, 41056, 42016, 43681, 44051, 46900, 51668, 53957, 56226,
        68596, 68810, 76525, 77600, 78449, 81591, 83870, 88690, 91954, 94306, 99498, 100841, 103038, 106260, 108356, 127092,
        131426
  );

DELETE FROM paper_method_exclusions x
USING nucleus_sampling_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM nucleus_sampling_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM nucleus_sampling_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


CREATE TEMP TABLE nucleus_sampling_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'nucleus-sampling'
  AND p.id IN (
        2111, 2159, 2340, 2455, 2540, 2650, 2651, 2810, 2854, 2899, 3035, 3060, 3141, 3175, 3179, 3214,
        3259, 3320, 3385, 3405, 3421, 3434, 3437, 3445, 3493, 3506, 3507, 3512, 3545, 3604, 3634, 3667,
        4003, 4007, 4096, 4099, 4141, 4151, 4201, 4209, 4226, 4275, 4287, 4288, 4290, 4315, 4335, 4345,
        4346, 4383, 4386, 4418, 4485, 4645, 4738, 4756, 4764, 4769, 4812, 4814, 4815, 4846, 4885, 4956,
        4974, 5010, 5057, 5205, 5258, 5263, 5469, 5486, 5523, 5656, 5661, 5747, 5755, 5838, 5851, 5863,
        5879, 5946, 5975, 6009, 6052, 6118, 6125, 6200, 6498, 6524, 6545, 6574, 6588, 6595, 6611, 6624,
        6632, 6642, 6646, 6650, 6681, 6702, 6786, 6861, 6877, 6887, 6929, 6939, 6950, 6961, 6972, 6973,
        6979, 7142, 7238, 7283, 7291, 7499, 7536, 7538, 7555, 7695, 7707, 7722, 7794, 7819, 7848, 7892,
        7898, 7906, 7908, 7909, 7916, 7926, 7948, 7982, 8046, 8070, 8074, 8244, 8266, 8298, 8306, 8315,
        8318, 8369, 8400, 8418, 8592, 8602, 8617, 8646, 8691, 8728, 8729, 8751, 8787, 8811, 8819, 8879,
        8883, 8890, 8906, 8907, 8943, 8949, 9008, 9021, 9025, 9142, 9178, 9222, 9234, 9242, 9370, 9411,
        9645, 9742, 9775, 9798, 9879, 9890, 9930, 9984, 10029, 10070, 10129, 10159, 10245, 10278, 10280, 10322,
        10365, 10367, 10378, 10385, 10421, 10445, 10482, 10492, 10518, 10551, 10602, 10667, 10795, 10803, 10821, 10835,
        10855, 10963, 10975, 10997, 11000, 11034, 11038, 11056, 11081, 11128, 11133, 11144, 11193, 11263, 11270, 11381,
        11414, 11436, 11474, 11692, 11705, 11768, 11804, 11877, 11894, 12025, 12034, 12055, 12057, 12070, 12083, 12138,
        12139, 12153, 12163, 12179, 12193, 12205, 12213, 12257, 12269, 12339, 12457, 12458, 12492, 12521, 12600, 12717,
        12721, 12756, 12766, 12927, 12933, 12952, 12970, 13032, 13034, 13081, 13146, 13159, 13276, 13291, 13296, 13343,
        13421, 13539, 13710, 13724, 13765, 13902, 13946, 13991, 14062, 14115, 14231, 14266, 14296, 14330, 14349, 14476,
        14615, 14617, 14620, 14687, 14688, 14746, 14769, 14904, 14993, 15003, 15009, 15020, 15028, 15090, 15124, 15149,
        15162, 15211, 15238, 15312, 15400, 15416, 15453, 15469, 15502, 15507, 15608, 15640, 15670, 15734, 15743, 15763,
        15839, 15871, 15883, 15953, 15956, 15957, 15959, 15960, 15990, 16027, 16051, 16052, 16059, 16063, 16107, 16108,
        16127, 16155, 16198, 16200, 16201, 16250, 16284, 16347, 16378, 16407, 16421, 16651, 16736, 16818, 16901, 16942,
        17021, 17117, 17186, 17189, 17201, 17241, 17296, 17317, 17421, 17424, 17561, 17584, 17705, 17794, 17892, 17908,
        17915, 17920, 17932, 18035, 18042, 18121, 18144, 18171, 18211, 18221, 18369, 18524, 18626, 18734, 18808, 18816,
        18863, 18897, 18922, 19071, 19073, 19164, 19178, 19252, 19257, 19318, 19396, 19535, 19656, 19717, 19736, 19748,
        19753, 19792, 19914, 20016, 20053, 20138, 20355, 20408, 20456, 20520, 20543, 20547, 20676, 20688, 20709, 20714,
        20934, 20974, 21015, 21022, 21033, 21036, 21069, 21074, 21143, 21144, 21184, 21208, 21214, 21258, 21299, 21351,
        21420, 21468, 21505, 21537, 21544, 21618, 21654, 21706, 21714, 21753, 21796, 21804, 21827, 21857, 21920, 21942,
        21954, 21971, 21985, 21997, 22013, 22060, 22101, 22108, 22111, 22120, 22165, 22184, 22221, 22233, 22256, 22273,
        22300, 22361, 22380, 22382, 22403, 22407, 22420, 22439, 22460, 22467, 22476, 22481, 22502, 22531, 22623, 22627,
        22711, 22712, 22750, 22831, 22837, 22849, 23006, 23105, 23120, 23149, 23221, 23224, 23264, 23272, 23289, 23295,
        23359, 23372, 23381, 23450, 23554, 23639, 23683, 23891, 23897, 23948, 23985, 23999, 24037, 24041, 24095, 24166,
        24176, 24226, 24234, 24345, 24365, 24370, 24439, 24453, 24461, 24487, 24506, 24561, 24577, 24580, 24625, 24735,
        24741, 24877, 24892, 24943, 24951, 25022, 25121, 25165, 25250, 25278, 25285, 25341, 25366, 25412, 25442, 25446,
        25451, 25491, 25619, 25645, 25649, 25713, 25723, 25748, 25764, 25807, 25810, 25852, 25857, 26031, 26043, 26051,
        26076, 26247, 26248, 26287, 26403, 26502, 26522, 26541, 26558, 26640, 26668, 26673, 26685, 26733, 26853, 27061,
        27103, 27151, 27152, 27156, 27203, 27209, 27300, 27383, 27452, 27482, 27502, 27525, 27608, 27670, 27703, 27769,
        27771, 27795, 27822, 27857, 27860, 27979, 28068, 28082, 28085, 28143, 28264, 28270, 28273, 28341, 28362, 28363,
        28372, 28377, 28412, 28456, 28483, 28609, 28631, 28750, 28780, 28794, 28879, 28938, 28940, 28985, 29065, 29153,
        29227, 29236, 29242, 29357, 29438, 29509, 29558, 29684, 29735, 29758, 29847, 29862, 29890, 29920, 30124, 30270,
        30337, 30396, 30438, 30560, 30675, 30789, 30830, 30895, 30941, 30970, 31024, 31064, 31212, 31317, 31349, 31518,
        31597, 31611, 31618, 31699, 31829, 31883, 31968, 32109, 32187, 32269, 32283, 32312, 32446, 32457, 32466, 32501,
        32536, 32561, 32665, 32729, 33020, 33099, 33131, 33144, 33223, 33230, 33271, 33291, 33310, 33380, 33501, 33549,
        33572, 33607, 33662, 33669, 33685, 33713, 33899, 33945, 33971, 34023, 34210, 34280, 34311, 34315, 34417, 34535,
        34639, 34642, 34698, 34771, 34871, 34986, 35032, 35119, 35143, 35192, 35358, 35378, 35438, 35565, 35567, 35672,
        35680, 35916, 35926, 36093, 36213, 36319, 36441, 36547, 36579, 36624, 36675, 36753, 36764, 36776, 36788, 36791,
        37068, 37095, 37323, 37329, 37587, 37656, 37664, 37665, 37712, 37721, 37744, 37823, 37824, 37918, 37967, 38036,
        38038, 38091, 38111, 38255, 38346, 38452, 38520, 38686, 38857, 38872, 38934, 38980, 38987, 39017, 39054, 39095,
        39098, 39356, 39415, 39506, 39580, 39738, 39837, 39885, 39913, 39950, 40111, 40199, 40257, 40661, 40852, 41261,
        41298, 41538, 42444, 42457, 42487, 42584, 42863, 42985, 43086, 43148, 43299, 43360, 43398, 43474, 43478, 43578,
        43596, 43635, 43667, 43890, 43955, 43969, 43982, 44002, 44027, 44117, 44162, 44190, 44239, 44270, 44281, 44297,
        44593, 44613, 44632, 44774, 44842, 44939, 44960, 45050, 45151, 45248, 45649, 45831, 46200, 46541, 46791, 47184,
        47368, 47591, 47637, 47786, 47787, 47845, 47910, 47928, 48147, 48203, 48249, 48324, 48363, 48559, 48763, 48771,
        48831, 48894, 48896, 49013, 49034, 49042, 49086, 49109, 49177, 49235, 49251, 49262, 49453, 49506, 49537, 49705,
        49724, 49752, 50042, 50056, 50059, 50190, 50267, 50274, 50294, 50371, 50698, 50725, 50776, 50790, 50918, 50980,
        51031, 51034, 51130, 51162, 51255, 51327, 51335, 51348, 51440, 51466, 51476, 51854, 51858, 51898, 52177, 52383,
        53013, 53116, 53151, 53284, 53351, 53572, 53587, 53588, 53789, 54141, 54144, 54262, 54589, 54711, 54811, 54845,
        54916, 55037, 55085, 55136, 55273, 55290, 55305, 55400, 55800, 55959, 56065, 56260, 56283, 56298, 56318, 56370,
        56427, 56480, 56798, 56962, 57152, 57154, 57302, 57374, 57399, 57477, 57560, 57655, 57789, 58159, 58164, 58172,
        59128, 59235, 59594, 59908, 60003, 60358, 60708, 60735, 60821, 60822, 60852, 60878, 60882, 61079, 61145, 61326,
        61359, 61440, 61470, 61696, 61825, 62165, 62319, 62732, 62734, 62746, 62885, 62926, 63122, 63251, 63431, 63698,
        63726, 63923, 63985, 64079, 64184, 64196, 64311, 64476, 64510, 65314, 65364, 65407, 65722, 65920, 65934, 66005,
        66069, 66134, 66135, 66281, 66388, 66446, 66479, 67073, 67207, 67256, 67388, 67405, 67496, 67587, 67754, 68137,
        68306, 68883, 69488, 69507, 69561, 69998, 70198, 70300, 70352, 70361, 70754, 70767, 70957, 71141, 71293, 71364,
        71374, 71453, 71463, 72099, 72158, 72189, 72195, 72203, 72504, 72753, 72785, 73261, 73527, 73627, 73807, 74174,
        74269, 74344, 74356, 74360, 74516, 74692, 74859, 75052, 75381, 76869, 76889, 76952, 77080, 77178, 77179, 77439,
        77887, 78345, 78681, 78862, 78926, 79032, 79073, 79116, 79119, 79393, 79651, 79668, 79915, 80095, 80109, 80327,
        80389, 80487, 80515, 80774, 81046, 83142, 83963, 84491, 85163, 85592, 85640, 86317, 86413, 86639, 86758, 86897,
        86920, 87012, 87132, 87151, 88841, 88870, 88953, 89084, 89216, 89265, 89309, 89329, 89377, 89623, 89832, 90009,
        90084, 90442, 91005, 91080, 91263, 91490, 91593, 91850, 92065, 92203, 92600, 92613, 92635, 92739, 92754, 92765,
        92855, 92974, 93349, 93391, 93482, 93620, 93738, 93794, 94002, 94012, 94024, 94177, 94198, 94255, 94333, 94338,
        94808, 95675, 98510, 98704, 99073, 99611, 100234, 100251, 100259, 100298, 100724, 100839, 100860, 100864, 100899, 101043,
        101067, 101131, 101159, 101383, 101452, 101493, 101636, 101730, 101885, 102029, 102084, 102179, 102195, 102221, 102255, 102258,
        102281, 102287, 102465, 102530, 102731, 102797, 102825, 102904, 102943, 103015, 103029, 103086, 103173, 103241, 103417, 103442,
        103448, 103458, 103526, 103581, 103717, 103769, 104010, 104875, 106111, 106192, 106224, 106261, 106803, 107086, 107123, 107234,
        107333, 107537, 107668, 107739, 108411, 109119, 109549, 109581, 109676, 109702, 110015, 110154, 110161, 110171, 110326, 110333,
        110372, 110403, 110474, 110480, 110611, 110693, 110752, 110930, 111001, 111019, 111070, 111091, 113378, 115600, 115779, 116413,
        116741, 117199, 117393, 118533, 118946, 120373, 120619, 122174, 122408, 122599, 122737, 122965, 123055, 123218, 123222, 123268,
        123283, 124991, 125405, 126405, 127641, 127695, 128374, 128394, 128562, 128846, 129036, 129241, 129568, 129748, 129881, 130156,
        130242, 130556, 130804, 131269, 131313, 132004, 132018, 132019, 132023, 132036, 132047, 132053, 132066
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the source paper or matches the name without naming, using, extending or comparing against Nucleus Sampling'
FROM nucleus_sampling_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING nucleus_sampling_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING nucleus_sampling_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- contrastive-decoding: 94 links, 248 exclusions. S2 local citers reviewed: 308.

CREATE TEMP TABLE contrastive_decoding_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'contrastive-decoding'
  AND p.id IN (
        9066, 11088, 15149, 20138, 20529, 23359, 23891, 25191, 25701, 27855, 28576, 29556, 32269, 33230, 33346, 33592,
        34453, 35477, 35680, 35904, 36064, 36213, 36608, 36710, 36732, 37678, 37889, 38914, 41724, 42746, 44368, 46643,
        47786, 50133, 51436, 51697, 53274, 53430, 53903, 55273, 55590, 57714, 58187, 60524, 63105, 65113, 65367, 66121,
        66214, 66388, 68919, 71922, 73618, 74030, 74035, 74788, 74808, 76679, 84341, 84504, 84631, 84799, 85217, 86040,
        86065, 86323, 88476, 89728, 90883, 92065, 92728, 93968, 100129, 101173, 101670, 103241, 103564, 103581, 106393, 106880,
        108235, 110136, 110233, 110883, 111021, 120709, 121175, 121224, 121290, 122156, 122617, 123283, 128043, 128085
  );

DELETE FROM paper_method_exclusions x
USING contrastive_decoding_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM contrastive_decoding_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM contrastive_decoding_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();


CREATE TEMP TABLE contrastive_decoding_excluded ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'contrastive-decoding'
  AND p.id IN (
        11804, 12241, 12257, 12721, 13034, 15484, 15870, 15953, 16127, 16200, 16378, 17117, 17920, 18211, 19257, 20197,
        20271, 20369, 20963, 20974, 21126, 21141, 21208, 21281, 21414, 21505, 21664, 21799, 21954, 22097, 22233, 22361,
        22837, 23120, 23215, 23450, 24188, 25121, 25207, 25829, 25877, 26091, 26127, 26495, 26685, 26809, 27151, 27300,
        27320, 27383, 27603, 28094, 28107, 28128, 28237, 28435, 28480, 28780, 29227, 29583, 30105, 30244, 30337, 30903,
        31259, 31577, 31590, 31699, 31710, 31775, 31886, 32283, 32305, 32446, 32822, 33271, 33494, 33526, 33572, 33607,
        33662, 33738, 33937, 34315, 34503, 34978, 35243, 35926, 35930, 36755, 36776, 37432, 37551, 37882, 37959, 37979,
        38404, 38522, 38555, 38837, 39137, 39626, 39961, 40111, 40725, 40919, 41985, 42106, 42278, 42398, 42952, 43234,
        43360, 43593, 43723, 45080, 45176, 46003, 46114, 46433, 46722, 47284, 47845, 47866, 48363, 48777, 49286, 49377,
        49908, 50278, 50931, 51939, 53572, 53588, 53909, 53957, 54153, 55051, 55072, 55160, 55305, 56318, 56349, 56434,
        57789, 58041, 58186, 58269, 59705, 59891, 60140, 60205, 60882, 61470, 62515, 63698, 64184, 64191, 65549, 66455,
        67586, 68137, 68380, 68883, 69441, 69683, 69699, 70290, 71374, 72174, 72504, 72818, 72855, 74174, 74614, 76025,
        76342, 76358, 79032, 79217, 83463, 84056, 84095, 84499, 85392, 85785, 86057, 86592, 86797, 87519, 89142, 89329,
        90515, 90828, 91759, 91912, 92635, 92855, 92931, 93177, 97997, 98705, 98887, 99189, 99707, 99973, 100009, 101452,
        102255, 102465, 102809, 103092, 103467, 103666, 103690, 103804, 104513, 105950, 107234, 109702, 110047, 110084, 110161, 110199,
        110334, 110605, 110752, 111066, 113317, 113378, 113560, 114210, 119671, 120668, 122626, 123046, 124187, 127419, 128394, 129084,
        129241, 129568, 129604, 130046, 130882, 131269, 131679, 132022
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id,
       'Method gap fill 2026-11-10: cites the source paper or matches the name without naming, using, extending or comparing against Contrastive Decoding'
FROM contrastive_decoding_excluded
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING contrastive_decoding_excluded x
WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id;

DELETE FROM paper_methods pm
USING contrastive_decoding_excluded x
WHERE pm.paper_id = x.paper_id AND pm.method_id = x.method_id;


-- supervised-fine-tuning-sft: 1950 links, 0 exclusions.

CREATE TEMP TABLE supervised_fine_tuning_sft_curated ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'supervised-fine-tuning-sft'
  AND p.id IN (
        6547, 7670, 8991, 9183, 9600, 10365, 10639, 10933, 11038, 11084, 11210, 11397, 12083, 12093, 12124, 12157,
        12170, 12199, 12225, 12709, 12725, 12902, 12999, 13160, 13177, 13386, 13541, 13585, 14150, 14445, 14450, 14505,
        14627, 14733, 14734, 14737, 14746, 14748, 14752, 14820, 14991, 15015, 15020, 15031, 15035, 15103, 15157, 15233,
        15279, 15315, 15336, 15383, 15417, 15444, 15473, 15518, 15603, 15635, 15659, 15666, 15717, 15730, 15743, 15764,
        15802, 15804, 15809, 15830, 15888, 15898, 15948, 15964, 15969, 15997, 16027, 16047, 16069, 16120, 16122, 16143,
        16158, 16186, 16191, 16203, 16209, 16223, 16263, 16284, 16300, 16479, 16503, 16751, 16767, 16791, 16806, 16953,
        16967, 17019, 17102, 17127, 17128, 17152, 17188, 17193, 17200, 17273, 17388, 17422, 17433, 17463, 17478, 17543,
        17558, 17592, 17610, 17664, 17676, 17721, 17766, 17777, 17782, 17894, 17901, 17934, 17966, 17971, 18038, 18083,
        18095, 18108, 18152, 18169, 18284, 18329, 18334, 18380, 18443, 18639, 18674, 18704, 18743, 18763, 18802, 18810,
        18819, 18859, 18873, 18874, 18979, 19018, 19055, 19087, 19169, 19172, 19188, 19190, 19227, 19370, 19506, 19541,
        19543, 19567, 19598, 19660, 19682, 19691, 19700, 19733, 19736, 19737, 19756, 19766, 19793, 19794, 19840, 19851,
        19945, 19981, 19993, 20123, 20138, 20171, 20173, 20195, 20206, 20207, 20212, 20216, 20233, 20284, 20285, 20286,
        20292, 20299, 20377, 20428, 20445, 20523, 20574, 20583, 20625, 20627, 20656, 20682, 20752, 20759, 20807, 20893,
        20902, 20906, 20911, 20971, 20974, 20998, 21018, 21020, 21109, 21126, 21149, 21160, 21165, 21168, 21172, 21173,
        21181, 21183, 21187, 21193, 21212, 21224, 21228, 21239, 21255, 21261, 21360, 21365, 21398, 21427, 21458, 21475,
        21492, 21542, 21549, 21569, 21582, 21589, 21641, 21664, 21723, 21724, 21729, 21740, 21757, 21762, 21813, 21816,
        21859, 21892, 21930, 21959, 21980, 22018, 22028, 22029, 22088, 22099, 22108, 22115, 22128, 22148, 22178, 22181,
        22221, 22222, 22249, 22273, 22281, 22321, 22330, 22331, 22363, 22364, 22430, 22439, 22451, 22477, 22495, 22497,
        22507, 22536, 22642, 22644, 22650, 22672, 22730, 22761, 22786, 22788, 22804, 22816, 22835, 22837, 22844, 22876,
        22941, 22966, 23124, 23157, 23167, 23202, 23221, 23253, 23254, 23291, 23292, 23294, 23318, 23340, 23343, 23374,
        23385, 23408, 23430, 23461, 23483, 23492, 23497, 23510, 23530, 23600, 23627, 23646, 23654, 23656, 23735, 23842,
        23897, 23899, 23929, 23951, 23993, 24037, 24047, 24052, 24055, 24110, 24112, 24119, 24122, 24162, 24167, 24195,
        24200, 24202, 24216, 24221, 24275, 24283, 24331, 24400, 24479, 24519, 24622, 24633, 24636, 24638, 24695, 24699,
        24741, 24754, 24813, 24851, 24876, 24941, 24987, 24993, 24998, 25022, 25054, 25071, 25088, 25106, 25127, 25131,
        25175, 25180, 25185, 25188, 25208, 25209, 25247, 25289, 25315, 25323, 25351, 25359, 25373, 25396, 25397, 25446,
        25465, 25488, 25510, 25529, 25536, 25611, 25698, 25723, 25751, 25754, 25766, 25795, 25821, 25834, 25871, 25882,
        25914, 25930, 25955, 25965, 25971, 26007, 26009, 26155, 26186, 26210, 26229, 26243, 26263, 26294, 26326, 26332,
        26345, 26374, 26414, 26432, 26434, 26452, 26483, 26510, 26530, 26542, 26543, 26570, 26571, 26573, 26617, 26640,
        26653, 26723, 26746, 26754, 26785, 26815, 26829, 26889, 26925, 26945, 26955, 26990, 27011, 27013, 27051, 27056,
        27131, 27138, 27144, 27209, 27228, 27231, 27291, 27307, 27323, 27328, 27341, 27359, 27372, 27377, 27400, 27414,
        27426, 27443, 27446, 27456, 27465, 27481, 27482, 27514, 27524, 27531, 27532, 27534, 27566, 27580, 27631, 27640,
        27650, 27668, 27670, 27684, 27696, 27721, 27738, 27790, 27803, 27826, 27888, 27911, 27943, 27944, 27975, 27977,
        27979, 27984, 27988, 27989, 28008, 28093, 28095, 28115, 28133, 28136, 28143, 28147, 28171, 28215, 28289, 28290,
        28296, 28318, 28349, 28367, 28420, 28423, 28439, 28457, 28513, 28540, 28553, 28595, 28641, 28664, 28713, 28719,
        28740, 28760, 28761, 28775, 28782, 28783, 28806, 28819, 28828, 28869, 28906, 28931, 28959, 28993, 29005, 29120,
        29124, 29181, 29185, 29199, 29243, 29405, 29409, 29465, 29467, 29474, 29514, 29586, 29760, 29779, 29802, 29847,
        29855, 29868, 29894, 29926, 29949, 29977, 29988, 30039, 30061, 30105, 30114, 30123, 30170, 30208, 30233, 30234,
        30235, 30247, 30280, 30336, 30403, 30496, 30519, 30531, 30533, 30574, 30613, 30648, 30657, 30681, 30697, 30706,
        30757, 30764, 30772, 30878, 30897, 30901, 30940, 30966, 30995, 31018, 31074, 31077, 31090, 31107, 31142, 31177,
        31217, 31276, 31309, 31331, 31337, 31403, 31405, 31431, 31443, 31472, 31506, 31512, 31513, 31526, 31535, 31543,
        31558, 31580, 31611, 31633, 31640, 31648, 31663, 31695, 31850, 31852, 31939, 31945, 31965, 32015, 32026, 32037,
        32043, 32049, 32118, 32163, 32239, 32262, 32292, 32315, 32342, 32373, 32491, 32492, 32505, 32524, 32569, 32573,
        32575, 32651, 32679, 32862, 32870, 32884, 32908, 32953, 32954, 32969, 32984, 33006, 33010, 33030, 33062, 33087,
        33101, 33151, 33157, 33167, 33176, 33182, 33222, 33226, 33228, 33258, 33263, 33281, 33296, 33363, 33365, 33403,
        33449, 33455, 33592, 33599, 33613, 33623, 33638, 33641, 33688, 33767, 33777, 33787, 33794, 33841, 33867, 33868,
        33876, 33882, 33931, 33952, 34015, 34025, 34055, 34056, 34090, 34091, 34101, 34122, 34128, 34170, 34179, 34227,
        34255, 34288, 34311, 34321, 34332, 34350, 34424, 34448, 34467, 34509, 34519, 34530, 34534, 34601, 34642, 34653,
        34654, 34665, 34701, 34707, 34721, 34734, 34780, 34782, 34862, 34909, 34923, 34927, 34928, 34973, 34977, 34983,
        35021, 35073, 35092, 35163, 35169, 35186, 35215, 35281, 35338, 35367, 35388, 35457, 35490, 35492, 35521, 35526,
        35585, 35598, 35603, 35617, 35622, 35630, 35676, 35705, 35709, 35756, 35769, 35775, 35778, 35808, 35815, 35876,
        35898, 35912, 36023, 36073, 36125, 36146, 36148, 36223, 36224, 36239, 36244, 36246, 36262, 36289, 36291, 36301,
        36304, 36370, 36438, 36480, 36516, 36530, 36547, 36633, 36653, 36668, 36700, 36745, 36914, 36948, 36976, 36979,
        37095, 37119, 37144, 37153, 37156, 37160, 37175, 37181, 37187, 37191, 37225, 37228, 37265, 37380, 37395, 37400,
        37480, 37514, 37529, 37533, 37549, 37558, 37573, 37627, 37669, 37682, 37683, 37731, 37745, 37758, 37762, 37783,
        37794, 37806, 37880, 37915, 37927, 37949, 37973, 38009, 38120, 38177, 38213, 38368, 38410, 38419, 38445, 38454,
        38483, 38488, 38581, 38638, 38647, 38651, 38655, 38680, 38710, 38724, 38760, 38921, 38992, 39014, 39037, 39108,
        39124, 39130, 39140, 39154, 39191, 39233, 39264, 39279, 39304, 39430, 39462, 39464, 39503, 39526, 39539, 39624,
        39638, 39695, 39721, 39838, 39880, 39901, 39910, 40021, 40033, 40082, 40108, 40118, 40180, 40182, 40185, 40207,
        40274, 40294, 40337, 40383, 40420, 40459, 40489, 40647, 40661, 40756, 40758, 40827, 40851, 40854, 40862, 40941,
        40952, 40982, 40995, 41048, 41064, 41067, 41124, 41130, 41145, 41147, 41165, 41184, 41220, 41221, 41222, 41273,
        41280, 41368, 41370, 41374, 41380, 41394, 41411, 41438, 41452, 41604, 41609, 41644, 41664, 41689, 41720, 41737,
        41742, 41744, 41760, 41795, 41796, 41797, 41822, 41833, 41851, 41881, 41887, 41911, 41912, 41972, 42001, 42030,
        42048, 42049, 42195, 42211, 42216, 42315, 42318, 42362, 42368, 42369, 42407, 42446, 42521, 42588, 42612, 42621,
        42625, 42626, 42629, 42654, 42657, 42669, 42824, 42869, 42898, 42902, 42910, 43019, 43058, 43068, 43070, 43080,
        43113, 43116, 43212, 43261, 43337, 43359, 43508, 43544, 43583, 43596, 43683, 43753, 43798, 43966, 44025, 44037,
        44145, 44148, 44167, 44185, 44300, 44327, 44394, 44415, 44468, 44553, 44576, 44596, 44613, 44615, 44663, 44699,
        44704, 44718, 44750, 44795, 44798, 44845, 44853, 44858, 44897, 44919, 44929, 44931, 45041, 45119, 45134, 45140,
        45156, 45262, 45270, 45326, 45331, 45359, 45424, 45484, 45682, 45694, 45707, 45723, 45785, 45800, 45931, 45960,
        46109, 46119, 46146, 46234, 46245, 46262, 46306, 46410, 46414, 46500, 46525, 46541, 46615, 46630, 46641, 46693,
        46705, 46734, 46941, 46944, 46984, 47002, 47029, 47075, 47106, 47164, 47195, 47263, 47291, 47326, 47363, 47408,
        47427, 47430, 47497, 47588, 47594, 47628, 47652, 47658, 47696, 47816, 47908, 47970, 48015, 48027, 48029, 48071,
        48075, 48109, 48148, 48156, 48190, 48222, 48277, 48384, 48400, 48487, 48493, 48515, 48532, 48540, 48582, 48620,
        48634, 48674, 48733, 48738, 48782, 48783, 48797, 48837, 48915, 48917, 48954, 48990, 48993, 49055, 49073, 49121,
        49137, 49148, 49182, 49262, 49274, 49309, 49352, 49392, 49406, 49428, 49446, 49461, 49490, 49502, 49602, 49620,
        49672, 49675, 49689, 49821, 49852, 50014, 50126, 50172, 50188, 50383, 50542, 50550, 50569, 50582, 50724, 50740,
        50771, 50776, 50843, 50927, 51059, 51076, 51179, 51463, 51655, 51658, 51759, 51806, 51812, 51845, 51869, 51894,
        51920, 52007, 52047, 52085, 52109, 52395, 52456, 52476, 52550, 52557, 52607, 52676, 52715, 52770, 53006, 53052,
        53230, 53268, 53325, 53357, 53407, 53411, 53611, 53631, 53640, 53692, 53730, 53734, 53739, 53845, 53853, 53946,
        53959, 53980, 54037, 54057, 54088, 54217, 54236, 54623, 54687, 54690, 54785, 54822, 54846, 54864, 54886, 54978,
        54982, 55057, 55269, 55364, 55389, 55404, 55588, 55596, 55632, 55635, 55778, 55852, 55899, 55905, 55915, 56079,
        56148, 56217, 56325, 56396, 56413, 56424, 56434, 56520, 56671, 56675, 56732, 56750, 56957, 57062, 57069, 57303,
        57532, 57612, 57621, 57677, 57909, 57910, 57988, 58041, 58164, 58171, 58187, 58241, 58280, 58311, 58312, 58381,
        58394, 58638, 58921, 58955, 59072, 59175, 59182, 59198, 59220, 59366, 59378, 59396, 59521, 59665, 59751, 59765,
        59773, 59844, 59878, 60025, 60063, 60280, 60311, 60397, 60406, 60440, 60449, 60484, 60568, 60631, 60682, 60770,
        60821, 60882, 61057, 61066, 61108, 61115, 61147, 61157, 61270, 61331, 61337, 61441, 61584, 61609, 61632, 61681,
        61684, 61839, 61885, 62053, 62067, 62152, 62182, 62235, 62245, 62285, 62332, 62336, 62380, 62404, 62460, 62556,
        62571, 62685, 62835, 62935, 62952, 63170, 63208, 63221, 63300, 63578, 63588, 63592, 63739, 63805, 63902, 63923,
        63985, 64081, 64123, 64375, 64387, 64431, 64656, 64701, 64748, 64785, 64869, 64886, 64908, 64919, 64959, 64986,
        65054, 65068, 65190, 65303, 65351, 65369, 65576, 65581, 65584, 65590, 65707, 65773, 65782, 65863, 65935, 66023,
        66056, 66160, 66272, 66278, 66367, 66484, 66498, 66571, 66591, 66664, 66681, 66711, 66727, 66729, 66797, 66800,
        66867, 66869, 67011, 67014, 67142, 67187, 67219, 67279, 67290, 67412, 67488, 67544, 67619, 67723, 67761, 67817,
        68012, 68056, 68086, 68212, 68244, 68291, 68313, 68393, 68408, 68414, 68434, 68510, 68579, 68755, 68760, 68763,
        68769, 68844, 68968, 69091, 69125, 69186, 69272, 69311, 69336, 69373, 69383, 69413, 69416, 69513, 69537, 69547,
        69581, 69586, 69611, 69788, 69906, 69911, 69959, 69971, 69986, 69988, 69995, 70077, 70166, 70189, 70319, 70341,
        70495, 70531, 70720, 70757, 70792, 70890, 70927, 71020, 71075, 71187, 71193, 71299, 71338, 71349, 71434, 71453,
        71477, 71519, 71761, 71833, 71897, 71951, 72026, 72137, 72217, 72269, 72289, 72305, 72325, 72417, 72454, 72456,
        72468, 72545, 72562, 72653, 72787, 72837, 72914, 72931, 73015, 73107, 73366, 73375, 73481, 73512, 73537, 73566,
        73594, 73595, 73629, 73639, 73654, 73734, 73938, 74023, 74036, 74043, 74065, 74099, 74235, 74307, 74377, 74445,
        74470, 74489, 74619, 74703, 74775, 74804, 74807, 74873, 74959, 75073, 75176, 75264, 75330, 75374, 75392, 75407,
        75654, 75731, 75917, 75985, 76130, 76289, 76380, 76456, 76475, 76510, 76759, 76830, 76855, 76966, 77122, 77218,
        77463, 77553, 77603, 77680, 77747, 77766, 77779, 77812, 77827, 78127, 78336, 78437, 78555, 78569, 78655, 79021,
        79061, 82850, 82858, 82984, 83187, 83244, 83376, 83384, 83478, 83573, 83638, 83657, 83679, 83731, 83816, 83943,
        83990, 84037, 84048, 84183, 84246, 84269, 84537, 84862, 85134, 85546, 85603, 85604, 85655, 85707, 86601, 87014,
        87039, 87112, 87350, 87377, 87416, 87641, 87674, 87862, 87907, 87975, 88026, 88426, 88844, 89242, 89339, 89545,
        89604, 89822, 90079, 90100, 90168, 90241, 90321, 90345, 90488, 90685, 90800, 90941, 91022, 91061, 91170, 91171,
        91413, 91446, 91544, 91683, 91814, 92070, 92085, 92131, 92186, 92472, 92477, 92515, 92569, 92583, 92635, 92701,
        92742, 92748, 92800, 92839, 92858, 93023, 93063, 93204, 93343, 93448, 93487, 93564, 93662, 93741, 93865, 94249,
        94286, 94352, 94365, 94423, 94435, 94513, 94619, 94685, 94692, 94960, 96322, 97133, 97185, 97938, 97977, 97986,
        98063, 98098, 98117, 98193, 98204, 98227, 98229, 98315, 98420, 98473, 98565, 98843, 99200, 99267, 99827, 99853,
        100226, 100394, 100590, 100634, 100703, 100806, 101233, 101425, 101730, 101885, 102092, 102409, 102553, 102764, 102769, 102799,
        102816, 102895, 102946, 102976, 103068, 103103, 103260, 103361, 103422, 103477, 103488, 103570, 103604, 103718, 103731, 103733,
        104308, 104518, 104742, 105004, 105203, 105330, 105444, 105884, 106079, 106204, 106223, 106240, 106254, 106269, 106289, 106356,
        106379, 106666, 106686, 106798, 106823, 106846, 106963, 107598, 107611, 107945, 108346, 108414, 108458, 108483, 108764, 108981,
        109106, 109131, 109153, 109680, 109686, 109945, 109950, 109960, 110120, 110121, 110228, 110293, 110294, 110333, 110380, 110381,
        110434, 110524, 110563, 110583, 110604, 110614, 110635, 110678, 110787, 110833, 110881, 110885, 110886, 110951, 110965, 110972,
        110973, 111011, 111064, 111074, 111102, 111231, 111587, 111631, 111850, 111885, 112081, 112085, 112584, 113302, 113366, 113383,
        113602, 113766, 113824, 113902, 114017, 114040, 115545, 115598, 115714, 115739, 116219, 116406, 116478, 116529, 116847, 117011,
        117133, 118163, 118237, 118278, 118717, 118759, 119361, 119623, 119646, 119968, 120593, 120724, 121128, 121598, 121956, 122115,
        122148, 122292, 122683, 122863, 123165, 123170, 123268, 123407, 123720, 123721, 124023, 124525, 124565, 124874, 124977, 125141,
        125243, 125392, 125485, 125498, 125531, 125564, 125733, 125799, 125837, 125869, 125905, 126401, 126511, 126699, 127049, 127076,
        127419, 127520, 127619, 127770, 127828, 127854, 127897, 128256, 128323, 128521, 128641, 128756, 128888, 128992, 129268, 129382,
        129385, 129783, 129796, 129934, 130055, 130221, 130228, 130275, 130610, 130993, 131122, 131648, 131742, 131917
  );

DELETE FROM paper_method_exclusions x
USING supervised_fine_tuning_sft_curated c
WHERE x.paper_id = c.paper_id AND x.method_id = c.method_id;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM supervised_fine_tuning_sft_curated
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM supervised_fine_tuning_sft_curated
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
