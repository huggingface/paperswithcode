-- Add Conformal Prediction (no introducing paper in the catalog; external reference).
-- Added 2026-10-20 because production chat users looked it up with
-- pwc_get_method and it was missing from the catalog.

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
    'conformal-prediction',
    'Conformal Prediction',
    'Conformal Prediction',
    'Conformal prediction is a distribution-free framework that turns any trained model into one that outputs prediction sets or intervals with a guaranteed coverage level, for example containing the true label 90% of the time, assuming only exchangeable data. Split conformal prediction scores a held-out calibration set with a nonconformity score, takes the (1 − α) quantile as a threshold, and includes every candidate label whose score falls below it. Developed by Vovk, Gammerman and Shafer (Algorithmic Learning in a Random World, 2005), it is now used for uncertainty quantification in classification, regression, time-series forecasting and LLM outputs.',
    'conformal prediction, conformal predictor, conformal predictors, split conformal, conformal risk control',
    (
        SELECT id
        FROM areas
        WHERE name = 'General'
        LIMIT 1
    ),
    NULL,
    NULL,
    'https://arxiv.org/abs/2107.07511',
    'A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification',
    NULL,
    NULL,
    'Illustration by Papers with Code'
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

-- 231 papers match the method keywords (same matcher as the
-- daily keyword backfill).
CREATE TEMP TABLE conformal_prediction_keyword_papers ON COMMIT DROP AS
SELECT p.id AS paper_id, m.id AS method_id
FROM papers p
CROSS JOIN methods m
WHERE m.slug = 'conformal-prediction'
  AND p.id IS DISTINCT FROM m.source_paper_id
  AND p.id IN (
        6777, 9979, 10567, 10985, 11631, 11838, 11845, 12931, 13052, 13128, 13994, 14116,
        16444, 16517, 16955, 16956, 17156, 17561, 18004, 18364, 21231, 24819, 27125, 27963,
        28997, 29377, 30003, 30265, 30936, 32167, 36274, 42225, 42268, 43096, 43981, 44008,
        44504, 47936, 49065, 50956, 51589, 54676, 55464, 56956, 58656, 60052, 60108, 61196,
        61565, 63094, 63625, 65445, 66236, 66630, 66755, 66921, 67965, 68187, 68754, 68956,
        70359, 71453, 71717, 72732, 73397, 74244, 74785, 75217, 75271, 76104, 76324, 76669,
        77009, 77187, 78880, 82995, 84022, 84521, 85171, 85501, 85666, 85861, 85891, 86161,
        86164, 86189, 86209, 86220, 86266, 86354, 86521, 86549, 86552, 86602, 86754, 86942,
        86993, 87043, 87093, 87388, 87465, 87851, 88431, 88536, 88672, 88678, 88766, 88905,
        88933, 88969, 89033, 89053, 89059, 89089, 89106, 89184, 89299, 89326, 89328, 89331,
        89425, 89456, 89460, 89483, 89490, 89644, 89674, 89878, 89942, 89983, 90555, 90809,
        91102, 91300, 91317, 91553, 91687, 91818, 91859, 91941, 91976, 92062, 92322, 92329,
        92401, 92641, 92671, 92965, 93299, 93366, 93635, 93704, 93929, 93938, 94128, 94224,
        94358, 94401, 94498, 94736, 94786, 95264, 95525, 95889, 95997, 96205, 96764, 96776,
        97700, 98703, 99155, 99270, 99307, 99405, 99464, 99652, 100019, 100061, 100166, 100283,
        100366, 100463, 100494, 100594, 100710, 100813, 100816, 100844, 101152, 101268, 101270, 101302,
        101643, 101752, 101854, 101883, 101892, 102029, 102073, 102099, 102121, 102329, 103445, 105041,
        105042, 105043, 105604, 105773, 106232, 106510, 106744, 106826, 106866, 107388, 107553, 107676,
        107696, 107846, 108810, 110203, 110568, 113244, 113709, 114008, 115132, 115241, 117198, 118276,
        118310, 120027, 121862
  );

INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM conformal_prediction_keyword_papers x
WHERE NOT EXISTS (
    SELECT 1 FROM paper_method_exclusions e
    WHERE e.paper_id = x.paper_id AND e.method_id = x.method_id
)
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT x.paper_id, x.method_id, 'keyword' FROM conformal_prediction_keyword_papers x
JOIN paper_methods pm ON pm.paper_id = x.paper_id AND pm.method_id = x.method_id
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
