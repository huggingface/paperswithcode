-- Add a Document Retrieval subtask under Retrieval and move the ViDoRe
-- leaderboards there from document-understanding. ViDoRe ranks retrievers on
-- page-level search over visually rich documents, which is retrieval rather
-- than document parsing or extraction. Leaderboards are keyed by (task,
-- dataset), so the task link, the leaderboard metrics, the evaluation rows and
-- the badge tombstones all move together.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id, image_credit
)
VALUES (
    'Document Retrieval',
    'document-retrieval',
    'Document retrieval ranks the documents or document pages that answer a query from a large collection. Modern systems embed whole page images with vision-language models (as in [ColPali](/paper/2407.01449)) or combine OCR text with layout, so tables, figures and charts become searchable without a brittle parsing pipeline. It is the retrieval stage of document [retrieval-augmented generation](/tasks/retrieval-augmented-generation) and builds on [Document Understanding](/tasks/document-understanding) and text [Retrieval](/tasks/retrieval).',
    'document retrieval, visual document retrieval, visually rich document retrieval, document page retrieval, page retrieval, multimodal document retrieval, PDF retrieval, document search, ViDoRe, late-interaction document retrieval',
    (SELECT area_id FROM tasks WHERE slug = 'retrieval' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'retrieval' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'retrieval' LIMIT 1),
    '[ColPali: Efficient Document Retrieval with Vision Language Models](/paper/2407.01449)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

CREATE TEMP TABLE benchmark_task_moves ON COMMIT DROP AS
SELECT d.id AS dataset_id, old_t.id AS old_task_id, new_t.id AS new_task_id, new_t.slug AS new_task_slug
FROM (
    VALUES
        ('vidore', 'document-understanding', 'document-retrieval'),
        ('vidore-v2', 'document-understanding', 'document-retrieval'),
        ('vidore-v3', 'document-understanding', 'document-retrieval')
) AS v(dataset_slug, old_task_slug, new_task_slug)
JOIN datasets d ON d.slug = v.dataset_slug
JOIN tasks old_t ON old_t.slug = v.old_task_slug
JOIN tasks new_t ON new_t.slug = v.new_task_slug;

INSERT INTO task_datasets (task_id, dataset_id, created_at, updated_at, supports_harness)
SELECT m.new_task_id, td.dataset_id, td.created_at, now(), td.supports_harness
FROM task_datasets td
JOIN benchmark_task_moves m ON m.dataset_id = td.dataset_id AND m.old_task_id = td.task_id
ON CONFLICT DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id, created_at)
SELECT m.new_task_id, tdm.dataset_id, tdm.metric_id, tdm.created_at
FROM task_dataset_metrics tdm
JOIN benchmark_task_moves m ON m.dataset_id = tdm.dataset_id AND m.old_task_id = tdm.task_id
ON CONFLICT DO NOTHING;

UPDATE evaluations e
SET task_id = m.new_task_id, updated_at = now()
FROM benchmark_task_moves m
WHERE e.dataset_id = m.dataset_id AND e.task_id = m.old_task_id;

UPDATE evaluation_badge_tombstones t
SET task_id = m.new_task_id, task_slug = m.new_task_slug
FROM benchmark_task_moves m
WHERE t.dataset_id = m.dataset_id AND t.task_id = m.old_task_id;

DELETE FROM task_dataset_metrics tdm
USING benchmark_task_moves m
WHERE tdm.dataset_id = m.dataset_id AND tdm.task_id = m.old_task_id;

DELETE FROM task_datasets td
USING benchmark_task_moves m
WHERE td.dataset_id = m.dataset_id AND td.task_id = m.old_task_id;

-- Papers with a result on a moved leaderboard belong to the new task.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT e.paper_id, m.new_task_id, 'manual'
FROM evaluations e
JOIN benchmark_task_moves m ON m.dataset_id = e.dataset_id AND m.new_task_id = e.task_id
ON CONFLICT DO NOTHING;

-- The papers that introduced the ViDoRe benchmarks.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'document-retrieval'
WHERE p.arxiv_id IN ('2407.01449', '2505.17166', '2601.08620') AND p.is_latest_version
ON CONFLICT DO NOTHING;
