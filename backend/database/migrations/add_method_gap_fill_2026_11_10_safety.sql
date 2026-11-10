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
    'jailbreak', 'Jailbreak',
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
          '2504.19475', '2602.05859', '2301.04709', '2501.16496', '2503.06269', '2505.03368', '2505.20254', '2603.22295', '2601.03047', '2308.14179', '2504.13151', '2301.05217', '2304.14997', '2402.05110', '2402.12201', '2405.10927',
          '2406.16320', '2407.14494', '2409.10504', '2411.10950', '2503.12730', '2503.20483', '2504.07898', '2505.14352', '2509.00328', '2601.14004', '2602.16823', '2603.09988', '2602.04902', '2511.05923', '2507.08802', '2507.02559',
          '2407.02646', '2503.10894', '2502.20914', '2605.17504', '2510.00845', '2606.00033', '2604.14477', '2608.14922', '2410.08417', '2410.11414', '2503.12734', '2508.15882', '2601.02989', '2510.25674', '2502.17516', '2601.19208',
          '2606.12629', '2507.22928', '2609.35210', '2605.12639', '2605.13930', '2409.13710', '2306.01128', '2405.17425', '2410.07656', '2412.04139', '2506.19382', '2503.05613', '2407.08734', '2606.22673', '2205.10487', '2209.10652',
          '2211.00593', '2302.03025', '2305.03452', '2309.08600', '2309.16042', '2310.08744', '2310.18969', '2311.12786', '2311.17030', '2312.09230', '2312.16291', '2401.12181', '2402.10688', '2404.07129', '2404.15255', '2405.03205',
          '2405.10928', '2405.12241', '2405.12522', '2405.13816', '2405.13868', '2406.11944', '2406.16235', '2406.17759', '2407.00886', '2407.14499', '2410.06981', '2410.09223', '2410.12949', '2410.13708', '2410.20526', '2412.04703',
          '2412.12841', '2412.14133', '2412.17626', '2501.02362', '2501.15740', '2501.18838', '2502.09135', '2502.12131', '2503.01773', '2504.04264', '2504.08016', '2504.12585', '2504.14218', '2505.16538', '2505.19440', '2506.07985',
          '2506.10423', '2506.10920', '2506.14002', '2506.20790', '2507.12990', '2510.13251', '2601.10825', '2601.21996', '2602.07080', '2602.22600', '2603.06854', '2604.02605', '2604.21691', '2604.11061', '2604.06005', '2603.25052',
          '2603.19460', '2603.14923', '2603.08234', '2602.22253', '2602.18262', '2602.14759', '2602.12026', '2602.10437', '2602.10168', '2602.04613', '2602.00924', '2601.12879', '2512.10805', '2512.08892', '2511.20798', '2511.13653',
          '2511.08379', '2511.07002', '2510.25776', '2510.18900', '2510.14936', '2510.03366', '2510.02629', '2402.02619', '2510.01048', '2509.20784', '2509.18136', '2509.03738', '2508.21258', '2508.16652', '2508.15807', '2508.09019',
          '2507.12950', '2506.07691', '2505.13737', '2503.24277', '2502.17514', '2502.04878', '2406.13564', '2605.19908', '2605.27354', '2511.17699', '2601.06338', '2509.23323', '2411.04105', '2505.22411', '2504.15473', '2502.03618',
          '2407.13594', '2410.06331', '2502.11812', '2506.05774', '2502.01954', '2503.02080', '2410.07476', '2511.04638', '2603.30002', '2509.23684', '2605.14075', '2501.17727', '2506.16975', '2603.09972', '2508.01916', '2507.12553',
          '2509.20977', '2606.06664', '2505.18441', '2603.23268', '2602.13524', '2602.15183', '2602.01605', '2602.07050', '2506.15199', '2602.23164', '2601.13548', '2604.08764', '2602.16740', '2601.22818', '2602.22968', '2606.08236',
          '2602.22719', '2606.19353', '2604.25167', '2602.07930', '2606.01243', '2604.22345', '2607.10034', '2603.23301', '2602.04718', '2604.13950', '2604.24302', '2509.05309', '2608.19338', '2608.22614', '2503.08200', '2509.18792',
          '2609.03026', '2609.09113', '2511.22697', '2607.02494', '2605.19792', '2610.09087', '2605.14694', '2605.08298', '2601.15441', '2605.21849', '2606.15796', '2602.13483', '2610.20851', '2610.04905', '2608.26419', '2605.06076',
          '2605.17204', '2606.09899', '2608.05158', '2608.24065', '2606.27510', '2609.07681'
      )
      OR
      (p.source = 'external' AND p.id IN (
          128690, 127593, 120782, 124367, 125728, 128627, 83337, 110900, 111110, 125369, 126045, 127436, 128344, 129843, 130017, 130220,
          130223, 130667, 131044
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
          '2311.08360', '2402.12219', '2410.09637', '2504.17017', '2601.22203', '2509.20935', '2507.10624', '2603.17809', '2412.20292', '2509.19988', '2602.05532', '2605.30635', '2506.22740', '2604.12806'
      )
      OR
      (p.source = 'external' AND p.id IN (
          126136, 126524, 129379, 130236
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
          '2309.16042', '2310.10348', '2311.17030', '2404.15255', '2308.14179', '2606.09899', '2606.27510', '2603.13768', '2602.05234', '2511.05923', '2605.24614', '2606.03085', '2410.14155', '2603.13652', '2601.00267', '2508.21258',
          '2403.00745', '2301.04213', '2301.04709', '2404.03646', '2411.06424', '2603.22295', '2505.08265', '2604.22166', '2304.14997', '2307.09458', '2401.12631', '2402.12201', '2402.18154', '2403.00824', '2403.17806', '2407.00886',
          '2407.14494', '2410.14405', '2412.12841', '2502.04577', '2502.09935', '2502.20475', '2503.12730', '2504.07898', '2504.12996', '2505.16002', '2508.15882', '2601.11061', '2602.11910', '2604.19117', '2602.16698', '2603.09988',
          '2602.10382', '2602.00449', '2601.17086', '2510.03366', '2509.22674', '2507.09875', '2507.02559', '2506.12044', '2502.00726', '2404.03623', '2402.18344', '2412.02542', '2502.11806', '2504.13151', '2503.01090', '2407.15018',
          '2509.21044', '2506.20746', '2510.11390', '2605.02958', '2510.00845', '2604.10031', '2508.02360', '2604.19052', '2604.09364', '2508.02087', '2507.22928', '2607.26326', '2509.23676', '2510.11210', '2610.22169', '2608.10430',
          '2606.05403', '2607.04846', '2602.08548', '2605.13156'
      )
      OR
      (p.source = 'external' AND p.id IN (
          125728, 124795, 109994, 125290, 126806, 126951, 127220, 127536, 127593, 131096, 131206
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
          '2603.14688', '2409.00119', '2602.19631', '2509.08592'
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
          '2303.08112', '2604.02608', '2411.19187', '2602.13567', '2609.01936', '2606.07617', '2404.05971', '2405.03205', '2406.11193', '2409.04185', '2411.04986', '2412.04537', '2502.15007', '2502.15603', '2503.12730', '2505.14352',
          '2507.02199', '2508.15882', '2510.01070', '2601.11061', '2604.02486', '2604.15557', '2604.11061', '2602.00449', '2602.15038', '2510.01685', '2509.06608', '2506.22724', '2505.18706', '2502.16570', '2511.19972', '2601.20009',
          '2606.25182', '2606.22473', '2604.18712', '2605.10622', '2604.06374', '2604.09364', '2604.09885', '2508.02087', '2609.11085', '2602.20031', '2508.21380', '2609.38810', '2607.03502'
      )
      OR
      (p.source = 'external' AND p.id IN (
          121088, 109994, 110004, 125992, 126135
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
          '2610.17495'
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
          '2308.07269', '2410.16251', '2401.07453', '2411.12790', '2405.00664', '2411.06638', '2508.01302', '2505.01343', '2310.02129', '2401.01286', '2402.13462', '2403.05330', '2503.05683', '2503.05212', '2402.09394', '2401.04700',
          '2402.11905', '2405.14768', '2502.11177', '2405.16821', '2509.24502', '2506.13772', '2512.00881', '2508.05083', '2607.05310', '2308.08742', '2402.09656', '2402.16123', '2403.07175', '2403.14236', '2403.14472', '2404.13752',
          '2405.19086', '2406.04496', '2406.20030', '2407.06249', '2409.10132', '2410.07819', '2412.17727', '2502.10626', '2502.15826', '2503.02701', '2503.20756', '2509.22072', '2512.04753', '2602.03696', '2510.22139', '2510.21059',
          '2502.14838', '2408.10411', '2405.15349', '2602.10965', '2606.00477', '2502.19953', '2505.14393', '2110.11309', '2202.05262', '2305.13172', '2312.11795', '2401.10647', '2402.05827', '2402.06155', '2402.11324', '2406.10777',
          '2406.17764', '2409.05806', '2410.14276', '2502.01636', '2504.01196', '2505.11876', '2505.23291', '2510.07896', '2603.15518', '2510.01172', '2602.08550', '2510.25798', '2509.21993', '2410.09508', '2502.03748', '2411.15432',
          '2503.01090', '2503.00306', '2505.18774', '2606.00570', '2604.19089', '2601.11042', '2511.13243', '2508.07022', '2506.20606', '2505.15702', '2505.18933', '2602.20207', '2211.11031', '2301.04213', '2305.14795', '2307.12976',
          '2402.08631', '2403.07350', '2403.13355', '2404.03646', '2405.13967', '2406.11139', '2406.11263', '2410.02355', '2410.03122', '2503.08588', '2505.12345', '2505.23026', '2602.02543', '2601.17086', '2510.06627', '2506.09672',
          '2505.22156', '2502.00602', '2506.07899', '2410.06331', '2410.17194', '2510.02392', '2606.01053', '2605.11836', '2602.10134', '2604.11214', '2505.07899', '2605.06096', '2608.11660', '2507.03377', '2610.02772', '2606.23276',
          '2603.12677', '2402.17811', '2403.17431', '2504.15133', '2507.18028', '2606.09707', '2605.26670', '2502.19870', '2310.11958', '2407.20224', '2305.15529', '2303.08084', '2505.14679', '2512.14395', '2604.05540', '2511.14018',
          '2609.09054', '2305.12740', '2305.17553', '2310.08475', '2311.16087', '2401.10521', '2405.17969', '2406.12670', '2502.05628', '2503.07392', '2503.16356', '2510.19457', '2510.16917', '2604.07965', '2603.15656', '2506.13285',
          '2510.13500', '2602.02408', '2601.07873', '2206.15465', '2301.10405', '2309.17410', '2310.02168', '2310.10378', '2310.13730', '2311.04661', '2312.04364', '2402.04624', '2402.15302', '2403.06259', '2403.13807', '2404.00486',
          '2404.11534', '2406.09325', '2406.11194', '2407.06483', '2409.00617', '2409.14144', '2410.12949', '2410.18785', '2412.08201', '2506.08920', '2603.24653', '2602.10021', '2601.15686', '2601.10639', '2510.27400', '2509.18868',
          '2605.16865', '2605.18879', '2604.10032', '2510.11268', '2412.02542', '2505.18832', '2502.05759', '2502.10438', '2404.00216', '2405.16720', '2505.20819', '2605.20273', '2603.15117', '2606.17057', '2606.03096', '2508.02092',
          '2511.12828', '2509.08778', '2603.12598', '2609.00184'
      )
      OR
      (p.source = 'external' AND p.id IN (
          110387, 111063, 121907, 130983, 110053, 113556, 127048, 127562, 129037, 129861, 130955, 110903, 125909, 110525, 127095, 128357
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
          '2205.12374', '2608.01973', '2311.18166', '2205.15480', '2211.09800', '2307.03941', '2311.11908', '2401.12874', '2402.01364', '2402.08787', '2402.10688', '2402.14522', '2403.07809', '2404.11672', '2407.15549', '2410.19427',
          '2501.18887', '2502.06755', '2504.05523', '2504.15585', '2506.09227', '2509.10708', '2602.21499', '2507.20930', '2406.10868', '2512.01329', '2510.13462', '2505.17721', '2410.00487', '2505.24262', '2605.24906', '2603.03335',
          '2601.21601', '2507.18178', '2608.16328', '2505.24428'
      )
      OR
      (p.source = 'external' AND p.id IN (
          130718
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
          '2501.07238', '2506.00781', '2209.07858', '2401.12915', '2408.11851', '2510.02677', '2311.07689', '2401.16656', '2504.03174', '2505.20162', '2601.13518', '2510.02609', '2607.26115', '2306.09442', '2311.06237', '2402.04249',
          '2402.19464', '2405.18540', '2505.21936', '2602.02164', '2407.16667', '2510.18131', '2308.04265', '2310.14303', '2404.03411', '2406.15481', '2407.14937', '2410.02828', '2411.18676', '2503.15754', '2601.01592', '2605.00553',
          '2512.20677', '2509.21011', '2508.00923', '2507.16329', '2507.22063', '2410.01606', '2605.04808', '2509.15551', '2606.05101', '2510.09689', '2608.05108', '2509.19143', '2202.03286', '2308.09662', '2310.12505', '2311.08592',
          '2404.00629', '2404.06664', '2405.12604', '2405.19026', '2405.19360', '2501.18837', '2505.06913', '2604.28157', '2602.19948', '2601.10971', '2601.10589', '2507.07248', '2506.22523', '2506.14682', '2504.01278', '2605.22880',
          '2506.10047', '2603.22882', '2505.21074', '2602.20170', '2605.00699', '2506.11083', '2606.31227', '2509.10546', '2510.07239', '2607.21735', '2609.34920', '2301.12867', '2309.06135', '2309.10253', '2310.09624', '2402.13946',
          '2404.08676', '2407.12784', '2408.10701', '2409.15398', '2410.17401', '2501.01830', '2503.01908', '2506.09600', '2508.03936', '2510.02286', '2601.03699', '2603.22341', '2603.18762', '2602.10148', '2603.20198', '2601.22569',
          '2509.15478', '2510.18314', '2509.23694', '2504.19855', '2511.21145', '2509.21947', '2605.08876', '2604.05549', '2604.18789', '2601.03265', '2604.21159', '2411.16769', '2603.13026', '2606.20408', '2608.00677', '2509.15260',
          '2609.32400', '2210.04610', '2305.19713', '2311.09433', '2406.11654', '2505.05849', '2505.24672', '2509.14651', '2502.14847', '2512.00412', '2610.22722', '2506.00782', '2408.02632', '2410.13886', '2502.09638', '2504.15047',
          '2508.10108', '2511.14195', '2310.02446', '2401.10647', '2405.21018', '2406.18510', '2407.13833', '2409.11445', '2601.11516', '2603.15714', '2512.07810', '2510.17017', '2507.20526', '2506.07468', '2602.16346', '2608.17067',
          '2604.07831', '2607.11070', '2310.02224', '2310.03693', '2310.06987', '2310.15140', '2311.09641', '2312.05187', '2312.06942', '2312.14302', '2401.12509', '2402.08567', '2403.01038', '2403.08424', '2404.00399', '2404.16873',
          '2406.07594', '2406.11036', '2406.11978', '2406.14393', '2406.18682', '2407.16318', '2408.00761', '2408.15221', '2409.00138', '2409.00551', '2409.11276', '2409.17458', '2410.05295', '2411.14133', '2411.17693', '2412.16720',
          '2501.00069', '2501.04931', '2501.07927', '2501.17433', '2502.03052', '2503.14827', '2503.18929', '2504.13203', '2505.10838', '2506.17299', '2507.05980', '2507.06260', '2508.10390', '2508.19500', '2509.17938', '2511.12710',
          '2512.10675', '2602.06854', '2602.14689', '2602.20021', '2603.02482', '2601.02670', '2603.25176', '2603.24935', '2603.17305', '2603.16576', '2602.07391', '2602.05746', '2603.06594', '2601.15331', '2509.05367', '2512.20806',
          '2512.13526', '2511.21990', '2511.20686', '2511.16709', '2511.10222', '2511.01375', '2511.00203', '2510.17947', '2509.25896', '2509.21029', '2509.08729', '2508.19461', '2508.14904', '2508.08243', '2508.04196', '2508.00555',
          '2507.22564', '2507.19060', '2506.24068', '2506.00359', '2411.00827', '2505.06843', '2408.04811', '2406.09179', '2601.04603', '2606.23496', '2605.10067', '2510.17759', '2601.04740', '2510.17687', '2605.24883', '2607.26314',
          '2602.06440', '2505.14300', '2508.06194', '2509.08000', '2608.09158', '2605.17380', '2605.12673', '2310.10012', '2609.30383', '2606.04027', '2610.22124', '2605.08427'
      )
      OR
      (p.source = 'external' AND p.id IN (
          128448, 110627, 128704, 109971, 128588, 129879, 121047, 127047, 128146, 110123, 120852, 127443
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
          '2307.02483', '2401.05998', '2404.17546', '2405.01886', '2407.15549', '2501.15570', '2305.07153', '2308.01263', '2308.06463', '2310.20624', '2311.11202', '2312.00027', '2403.04224', '2403.05030', '2407.12383', '2410.09421',
          '2504.03289', '2504.12553', '2506.02479', '2512.04124', '2511.05865', '2509.08592', '2506.00062', '2409.19476', '2404.05880', '2308.00862', '2505.12677', '2406.14595', '2503.06550', '2410.19406', '2410.20971', '2602.08621',
          '2606.14351', '2610.00960'
      )
      OR
      (p.source = 'external' AND p.id IN (
          106032, 131941
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
          '2502.07557', '2504.10694', '2502.10438', '2603.17372', '2406.11682', '2504.19440', '2411.01565', '2405.20015', '2308.03825', '2402.10260', '2605.24535', '2305.13860', '2404.03027', '2409.14866', '2408.04811', '2402.03299',
          '2404.01318', '2405.20653', '2406.18122', '2411.07494', '2502.09638', '2601.03600', '2404.01833', '2411.00827', '2505.23839', '2312.02119', '2406.18510', '2410.09804', '2501.13772', '2502.11084', '2506.17299', '2508.20848',
          '2406.05498', '2402.02309', '2307.08715', '2601.03005', '2309.10253', '2310.04451', '2310.08419', '2311.09096', '2402.08567', '2402.08983', '2402.13494', '2403.12171', '2404.02151', '2404.03411', '2409.19149', '2411.18688',
          '2412.03556', '2502.16903', '2505.17598', '2601.02670', '2603.08234', '2602.01025', '2506.00782', '2503.20823', '2502.04204', '2407.15211', '2510.21910', '2510.20956', '2605.18915', '2602.06440', '2311.08268', '2401.10862',
          '2401.17263', '2402.16459', '2403.08424', '2405.21018', '2406.01288', '2408.15221', '2412.05892', '2412.05934', '2412.17522', '2501.02629', '2504.03770', '2505.15406', '2506.02479', '2510.05025', '2412.18171', '2411.11496',
          '2410.20971', '2602.22983', '2506.12913', '2605.07414', '2508.16406', '2607.11070', '2610.34074', '2311.05608', '2311.14455', '2401.06373', '2401.06561', '2401.06824', '2401.17256', '2402.08679', '2403.00867', '2403.04783',
          '2406.05644', '2408.11313', '2410.13334', '2411.06426', '2412.01547', '2501.18837', '2502.04322', '2502.19820', '2511.04707', '2512.06589', '2603.19127', '2602.18154', '2502.11090', '2512.18244', '2511.10519', '2511.01375',
          '2510.02833', '2508.13246', '2508.01741', '2501.10639', '2505.21556', '2504.08104', '2503.06519', '2410.02298', '2405.20099', '2404.05880', '2402.16914', '2402.09091', '2603.21208', '2506.22666', '2507.01513', '2603.00565',
          '2509.23281', '2605.24497', '2605.01687', '2605.17128', '2508.06194', '2508.13048', '2504.09466', '2603.11149', '2305.12082', '2307.02483', '2307.14539', '2310.03684', '2310.06987', '2311.03348', '2402.09177', '2402.10601',
          '2404.16369', '2406.07188', '2406.18495', '2407.02855', '2409.00137', '2409.17458', '2410.05295', '2410.18469', '2411.08410', '2411.14133', '2412.08201', '2412.08615', '2501.04931', '2502.01925', '2502.09990', '2502.12970',
          '2503.01865', '2505.10838', '2505.11790', '2505.22037', '2507.02844', '2508.10390', '2511.12710', '2602.06854', '2509.25843', '2602.24009', '2603.01291', '2505.17568', '2511.18933', '2511.02356', '2509.21029', '2509.14297',
          '2508.05087', '2508.03054', '2508.00555', '2506.16760', '2504.21307', '2503.17987', '2503.12339', '2502.18504', '2501.12210', '2412.08608', '2410.09040', '2403.02910', '2512.06674', '2412.10321', '2505.19610', '2410.19937',
          '2604.10326', '2606.11817', '2606.25182', '2605.24550', '2605.04700', '2601.03265', '2512.23173', '2503.12931', '2605.27932', '2605.10582', '2310.06474', '2311.03191', '2402.11753', '2402.13457', '2402.15180', '2403.09792',
          '2404.07921', '2406.18118', '2410.02832', '2410.04190', '2410.12855', '2410.22143', '2501.18632', '2502.01154', '2502.03052', '2502.14486', '2502.14744', '2502.16750', '2502.19883', '2503.01839', '2503.10619', '2504.11168',
          '2504.13203', '2505.13862', '2505.16446', '2506.07402', '2506.10597', '2506.12880', '2602.10179', '2604.19274', '2603.07028', '2511.13127', '2602.10148', '2602.07107', '2601.20903', '2601.05445', '2511.15304', '2511.11784',
          '2511.07315', '2510.21285', '2510.17904', '2510.03417', '2509.11629', '2508.09218', '2508.10029', '2507.21540', '2507.22171', '2507.02332', '2505.06679', '2502.15806', '2502.09723', '2501.18638', '2402.18104', '2502.00653',
          '2603.22094', '2411.01077', '2502.01633', '2504.05838', '2502.10794', '2411.16721', '2410.01294', '2601.04603', '2603.03081', '2509.22292', '2510.17759', '2601.09321', '2605.18168', '2606.02640', '2601.19487', '2601.03416',
          '2512.12069', '2604.09748', '2506.15734', '2507.05248', '2505.19684', '2507.11630', '2509.10931', '2605.10779', '2306.13213', '2310.02446', '2310.06387', '2402.06255', '2405.01229', '2405.20775', '2407.08441', '2409.11445',
          '2410.03857', '2410.13886', '2501.19180', '2502.13162', '2502.13603', '2505.13541', '2507.13474', '2510.09023', '2602.08741', '2512.07761', '2604.07835', '2602.20999', '2601.10971', '2512.05485', '2511.17874', '2510.05379',
          '2508.16889', '2508.12072', '2502.12893', '2411.18000', '2410.04234', '2605.20286', '2605.10067', '2605.20654', '2605.02958', '2605.00583', '2606.02111', '2606.04027', '2602.04896', '2609.30841', '2605.26409', '2605.05709',
          '2301.12867', '2304.05197', '2404.14461', '2406.14393', '2408.16163', '2410.10700', '2501.01830', '2508.03365', '2512.04124', '2509.08729', '2505.08804', '2402.16006', '2603.29038', '2601.07141', '2605.10998', '2407.16667',
          '2410.09024', '2501.01335', '2507.06282', '2412.03235', '2508.19292', '2310.15140', '2502.15427', '2601.04034', '2606.16242', '2502.15334', '2605.12128', '2405.08317', '2407.11969', '2505.20259', '2506.07452', '2507.11097',
          '2601.01747', '2510.26096', '2507.11500', '2506.05346', '2604.12817', '2606.23496', '2602.11096', '2403.09513', '2605.21834', '2402.15570', '2407.02551', '2407.08770', '2408.07663', '2411.09125', '2502.11411', '2502.13946',
          '2503.03710', '2503.04856', '2505.11413', '2510.11570', '2604.18756', '2602.16977', '2601.03537', '2511.06512', '2510.17947', '2510.15476', '2510.01494', '2509.15202', '2508.10031', '2506.00781', '2605.22880', '2510.00565',
          '2605.01899', '2604.25921', '2501.02018', '2510.13698', '2609.39902', '2512.06655', '2401.05998', '2402.03303', '2402.14020', '2404.13968', '2404.16020', '2404.16873', '2406.03589', '2407.15549', '2408.11006', '2408.11851',
          '2409.00598', '2410.02163', '2411.17075', '2412.07724', '2501.01872', '2501.14073', '2501.16534', '2501.18628', '2502.02384', '2504.07113', '2505.04388', '2505.06538', '2505.14607', '2505.14667', '2505.16186', '2505.20162',
          '2505.21784', '2506.12299', '2506.13901', '2507.03167', '2507.11878', '2509.18058', '2510.01586', '2510.11851', '2604.05179', '2603.23509', '2602.14161', '2602.04448', '2602.03402', '2602.01600', '2601.10589', '2512.07141',
          '2512.01353', '2511.16229', '2510.20129', '2509.09708', '2509.16060', '2509.14651', '2508.19697', '2508.17739', '2505.17089', '2504.01278', '2502.18935', '2501.08814', '2605.05662', '2605.24834', '2505.17132', '2502.13329',
          '2505.19911', '2603.30034', '2510.02609', '2602.21346', '2506.07022', '2509.23362', '2509.24296', '2606.11409', '2602.16346', '2605.08930', '2604.22134', '2604.12359', '2607.07918', '2605.27823', '2608.09867', '2508.15648',
          '2512.02973', '2603.14825', '2609.36956', '2510.02194', '2605.02971', '2603.24511', '2305.03495', '2306.11698', '2307.15043', '2308.09662', '2308.10741', '2309.00614', '2310.01386', '2310.02224', '2310.03693', '2310.10844',
          '2310.14303', '2310.19181', '2311.04235', '2311.05915', '2311.06899', '2311.16101', '2311.16119', '2401.01967', '2401.10647', '2401.11206', '2401.18018', '2402.02207', '2402.05162', '2402.10196', '2402.12991', '2402.15302',
          '2402.15911', '2403.09037', '2403.13031', '2404.13208', '2405.06823', '2405.09055', '2405.11647', '2405.12523', '2405.14577', '2405.19360', '2406.05946', '2406.07057', '2406.11717', '2406.12935', '2407.00075', '2407.01376',
          '2407.05965', '2407.09121', '2407.16318', '2407.16637', '2407.16997', '2408.11727', '2410.01524', '2410.02828', '2410.03769', '2410.13236', '2410.13722', '2410.13785', '2410.18210', '2411.11296', '2411.12946', '2412.00357',
          '2412.02626', '2412.09565', '2412.11041', '2412.16720', '2412.19792', '2501.15446', '2501.16497', '2502.05206', '2502.05374', '2502.07985', '2502.12202', '2502.12659', '2502.17424', '2502.19537', '2503.00224', '2503.03502',
          '2503.06269', '2503.16861', '2503.18991', '2504.01308', '2504.01550', '2504.02193', '2504.07887', '2504.10081', '2504.12562', '2505.05619', '2505.14536', '2505.20809', '2505.24621', '2505.24672', '2506.06444', '2506.07645',
          '2506.07736', '2506.08885', '2506.09600', '2506.22957', '2508.02063', '2508.12535', '2509.22067', '2510.00938', '2601.01592', '2601.11516', '2601.10387', '2601.08441', '2601.07853', '2601.22636', '2602.04581', '2602.14689',
          '2602.14364', '2602.16729', '2604.09544', '2604.16659', '2604.23775', '2604.27818', '2604.18487', '2603.27918', '2603.25176', '2603.17305', '2603.15800', '2506.15751', '2603.04355', '2603.13292', '2508.20570', '2602.06911',
          '2603.20198', '2603.06594', '2602.02600', '2601.15331', '2601.05739', '2601.03868', '2512.20293', '2601.03273', '2512.16602', '2512.15712', '2511.22047', '2511.18921', '2511.12497', '2511.09880', '2511.08379', '2511.06852',
          '2511.00203', '2510.26847', '2510.25941', '2510.19169', '2510.16794', '2510.12133', '2510.11837', '2510.01088', '2509.24393', '2509.24319', '2509.24269', '2509.21768', '2509.09660', '2509.05883', '2509.04781', '2509.01909',
          '2508.19980', '2508.18649', '2508.17540', '2508.04196', '2508.00935', '2507.22564', '2507.14987', '2507.00971', '2506.22523', '2506.19563', '2506.19140', '2506.16078', '2506.04704', '2505.23556', '2505.19773', '2505.19766',
          '2505.17306', '2505.03574', '2504.19521', '2504.15241', '2503.20279', '2503.05021', '2502.00406', '2412.16339', '2410.01606', '2406.00045', '2308.14132', '2605.12290', '2605.22984', '2511.11301', '2603.07590', '2603.22882',
          '2604.08846', '2507.06489', '2502.13095', '2502.00669', '2502.17578', '2503.01926', '2502.17254', '2502.09674', '2502.04040', '2407.18213', '2410.10414', '2405.19237', '2409.20089', '2506.06975', '2510.07985', '2505.16567',
          '2602.20170', '2602.05535', '2510.06790', '2507.04531', '2506.17052', '2606.10740', '2605.08116', '2510.11834', '2603.23268', '2606.19755', '2602.08621', '2603.15684', '2605.19966', '2606.26396', '2601.22313', '2605.25194',
          '2605.26158', '2606.31227', '2604.10299', '2604.15717', '2510.17687', '2604.15780', '2604.18660', '2508.04204', '2510.08646', '2604.21159', '2605.01913', '2604.07615', '2604.02574', '2411.16769', '2604.19001', '2605.17173',
          '2604.07223', '2509.08000', '2509.11141', '2508.03986', '2511.00509', '2505.24428', '2509.16088', '2403.09572', '2505.20309', '2609.35291', '2606.31876', '2510.05197', '2610.07532', '2610.01062', '2609.32717', '2610.16084',
          '2609.32602', '2606.22673', '2603.15647', '2605.21706', '2605.26315', '2605.08427'
      )
      OR
      (p.source = 'external' AND p.id IN (
          121679, 129071, 110425, 127990, 129651, 120852, 121258, 129430, 127992, 129976, 130600, 110123, 111492, 120673, 127042, 118647,
          124851, 125790, 120973, 110164, 125843, 128738, 130708, 110315, 110376, 120479, 125264, 126150, 127468, 128074, 128207
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
          '2503.17198', '2405.15012', '2410.23687', '2502.00299', '2502.00306', '2504.04717', '2506.04255', '2511.20494', '2604.06950', '2603.21354', '2603.04444', '2602.21236', '2601.08490', '2512.16962', '2505.16888', '2505.15420',
          '2604.09839', '2605.20266', '2506.00794', '2502.00921', '2606.21638', '2606.12716', '2603.00029', '2604.14053', '2609.14803', '2609.29429', '2610.25060', '2605.30040'
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
          '2310.12815', '2409.14729', '2604.01194', '2410.23308', '2306.05499', '2311.01011', '2312.17673', '2402.00898', '2602.06268', '2409.19521', '2410.22770', '2411.00348', '2506.05446', '2507.02735', '2604.08499', '2603.29418',
          '2603.11875', '2601.13612', '2511.20597', '2504.11358', '2508.20890', '2505.12368', '2502.16580', '2501.15145', '2603.12277', '2603.13026', '2608.05108', '2608.21500', '2302.12173', '2308.10819', '2312.14197', '2406.13352',
          '2409.13331', '2410.22284', '2501.09798', '2503.18813', '2504.11168', '2505.05849', '2506.08837', '2510.01354', '2604.28157', '2604.03598', '2602.05746', '2601.17548', '2601.11199', '2601.04795', '2507.07417', '2510.26328',
          '2510.19207', '2509.22040', '2509.05883', '2509.05831', '2504.19793', '2506.09956', '2504.18575', '2502.13141', '2410.07283', '2402.06363', '2605.31042', '2605.30837', '2605.25194', '2602.07104', '2509.07617', '2605.17634',
          '2410.13236', '2502.05174', '2510.09023', '2603.15714', '2602.10453', '2602.07918', '2602.03117', '2601.22569', '2601.17549', '2601.10923', '2601.13186', '2601.07072', '2509.22830', '2504.14348', '2506.23260', '2403.02691',
          '2512.05745', '2506.02456', '2602.01795', '2604.09024', '2509.25448', '2608.16393', '2505.11717', '2507.13686', '2609.35932', '2503.00061', '2505.14534', '2603.22489', '2507.15042', '2508.15310', '2610.08773', '2509.00088',
          '2505.21936', '2606.07131', '2603.24511', '2404.13161', '2406.03589', '2506.14866', '2510.03204', '2510.09462', '2602.07398', '2604.05179', '2602.20156', '2602.14161', '2602.05066', '2601.15528', '2511.04508', '2510.11837',
          '2505.03574', '2602.11416', '2503.10566', '2512.23128', '2607.26115', '2610.19118', '2308.03825', '2311.16119', '2403.10949', '2404.13208', '2405.20902', '2408.03837', '2410.02644', '2410.09102', '2410.16950', '2410.17520',
          '2412.01547', '2502.05206', '2502.12659', '2503.09334', '2503.11519', '2504.09593', '2504.20769', '2505.23643', '2506.04202', '2506.15674', '2508.03793', '2509.17938', '2510.05025', '2510.01586', '2510.21057', '2601.10156',
          '2601.10338', '2601.09923', '2601.07853', '2602.08995', '2603.03205', '2604.10577', '2605.01449', '2604.15415', '2604.10286', '2604.02954', '2603.27517', '2603.25176', '2603.12644', '2603.11853', '2603.11619', '2603.00991',
          '2602.20867', '2602.01129', '2601.21083', '2601.12822', '2601.12449', '2601.05755', '2601.01241', '2512.20293', '2510.19169', '2510.16794', '2510.13351', '2510.15994', '2509.23994', '2509.23694', '2510.05106', '2509.14295',
          '2509.11431', '2509.05608', '2508.19461', '2507.22304', '2507.20526', '2506.14682', '2410.13919', '2406.05498', '2309.02926', '2605.28617', '2605.30189', '2506.12104', '2509.23519', '2505.00626', '2402.17840', '2403.06833',
          '2406.19501', '2505.20435', '2507.04531', '2505.16934', '2606.20636', '2606.12716', '2510.18131', '2606.16242', '2504.21228', '2601.07185', '2604.11806', '2604.07223', '2511.12423', '2605.27823', '2508.11733', '2608.09867',
          '2608.11878', '2608.15888', '2510.11238', '2605.17380', '2609.06966', '2609.05903', '2609.17320', '2609.37040', '2610.19422', '2610.17301', '2607.05277', '2606.15308', '2603.09781', '2611.02332'
      )
      OR
      (p.source = 'external' AND p.id IN (
          104401, 127127, 127989, 129805
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
          '2307.16888', '2508.15250', '2606.13044', '2606.20922', '2405.12750', '2410.23687', '2504.10465', '2510.24801', '2603.19974', '2602.01942', '2601.12560', '2601.08490', '2601.04583', '2601.03868', '2512.16962', '2511.19483',
          '2509.15775', '2506.22183', '2505.15420', '2602.23956', '2509.17371', '2508.02110', '2407.18213', '2604.16966', '2607.21151', '2509.10122', '2604.07831', '2609.29647', '2609.29429'
      )
      OR
      (p.source = 'external' AND p.id IN (
          127116
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
