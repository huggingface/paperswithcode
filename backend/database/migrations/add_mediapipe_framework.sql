-- Add MediaPipe to the computer-vision framework catalog.
-- Production chat users looked it up with pwc_get_framework (2026-11-11 audit).

BEGIN;

INSERT INTO repositories (url, owner, name, num_stars, source)
VALUES ('https://github.com/google-ai-edge/mediapipe', 'google-ai-edge', 'mediapipe', 0, 'framework_catalog')
ON CONFLICT (url) DO NOTHING;

INSERT INTO frameworks (
    category_id, repository_id, introducing_paper_id, slug, name, organization_name,
    description, when_to_use, docs_url, display_order, abstract_linking
)
SELECT
    category.id,
    repository.id,
    (SELECT paper.id FROM papers paper
     WHERE paper.arxiv_id = '1906.08172'
     ORDER BY paper.is_latest_version DESC, paper.id DESC LIMIT 1),
    'mediapipe',
    'MediaPipe',
    'Google',
    'A cross-platform framework for on-device perception pipelines, with ready-made solutions for hand, face, and pose landmark detection, object detection, segmentation, and gesture recognition that run in real time on mobile, desktop, web, and edge devices.',
    'Use MediaPipe for real-time hand, face, or body landmarks and gestures on device, or as a fast keypoint front end for sign-language, gesture, and fitness applications.',
    'https://developers.google.com/edge/mediapipe/solutions/guide',
    5,
    'always'
FROM framework_categories category
JOIN framework_domains domain ON domain.id = category.domain_id AND domain.slug = 'computer-vision'
JOIN repositories repository ON repository.url = 'https://github.com/google-ai-edge/mediapipe'
WHERE category.slug = 'vision-model-libraries'
ON CONFLICT (slug) DO UPDATE SET
    category_id = EXCLUDED.category_id,
    repository_id = EXCLUDED.repository_id,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    name = EXCLUDED.name,
    organization_name = EXCLUDED.organization_name,
    description = EXCLUDED.description,
    when_to_use = EXCLUDED.when_to_use,
    docs_url = EXCLUDED.docs_url,
    display_order = EXCLUDED.display_order,
    abstract_linking = EXCLUDED.abstract_linking,
    updated_at = now();

INSERT INTO framework_platforms (framework_id, platform)
SELECT framework.id, platform.name
FROM frameworks framework
CROSS JOIN (VALUES ('cpu'), ('gpu'), ('apple')) AS platform(name)
WHERE framework.slug = 'mediapipe'
ON CONFLICT DO NOTHING;

COMMIT;
