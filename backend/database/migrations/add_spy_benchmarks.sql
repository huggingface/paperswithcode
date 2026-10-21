-- Add SPY subset leaderboards ("SPY Legal Questions", "SPY Medical Consultations")
-- under task pii-detection, metric F1 (exact-match span-level, native 0-1 scale).
-- Re-runnable / idempotent; keyed by slugs and names, not ids.
-- Source paper: "SPY: Enhancing Privacy with Synthetic PII Detection Dataset"
-- (NAACL 2025 SRW), external paper row with source_url https://aclanthology.org/2025.naacl-srw.23/
BEGIN;

-- 1. Subset datasets (children of the existing combined 'spy' dataset).
INSERT INTO datasets (
    name, full_name, slug, description, short_description, url, hf_url, homepage,
    parent_dataset_id, variant_type, split_name,
    introducing_paper_id, introducing_paper_title, paper_url,
    introduced_date, introduced_year, modalities, languages
)
SELECT v.name, v.full_name, v.slug, v.description, v.short_description,
       parent.url, parent.hf_url, parent.homepage,
       parent.id, 'variant', v.split_name,
       p.id, p.title, 'https://paperswithcode.co/paper/' || COALESCE(p.arxiv_id, p.id::text),
       parent.introduced_date, parent.introduced_year, parent.modalities, parent.languages
FROM (VALUES
    ('SPY Legal Questions',
     'Synthetic PII Yesterday - Legal Questions',
     'spy-legal-questions',
     'Legal Questions subset of SPY (Synthetic PII Yesterday): legal Q&A forum style documents with synthetic PII annotated for seven types (name, address, email, phone_num, id_num, url, username). Leaderboard metric is exact-match span-level F1, where a prediction counts only if both the PII label and the character boundaries match a gold span (protocol of GLiNER2-PII, arXiv 2605.09973, Table 2: 100 evaluation documents).',
     'SPY legal-domain subset for PII detection; exact-match span-level F1.',
     'Legal Questions'),
    ('SPY Medical Consultations',
     'Synthetic PII Yesterday - Medical Consultations',
     'spy-medical-consultations',
     'Medical Consultations subset of SPY (Synthetic PII Yesterday): medical consultation transcript style documents with synthetic PII annotated for seven types (name, address, email, phone_num, id_num, url, username). Leaderboard metric is exact-match span-level F1, where a prediction counts only if both the PII label and the character boundaries match a gold span (protocol of GLiNER2-PII, arXiv 2605.09973, Table 2: 100 evaluation documents).',
     'SPY medical-domain subset for PII detection; exact-match span-level F1.',
     'Medical Consultations')
) AS v(name, full_name, slug, description, short_description, split_name)
JOIN datasets parent ON parent.slug = 'spy'
JOIN papers p ON p.source = 'external'
             AND p.source_url = 'https://aclanthology.org/2025.naacl-srw.23/'
ON CONFLICT (slug) DO NOTHING;

-- 2. Link the subsets to task pii-detection.
INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
JOIN datasets d ON d.slug IN ('spy-legal-questions', 'spy-medical-consultations')
WHERE t.slug = 'pii-detection'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

-- 3. Leaderboard metric: existing 'F1' (scale source-defined; stored on 0-1).
INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug IN ('spy-legal-questions', 'spy-medical-consultations')
JOIN metrics m ON m.name = 'F1'
WHERE t.slug = 'pii-detection'
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

-- 4. Tag the SPY source paper with pii-detection as a manual link.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'pii-detection'
WHERE p.source = 'external'
  AND p.source_url = 'https://aclanthology.org/2025.naacl-srw.23/'
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

COMMIT;
