INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'PII Detection',
    'pii-detection',
    'PII detection locates personally identifiable information, such as names, phone numbers, email and postal addresses, account and ID numbers, and health identifiers, in text, documents, or multi-turn conversations, typically as typed character spans that can then be redacted, masked, or replaced with surrogates. It is a privacy-focused relative of [Named Entity Recognition](/tasks/named-entity-recognition) that underpins data anonymization and de-identification, scrubbing of LLM training corpora and chat logs, and compliance with privacy regulations; benchmarks usually report span- or character-level precision, recall, and F1, and increasingly test context-aware detection across long conversations and many languages. See also [Membership Inference](/tasks/membership-inference) for measuring privacy leakage from trained models.',
    'PII detection, PII identification, PII extraction, PII redaction, PII masking, PII anonymization, PII de-identification, PII detector, PII detectors, personally identifiable information detection, detecting personally identifiable information, personally identifiable information redaction, personal information detection, personal data detection, sensitive information detection, text anonymization, text de-identification, clinical de-identification, clinical text de-identification, PHI de-identification, PHI detection, protected health information detection',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    0,
    NULL,
    NULL,
    '[PII-TRACE: A Benchmark for Context-Aware PII Detection in Multi-Turn LLM Conversations](/paper/2609.22200)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
