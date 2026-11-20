# ADR 0016: Search and embeddings

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Embedding generation activation locks papers in SHARE mode

Activating a new embedding generation verifies that every paper's title/abstract hash matches its embedding, then flips the active generation. The function takes `LOCK TABLE papers IN SHARE MODE` so INSERT/UPDATE/DELETE (ROW EXCLUSIVE) block until the flip commits and the checked corpus cannot change, while ordinary paper reads continue during this rare operation.

Code: `backend/services/paper_embedding_pipeline.py::activate_generation`

## Exact title and arXiv ID matches override hybrid search fusion

Hybrid search fuses keyword and semantic results with reciprocal rank fusion, which can bury an exact match. Papers whose title or arXiv ID exactly matches the query are pinned ahead of fused results so identity lookups stay deterministic.

Code: `backend/services/paper_retrieval_service.py::PaperRetrievalService._search_papers_hybrid`

## Fuzzy typo repair weights edit confidence by name coverage

Fuzzy entity matching scores each token window of a name by Damerau-Levenshtein confidence multiplied by 0.7 + 0.3 * coverage. Coverage favours an equally good repair that explains more of the displayed name, while the 0.7 floor keeps a single misspelled long token inside a multi-token name recoverable.

Code: `backend/services/entity_search.py::_edit_confidence`

## Keyword paper search unions identity and lexical lanes to use the GIN index

Exact-title and arXiv identity predicates are not covered by the partial GIN full-text index, and ORing them into the lexical query would prevent PostgreSQL from using it. Keyword search runs identity matches and lexical matches as separate lanes, aggregates per paper keeping the best identity tier and FTS rank, and only then applies the SQL limit.

Candidate rows are ranked on narrow columns (identity tier, lexical rank, citations, date) before full paper records are fetched, so wide rows are loaded only for the final page. Citation and date tie-breakers are identical across lanes for a given paper, so aggregation does not change them.

Code: `backend/services/paper_retrieval_service.py::PaperRetrievalService._search_papers_fts`

## Method canonical paper falls back to most-cited paper in the method's set

When a method has no resolvable source paper, the canonical paper is chosen from papers already tagged with that method by Semantic Scholar citation count, with oldest publication date and then stable id breaking missing or equal counts. Citations are only used as a prior inside that already-resolved set, never globally.

Code: `backend/services/paper_retrieval_service.py::PaperRetrievalService._method_source_paper`

## Numeric API IDs are not entity search identities

Entity search treats a query that exactly matches a slug as an identity match, but purely numeric queries are excluded because numeric API IDs would otherwise hijack searches for numbers. An entity with a numeric slug is still reachable through its canonical route.

Code: `backend/services/entity_search.py::prepare_entity_search`

## Query embedding endpoints deploy from the HF endpoint catalog

Hugging Face Inference Endpoints deployed from the catalog run TEI for compatible embedding models, which supports the Matryoshka `dimensions` parameter. A generic PyTorch endpoint uses the inference toolkit and silently ignores `dimensions`, producing vectors of the wrong size. The query endpoint is therefore always deployed via `hf endpoints catalog deploy` and then pinned to a revision and scaling.

Code: `backend/cli.py::plan_query_endpoint`

## Search queries split inner punctuation like the indexed title copy

papers.search_vector indexes the title twice, once raw and once with non-alphanumeric runs replaced by spaces, so 'V4.1' or 'Qwen2.5-VL' are also indexed as separate tokens. Query terms with punctuation inside a word get a split variant ORed in so they match that second copy; negated queries skip the variant because ORing it in would bring back what a '-term' excludes.

Queries containing a negated '-term' do not get split punctuation variants ORed in, because the OR would re-admit papers the negation excludes.

Code: `backend/services/paper_retrieval_service.py::_INNER_PUNCTUATION`, `backend/services/paper_retrieval_service.py::_NEGATED_TERM`

## Search-plan tests reindex GIN after bulk-loading fixture rows

The FTS plan test creates idx_papers_latest_search_vector while the papers table is empty, so rows bulk-inserted afterwards sit in GIN's pending list, and on a tiny table the planner rationally picks a sequential scan or the latest-version index. The test therefore inserts a representative 2000-row selective shape, runs REINDEX and ANALYZE to model the post-backfill production index, and disables seqscan before asserting the GIN plan.

Code: `backend/tests/paper/test_search_fts.py::test_trigger_insert_update_coverage_and_partial_index`

## Single-term entity searches rank as textual ties broken by trends

PostgreSQL ts_rank_cd cover density for a single term only counts repetitions, and the raw-name vector double-counts hyphenated compounds such as 'human-scene'. Single-term queries therefore give every prefix match the same relevance and let entity trend signals break ties, as deterministic_match does; multi-term queries rank adjacency on the separator-normalized name.

Code: `backend/services/entity_search.py::postgres_search_expressions`

## papers.search_vector is maintained only by a PostgreSQL trigger

The full-text search vector on papers is computed by the papers_search_vector_update() trigger function in PostgreSQL. Application code reads the column for ranking but never builds or writes it in Python, so the weighting lives in one place. Changing the weighting requires a SQL migration plus a backfill, not an ORM change.

Code: `backend/models/database/papers.py::Paper.search_vector`
