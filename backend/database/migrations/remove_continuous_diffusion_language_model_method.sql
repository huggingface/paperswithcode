-- Remove the Continuous Diffusion Language Model method. The broader
-- continuous-language-model method (continuous diffusion and flow language
-- models) now covers the same family with reviewed paper links. Every true
-- continuous-LM paper on the old method is already linked there. Its other
-- links came from Diffusion-LM citers and were mostly discrete diffusion LMs:
-- the reviewed DLM papers move to diffusion-language-model-dlm as manual
-- links, the rest are dropped. Run with a raw DBAPI cursor.

UPDATE methods
SET aliases = ARRAY['Continuous Diffusion Language Model', 'Continuous Flow Language Model', 'Flow Language Model', 'Flow Map Language Model'],
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'continuous-language-model';

UPDATE methods
SET description = replace(
        replace(description, '[diffusion](/methods/continuous-diffusion-language-model)', '[diffusion](/methods/diffusion)'),
        '/methods/continuous-diffusion-language-model', '/methods/continuous-language-model'),
    updated_at = CURRENT_TIMESTAMP
WHERE description LIKE '%/methods/continuous-diffusion-language-model%';

CREATE TEMP TABLE cdlm_to_dlm ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
JOIN methods old ON old.slug = 'continuous-diffusion-language-model'
JOIN paper_methods pm ON pm.paper_id = p.id AND pm.method_id = old.id
CROSS JOIN methods m
WHERE m.slug = 'diffusion-language-model-dlm'
  AND p.arxiv_id IN (
      '2606.15805', -- Mean-Field Parallel Decoding for Discrete Diffusion Language Models
      '2605.24173', -- Extracting Training Data from Diffusion Language Models via Infilling
      '2603.02333', -- Characterizing Memorization in Diffusion Language Models
      '2608.23167', -- Accelerating Diffusion Language Models via Structured Suffix Modeling
      '2601.22629', -- Denoising Time Matters: Diverse Generation in Diffusion Language Models
      '2602.22871', -- Test-Time Scaling with Diffusion Language Models via Reward-Guided Stitching
      '2605.29727'  -- BASTION: Budget-Aware Speculative Decoding with Block Diffusion Drafting
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM cdlm_to_dlm
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM cdlm_to_dlm
ON CONFLICT (paper_id, method_id, evidence_type) DO NOTHING;

-- research_follows has no foreign key; move method follows to the new method.
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
             SELECT f.hf_subject, ''method'', n.id, f.created_at
             FROM %s f
             JOIN public.methods o ON o.id = f.entity_id AND o.slug = ''continuous-diffusion-language-model''
             JOIN public.methods n ON n.slug = ''continuous-language-model''
             WHERE f.kind = ''method''
             ON CONFLICT (hf_subject, kind, entity_id) DO NOTHING',
            follows, follows
        );
        EXECUTE format(
            'DELETE FROM %s f
             USING public.methods m
             WHERE f.kind = ''method''
               AND f.entity_id = m.id
               AND m.slug = ''continuous-diffusion-language-model''',
            follows
        );
    END LOOP;
END $$;

-- Evidence and abstract mentions have no foreign key to methods.
DELETE FROM paper_method_evidence e
USING methods m
WHERE e.method_id = m.id AND m.slug = 'continuous-diffusion-language-model';

DELETE FROM paper_abstract_mentions a
USING methods m
WHERE a.entity_type = 'method' AND a.entity_id = m.id
  AND m.slug = 'continuous-diffusion-language-model';

-- paper_methods, exclusions and reference-backfill months cascade.
DELETE FROM methods
WHERE slug = 'continuous-diffusion-language-model';
