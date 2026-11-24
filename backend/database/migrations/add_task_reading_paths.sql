-- Migration: "Start here" reading paths on task pages
--
-- Hand-curated papers for GET /api/v1/tasks/{task_id}/reading-path. Each row
-- places one paper in one step (overview, foundations, recent) of a task's
-- path, ordered by position. Tasks without rows get an automatic path, and a
-- task with rows for only some steps gets the rest filled automatically.
-- Add or change paths with plain INSERT/UPDATE/DELETE; no deploy is needed.
--
-- Run once as the schema owner (postgres). Idempotent.

CREATE TABLE IF NOT EXISTS public.task_reading_path_papers (
    task_id BIGINT NOT NULL REFERENCES public.tasks(id) ON DELETE CASCADE,
    paper_id BIGINT NOT NULL REFERENCES public.papers(id) ON DELETE CASCADE,
    step VARCHAR(16) NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (task_id, paper_id),
    CONSTRAINT task_reading_path_papers_step
        CHECK (step IN ('overview', 'foundations', 'recent'))
);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.task_reading_path_papers
    TO paperswithcode_user;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT ON TABLE public.task_reading_path_papers TO pwc_staging;
    END IF;
END
$$;

COMMENT ON TABLE public.task_reading_path_papers IS
'Hand-curated "Start here" reading path papers per task (overview, foundations, recent).';

INSERT INTO public.task_reading_path_papers (task_id, paper_id, step, position, note)
SELECT t.id, p.id, v.step, v.position, v.note
FROM (VALUES
    ('object-detection', '1905.05055', 'overview', 0,
     'Traces two decades of detectors, from hand-crafted features to deep networks, and explains the key datasets and metrics.'),
    ('object-detection', '1311.2524', 'foundations', 0,
     'R-CNN: the first detector to show that CNN features from region proposals beat hand-crafted pipelines.'),
    ('object-detection', '1506.01497', 'foundations', 1,
     'Faster R-CNN: learns the region proposals too, giving the two-stage design most later detectors build on.'),
    ('object-detection', '1506.02640', 'foundations', 2,
     'YOLO: treats detection as a single regression problem, starting the family of fast one-stage detectors.'),
    ('object-detection', '2304.08069', 'recent', 0,
     'RT-DETR: a transformer detector that matches YOLO-class speed without non-maximum suppression.'),
    ('object-detection', '2303.05499', 'recent', 1,
     'Grounding DINO: detects arbitrary objects named in text, moving detection beyond a fixed label set.'),
    ('object-detection', '2405.14458', 'recent', 2,
     'YOLOv10: an NMS-free, end-to-end YOLO that shows how the real-time line has evolved.'),
    ('language-modeling', '2303.18223', 'overview', 0,
     'A broad, regularly updated survey of how large language models are pre-trained, adapted, used and evaluated.'),
    ('language-modeling', '1706.03762', 'foundations', 0,
     'The Transformer: the attention-only architecture behind nearly every modern language model.'),
    ('language-modeling', '1810.04805', 'foundations', 1,
     'BERT: popularised large-scale pre-training followed by fine-tuning.'),
    ('language-modeling', '2005.14165', 'foundations', 2,
     'GPT-3: showed that scaling autoregressive models enables few-shot learning from prompts alone.'),
    ('language-modeling', '2407.21783', 'recent', 0,
     'Llama 3: a detailed open report on building a frontier-scale model, from data to post-training.'),
    ('language-modeling', '2501.12948', 'recent', 1,
     'DeepSeek-R1: uses reinforcement learning to teach a model to reason step by step.'),
    ('language-modeling', '2505.09388', 'recent', 2,
     'Qwen3: an open model family with switchable thinking and non-thinking modes.'),
    ('image-classification', '1409.0575', 'overview', 0,
     'The ImageNet challenge paper: explains the benchmark that drove the field and how classifiers improved on it.'),
    ('image-classification', '1512.03385', 'foundations', 0,
     'ResNet: residual connections made very deep networks trainable and became the default backbone.'),
    ('image-classification', '2010.11929', 'foundations', 1,
     'Vision Transformer: showed that a plain transformer on image patches can match CNNs at scale.'),
    ('image-classification', '2201.03545', 'foundations', 2,
     'ConvNeXt: modernises the ConvNet with transformer-era design choices and closes the gap again.'),
    ('image-classification', '2304.07193', 'recent', 0,
     'DINOv2: self-supervised visual features strong enough to classify well with a simple linear probe.'),
    ('image-classification', '2502.14786', 'recent', 1,
     'SigLIP 2: image-text pre-training that gives strong zero-shot classification across languages.'),
    ('image-classification', '2508.10104', 'recent', 2,
     'DINOv3: scales self-supervised learning further and is a current go-to vision backbone.')
) AS v(task_slug, arxiv_id, step, position, note)
JOIN public.tasks t ON t.slug = v.task_slug
JOIN public.papers p ON p.arxiv_id = v.arxiv_id AND p.is_latest_version
ON CONFLICT (task_id, paper_id) DO NOTHING;
