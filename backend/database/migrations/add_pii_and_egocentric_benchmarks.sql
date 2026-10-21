-- Benchmarks added on 2026-10-21 for the new PII Detection and Egocentric Vision tasks.
-- Already applied to production. Evaluation rows were imported separately.

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('Character F1', 'Character-level F1', 'higher_is_better', 'Label-agnostic F1 over PII character positions: precision and recall of predicted vs gold PII characters (PII-TRACE main metric). 0-1 fraction.', '0-1')
ON CONFLICT (name) DO NOTHING;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('Consistent Detection', 'Consistent Detection (CD)', 'higher_is_better', 'Entity-level PII coverage: fraction of gold identifier clusters (entities) whose every mention is detected across the conversation (PII-TRACE). 0-1 fraction.', '0-1')
ON CONFLICT (name) DO NOTHING;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('Strict-F1', 'Strict F1', 'higher_is_better', 'F1 requiring the predicted PII entity span, its subject attribution, and its PII type to all match the ground truth (PII-Bench protocol).', '0-1')
ON CONFLICT (name) DO NOTHING;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('Entity Recall (Direct IDs)', 'Entity-level Recall on Direct Identifiers (ER_di)', 'higher_is_better', 'TAB entity-level recall on direct identifiers, micro-averaged over all annotators; an entity counts as protected only if all of its mentions are masked (Pilán et al. 2022, Eq. 1). Native 0-1 scale.', '0-1')
ON CONFLICT (name) DO NOTHING;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('Entity Recall (Quasi IDs)', 'Entity-level Recall on Quasi-Identifiers (ER_qi)', 'higher_is_better', 'TAB entity-level recall on quasi-identifiers, micro-averaged over all annotators; an entity counts as protected only if all of its mentions are masked (Pilán et al. 2022, Eq. 2). Native 0-1 scale.', '0-1')
ON CONFLICT (name) DO NOTHING;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('Weighted Precision (Direct+Quasi IDs)', 'Information-content-weighted Token Precision on Direct and Quasi-Identifiers (WP_di+qi)', 'higher_is_better', 'TAB token-level precision on all masked identifiers, with each masked token weighted by its BERT-estimated information content and micro-averaged over annotators (Pilán et al. 2022, Eq. 4). Native 0-1 scale.', '0-1')
ON CONFLICT (name) DO NOTHING;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('ED@20 Verb', 'Edit distance at Z=20 (verb)', 'lower_is_better', 'Ego4D long-term action anticipation: minimum Damerau-Levenshtein edit distance, normalized by sequence length, between the ground-truth future sequence of Z=20 verbs and the best of K=5 predicted sequences. Lower is better; reported on a 0-1 scale.', '0-1')
ON CONFLICT (name) DO NOTHING;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('ED@20 Noun', 'Edit distance at Z=20 (noun)', 'lower_is_better', 'Ego4D long-term action anticipation: minimum normalized Damerau-Levenshtein edit distance between the ground-truth future sequence of Z=20 nouns and the best of K=5 predicted sequences. Lower is better; reported on a 0-1 scale.', '0-1')
ON CONFLICT (name) DO NOTHING;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('ED@20 Action', 'Edit distance at Z=20 (action)', 'lower_is_better', 'Ego4D long-term action anticipation: minimum normalized Damerau-Levenshtein edit distance between the ground-truth future sequence of Z=20 (verb, noun) actions and the best of K=5 predicted sequences; an action is correct only if both verb and noun match. Lower is better; reported on a 0-1 scale.', '0-1')
ON CONFLICT (name) DO NOTHING;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('mAP Avg IoU=0.1:0.5', 'Mean average precision averaged over temporal IoU 0.1-0.5', 'higher_is_better', 'Official Ego4D Moments Queries metric: mean average precision over moment categories, averaged over temporal IoU thresholds 0.1, 0.2, 0.3, 0.4 and 0.5. Percent scale.', '0-100')
ON CONFLICT (name) DO NOTHING;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('stAP@0.25', 'Spatio-temporal average precision at IoU 0.25', 'higher_is_better', 'Ego4D Visual Queries 2D: spatio-temporal average precision of the predicted response track (per-frame boxes) at spatio-temporal IoU threshold 0.25. Native 0-1 scale.', '0-1')
ON CONFLICT (name) DO NOTHING;

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES ('tAP@0.25', 'Temporal average precision at IoU 0.25', 'higher_is_better', 'Ego4D Visual Queries 2D: temporal average precision of the predicted response-track extent at temporal IoU threshold 0.25. Native 0-1 scale.', '0-1')
ON CONFLICT (name) DO NOTHING;

