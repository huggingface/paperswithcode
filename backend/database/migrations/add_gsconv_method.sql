-- Add GSConv, introduced in arXiv 2206.02424.
-- Added 2026-10-27 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url, image_url, image_credit,
    abstract_linking, aliases
)
VALUES (
    'gsconv',
    'GSConv',
    'GSConv (Slim-neck convolution)',
    'GSConv is a lightweight convolution for real-time object detectors that mixes a standard [convolution](/methods/convolution) with a [depthwise convolution](/methods/depthwise-convolution). A standard convolution produces half of the output channels, a depthwise separable convolution applied to that result produces the other half, and the two are concatenated and channel-shuffled so the cheap depthwise features take on information from the dense branch. This keeps accuracy close to a standard convolution at a lower cost. The same paper builds a Slim-neck from GSConv and the VoV-GSCSP module for the neck of [YOLO](/methods/yolo)-style detectors, which cuts parameters and FLOPs while improving accuracy across several YOLO baselines.',
    'GSConv, GS-Conv, GSConv module, VoV-GSCSP',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2206.02424' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Slim-neck by GSConv: A lightweight-design for real-time detector architectures',
    'https://github.com/alanli1997/slim-neck-by-gsconv/blob/master/gsconv-yolov5/models/common.py#L53',
    NULL,
    '[Slim-neck by GSConv: A lightweight-design for real-time detector architectures](/paper/2206.02424)',
    'always',
    ARRAY['GS-Conv']
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
WHERE slug = 'gsconv' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'gsconv' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Citation review 2026-10-27: Semantic Scholar lists 659 citers, 2 of them local.
-- DFIR-DETR (2512.07078) only lists the source in its references; exclude it so
-- the hourly reference backfill does not link it.
INSERT INTO paper_method_exclusions (paper_id, method_id, reason)
SELECT p.id, m.id, 'gsconv citation review 2026-10-27: cites the source in references only, does not use GSConv'
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gsconv' AND p.arxiv_id = '2512.07078' AND p.is_latest_version
ON CONFLICT (paper_id, method_id) DO UPDATE SET
    reason = EXCLUDED.reason,
    updated_at = now();

DELETE FROM paper_methods pm
USING paper_method_exclusions e
JOIN methods m ON m.id = e.method_id AND m.slug = 'gsconv'
WHERE pm.paper_id = e.paper_id AND pm.method_id = e.method_id;

-- Rethinking Features-Fused-Pyramid-Neck (2505.12820) cites the source and names
-- GSConv in its abstract.
CREATE TEMP TABLE gsconv_cited ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'gsconv' AND p.arxiv_id = '2505.12820' AND p.is_latest_version;

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM gsconv_cited x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'reference' FROM gsconv_cited x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
