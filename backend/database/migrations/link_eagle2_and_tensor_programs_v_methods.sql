-- EAGLE-2 (2406.16858) is covered by the eagle method and Tensor Programs V
-- (2203.03466) introduced muTransfer on top of muP; tag both as manual links.
INSERT INTO paper_methods (paper_id, method_id)
SELECT p.id, m.id
FROM papers p
JOIN methods m ON (m.slug, p.arxiv_id) IN (('eagle', '2406.16858'), ('mup', '2203.03466'))
WHERE p.is_latest_version
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT p.id, m.id, 'manual'
FROM papers p
JOIN methods m ON (m.slug, p.arxiv_id) IN (('eagle', '2406.16858'), ('mup', '2203.03466'))
WHERE p.is_latest_version
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
