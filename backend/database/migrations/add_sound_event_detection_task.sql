-- Add Sound Event Detection as a top-level Audio task; production chat users
-- searched for it but the catalog had no matching task.

INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    parent_id,
    level,
    image_url,
    image_credit,
    is_visible
)
VALUES (
    'Sound Event Detection',
    'sound-event-detection',
    'Sound event detection (SED) recognizes which sound events occur in an audio recording and when, outputting class labels together with onset and offset times, often for overlapping (polyphonic) events such as speech, car engines, and rain. It extends clip-level [Audio Classification](/tasks/audio-classification) to temporal localization and is often trained with weak, clip-level labels or semi-supervised data. Sound event localization and detection (SELD) additionally estimates the direction of arrival. Systems are evaluated with event- and segment-based F1, error rate, and polyphonic sound detection score (PSDS) on the DCASE challenge datasets, DESED, AudioSet Strong, and URBAN-SED.',
    'sound event detection, polyphonic sound event detection, sound event localization and detection, sound event localisation and detection, SELD, acoustic event detection, audio event detection, weakly supervised sound event detection, DCASE, DESED',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    NULL,
    0,
    NULL,
    '[Sound Event Detection: A Tutorial](https://arxiv.org/abs/2107.05463)',
    true
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    parent_id = EXCLUDED.parent_id,
    level = EXCLUDED.level,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    is_visible = EXCLUDED.is_visible,
    updated_at = CURRENT_TIMESTAMP;
