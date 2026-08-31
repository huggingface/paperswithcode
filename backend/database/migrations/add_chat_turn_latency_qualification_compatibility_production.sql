BEGIN;

DO $$
BEGIN
    IF current_schema() <> 'public' THEN
        RAISE EXCEPTION
            'add_chat_turn_latency_qualification_compatibility_production.sql must run with search_path public';
    END IF;
END $$;

-- ChatTurnLatency maps these nullable fields in every environment. Production
-- does not create the staging-only qualification scope/evidence tables while
-- external Pi admission is disabled, but ordinary chat admission must still be
-- able to select and insert the shared latency row.
ALTER TABLE public.chat_turn_latency
    ADD COLUMN IF NOT EXISTS qualification_scope_id UUID,
    ADD COLUMN IF NOT EXISTS qualification_profile VARCHAR(32),
    ADD COLUMN IF NOT EXISTS qualification_workload VARCHAR(16);

ALTER TABLE public.chat_turn_latency OWNER TO paperswithcode_user;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.chat_turn_latency TO paperswithcode_user;
REVOKE ALL ON public.chat_turn_latency FROM pwc_staging;

COMMIT;
