-- Citation review 2026-10-15. Linking every local citer of ControlNet
-- (2302.05543) and DINOv2 (2304.07193) tagged ~3.3k and ~3.6k papers, but
-- only 224 and 177 of them mention the method in their title or abstract; a
-- sample of the rest cite it in passing. Keep the source paper and the
-- citers that name the method, and exclude the reference-only remainder so
-- the hourly reference backfill does not re-link it.
CREATE TEMP TABLE pruned_method_citers ON COMMIT DROP AS
SELECT pm.paper_id, pm.method_id
FROM paper_methods pm
JOIN methods m ON m.id = pm.method_id
JOIN papers p ON p.id = pm.paper_id
WHERE m.slug IN ('controlnet', 'dinov2')
  AND pm.paper_id IS DISTINCT FROM m.source_paper_id
  AND NOT EXISTS (
        SELECT 1
        FROM paper_method_evidence e
        WHERE e.paper_id = pm.paper_id
          AND e.method_id = pm.method_id
          AND e.evidence_type <> 'reference'
  )
  AND NOT (
        coalesce(p.title, '') || ' ' || coalesce(p.abstract, '')
        ~* CASE m.slug WHEN 'controlnet' THEN 'control ?nets?' ELSE 'dino ?v2' END
  );

INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT paper_id, method_id, 'cites the source in passing; method not named in title or abstract'
FROM pruned_method_citers
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_method_evidence e
USING pruned_method_citers c
WHERE e.paper_id = c.paper_id
  AND e.method_id = c.method_id
  AND e.evidence_type = 'reference';

DELETE FROM paper_methods pm
USING pruned_method_citers c
WHERE pm.paper_id = c.paper_id
  AND pm.method_id = c.method_id;
