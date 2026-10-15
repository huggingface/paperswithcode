-- Continual learning is a learning setting, so keep it as a task
-- (/tasks/continual-learning, added 2026-10-15) and remove the bare
-- duplicate method (no description, image or source). Carry the method's
-- curated and manually reviewed paper links over to the task as manual tags
-- so a keyword rebuild cannot drop them; its other links are already
-- auto-tagged on the task. Method follows move to the task; paper_methods,
-- evidence and exclusions cascade.

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

-- research_follows has no foreign key; move method follows to the task in
-- production (public) and staging (staging schema, when present).
DO $$
DECLARE
    schema_name text;
    follows regclass;
BEGIN
    FOREACH schema_name IN ARRAY ARRAY['public', 'staging'] LOOP
        CONTINUE WHEN NOT EXISTS (
            SELECT 1 FROM pg_namespace WHERE nspname = schema_name
        ) OR NOT has_schema_privilege(schema_name, 'USAGE');
        follows := to_regclass(format('%I.research_follows', schema_name));
        CONTINUE WHEN follows IS NULL;
        EXECUTE format(
            'INSERT INTO %s (hf_subject, kind, entity_id, created_at)
             SELECT f.hf_subject, ''task'', t.id, f.created_at
             FROM %s f
             JOIN public.methods m ON m.id = f.entity_id AND m.slug = ''continual-learning''
             JOIN public.tasks t ON t.slug = ''continual-learning''
             WHERE f.kind = ''method''
             ON CONFLICT (hf_subject, kind, entity_id) DO NOTHING',
            follows, follows
        );
        EXECUTE format(
            'DELETE FROM %s f
             USING public.methods m
             WHERE f.kind = ''method''
               AND f.entity_id = m.id
               AND m.slug = ''continual-learning''',
            follows
        );
    END LOOP;
END $$;

DELETE FROM methods
WHERE slug = 'continual-learning';
