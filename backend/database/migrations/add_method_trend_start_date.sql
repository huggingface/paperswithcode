-- Optional first month of a method's usage trend. method_history_start()
-- prefers it over the source paper date and introduced_year, so a method whose
-- source (for example a field survey) or introduced year is later than the
-- field itself can still chart its earlier papers. Reference backfills share
-- that start month. Additive and idempotent; apply before deploying code that
-- maps the column.

ALTER TABLE methods ADD COLUMN IF NOT EXISTS trend_start_date DATE;

COMMENT ON COLUMN methods.trend_start_date IS
    'Optional first month of the method usage trend; overrides source paper date and introduced_year.';

UPDATE methods
SET trend_start_date = DATE '2015-01-01', updated_at = CURRENT_TIMESTAMP
WHERE slug = 'continuous-language-model'
  AND trend_start_date IS DISTINCT FROM DATE '2015-01-01';
