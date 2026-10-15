-- Add Open-Set Recognition as a top-level General task; production chat users
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
    'Open-Set Recognition',
    'open-set-recognition',
    'Open-set recognition (OSR) requires a classifier to correctly label samples from the known training classes while rejecting samples from unknown classes that were never seen during training, instead of forcing them into a known label. It extends closed-set [Image Classification](/tasks/image-classification) to realistic deployments and is closely related to out-of-distribution detection in [Anomaly Detection](/tasks/anomaly-detection) and to open-world recognition. Methods calibrate confidence scores, reshape the feature space, or synthesize unknowns, and are evaluated with closed-set accuracy together with AUROC or open-set F1 on splits of MNIST, CIFAR-10, CIFAR+N, and TinyImageNet.',
    'open-set recognition, open set recognition, open-set classification, open set classification, open-world recognition, open world recognition, unknown class rejection, open-set detection, open set detection, open-set semi-supervised learning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    NULL,
    0,
    NULL,
    '[Recent Advances in Open Set Recognition: A Survey](https://arxiv.org/abs/1811.08581)',
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
