-- Chat lookup-miss taxonomy gap fill (2026-11-09 audit): tasks.
-- Hero images are imported separately with import_entity_image.py.

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Image Colorization',
    'image-colorization',
    'Image colorization predicts plausible colors for a grayscale image, sketch, or line drawing. Because many colorings are valid, methods range from regression and classification over color bins to GANs, diffusion models, and exemplar- or text-guided systems that let a user steer the result. The same models restore historical photos and film, and extend to video colorization with temporal consistency. Related: [Image Restoration](/tasks/image-restoration), [Image Generation](/tasks/image-generation).',
    'image colorization, video colorization, automatic colorization, exemplar-based colorization, grayscale image colorization, line art colorization, sketch colorization, colorization',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Visual Geo-Localization',
    'visual-geo-localization',
    'Visual geo-localization estimates where a photo was taken. Retrieval approaches match a query image against a geo-tagged database, either of the same view (visual place recognition) or of a different view, as in cross-view geo-localization that matches street-level or drone images to satellite imagery. Classification approaches predict a cell or coordinates on the globe directly. Related: [Image Retrieval](/tasks/image-retrieval), [Remote Sensing](/tasks/remote-sensing).',
    'visual geo-localization, cross-view geo-localization, cross-view image geo-localization, image geo-localization, image geolocalization, visual place recognition, drone-view geo-localization, UAV geo-localization, photo geolocation, worldwide image geolocation',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Fine-Grained Image Classification',
    'fine-grained-image-classification',
    'Fine-grained image classification separates visually similar subcategories of one object class, such as bird species, car models, aircraft variants, or flower types. Differences are small and local, so methods emphasize discriminative part localization, attention, high-resolution features, and strong pretrained backbones. Standard benchmarks include CUB-200-2011, Stanford Cars, FGVC-Aircraft, and Oxford Flowers. Related: [Image Classification](/tasks/image-classification).',
    'fine-grained image classification, fine-grained visual classification, fine-grained visual categorization, fine-grained image recognition, fine-grained visual recognition, fine-grained object recognition, FGVC',
    (SELECT area_id FROM tasks WHERE slug = 'image-classification'),
    (SELECT level + 1 FROM tasks WHERE slug = 'image-classification'),
    (SELECT id FROM tasks WHERE slug = 'image-classification')
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Medical Image Classification',
    'medical-image-classification',
    'Medical image classification assigns diagnostic labels to medical images such as chest X-rays, CT and MRI scans, histopathology slides, dermoscopy photos, and retinal fundus images. Labels can be a disease, a severity grade, or a finding. Datasets are small and imbalanced, so work centers on transfer learning, medical foundation models, weak supervision, and calibration. Related: [Medical Image Segmentation](/tasks/medical-image-segmentation), [Image Classification](/tasks/image-classification).',
    'medical image classification, chest X-ray classification, skin lesion classification, histopathology image classification, diabetic retinopathy grading, diabetic retinopathy classification, brain tumor classification, medical image diagnosis',
    (SELECT area_id FROM tasks WHERE slug = 'medical-imaging'),
    (SELECT level + 1 FROM tasks WHERE slug = 'medical-imaging'),
    (SELECT id FROM tasks WHERE slug = 'medical-imaging')
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Image Forgery Detection',
    'image-forgery-detection',
    'Image forgery detection decides whether an image has been edited and usually localizes the tampered region. Classic manipulations are splicing, copy-move, and object removal; newer work also covers inpainting and edits made with generative models. Methods look for noise, compression, and camera traces that edits disturb. Face swaps and fully synthetic faces are covered by [Deepfake Detection](/tasks/deepfake-detection).',
    'image forgery detection, image forgery localization, image manipulation detection, image manipulation localization, image tampering detection, image tampering localization, copy-move forgery, splicing detection, image splicing detection, tampered image',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Virtual Try-On',
    'virtual-try-on',
    'Virtual try-on synthesizes an image or video of a person wearing a target garment while keeping the person''s pose, body shape, and identity. Pipelines warp the garment to the body and blend it in; recent diffusion-based systems condition a pretrained image generator on the garment and person directly. Related: [Image Generation](/tasks/image-generation).',
    'virtual try-on, virtual try on, image-based virtual try-on, video virtual try-on, VTON, garment try-on, try-on',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Small Object Detection',
    'small-object-detection',
    'Small object detection finds objects that cover only a few pixels, such as distant pedestrians, vehicles in aerial images, or tiny defects. Downsampling destroys their features and standard anchors and IoU thresholds suit them poorly, so methods use high-resolution feature pyramids, super-resolution, context, tiling, and size-aware label assignment. Benchmarks include VisDrone, AI-TOD, and the small-object split of COCO. Related: [Object Detection](/tasks/object-detection).',
    'small object detection, tiny object detection, small-object detection, tiny-object detection, small objects detection',
    (SELECT area_id FROM tasks WHERE slug = 'object-detection'),
    (SELECT level + 1 FROM tasks WHERE slug = 'object-detection'),
    (SELECT id FROM tasks WHERE slug = 'object-detection')
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Defect Detection',
    'defect-detection',
    'Visual defect detection finds and localizes flaws in manufactured products and infrastructure, such as surface scratches on steel, faults on printed circuit boards, fabric defects, weld defects, and cracks in pavement or concrete. When labeled defects exist it is trained as detection or segmentation; when they are rare it is treated as [Anomaly Detection](/tasks/anomaly-detection). Related: [Object Detection](/tasks/object-detection).',
    'surface defect detection, industrial defect detection, PCB defect detection, visual defect detection, defect inspection, fabric defect detection, weld defect detection, steel surface defect, crack detection, crack segmentation, pavement crack detection',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tasks (name, slug, description, keywords, area_id, level, parent_id)
VALUES (
    'Sign Language Recognition',
    'sign-language-recognition',
    'Sign language recognition turns videos of signing into glosses or text. Isolated recognition classifies single signs; continuous recognition transcribes whole sentences, and sign language translation produces spoken-language text. The reverse direction, sign language production, generates signing avatars or video from text. Models combine hand, face, and body pose with video features. Related: [Action Recognition](/tasks/action-recognition), [Pose Estimation](/tasks/pose-estimation).',
    'sign language recognition, continuous sign language recognition, isolated sign language recognition, sign language translation, sign language production, sign language generation, fingerspelling recognition',
    (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
    0,
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;

-- "sign recognition" briefly tagged traffic-sign papers; remove auto tags that
-- do not mention sign language or fingerspelling.
DELETE FROM paper_tasks pt
USING tasks t, papers p
WHERE pt.task_id = t.id
  AND p.id = pt.paper_id
  AND t.slug = 'sign-language-recognition'
  AND pt.source = 'auto'
  AND coalesce(p.title, '') || ' ' || coalesce(p.abstract, '') !~* '(sign language|fingerspelling)';
