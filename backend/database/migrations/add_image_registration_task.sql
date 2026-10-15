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
    'Image Registration',
    'image-registration',
    'Image registration estimates the spatial transformation that aligns a moving image to a fixed image, from rigid and affine transforms to dense deformable fields. It is central to [Medical Imaging](/tasks/medical-imaging), where scans are aligned across time, patients, or modalities, and is also used in remote sensing and microscopy. Learning-based methods predict deformation fields directly and are evaluated with Dice overlap of propagated segmentations, landmark error, and deformation regularity. It is related to [Image Matching](/tasks/image-matching).',
    'image registration, deformable image registration, medical image registration, multimodal image registration, multi-modal image registration, unsupervised image registration, diffeomorphic image registration, diffeomorphic registration',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[VoxelMorph: A Learning Framework for Deformable Medical Image Registration](/paper/1809.05231)',
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
