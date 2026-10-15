-- Add AlexNet method, sourced from the NeurIPS 2012 paper (external paper
-- row 83650, no arXiv id).

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'alexnet',
    'AlexNet',
    'AlexNet',
    'AlexNet is the deep [convolutional neural network](/methods/cnn) of Krizhevsky, Sutskever and Hinton that won the ImageNet ILSVRC-2012 classification challenge and set off the deep learning era in computer vision. It has eight learned layers, five [convolutional](/methods/convolution) and three fully connected, with about 60 million parameters, and was split across two GTX 580 GPUs that communicate only at certain layers. Its key ingredients were ReLU activations for fast training, overlapping [max pooling](/methods/max-pooling), local response normalization, aggressive data augmentation and [dropout](/methods/dropout) in the fully connected layers. AlexNet reached a 15.3% top-5 test error in ILSVRC-2012 against 26.2% for the runner-up. Later CNNs such as VGG, GoogLeNet and [ResNet](/methods/resnet) built directly on its design.',
    'AlexNet',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2012,
    (
        SELECT id
        FROM papers
        WHERE source = 'external'
          AND title = 'ImageNet Classification with Deep Convolutional Neural Networks'
          AND is_latest_version
        ORDER BY id DESC
        LIMIT 1
    ),
    NULL,
    'ImageNet Classification with Deep Convolutional Neural Networks',
    'https://github.com/pytorch/vision/blob/main/torchvision/models/alexnet.py',
    NULL,
    '[ImageNet Classification with Deep Convolutional Neural Networks](/paper/83650)'
)
ON CONFLICT (slug) DO UPDATE
SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id
FROM methods
WHERE slug = 'alexnet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'alexnet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