INSERT INTO datasets (slug, introducing_paper_id, name, full_name, description, url, hf_url, short_description, homepage, license_name, license_url, introduced_date, introduced_year, modalities, languages, warning, split_name, variant_type, paper_url)
VALUES ('hd-epic-vqa', (SELECT id FROM papers WHERE arxiv_id = '2502.04144' AND is_latest_version LIMIT 1), 'HD-EPIC VQA', 'HD-EPIC VQA Benchmark', 'Video question answering benchmark built on HD-EPIC, a highly detailed egocentric kitchen video dataset (41 hours, 9 participants, digital-twin kitchens). It contains 26,650 five-way multiple-choice questions generated from 30 prototypes across 7 categories: Recipe, Ingredient, Nutrition, Fine-grained Action, 3D Perception, Object Motion, and Gaze, with inputs ranging from single frames to 7+ hours of video. The leaderboard metric is overall accuracy (%), the average of the 7 per-category accuracies (each averaged over its prototypes), as reported in Table 2 of the HD-EPIC paper. Chance is 20%. Rows must use the full video-input benchmark; blind/language-only, ground-truth-narration, or category subset results are not comparable.', 'https://hd-epic.github.io/', NULL, '26,650 five-way multiple-choice VQA questions over long egocentric kitchen videos (7 categories, 30 prototypes).', 'https://hd-epic.github.io/', NULL, NULL, '2025-02-06', 2025, '["Video", "Text"]'::jsonb, NULL, NULL, NULL, NULL, 'https://paperswithcode.co/paper/2502.04144')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d WHERE t.slug = 'egocentric-vision' AND d.slug = 'hd-epic-vqa'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'egocentric-vision' AND d.slug = 'hd-epic-vqa' AND m.name = 'Accuracy'
ON CONFLICT DO NOTHING;

INSERT INTO datasets (slug, introducing_paper_id, name, full_name, description, url, hf_url, short_description, homepage, license_name, license_url, introduced_date, introduced_year, modalities, languages, warning, split_name, variant_type, paper_url)
VALUES ('pii-trace', (SELECT id FROM papers WHERE arxiv_id = '2609.22200' AND is_latest_version LIMIT 1), 'PII-TRACE', 'PII-TRACE (Tracing Recurring PII Across Conversational Exchanges)', 'PII-TRACE is a benchmark for context-aware PII detection in multi-turn LLM conversations. It contains 13,148 synthetic multi-turn dialogues in 13 languages annotated with character-level spans for nine identifier types and cross-turn identifier clusters, so detectors are scored both on character-level precision/recall/F1 and on whether they consistently cover every mention of a recurring identifier across turns. The test split has 1,922 conversations, including PII-free conversations for false-positive measurement.', 'https://huggingface.co/datasets/perplexity-ai/PII-TRACE', 'https://huggingface.co/datasets/perplexity-ai/PII-TRACE', 'Multi-turn conversational PII detection benchmark (13,148 dialogues, 13 languages) with character spans and cross-turn identifier clusters.', NULL, NULL, NULL, '2026-08-31', 2026, '["Text"]'::jsonb, NULL, NULL, NULL, NULL, 'https://paperswithcode.co/paper/2609.22200')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d WHERE t.slug = 'pii-detection' AND d.slug = 'pii-trace'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'pii-detection' AND d.slug = 'pii-trace' AND m.name = 'Character F1'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'pii-detection' AND d.slug = 'pii-trace' AND m.name = 'Consistent Detection'
ON CONFLICT DO NOTHING;

