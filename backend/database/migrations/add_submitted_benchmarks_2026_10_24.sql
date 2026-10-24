-- Benchmarks suggested through the paper-page submission queue and approved in
-- the 2026-10-24 triage (submissions 1327, 1412, 1528, 1755, 1778, 1779).
-- Each benchmark gets one task and one primary metric; no evaluation rows.

BEGIN;

DO $$
BEGIN
    IF (
        SELECT count(*) FROM papers
        WHERE is_latest_version
          AND (id, arxiv_id) IN (
              (42165, '2412.18424'), (434, '1608.00272'), (65684, '2510.25387'),
              (109844, '2608.25061'), (6266, '2107.07933'), (76290, '2409.16252')
          )
    ) <> 6 THEN
        RAISE EXCEPTION 'Benchmark source paper identity precondition failed';
    END IF;

    IF (
        SELECT count(*) FROM tasks
        WHERE (id, slug) IN (
            (308, 'document-understanding'), (437, 'visual-grounding'),
            (917, 'composed-image-retrieval'), (865, 'code-generation'),
            (351, 'earth-observation')
        )
    ) <> 5 THEN
        RAISE EXCEPTION 'Benchmark task identity precondition failed';
    END IF;
END
$$;

INSERT INTO metrics (name, full_name, direction, scale, description)
VALUES (
    'Speedup',
    'Speedup over baseline',
    'higher_is_better',
    'unbounded',
    'Ratio of the baseline runtime to the runtime of the evaluated implementation (baseline time / candidate time); values above 1 mean the candidate is faster. The baseline is defined by each benchmark.'
)
ON CONFLICT (name) DO NOTHING;

CREATE TEMP TABLE submitted_benchmarks (
    slug text PRIMARY KEY,
    name text NOT NULL,
    full_name text NOT NULL,
    paper_id bigint NOT NULL,
    task_id bigint NOT NULL,
    metric_name text NOT NULL,
    homepage text NOT NULL,
    introduced_date date NOT NULL,
    modalities jsonb NOT NULL,
    abstract_linking text NOT NULL,
    aliases text[] NOT NULL,
    short_description text NOT NULL,
    description text NOT NULL
) ON COMMIT DROP;

INSERT INTO submitted_benchmarks VALUES
('longdocurl', 'LongDocURL',
 'LongDocURL: a Comprehensive Multimodal Long Document Benchmark Integrating Understanding, Reasoning, and Locating',
 42165, 308, 'Accuracy', 'https://github.com/dengc2023/LongDocURL', DATE '2024-12-24',
 '["images", "text", "documents"]', 'always', ARRAY['LongDocURL'],
 'A long-document question answering benchmark of 2,325 questions over more than 33,000 PDF pages, covering understanding, numerical reasoning, and cross-element locating.',
 'LongDocURL evaluates large vision-language models on long, visually rich documents (average of about 86 pages). Its 2,325 human-verified question-answer pairs span 20 sub-tasks grouped into three primary tasks: long-document Understanding, numerical Reasoning, and cross-element Locating, with evidence drawn from text, layout, charts and images, and tables on single or multiple pages. The leaderboard reports the overall generalized accuracy score (0-100) on the full benchmark.'),
('refcoco-plus', 'RefCOCO+',
 'RefCOCO+ (Referring Expressions COCO+, val split)',
 434, 437, 'Accuracy', 'https://github.com/lichengunc/refer', DATE '2016-07-31',
 '["images", "text"]', 'judge', ARRAY['RefCOCO+', 'RefCOCO plus'],
 'A referring expression comprehension benchmark on MS COCO images whose expressions avoid absolute location words.',
 'RefCOCO+ contains 141,564 referring expressions for 49,856 objects in 19,992 MS COCO images, collected with the ReferIt game. Unlike RefCOCO, location words such as "left" or "right" were disallowed, so expressions describe objects by appearance. Referring expression comprehension models localize the described object, and a prediction counts as correct when its box has IoU of at least 0.5 with the ground truth. This leaderboard reports top-1 accuracy on the val split; testA (people) and testB (other objects) results are not mixed into it.'),
