-- MuSiQue benchmark on Multi-Hop Question Answering (2026-11-23 chat health
-- audit lookup miss). The leaderboard metric is Answer F1 on MuSiQue-Ans, the
-- headline metric of the source paper.

INSERT INTO datasets (
    name, full_name, slug, description, short_description, url, homepage,
    introducing_paper_id, introducing_paper_title, paper_url,
    introduced_year, license_name, abstract_linking
)
SELECT
    'MuSiQue',
    'MuSiQue: Multihop Questions via Single-hop Question Composition',
    'musique',
    'MuSiQue is a multi-hop reading comprehension benchmark of about 25K 2-4 hop questions built by composing connected single-hop questions from existing Wikipedia QA datasets. The construction filters out compositions that a single-hop model can shortcut, so answering requires connected reasoning across paragraphs; each question comes with 20 paragraphs that mix supporting and hard distractor passages. MuSiQue-Ans contains answerable questions, and MuSiQue-Full pairs each with an unanswerable contrast question. Systems are scored on answer F1 and supporting-paragraph F1, and the gap between human and model performance is much larger than on HotpotQA or 2WikiMultiHopQA.',
    'A 2-4 hop question answering benchmark composed from connected single-hop questions so that shortcuts do not work.',
    'https://github.com/StonyBrookNLP/musique',
    'https://github.com/StonyBrookNLP/musique',
    p.id,
    p.title,
    'https://paperswithcode.co/paper/' || p.arxiv_id,
    2022,
    'CC BY 4.0',
    'always'
FROM papers p
WHERE p.arxiv_id = '2108.00573'
ORDER BY p.is_latest_version DESC, p.id DESC
LIMIT 1
ON CONFLICT DO NOTHING;

UPDATE datasets d SET
    introducing_paper_id = p.id,
    introducing_paper_title = p.title,
    paper_url = 'https://paperswithcode.co/paper/' || p.arxiv_id,
    updated_at = CURRENT_TIMESTAMP
FROM papers p
WHERE d.slug = 'musique' AND p.arxiv_id = '2108.00573' AND p.is_latest_version;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t, datasets d
WHERE t.slug = 'multi-hop-question-answering' AND d.slug = 'musique'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t, datasets d, metrics m
WHERE t.slug = 'multi-hop-question-answering' AND d.slug = 'musique'
  AND m.name = 'Answer F1'
ON CONFLICT DO NOTHING;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p, tasks t
WHERE p.arxiv_id = '2108.00573' AND p.is_latest_version
  AND t.slug = 'multi-hop-question-answering'
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';
