-- Add Time Series Anomaly Detection as a subtask of anomaly-detection; production chat users searched for it
-- but the catalog had no matching task.

INSERT INTO tasks (
    name,
    slug,
    description,
    keywords,
    area_id,
    parent_id,
    level,
    image_url,
    image_credit,
    is_visible
)
VALUES (
    'Time Series Anomaly Detection',
    'time-series-anomaly-detection',
    'Time series anomaly detection identifies time points or subsequences in univariate or multivariate time series that deviate from normal temporal behaviour, such as point, contextual, and collective anomalies in sensor, server-monitoring, and industrial telemetry. Methods are usually unsupervised and score anomalies by forecasting error, reconstruction error, or association discrepancy, building on [Time Series Forecasting](/tasks/time-series-forecasting) and representation learning. It is a subtask of [Anomaly Detection](/tasks/anomaly-detection), commonly evaluated with (point-adjusted) F1, VUS, and AUC on benchmarks such as SMD, MSL, SMAP, SWaT, PSM, and the UCR anomaly archive.',
    'time series anomaly detection, time-series anomaly detection, multivariate time series anomaly detection, univariate time series anomaly detection, anomaly detection in time series, TSAD, time series outlier detection, sensor anomaly detection',
    (SELECT area_id FROM tasks WHERE slug = 'anomaly-detection' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'anomaly-detection' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'anomaly-detection' LIMIT 1),
    NULL,
    '[Deep Learning for Time Series Anomaly Detection: A Survey](https://arxiv.org/abs/2211.05244)',
    true
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    parent_id = EXCLUDED.parent_id,
    level = EXCLUDED.level,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    is_visible = EXCLUDED.is_visible,
    updated_at = CURRENT_TIMESTAMP;
