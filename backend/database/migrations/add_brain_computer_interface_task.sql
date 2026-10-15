-- Add Brain-Computer Interface as a top-level Other task; production chat users
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
    'Brain-Computer Interface',
    'brain-computer-interface',
    'Brain-computer interface (BCI) research decodes neural activity, most often non-invasive electroencephalography (EEG) and sometimes intracranial recordings, into commands, intentions, or perceptual content. Common paradigms include motor imagery, event-related potentials such as P300, and steady-state visually evoked potentials, alongside broader EEG decoding of speech, images, and emotion. Models must cope with low signal-to-noise ratios and large subject-to-subject variability, motivating compact convolutional networks, transfer learning, and EEG foundation models. Related tasks include [Emotion Recognition](/tasks/emotion-recognition) and [Time Series Classification](/tasks/time-series-classification).',
    'brain-computer interface, brain-computer interfaces, brain computer interface, brain-machine interface, BCI, EEG decoding, EEG classification, EEG-based classification, motor imagery, motor imagery classification, motor imagery decoding, P300 speller, SSVEP, steady-state visual evoked potential, EEG foundation model',
    (SELECT id FROM areas WHERE name = 'Other' LIMIT 1),
    NULL,
    0,
    NULL,
    '[EEGNet: A Compact Convolutional Network for EEG-based Brain-Computer Interfaces](https://arxiv.org/abs/1611.08024)',
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
