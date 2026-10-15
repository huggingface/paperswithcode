-- Continual learning is a learning setting, so keep it as a task
-- (/tasks/continual-learning, added 2026-10-15) and remove the bare
-- duplicate method (no description, image or source). Carry the method's
-- curated and manually reviewed paper links over to the task as manual tags
-- so a keyword rebuild cannot drop them; its other links are already
-- auto-tagged on the task. paper_methods, evidence and exclusions cascade.

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT pm.paper_id, t.id, 'manual'
FROM paper_methods pm
JOIN methods m ON m.id = pm.method_id AND m.slug = 'continual-learning'
JOIN tasks t ON t.slug = 'continual-learning'
WHERE EXISTS (
    SELECT 1 FROM paper_method_evidence e
    WHERE e.paper_id = pm.paper_id
      AND e.method_id = pm.method_id
      AND e.evidence_type IN ('curation', 'manual')
)
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT pm.paper_id, t.id, 'auto'
FROM paper_methods pm
JOIN methods m ON m.id = pm.method_id AND m.slug = 'continual-learning'
JOIN tasks t ON t.slug = 'continual-learning'
ON CONFLICT (paper_id, task_id) DO NOTHING;

DELETE FROM methods
WHERE slug = 'continual-learning';