('i-cir', 'i-CIR',
 'i-CIR: Instance-Level Composed Image Retrieval',
 65684, 917, 'mAP', 'https://vrg.fel.cvut.cz/icir/', DATE '2025-10-29',
 '["images", "text"]', 'always', ARRAY['i-CIR', 'iCIR', 'instance-level CIR'],
 'An instance-level composed image retrieval benchmark with 202 object instances and 1,883 composed image-plus-text queries.',
 'i-CIR evaluates instance-level composed image retrieval: each query combines an image of a particular object instance with a text modification, and the goal is to retrieve images of that same instance that satisfy the modification. It contains 202 instances and 1,883 composed queries, each instance with its own database of semi-automatically mined hard negatives (about 750K images in total), making it as challenging as retrieval among more than 40M random distractors. The leaderboard reports macro-mAP (%): mAP over the queries of each instance, averaged over instances.'),
('datakernelbench', 'DataKernelBench',
 'DataKernelBench: Can LLMs Optimize Database Queries on GPUs?',
 109844, 865, 'Speedup', 'https://kerneldf.github.io/datakernelbench', DATE '2026-08-25',
 '["text", "code"]', 'always', ARRAY['DataKernelBench'],
 'A benchmark of LLMs generating CUDA or Triton GPU kernels for the 22 TPC-H database queries.',
 'DataKernelBench translates SQL queries into validated PyTorch TorchPlan programs and asks LLMs to optimize either the core tensor snippet or the full query in CUDA or Triton, with execution-guided repair. Generated modules must match the reference output and beat the baseline to be accepted; otherwise the baseline runtime is used. The leaderboard reports overall speedup over TorchPlan with torch.compile on the 22 TPC-H queries at scale factor 10 on one NVIDIA H100 GPU (main leaderboard, Table 1).'),
('pastis-semantic-segmentation', 'PASTIS (Semantic Segmentation)',
 'PASTIS: Panoptic Agricultural Satellite TIme Series (semantic segmentation)',
 6266, 351, 'mIoU', 'https://github.com/VSainteuf/pastis-benchmark', DATE '2021-07-16',
 '["images", "time series", "satellite"]', 'judge', ARRAY['PASTIS', 'PASTIS semantic segmentation'],
 'Crop-type semantic segmentation of Sentinel-2 satellite image time series over 2,433 French agricultural patches.',
 'PASTIS (Panoptic Agricultural Satellite TIme Series) contains 2,433 Sentinel-2 image time series of 128x128 pixels over France, with 33 to 61 acquisitions per patch and pixel-level crop-type and parcel annotations. The semantic segmentation benchmark follows the official five-fold cross-validation and scores all 19 evaluated classes (18 crop types plus background; the void label is ignored). The leaderboard reports mIoU (%) averaged over the five folds; panoptic results and binary field delineation are not part of this board.'),
('fields-of-the-world', 'Fields of The World',
 'Fields of The World (FTW): a benchmark dataset for global agricultural field boundary segmentation',
 76290, 351, 'IoU', 'https://fieldsofthe.world/', DATE '2024-09-24',
 '["images", "satellite"]', 'always', ARRAY['FTW', 'Fields of the World'],
 'An agricultural field boundary segmentation benchmark with 70,462 Sentinel-2 samples from 24 countries on four continents.',
 'Fields of The World (FTW) pairs multi-date, multi-spectral Sentinel-2 images with instance and semantic field masks for 70,462 samples from 24 countries in Europe, Africa, Asia, and South America, with blocked training, validation, and test splits per country. The benchmark recommends evaluating on the per-country test sets. This leaderboard reports pixel-level IoU of the field class (0-1) averaged over the country test sets; per-country, worst-country, object-level, and two-class mean IoU numbers are not mixed into it.');

INSERT INTO datasets (
    name, full_name, slug, description, short_description, url, homepage,
    introducing_paper_id, introducing_paper_title, paper_url,
    introduced_date, introduced_year, modalities, abstract_linking, aliases
)
SELECT
    b.name, b.full_name, b.slug, b.description, b.short_description,
    b.homepage, b.homepage, p.id, p.title,
    'https://paperswithcode.co/paper/' || p.arxiv_id,
    b.introduced_date, EXTRACT(YEAR FROM b.introduced_date)::int,
    b.modalities, b.abstract_linking, b.aliases
FROM submitted_benchmarks b
JOIN papers p ON p.id = b.paper_id
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    url = EXCLUDED.url,
    homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities,
    abstract_linking = EXCLUDED.abstract_linking,
    aliases = EXCLUDED.aliases,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT paper_id, task_id, 'manual' FROM submitted_benchmarks
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT b.task_id, d.id, FALSE
FROM submitted_benchmarks b
JOIN datasets d ON d.slug = b.slug
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT b.task_id, d.id, m.id
FROM submitted_benchmarks b
JOIN datasets d ON d.slug = b.slug
JOIN metrics m ON m.name = b.metric_name
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

COMMIT;
