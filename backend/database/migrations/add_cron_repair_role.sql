-- Migration: pwc_cron_repair, the database role for source-repairable CRON jobs
--
-- An autonomous CRON source repair rewrites a job and lets it run on its
-- schedule. Jobs it may repair connect as pwc_cron_repair instead of the
-- application role. The role mirrors the application role's table and
-- sequence privileges in public, minus every write on the taxonomy tables and
-- on views (a view writes with its owner's privileges), so
-- a repaired job keeps working while it can never create or change tasks,
-- methods, datasets, metrics, conferences, areas, or their links. It gets no
-- role membership, no schema CREATE, and no access to the staging schema.
--
-- The role is created without a password, so it cannot log in until
-- deploy/configure_db_roles.py sets the one in
-- /etc/paperswithcode/repair-cron.env. Run as postgres; the script is
-- idempotent and fails closed. Rerun it after adding a table a repairable job
-- writes, because privileges are mirrored once, not by default privileges.
--
--   sudo -u postgres psql -v ON_ERROR_STOP=1 -d paperswithcode_hf \
--     -f backend/database/migrations/add_cron_repair_role.sql

BEGIN;

DO $$
DECLARE
    granted_role text;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user'
    ) THEN
        RAISE EXCEPTION 'application role paperswithcode_user is missing';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_cron_repair') THEN
        CREATE ROLE pwc_cron_repair LOGIN NOINHERIT;
    END IF;
    FOR granted_role IN
        SELECT quote_ident(parent.rolname)
          FROM pg_auth_members membership
          JOIN pg_roles member ON member.oid = membership.member
          JOIN pg_roles parent ON parent.oid = membership.roleid
         WHERE member.rolname = 'pwc_cron_repair'
    LOOP
        EXECUTE 'REVOKE ' || granted_role || ' FROM pwc_cron_repair';
    END LOOP;
END $$;

ALTER ROLE pwc_cron_repair WITH
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
ALTER ROLE pwc_cron_repair SET search_path = public;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM pwc_cron_repair;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM pwc_cron_repair;
REVOKE CREATE ON SCHEMA public FROM pwc_cron_repair;
GRANT USAGE ON SCHEMA public TO pwc_cron_repair;

DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO pwc_cron_repair', current_database()
    );
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'staging') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA staging FROM pwc_cron_repair;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA staging FROM pwc_cron_repair;
        REVOKE ALL ON SCHEMA staging FROM pwc_cron_repair;
    END IF;
END $$;

CREATE TEMPORARY TABLE cron_repair_taxonomy_tables (name text PRIMARY KEY)
    ON COMMIT DROP;
INSERT INTO cron_repair_taxonomy_tables (name) VALUES
    ('areas'),
    ('tasks'),
    ('methods'),
    ('datasets'),
    ('metrics'),
    ('conferences'),
    ('paper_tasks'),
    ('paper_methods'),
    ('paper_method_evidence'),
    ('paper_method_exclusions'),
    ('paper_datasets'),
    ('paper_conferences'),
    ('task_datasets'),
    ('task_dataset_metrics'),
    ('task_sister_tasks'),
    ('task_frameworks'),
    ('task_recommended_frameworks'),
    ('benchmark_task_board_exceptions');

DO $$
DECLARE
    relation record;
    privilege text;
BEGIN
    FOR relation IN
        SELECT c.oid, c.relname, c.relkind
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
    LOOP
        IF relation.relkind = 'S' THEN
            FOREACH privilege IN ARRAY ARRAY['USAGE', 'SELECT', 'UPDATE'] LOOP
                IF has_sequence_privilege(
                    'paperswithcode_user', relation.oid, privilege
                ) THEN
                    EXECUTE format(
                        'GRANT %s ON SEQUENCE public.%I TO pwc_cron_repair',
                        privilege, relation.relname
                    );
                END IF;
            END LOOP;
        ELSE
            FOREACH privilege IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']
            LOOP
                IF has_table_privilege('paperswithcode_user', relation.oid, privilege)
                   AND (
                       privilege = 'SELECT'
                       OR (
                           relation.relkind IN ('r', 'p')
                           AND relation.relname NOT IN (
                               SELECT name FROM cron_repair_taxonomy_tables
                           )
                       )
                   )
                THEN
                    EXECUTE format(
                        'GRANT %s ON public.%I TO pwc_cron_repair',
                        privilege, relation.relname
                    );
                END IF;
            END LOOP;
        END IF;
    END LOOP;
END $$;

DO $$
DECLARE
    taxonomy_table text;
    prohibited_privilege text;
BEGIN
    IF EXISTS (
        SELECT 1
          FROM pg_auth_members membership
          JOIN pg_roles member ON member.oid = membership.member
         WHERE member.rolname = 'pwc_cron_repair'
    ) THEN
        RAISE EXCEPTION 'repair role retains a role membership';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles
         WHERE rolname = 'pwc_cron_repair'
           AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls
                OR rolreplication OR rolinherit)
    ) THEN
        RAISE EXCEPTION 'repair role has an elevated attribute';
    END IF;
    IF has_schema_privilege('pwc_cron_repair', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'repair role can create schema objects';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'staging')
       AND has_schema_privilege('pwc_cron_repair', 'staging', 'USAGE') THEN
        RAISE EXCEPTION 'repair role can use the staging schema';
    END IF;
    FOR taxonomy_table IN
        SELECT t.name
          FROM cron_repair_taxonomy_tables t
          JOIN pg_class c ON c.relname = t.name
          JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
    LOOP
        FOREACH prohibited_privilege IN ARRAY ARRAY[
            'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
        ] LOOP
            IF has_table_privilege(
                'pwc_cron_repair', 'public.' || quote_ident(taxonomy_table),
                prohibited_privilege
            ) THEN
                RAISE EXCEPTION 'repair role can % taxonomy table %',
                    prohibited_privilege, taxonomy_table;
            END IF;
        END LOOP;
    END LOOP;
    IF EXISTS (
        SELECT 1
          FROM pg_attribute attribute
          JOIN pg_class relation ON relation.oid = attribute.attrelid
          JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = 'public'
           AND relation.relname IN (SELECT name FROM cron_repair_taxonomy_tables)
           AND attribute.attnum > 0
           AND NOT attribute.attisdropped
           AND (
               has_column_privilege(
                   'pwc_cron_repair', relation.oid, attribute.attnum, 'INSERT'
               )
               OR has_column_privilege(
                   'pwc_cron_repair', relation.oid, attribute.attnum, 'UPDATE'
               )
           )
    ) THEN
        RAISE EXCEPTION 'repair role can write a taxonomy column';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM pg_class relation
          JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = 'public'
           AND relation.relkind NOT IN ('r', 'p', 'S', 'i', 'I', 't', 'c')
           AND (
               has_table_privilege('pwc_cron_repair', relation.oid, 'INSERT')
               OR has_table_privilege('pwc_cron_repair', relation.oid, 'UPDATE')
               OR has_table_privilege('pwc_cron_repair', relation.oid, 'DELETE')
           )
    ) THEN
        RAISE EXCEPTION 'repair role can write through a view';
    END IF;
END $$;

COMMIT;