INSERT INTO datasets (slug, introducing_paper_id, name, full_name, description, url, hf_url, short_description, homepage, license_name, license_url, introduced_date, introduced_year, modalities, languages, warning, split_name, variant_type, paper_url)
VALUES ('pii-bench-query-aware', (SELECT id FROM papers WHERE arxiv_id = '2502.18545' AND is_latest_version LIMIT 1), 'PII-Bench (Query-Aware)', 'PII-Bench: Evaluating Query-Aware Privacy Protection Systems', 'PII-Bench evaluates privacy protection systems that must detect and mask personally identifiable information in user prompts while preserving PII needed to answer the query. It has 2,842 samples covering 55 fine-grained PII categories across four subsets: PII-Single (1,214 single-subject description-query pairs), PII-Multi (1,228 multi-subject pairs), PII-Hard (200) and PII-Distract (200). This leaderboard uses the PII detection task on PII-Single, scored by Strict-F1 (subject, span and PII type must all match). Distinct from PIIBench (arXiv 2604.15776).', 'https://arxiv.org/abs/2502.18545', NULL, 'Query-aware PII detection and masking benchmark (Fudan University). Leaderboard reports Strict-F1 on the PII-Single subset.', NULL, NULL, NULL, '2025-02-25', 2025, '["text"]'::jsonb, '["en"]'::jsonb, NULL, 'PII-Single', 'subset', 'https://paperswithcode.co/paper/2502.18545')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d WHERE t.slug = 'pii-detection' AND d.slug = 'pii-bench-query-aware'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'pii-detection' AND d.slug = 'pii-bench-query-aware' AND m.name = 'Strict-F1'
ON CONFLICT DO NOTHING;

INSERT INTO datasets (slug, introducing_paper_id, name, full_name, description, url, hf_url, short_description, homepage, license_name, license_url, introduced_date, introduced_year, modalities, languages, warning, split_name, variant_type, paper_url)
VALUES ('piibench', (SELECT id FROM papers WHERE arxiv_id = '2604.15776' AND is_latest_version LIMIT 1), 'PIIBench', 'PIIBench: A Unified Multi-Source Benchmark Corpus for PII Detection', 'PIIBench is a unified benchmark corpus for Personally Identifiable Information (PII) detection that consolidates ten public datasets (synthetic PII corpora, multilingual NER benchmarks, and financial-domain text) into 2,369,883 annotated sequences and 3.35M entity mentions across 48 canonical PII entity types in a standardized BIO tagging scheme, with stratified 80/10/10 splits. Leaderboard results are span-level seqeval micro F1 (exact span and type match) on the 1,398-record stratified 1% test subset.', 'https://github.com/pritesh-2711/pii-bench', 'https://huggingface.co/datasets/Pritesh-2711/pii-bench', 'Unified multi-source PII detection benchmark: 48 canonical PII entity types in BIO format from ten consolidated datasets; span-level seqeval F1 on the stratified 1% test subset.', 'https://github.com/pritesh-2711/pii-bench', 'Apache-2.0', 'https://github.com/pritesh-2711/pii-bench/blob/main/LICENSE', '2026-04-17', 2026, '["Text"]'::jsonb, NULL, NULL, 'test (1% stratified subset)', 'split', 'https://paperswithcode.co/paper/2604.15776')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d WHERE t.slug = 'pii-detection' AND d.slug = 'piibench'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'pii-detection' AND d.slug = 'piibench' AND m.name = 'F1'
ON CONFLICT DO NOTHING;

