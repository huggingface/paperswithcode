-- Add Occupancy Networks method, sourced from arXiv 1812.03828 (indexed
-- 2026-10-15 as paper 123502).

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
    'occupancy-networks',
    'Occupancy Networks',
    'Occupancy Networks (ONet)',
    'Occupancy Networks represent 3D geometry implicitly as the continuous decision boundary of a neural classifier. Given a 3D point p and an observation x, such as an image, a point cloud or a coarse voxel grid, the network predicts the probability that p lies inside the object, and the surface is the level set where this occupancy equals a threshold. Unlike voxels, point clouds or meshes, the representation has no fixed resolution and needs little memory, so shapes can be extracted at any resolution; the paper proposes Multiresolution IsoSurface Extraction (MISE), which refines an octree near the surface before marching cubes. Occupancy Networks were applied to single-image 3D reconstruction, point cloud completion, voxel super-resolution and unconditional shape generation. With concurrent DeepSDF and IM-NET they introduced neural implicit representations, which later led to [NeRF](/methods/nerf).',
    'Occupancy Network, Occupancy Networks',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2018,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1812.03828'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Occupancy Networks: Learning 3D Reconstruction in Function Space',
    'https://github.com/autonomousvision/occupancy_networks',
    NULL,
    '[Occupancy Networks: Learning 3D Reconstruction in Function Space](/paper/1812.03828)'
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
WHERE slug = 'occupancy-networks'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'occupancy-networks'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
