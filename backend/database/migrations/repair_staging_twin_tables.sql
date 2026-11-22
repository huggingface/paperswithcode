-- Repair drift between `staging` tables and their `public` originals.
--
-- `consolidate_staging_schema.sql` created staging copies with
-- `LIKE public.<table> INCLUDING ALL`, which keeps serial defaults pointing at
-- the `public` sequence. `pwc_staging` cannot use those sequences, so inserts
-- into `staging.pending_paper_edits` failed with "permission denied for
-- sequence pending_paper_edits_id_seq". This gives every such staging column
-- its own staging-owned sequence, continuing after the staging rows' maximum.
--
-- It also adds the `public` columns that later migrations never copied to
-- staging, which the shared ORM selects (paper_curation_jobs.candidate_id and
-- bootstrap_bundle_sha256, paper_curation_workflows.source_candidate_id and
-- source_revision, catalog_mutation_events.paper_id). Like earlier staging
-- column additions, these are plain nullable columns without cross-schema
-- foreign keys.
--
-- Run as postgres. Idempotent: safe to re-run.
\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
    item record;
    sequence_name text;
BEGIN
    FOR item IN
        SELECT c.relname AS table_name, a.attname AS column_name
        FROM pg_attrdef d
        JOIN pg_class c ON c.oid = d.adrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.adnum
        JOIN pg_depend dep ON dep.objid = d.oid
            AND dep.classid = 'pg_attrdef'::regclass
            AND dep.refclassid = 'pg_class'::regclass
        JOIN pg_class s ON s.oid = dep.refobjid AND s.relkind = 'S'
        JOIN pg_namespace sn ON sn.oid = s.relnamespace
        WHERE n.nspname = 'staging' AND sn.nspname <> 'staging'
    LOOP
        sequence_name := item.table_name || '_' || item.column_name || '_seq';
        EXECUTE format('CREATE SEQUENCE IF NOT EXISTS staging.%I', sequence_name);
        EXECUTE format('ALTER SEQUENCE staging.%I OWNER TO pwc_staging_owner', sequence_name);
        EXECUTE format(
            'ALTER SEQUENCE staging.%I OWNED BY staging.%I.%I',
            sequence_name, item.table_name, item.column_name
        );
        EXECUTE format(
            'SELECT setval(%L, COALESCE((SELECT max(%I) FROM staging.%I), 0) + 1, false)',
            'staging.' || quote_ident(sequence_name), item.column_name, item.table_name
        );
        EXECUTE format(
            'ALTER TABLE staging.%I ALTER COLUMN %I SET DEFAULT nextval(%L::regclass)',
            item.table_name, item.column_name, 'staging.' || quote_ident(sequence_name)
        );
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE staging.%I TO pwc_staging', sequence_name);
    END LOOP;
END $$;

DO $$
BEGIN
    IF to_regclass('staging.paper_curation_jobs') IS NOT NULL THEN
        ALTER TABLE staging.paper_curation_jobs
            ADD COLUMN IF NOT EXISTS candidate_id UUID,
            ADD COLUMN IF NOT EXISTS bootstrap_bundle_sha256 VARCHAR(64);
    END IF;
    IF to_regclass('staging.paper_curation_workflows') IS NOT NULL THEN
        ALTER TABLE staging.paper_curation_workflows
            ADD COLUMN IF NOT EXISTS source_candidate_id UUID,
            ADD COLUMN IF NOT EXISTS source_revision VARCHAR(64);
    END IF;
    IF to_regclass('staging.catalog_mutation_events') IS NOT NULL THEN
        ALTER TABLE staging.catalog_mutation_events
            ADD COLUMN IF NOT EXISTS paper_id BIGINT;
    END IF;
END $$;

COMMIT;