INSERT INTO datasets (slug, introducing_paper_id, name, full_name, description, url, hf_url, short_description, homepage, license_name, license_url, introduced_date, introduced_year, modalities, languages, warning, split_name, variant_type, paper_url)
VALUES ('charades-ego', (SELECT id FROM papers WHERE arxiv_id = '1804.09626' AND is_latest_version LIMIT 1), 'Charades-Ego', 'Charades-Ego — First-Person Action Recognition (Egocentric Test Set)', 'Charades-Ego contains 7,860 paired first- and third-person videos (68,536 activity instances, 68.8 hours) of scripted everyday indoor activities, sharing the 157 action classes of Charades. This leaderboard covers multi-label action recognition on the first-person (egocentric) subset: models are trained or fine-tuned on the ~3,085 first-person training videos and evaluated on the ~846 first-person test videos with video-level mean Average Precision (mAP). Zero-shot transfer results and third-person test results are a different protocol and do not belong on this leaderboard.', NULL, NULL, 'Charades-Ego first-person action recognition, fine-tuned on egocentric training videos and evaluated with video-level mAP on the egocentric test set.', NULL, NULL, NULL, '2018-04-25', 2018, '["Videos"]'::jsonb, NULL, 'Only fine-tuned/supervised first-person results on the Charades-Ego egocentric test set (video-level mAP) belong here. Exclude zero-shot evaluation and third-person test-set results.', 'First-person test set', NULL, 'https://paperswithcode.co/paper/1804.09626')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d WHERE t.slug = 'egocentric-vision' AND d.slug = 'charades-ego'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'egocentric-vision' AND d.slug = 'charades-ego' AND m.name = 'mAP'
ON CONFLICT DO NOTHING;

INSERT INTO datasets (slug, introducing_paper_id, name, full_name, description, url, hf_url, short_description, homepage, license_name, license_url, introduced_date, introduced_year, modalities, languages, warning, split_name, variant_type, paper_url)
VALUES ('text-anonymization-benchmark', (SELECT id FROM papers WHERE arxiv_id = '2202.00443' AND is_latest_version LIMIT 1), 'Text Anonymization Benchmark (TAB)', 'The Text Anonymization Benchmark (TAB)', 'TAB is an English corpus of 1,268 European Court of Human Rights court cases manually annotated with personal identifiers, their semantic category, need for masking (direct identifier, quasi-identifier or no mask), confidential attributes and co-reference relations, with multiple annotators per document. It ships train/dev/test splits and an evaluation framework that scores anonymization systems with entity-level recall on direct (ER_di) and quasi-identifiers (ER_qi) and an information-weighted token precision (WP_di+qi), micro-averaged over annotators. Leaderboard results use the test split.', 'https://github.com/NorskRegnesentral/text-anonymization-benchmark', 'https://huggingface.co/datasets/ildpil/text-anonymization-benchmark', 'Text anonymization benchmark of 1,268 ECHR court cases annotated with direct and quasi-identifiers.', 'https://github.com/NorskRegnesentral/text-anonymization-benchmark', 'MIT', 'https://github.com/NorskRegnesentral/text-anonymization-benchmark/blob/master/LICENSE.txt', '2022-01-25', 2022, '["text"]'::jsonb, '["en"]'::jsonb, NULL, NULL, NULL, 'https://paperswithcode.co/paper/2202.00443')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d WHERE t.slug = 'pii-detection' AND d.slug = 'text-anonymization-benchmark'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'pii-detection' AND d.slug = 'text-anonymization-benchmark' AND m.name = 'Entity Recall (Direct IDs)'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'pii-detection' AND d.slug = 'text-anonymization-benchmark' AND m.name = 'Entity Recall (Quasi IDs)'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'pii-detection' AND d.slug = 'text-anonymization-benchmark' AND m.name = 'Weighted Precision (Direct+Quasi IDs)'
ON CONFLICT DO NOTHING;

