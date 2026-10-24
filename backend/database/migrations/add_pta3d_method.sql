-- Patch Tanimoto Attention 3D (PTA3D) method (user submission 1777).
-- Introduced in arXiv 2409.13568 (paper 123973), journal version
-- https://doi.org/10.1016/j.rse.2026.115695. Hero image (Figure 3) is imported
-- separately with backend/database/import_entity_image.py.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit, abstract_linking, aliases
)
VALUES (
    'pta3d',
    'PTA3D',
    'Patch Tanimoto Attention 3D (PTA3D)',
    'Patch Tanimoto Attention 3D (PTA3D) is an attention mechanism for image time series that extends the 2D Patch Tanimoto Attention of the SSG2/PTAViT segmentation models (Diakogiannis et al., 2024), itself descended from the FracTAL Tanimoto attention, to an explicit temporal axis. Query, key and value tensors of shape C×T×H×W are partitioned into c×T×h×w patches that span channels, time and space, and every query patch is compared with every key patch using the bounded Tanimoto similarity. The resulting 8-D similarity map is compacted to a c×T×h×w emphasis map (by averaging or a small linear projection), optionally masked to be causal in time, and applied to the values by element-wise multiplication instead of softmax-weighted aggregation. Unlike separable channel/space/time attention, it keeps genuine spatio-temporal correspondences, and unlike standard softmax window attention it lets distant windows interact from the first stage at low memory cost. It supports both self-attention and cross-attention, the latter fusing Sentinel-1 SAR and Sentinel-2 optical time series in the PTAViT3D-CA model for cloud-robust agricultural field boundary delineation.',
    'PTA3D, PTA-3D, Patch Tanimoto Attention 3D, Patch Tanimoto Attention 3-D',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2024,
    123973,
    NULL,
    'Tackling fluffy clouds: robust agricultural field boundary delineation from Sentinel-1 and Sentinel-2 satellite image time series',
    'https://github.com/feevos/tfcl/blob/master/nn/layers/ptattention3d.py',
    NULL,
    '[Tackling fluffy clouds: robust agricultural field boundary delineation from Sentinel-1 and Sentinel-2 satellite image time series](/paper/2409.13568)',
    'always',
    ARRAY[]::text[]
)
ON CONFLICT (slug) DO UPDATE SET
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
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'pta3d' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
