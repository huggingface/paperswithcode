-- Add ST-GCN method, sourced from arXiv 1801.07455. The newest paper row
-- (is_latest_version) is selected; 1801.07455 has two local versions.

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
    'st-gcn',
    'ST-GCN',
    'Spatial Temporal Graph Convolutional Network (ST-GCN)',
    'ST-GCN applies [graph convolutional networks](/methods/gcn) to skeleton-based action recognition. A skeleton sequence is represented as a spatial-temporal graph whose nodes are body joints in every frame; spatial edges follow the natural connectivity of the body and temporal edges connect the same joint in consecutive frames. Stacked ST-GCN layers alternate spatial graph convolutions with temporal convolutions, using partitioning strategies (uni-labeling, distance and spatial configuration partitioning) to define neighbourhood weights and a learnable edge importance mask. It learns spatial and temporal patterns automatically instead of relying on hand-crafted part definitions, and outperformed earlier methods on Kinetics and NTU-RGB+D. ST-GCN became the base architecture for most later skeleton action recognition models such as 2s-AGCN and MS-G3D.',
    'ST-GCN, spatial temporal graph convolutional network',
    (
        SELECT id
        FROM areas
        WHERE name = 'Video'
        LIMIT 1
    ),
    2018,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1801.07455'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Spatial Temporal Graph Convolutional Networks for Skeleton-Based Action Recognition',
    'https://github.com/yysijie/st-gcn',
    NULL,
    '[Spatial Temporal Graph Convolutional Networks for Skeleton-Based Action Recognition](/paper/1801.07455)'
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
WHERE slug = 'st-gcn'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'st-gcn'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