INSERT INTO datasets (slug, introducing_paper_id, name, full_name, description, url, hf_url, short_description, homepage, license_name, license_url, introduced_date, introduced_year, modalities, languages, warning, split_name, variant_type, paper_url)
VALUES ('i2b2-2014-de-identification', (SELECT id FROM papers WHERE source = 'external' AND source_url = 'https://pmc.ncbi.nlm.nih.gov/articles/PMC4978170/pdf/nihms806528.pdf' LIMIT 1), 'i2b2 2014 De-identification', '2014 i2b2/UTHealth De-identification (n2c2 2014 Track 1)', 'The de-identification track (Track 1) of the 2014 i2b2/UTHealth NLP shared task (now distributed via n2c2/DBMI Data Portal). The corpus contains 1,304 longitudinal clinical narratives for 296 diabetic patients from Partners HealthCare, annotated for protected health information (PHI) under a broad interpretation of HIPAA with 7 categories and 25 sub-categories (names, professions, locations, ages, dates, contact details, IDs), and PHI replaced with realistic surrogates. The standard split is 790 training records and 514 test records. Systems are ranked by entity-based (strict span match) micro-averaged F1 over PHI on the official test set.', 'https://portal.dbmi.hms.harvard.edu/projects/n2c2-nlp/', NULL, 'Clinical PHI de-identification on 1,304 longitudinal medical records (i2b2/UTHealth 2014 Track 1), scored by entity-level strict micro F1.', 'https://portal.dbmi.hms.harvard.edu/projects/n2c2-nlp/', NULL, NULL, '2015-08-28', 2014, '["text"]'::jsonb, '["en"]'::jsonb, NULL, 'test', NULL, 'https://paperswithcode.co/paper/123914')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d WHERE t.slug = 'pii-detection' AND d.slug = 'i2b2-2014-de-identification'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'pii-detection' AND d.slug = 'i2b2-2014-de-identification' AND m.name = 'Micro F1'
ON CONFLICT DO NOTHING;

INSERT INTO datasets (slug, introducing_paper_id, name, full_name, description, url, hf_url, short_description, homepage, license_name, license_url, introduced_date, introduced_year, modalities, languages, warning, split_name, variant_type, paper_url)
VALUES ('ego4d-lta-test', (SELECT id FROM papers WHERE arxiv_id = '2110.07058' AND is_latest_version LIMIT 1), 'Ego4D LTA Test', 'Ego4D Long-Term Action Anticipation (Test)', 'Ego4D Long-Term Action Anticipation (LTA) asks a model to watch an egocentric video clip and predict the next Z=20 future actions as (verb, noun) sequences, producing K=5 candidate sequences. This leaderboard uses the official held-out test set (evaluated on the Ego4D challenge server; Ego4D v1 and v2 share the same LTA test set) and reports edit distance ED@20 for verbs, nouns and actions, where lower is better. Rows trained only on the smaller v1 training split are marked "(v1 train)".', 'https://ego4d-data.org/docs/benchmarks/forecasting/', NULL, NULL, 'https://github.com/EGO4D/forecasting', NULL, NULL, '2021-10-13', 2021, NULL, NULL, NULL, 'test', NULL, 'https://paperswithcode.co/paper/2110.07058')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d WHERE t.slug = 'egocentric-vision' AND d.slug = 'ego4d-lta-test'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d WHERE t.slug = 'action-anticipation' AND d.slug = 'ego4d-lta-test'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'action-anticipation' AND d.slug = 'ego4d-lta-test' AND m.name = 'ED@20 Verb'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'egocentric-vision' AND d.slug = 'ego4d-lta-test' AND m.name = 'ED@20 Verb'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'action-anticipation' AND d.slug = 'ego4d-lta-test' AND m.name = 'ED@20 Noun'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'egocentric-vision' AND d.slug = 'ego4d-lta-test' AND m.name = 'ED@20 Noun'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'action-anticipation' AND d.slug = 'ego4d-lta-test' AND m.name = 'ED@20 Action'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'egocentric-vision' AND d.slug = 'ego4d-lta-test' AND m.name = 'ED@20 Action'
ON CONFLICT DO NOTHING;

