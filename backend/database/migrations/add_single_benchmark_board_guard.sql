-- Keep each benchmark leaderboard on one task.
--
-- A (dataset, best_metric) leaderboard lives on exactly one task. An
-- evaluation that would leave the same leaderboard on a second task is
-- rejected at commit time, so a transaction that moves a whole board between
-- tasks still succeeds. A task that measures
-- a different protocol under the same metric name should use a renamed
-- benchmark variant (for example "ImageNet (256x256)"); the few existing
-- same-metric boards that predate this guard are listed as exceptions.
\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS public.benchmark_task_board_exceptions (
    dataset_id BIGINT NOT NULL REFERENCES public.datasets(id) ON DELETE CASCADE,
    task_id BIGINT NOT NULL REFERENCES public.tasks(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_id, task_id)
);

GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.benchmark_task_board_exceptions TO paperswithcode_user;
GRANT SELECT ON public.benchmark_task_board_exceptions TO pwc_staging;

INSERT INTO public.benchmark_task_board_exceptions (dataset_id, task_id, reason)
SELECT d.id, t.id, seed.reason
FROM (VALUES
    ('cifar-10', 'on-the-fly-category-discovery', 'Clustering accuracy on discovered categories, not classification accuracy'),
    ('cifar-100', 'on-the-fly-category-discovery', 'Clustering accuracy on discovered categories, not classification accuracy'),
    ('food-101', 'on-the-fly-category-discovery', 'Clustering accuracy on discovered categories, not classification accuracy'),
    ('stanford-cars', 'on-the-fly-category-discovery', 'Clustering accuracy on discovered categories, not classification accuracy'),
    ('ucf101', 'image-classification', 'Few-shot CLIP frame classification, not video action recognition'),
    ('crema-d', 'video-editing', 'Emotion accuracy of edited talking-face videos, not audio classification'),
    ('dl3dv-10k-2-view', '3d-generation', 'Pose-free 3D generation protocol with AUC@5, not novel-view synthesis'),
    ('re10k-2-view', '3d-generation', 'Pose-free 3D generation protocol with AUC@5, not novel-view synthesis'),
    ('scannet', '3d-object-detection', 'Box AP50, not instance-mask AP50'),
    ('s3dis', '3d-object-detection', 'Box AP50, not instance-mask AP50')
) AS seed(dataset_slug, task_slug, reason)
JOIN public.datasets d ON d.slug = seed.dataset_slug
JOIN public.tasks t ON t.slug = seed.task_slug
ON CONFLICT (dataset_id, task_id) DO NOTHING;

CREATE OR REPLACE FUNCTION public.check_single_benchmark_board()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    rival RECORD;
    dataset_name TEXT;
BEGIN
    IF NEW.dataset_id IS NULL OR NEW.task_id IS NULL OR NEW.best_metric IS NULL
        OR EXISTS (
            SELECT 1 FROM public.benchmark_task_board_exceptions x
            WHERE x.dataset_id = NEW.dataset_id AND x.task_id = NEW.task_id
        )
        -- A later statement in this transaction moved the row away.
        OR NOT EXISTS (
            SELECT 1 FROM public.evaluations
            WHERE dataset_id = NEW.dataset_id
              AND task_id = NEW.task_id
              AND best_metric = NEW.best_metric
        )
    THEN
        RETURN NULL;
    END IF;

    SELECT t.name, count(*) AS n INTO rival
    FROM public.evaluations e
    JOIN public.tasks t ON t.id = e.task_id
    WHERE e.dataset_id = NEW.dataset_id
      AND e.best_metric = NEW.best_metric
      AND e.task_id <> NEW.task_id
      AND NOT EXISTS (
          SELECT 1 FROM public.benchmark_task_board_exceptions x
          WHERE x.dataset_id = e.dataset_id AND x.task_id = e.task_id
      )
    GROUP BY t.id, t.name
    ORDER BY n DESC
    LIMIT 1;

    IF rival.n IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT name INTO dataset_name FROM public.datasets WHERE id = NEW.dataset_id;
    RAISE EXCEPTION
        'Benchmark "%" already has its % leaderboard on task "%" (% evaluations). Add this result to that task, or create a renamed benchmark variant (for example "ImageNet (256x256)") if this task measures a different protocol.',
        dataset_name, NEW.best_metric, rival.name, rival.n
        USING ERRCODE = 'check_violation',
              CONSTRAINT = 'evaluations_single_benchmark_board';
END;
$$;

-- The guard assumes no split leaderboards remain; merge any first.
DO $$
DECLARE
    split TEXT;
BEGIN
    SELECT string_agg(DISTINCT d.slug || ' / ' || e.best_metric, ', ') INTO split
    FROM public.evaluations e
    JOIN public.datasets d ON d.id = e.dataset_id
    WHERE e.best_metric IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM public.benchmark_task_board_exceptions x
          WHERE x.dataset_id = e.dataset_id AND x.task_id = e.task_id
      )
      AND EXISTS (
          SELECT 1 FROM public.evaluations o
          WHERE o.dataset_id = e.dataset_id
            AND o.best_metric = e.best_metric
            AND o.task_id <> e.task_id
            AND NOT EXISTS (
                SELECT 1 FROM public.benchmark_task_board_exceptions x
                WHERE x.dataset_id = o.dataset_id AND x.task_id = o.task_id
            )
      );
    IF split IS NOT NULL THEN
        RAISE EXCEPTION 'Split leaderboards remain: %', split;
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS evaluations_single_benchmark_board ON public.evaluations;
CREATE CONSTRAINT TRIGGER evaluations_single_benchmark_board
    AFTER INSERT OR UPDATE OF task_id, dataset_id, best_metric ON public.evaluations
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION public.check_single_benchmark_board();

COMMIT;
