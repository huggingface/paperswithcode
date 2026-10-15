-- Add FaceNet method, sourced from arXiv 1503.03832.

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
    'facenet',
    'FaceNet',
    'FaceNet',
    'FaceNet learns a direct mapping from face images to a compact Euclidean embedding in which distances correspond to face similarity. A deep [CNN](/methods/cnn) produces a 128-dimensional, L2-normalized embedding and is trained end-to-end with a triplet loss, which pulls an anchor face toward a positive of the same identity and pushes it away from a negative by at least a margin. Online mining of semi-hard negatives within large mini-batches keeps training stable. With the embedding fixed, face verification becomes thresholding a distance, recognition becomes [k-NN](/methods/knn) classification and clustering can use [k-means](/methods/k-means-clustering) or agglomerative clustering. FaceNet reached 99.63% accuracy on LFW and 95.12% on YouTube Faces DB, and triplet-based metric learning became a standard tool beyond face recognition.',
    'FaceNet',
    (
        SELECT id
        FROM areas
        WHERE name = 'Vision'
        LIMIT 1
    ),
    2015,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1503.03832'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'FaceNet: A Unified Embedding for Face Recognition and Clustering',
    NULL,
    NULL,
    '[FaceNet: A Unified Embedding for Face Recognition and Clustering](/paper/1503.03832)'
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
WHERE slug = 'facenet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source'
FROM methods
WHERE slug = 'facenet'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