INSERT INTO datasets (slug, introducing_paper_id, name, full_name, description, url, hf_url, short_description, homepage, license_name, license_url, introduced_date, introduced_year, modalities, languages, warning, split_name, variant_type, paper_url)
VALUES ('ego4d-mq-validation', (SELECT id FROM papers WHERE arxiv_id = '2110.07058' AND is_latest_version LIMIT 1), 'Ego4D MQ Validation', 'Ego4D Moments Queries (Validation)', 'Ego4D Moments Queries (MQ) is an episodic-memory temporal action localization task: given a long egocentric video and a query activity category from a 110-class taxonomy, localize all temporal segments where the camera wearer performs that activity. This leaderboard is restricted to the official validation split and reports mAP averaged over temporal IoU thresholds 0.1-0.5 and Recall@1 at temporal IoU 0.5.', 'https://ego4d-data.org/docs/benchmarks/episodic-memory/', NULL, NULL, 'https://github.com/EGO4D/episodic-memory', NULL, NULL, '2021-10-13', 2021, NULL, NULL, NULL, 'validation', NULL, 'https://paperswithcode.co/paper/2110.07058')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d WHERE t.slug = 'egocentric-vision' AND d.slug = 'ego4d-mq-validation'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'egocentric-vision' AND d.slug = 'ego4d-mq-validation' AND m.name = 'R@1 IoU=0.5'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'egocentric-vision' AND d.slug = 'ego4d-mq-validation' AND m.name = 'mAP Avg IoU=0.1:0.5'
ON CONFLICT DO NOTHING;

INSERT INTO datasets (slug, introducing_paper_id, name, full_name, description, url, hf_url, short_description, homepage, license_name, license_url, introduced_date, introduced_year, modalities, languages, warning, split_name, variant_type, paper_url)
VALUES ('ego4d-vq2d-validation', (SELECT id FROM papers WHERE arxiv_id = '2110.07058' AND is_latest_version LIMIT 1), 'Ego4D VQ2D Validation', 'Ego4D Visual Queries 2D Localization (Validation)', 'Ego4D Visual Queries 2D (VQ2D) asks a model, given a long egocentric video and a visual crop of an object, to find the last time the object was seen and return its response track as a sequence of 2D boxes. This leaderboard is restricted to the official validation split and reports spatio-temporal AP (stAP@0.25), temporal AP (tAP@0.25), and success rate (percentage of queries whose predicted response track overlaps the ground truth with stIoU > 0.05).', 'https://ego4d-data.org/docs/benchmarks/episodic-memory/', NULL, NULL, 'https://github.com/EGO4D/episodic-memory', NULL, NULL, '2021-10-13', 2021, NULL, NULL, NULL, 'validation', NULL, 'https://paperswithcode.co/paper/2110.07058')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE FROM tasks t, datasets d WHERE t.slug = 'egocentric-vision' AND d.slug = 'ego4d-vq2d-validation'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'egocentric-vision' AND d.slug = 'ego4d-vq2d-validation' AND m.name = 'Success Rate'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'egocentric-vision' AND d.slug = 'ego4d-vq2d-validation' AND m.name = 'stAP@0.25'
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id FROM tasks t, datasets d, metrics m
WHERE t.slug = 'egocentric-vision' AND d.slug = 'ego4d-vq2d-validation' AND m.name = 'tAP@0.25'
ON CONFLICT DO NOTHING;

-- Tag each benchmark's introducing paper with the benchmark's tasks.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT d.introducing_paper_id, td.task_id, 'manual'
FROM datasets d
JOIN task_datasets td ON td.dataset_id = d.id
WHERE d.slug IN ('pii-trace', 'piibench', 'pii-bench-query-aware', 'text-anonymization-benchmark',
                 'i2b2-2014-de-identification', 'charades-ego', 'hd-epic-vqa', 'ego4d-lta-test',
                 'ego4d-mq-validation', 'ego4d-vq2d-validation')
  AND d.introducing_paper_id IS NOT NULL
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';
