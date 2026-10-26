# Paper embeddings: evaluation, operations, and rollback

This system maintains one pinned title-plus-abstract embedding generation for
related papers and hybrid paper search. It is disabled by default. Nothing in
the development workflow creates a Hugging Face Bucket, Job, scheduled Job, or
Inference Endpoint unless an operator adds the command's explicit `--execute`
and confirmation value.

## Contracts and release gates

- Input is `normalized title + "\n\n" + normalized abstract`; title-only rows
  remain eligible. The exact `title-abstract-v1` formatter and content hash live
  in `backend/services/embedding_contracts.py`.
- The required pinned four-model bakeoff is
  `backend/config/embedding_bakeoff.json`. Qwen 256/512/1024 configurations use
  one full-dimensional pass. Jina is not production-eligible without an
  explicit license decision.
- The canonical judgment datasets belong in a private, revision-pinned HF
  Dataset repository. Git contains only the sanitized CI fixtures and loaders:
  `paper_search_relevance.json` and `related_papers_relevance.json`.
- Compare keyword-only, vector-only, and RRF hybrid modes. Related release
  metrics are nDCG@4, graded Precision@4, Recall@20, duplicate rate, diversity,
  coverage, and latency. Search release metrics are MRR@10, nDCG@10, Recall@20,
  exact-identity regressions, and p50/p95 latency.
- Do not activate a generation until the blinded related set beats the task
  baseline, natural-language hybrid search beats FTS, and every current paper
  has a vector. `pwc embeddings activate` enforces zero missing current rows.
- The canonical private judgment package is
  `nielsr/paperswithcode-relevance-judgments`, pinned for this pilot at revision
  `924febd6a2de42f450cce9cc20fab9909aeadd32`. Its first pass retains every
  pooled candidate for 20 balanced sources so all 13 systems have complete
  top-four judgment coverage. System provenance stays under `private/` until
  annotations and adjudication are frozen.
- F2LLM-v2-80M revision
  `f4a16a11c9f5c8c7e22694653de6ce75430f4538` natively emits 320 dimensions.
  The pinned configuration and validation must use 320; do not fabricate or
  truncate a 1024-dimensional representation for this model.

Create a blinded pool and score completed runs:

```bash
uv run --env-file backend/keys.env python backend/scripts/evaluate_embedding_bakeoff.py \
  run-f2llm.json run-qwen.json \
  --judgments backend/tests/fixtures/related_papers_relevance.json \
  --blinded-pool /tmp/related-annotation-pool.json
```

Download and launch the private first-pass annotation workflow:

```bash
uv run --env-file backend/keys.env hf download \
  nielsr/paperswithcode-relevance-judgments --type dataset \
  --revision 924febd6a2de42f450cce9cc20fab9909aeadd32 \
  --local-dir /tmp/pwc-related-judgments
uv run --env-file backend/keys.env python \
  backend/scripts/related_papers_annotation.py verify-package \
  --root /tmp/pwc-related-judgments
uv run --env-file backend/keys.env python \
  backend/scripts/related_papers_annotation.py serve \
  --tranche /tmp/pwc-related-judgments/data/first_pass/blinded_pool.jsonl \
  --state-dir /tmp/pwc-related-annotation-state \
  --annotator-id ANNOTATOR_1 --annotator-index 0 --annotator-count 2 \
  --open-browser
```

Use pseudonymous annotator IDs. The second annotator uses index `1`. Use the
same script's `export`, `merge`, `serve-adjudication`,
`export-adjudication`, and `validate` subcommands. Only after labels are frozen
may scoring run with its explicit `--confirm UNBLIND_AND_SCORE` gate.

## Safe pilot workflow

First install pgvector only in a disposable PostgreSQL 16 instance. Never point
the integration test at the application database:

```bash
TEST_PGVECTOR_DATABASE_URL=postgresql://.../pwc_vector_disposable \
uv run --env-file backend/keys.env pytest \
  backend/tests/paper/test_embeddings_migration.py
```

Apply `backend/database/migrations/add_paper_embeddings.sql` only in that
database. It creates generation tables, list partitions, dimension validation,
and a cosine HNSW expression index per generation. Record exact-vs-HNSW recall,
filtered recall, index/table bytes, build duration, KNN p50/p95, and server
memory before seeking production migration authority.

Export a bounded pilot. The database snapshot contains no credentials:

```bash
uv run --env-file backend/keys.env pwc embeddings export \
  --output-root /tmp/pwc-embedding-pilot --run-id pilot-001 \
  --model codefuse-ai/F2LLM-0.6B \
  --revision eb2778d335980b42b986c75d7fe3a78be19ef3a6 \
  --dimensions 1024 --max-rows 5000
```

Review an `hf buckets sync --dry-run` before uploading to a pre-existing private
Bucket. Bucket creation is a separate authorized operation. `pwc embeddings
run` prints its Job command by default; it forwards only `HF_TOKEN`, pins the
model revision, mounts the configured Bucket, and uses `l4x1` unless overridden.
The worker validates input checksums, dynamically reduces batches on OOM,
length-sorts inputs, calls `encode_document`, normalizes vectors, writes atomic
float16 Parquet shards, resumes completed shards, and records throughput,
package/hardware provenance, peak VRAM, and checksums.

Import into a new non-active generation, review its validation report and build
ANN/exact benchmark report, then activate separately:

```bash
uv run --env-file backend/keys.env pwc embeddings import \
  --input-manifest /tmp/run/input/manifest.json \
  --output /tmp/run/output --bucket-run-uri hf://buckets/OWNER/BUCKET/runs/pilot-001
uv run --env-file backend/keys.env pwc embeddings status --json
uv run --env-file backend/keys.env pwc embeddings activate GENERATION_ID --confirm ACTIVATE
```

