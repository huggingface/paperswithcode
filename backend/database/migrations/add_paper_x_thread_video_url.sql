-- Migration: inline video for X thread previews
--
-- Stores the MP4 of a post's first video or animated GIF so paper pages can
-- play it in place of the static thumbnail. Existing rows stay NULL until
-- `backend/scripts/backfill_x_thread_videos.py` re-previews them.
--
-- Run as the schema owner (postgres).

ALTER TABLE public.paper_x_threads
    ADD COLUMN IF NOT EXISTS video_url VARCHAR(1000);
