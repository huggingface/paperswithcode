-- Drop keywords that matched papers mentioning PII only in passing
-- (StarCoder, CheXpert Plus, Clinical BERT, ...); keep reviewed
-- anonymization/de-identification papers as manual tags.
UPDATE tasks SET keywords = 'PII detection, PII identification, PII extraction, PII masking, PII anonymization, PII de-identification, PII detector, PII detectors, personally identifiable information detection, detecting personally identifiable information, personally identifiable information redaction, personal information detection, personal data detection, sensitive information detection, PHI detection, protected health information detection', updated_at = CURRENT_TIMESTAMP
WHERE slug = 'pii-detection';

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual' FROM papers p, tasks t
WHERE t.slug = 'pii-detection' AND p.id IN (7832, 13912, 34074, 56291, 77403, 91108, 95110, 103094)
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

DELETE FROM paper_tasks
WHERE source = 'auto' AND paper_id IN (1968, 15416, 21778, 32024, 53172, 61989, 68673, 89222)
  AND task_id = (SELECT id FROM tasks WHERE slug = 'pii-detection');