## Incremental refresh and retention

The hourly `pwc-cron-refresh-paper-embeddings.timer` runs at minute 15, ordered
after the HF daily-paper import at minute 0, through `pwc-cron
refresh_paper_embeddings` (launcher lock and timeout in
`deploy/cron_launcher.py`; the GitHub workflow of the same name is manual
dispatch only). The job
(`.github/workflows/scripts/hourly/refresh_paper_embeddings.py`) sends at most
500 missing or content-changed latest papers to the protected TEI endpoint in
batches of 16 (`--limit`/`--batch-size`, or `PWC_EMBEDDING_CRON_LIMIT` and
`PWC_EMBEDDING_CRON_BATCH_SIZE`) and upserts validated, normalized vectors at
the active generation's dimension.

The document call uses `prompt_name=document`, matching the full-corpus
`SentenceTransformer.encode_document` contract. Before each upsert the source
paper rows are locked and their content hashes rechecked; a paper edited during
inference is skipped for the next run. Endpoint 408/429/502/503/504 responses
receive bounded retries for scale-from-zero and transient throttling. The
endpoint defaults to `PWC_HF_QUERY_EMBEDDING_ENDPOINT_URL`, with
`PWC_PAPER_EMBEDDING_ENDPOINT_URL` available as a job-specific override.

Each attempt is recorded in `embedding_pipeline_runs`, including no-work and
failed runs, and the job is registered in the admin CRON dashboard. Search
continues through FTS and related papers use the task fallback while a delta is
unavailable. The freshness SLO remains 24 hours.

For a large rebuild or a new generation, continue to use the immutable
export/Bucket/HF Job/import pipeline. The endpoint CRON is intentionally bounded
incremental maintenance, not a full-corpus replacement.

`pwc embeddings status` reports active generation, embedded/missing/title-only
coverage, oldest missing paper, the 24-hour breach state, and recent
export/import runs. Alert on: missing count increasing for two runs, oldest
missing over 24 hours, failed/incomplete Job, stale import rows, HNSW recall
below its measured gate, p95 KNN regression, endpoint fallback spikes, or disk
headroom below the measured two-generation rollout budget.

Bucket artifacts use immutable run prefixes. Feed reviewed run metadata to
`pwc embeddings retention-plan`; active, previous, and pinned runs are protected,
successful experiments retain 90 days, and failed runs retain 14. Applying a
reviewed plan is a separate destructive `retention-apply` command requiring
`--confirm DELETE_BUCKET_ARTIFACTS`.

## Serving, endpoint, and rollback

Related requests read the source document vector and execute one pgvector KNN;
there is no online model call. Missing/low-confidence vectors fill from the
existing first-task/citation fallback. A prior ArXiv version may provide the
source vector during a short refresh gap, but old versions never become
candidates and telemetry records that state.

Hybrid search calls an authenticated HF Inference Endpoint with the active
generation's exact model/revision/dimension/instruction contract. `pwc embeddings
endpoint-plan` deploys through the embedding catalog so the endpoint uses TEI,
then pins the revision and minimum-zero/maximum-one scaling policy. It does not
deploy by default. Query requests include the active generation's Matryoshka
dimension and the model's `query` prompt name. The application enforces a
bounded timeout,
non-blocking concurrency, a circuit breaker, response validation, a short
generation-versioned vector cache, and immediate FTS fallback on cold start or
error. Raw queries are not logged; logs use a normalized fingerprint.

The search endpoint accepts `?mode=keyword|semantic|hybrid` for per-request
switching. Without that parameter, `PWC_PAPER_SEARCH_MODE` selects the default.
Semantic and hybrid modes fall back to keyword search if query inference is
unavailable.

After retrieval, a shared canonical-entity stage recognizes exact method names,
full names, and slugs from the method taxonomy. A method's explicit
`source_paper_id` is promoted to rank one for bare navigational queries and
explicit requests such as "original BERT paper". Broader topical queries such
as "BERT compression" retain their normal retrieval order. If source metadata
is missing, the highest-cited latest paper linked to that method is used as a
fallback; `papers.citation_count` is refreshed from Semantic Scholar, with
publication date and paper ID as deterministic tie-breakers. The relevance
fixture's `expected_top` field is a release gate for canonical top-one results.

Short queries also support incomplete final terms and bounded spelling errors.
Method names are matched with conservative exact, whitespace-normalized,
token-prefix, and edit-distance tiers; ambiguous matches abstain. A partial
GiST `pg_trgm` title index generates incomplete-title and typo candidates.
Candidate title-token windows are reranked with
bounded edit distance and Semantic Scholar citations, and only a clear
similarity gap or a citation-dominant tie can force a fuzzy top result. Queries
longer than two terms stay on normal retrieval unless they explicitly resolve a
taxonomy entity. Apply `enable_pg_trgm.sql` before building
`add_paper_title_trigram_index.sql`; the latter must run outside a transaction
because it uses `CREATE INDEX CONCURRENTLY`.

Rollout flags are independent:

```text
PWC_RELATED_PAPERS_MODE=task|embedding
PWC_PAPER_SEARCH_MODE=keyword|semantic|hybrid
PWC_EMBEDDING_GENERATION_ID=<id>
PWC_QUERY_EMBEDDER=disabled|hf_endpoint
PWC_HF_QUERY_EMBEDDING_ENDPOINT_URL=https://...
```

Rollback changes flags or the configured generation. Keep the previous
generation and its index until the new generation is stable. Do not delete
generation data, rebuild/restart production, or scale/pause/delete external
resources during an incident without separate authority.
