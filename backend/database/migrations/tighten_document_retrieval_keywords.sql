-- Tighten the Document Retrieval task keywords. The bare phrases "document
-- retrieval", "document search" and "page retrieval" tagged open-domain QA,
-- RAG, fact-verification and agent-memory papers that only mention retrieving
-- documents in passing. Papers whose main contribution is document retrieval
-- but that no longer match the narrower keywords keep the task as a manual tag,
-- so the weekly keyword linker cannot drop or re-add them. Rebuild the task's
-- auto tags afterwards with:
--   link_papers_by_task_keywords.py --rebuild --task-slug document-retrieval

UPDATE tasks
SET keywords = 'visual document retrieval, visually rich document retrieval, multimodal document retrieval, visual document retriever, document page retrieval, document screenshot embedding, ad hoc document retrieval, ad-hoc document retrieval, long document retrieval, legal document retrieval, generative document retrieval, PDF retrieval, late-interaction document retrieval, ViDoRe, ColPali',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'document-retrieval';

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'document-retrieval'
WHERE p.is_latest_version
  AND p.arxiv_id IN (
    '1808.06528', '2003.07820', '2005.04908', '2009.07258', '2009.07531', '2010.01195',
    '2105.03599', '2201.03720', '2202.00373', '2206.02743', '2210.06023', '2212.05276',
    '2305.15115', '2310.08319', '2311.03057', '2311.08593', '2404.04163', '2406.12336',
    '2407.10691', '2407.12325', '2409.17383', '2410.18105', '2410.20056', '2411.01106',
    '2411.05572', '2501.15245', '2502.12342', '2504.05181', '2505.02466', '2505.19312',
    '2505.21700', '2505.24782', '2506.13778', '2506.14035', '2507.10057', '2508.03644',
    '2508.07493', '2508.20778', '2509.24869', '2510.08252', '2510.11693', '2510.22215',
    '2511.01208', '2512.15922', '2602.17687', '2604.14967', '2605.30917', '2606.25343',
    '2608.25625'
  )
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';
