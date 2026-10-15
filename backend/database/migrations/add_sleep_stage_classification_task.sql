-- Add Sleep Stage Classification as a top-level Other task; production chat users
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
    'Sleep Stage Classification',
    'sleep-stage-classification',
    'Sleep stage classification (sleep staging) automatically scores polysomnography recordings, such as EEG, EOG, and EMG signals, into sleep stages (Wake, N1, N2, N3, and REM), usually for consecutive 30-second epochs. Automated staging replaces time-consuming manual scoring by sleep experts and supports diagnosis of sleep disorders and wearable sleep monitoring. Models combine convolutional feature extraction with sequence modelling across epochs and are evaluated with accuracy, macro F1, and Cohen''s kappa on datasets such as Sleep-EDF, SHHS, and MASS. It is a specialized form of [Time Series Classification](/tasks/time-series-classification) within [Healthcare](/tasks/healthcare).',
    'sleep stage classification, sleep staging, automatic sleep staging, sleep stage scoring, sleep scoring, automatic sleep scoring, sleep stage detection, polysomnography, Sleep-EDF',
    (SELECT id FROM areas WHERE name = 'Other' LIMIT 1),
    NULL,
    0,
    NULL,
    '[U-Time: A Fully Convolutional Network for Time Series Segmentation Applied to Sleep Staging](https://arxiv.org/abs/1910.11162)',
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
