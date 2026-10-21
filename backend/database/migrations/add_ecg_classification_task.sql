-- Added 2026-10-21 because production chat users looked it up with
-- pwc_get_task and it was missing from the catalog.

INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    level,
    parent_id,
    image_url,
    image_credit,
    useful_leaderboards
)
VALUES (
    'ECG Classification',
    'ecg-classification',
    'ECG classification assigns diagnostic labels to electrocardiogram recordings, such as normal sinus rhythm, atrial fibrillation or other arrhythmias, from single-lead or 12-lead signals. Deep models, mostly 1D convolutional networks and Transformers, now match or exceed cardiologists on rhythm classification and are trained on datasets such as the MIT-BIH Arrhythmia Database, PhysioNet/CinC challenges and PTB-XL. It is a [time series classification](/tasks/time-series-classification) problem with direct clinical use.',
    'ECG classification, electrocardiogram classification, ECG arrhythmia classification, ECG arrhythmia detection, arrhythmia classification, arrhythmia detection, ECG signal classification, heartbeat classification, atrial fibrillation detection, 12-lead ECG, ECG diagnosis',
    (SELECT id FROM areas WHERE name = 'Other' LIMIT 1),
    0,
    NULL,
    NULL,
    '[Cardiologist-Level Arrhythmia Detection with Convolutional Neural Networks](/paper/1707.01836)',
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
