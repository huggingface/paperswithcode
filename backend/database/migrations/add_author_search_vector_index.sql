-- Match the author-name lane used by keyword paper search.
-- Run outside a transaction because CONCURRENTLY cannot run inside one.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_authors_name_search_vector
    ON authors USING gin (to_tsvector('simple'::regconfig, name));
