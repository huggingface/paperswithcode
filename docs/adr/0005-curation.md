# ADR 0005: Paper curation jobs and policy

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## A callback token presented for another job revokes only its owner job

When a curation worker presents a valid callback token for a different job, the worker is treated as compromised. The router stops only the job that owns the token (which invalidates it) instead of pausing all scheduled curation, since one worker must not be able to halt the scheduler. The token hash is cleared and committed before the remote cancel or next dispatch so the token is dead even if those later steps fail.

Code: `backend/routers/codex_curation_callbacks.py::_callback_job`

## A paper is queued at most once per re-check run

One add-evals run reads the whole paper and so covers every new board it mentions. reconcile() drops papers already queued for another benchmark in the same run instead of enqueuing duplicate jobs.

Code: `backend/services/new_benchmark_recheck_service.py::NewBenchmarkRecheckService.reconcile`

## Admin paper jobs wait for Markdown outside the dispatch queue

Admin add-evals and enrich-paper jobs that ran before the paper had any Markdown text are parked in an awaiting-Markdown state outside the dispatch queue. Hourly reconciliation releases them once the paper's Markdown exists, so they neither block the queue nor rerun pointlessly without text.

Code: `backend/services/codex_add_evals_service.py::ADMIN_MARKDOWN_KINDS`

## Automatic external-paper curation runs behind interactive admin jobs

External-paper curation jobs share the admin lane with interactive admin jobs, which run at priority 0. Automatic external-paper jobs use priority 50 so a human-triggered job is never queued behind a backlog of automatic ones.

Code: `backend/services/external_paper_curation_service.py::EXTERNAL_PAPER_PRIORITY`

## Autonomous Codex pricing follows the closed server alias

Model aliases such as diagnosis intentionally differ from model slugs. Pricing environment variables are selected by the same closed server-side alias that selects the model, so the price applied always matches the model actually run and cannot be chosen by a client-provided slug.

Code: `backend/services/autonomous_codex_runner.py::_pricing`

## Autonomous curation run context is committed before write policy checks

For autonomous curation callbacks the run context is created and committed immediately, before any policy check that may reject the requested write. This keeps run monitoring durable even when the write itself is refused and rolled back.

Code: `backend/routers/codex_curation_callbacks.py::_autonomous_callback_context`

## Awaiting-Markdown jobs drop their callback token

When a finished job is parked awaiting Markdown, its callback_token_hash is cleared so the finished attempt's runner can no longer call back. Releasing the job later issues a fresh token for the new attempt.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService.complete`

## Awaiting-Markdown scan rotates unavailable rows to the back

release_awaiting_markdown scans a bounded number of workflows waiting for Markdown, ordered by updated_at. Rows checked but still without Markdown get updated_at bumped so they rotate behind the rest of the scan; otherwise a large backlog of unavailable papers would fill every scan window and starve papers whose Markdown is ready.

Code: `backend/services/hf_daily_curation_service.py::HFDailyCurationService.release_awaiting_markdown`

## Awaiting-Markdown workflows resume regardless of the canary gate

Workflows awaiting Markdown already belong to the canary cohort. Releasing them consumes queue capacity but is not blocked by the gate that limits creating new canary workflows; otherwise the canary could never finish.

Code: `backend/services/hf_daily_curation_service.py::HFDailyCurationService.reconcile`

## Benchmark creation from gaps is the only autonomous taxonomy write

Taxonomy creation (tasks, methods, benchmarks) is otherwise reserved for humans. The autonomous curation operator is granted CREATE_BENCHMARK_FROM_GAP as the single exception, and only for benchmark-gap candidates reported by at least three papers, so agents cannot invent taxonomy from thin evidence.

Code: `backend/services/autonomous_capabilities.py::CAPABILITY_MANIFESTS`

## Benchmark gap review launches are authorized broadly and decisions re-checked at apply

A review-benchmark-gaps job is authorized at launch against the review queue as a whole, because its candidates are not known per-capability up front. Each per-candidate decision the overseer makes is authorized again when applied, so the launch grant alone never creates a benchmark.

Code: `backend/services/curation_autonomy.py::curation_primary_authorization`

## Benchmark mention matching prefilters lines by surface head token

The entity matcher is too slow to run over a whole paper. mentions() first keeps only lines containing the first token of some benchmark surface form and runs the matcher on those lines alone.

Code: `backend/services/new_benchmark_recheck_service.py::NewBenchmarkRecheckService.mentions`

## Bootstrap bundles are keyed by SHA-256 of canonical JSON

Remote-worker bootstrap bundles are content-addressed: the primary key is the SHA-256 of the bundle serialised as JSON with sorted keys and compact separators. Any writer must use the same canonical serialisation or identical bundles will hash differently and be stored twice, breaking dedup across jobs.

Code: `backend/models/database/curation.py::PaperCurationBootstrapBundle`

## Bounded re-review of rejected trending models

A sibling model release can establish the canonical family paper after the original model has dropped off the live HF trending page. Each pass therefore reconsiders a bounded, recency-ordered set of rejected candidates independently of today's discovery feed, so they can converge on the family paper.

Code: `backend/services/hf_trending_model_curation_service.py::HFTrendingModelCurationService._reconcile_once`

## Canary health excludes deferred overflow

The first curation canary cohort (codex_curation_canary_limit workflows) must reach healthy terminal states before the backlog may run. Deferred overflow is durable backlog, not part of that initial cohort, so it is excluded when evaluating canary health; counting it would keep the gate closed forever.

Code: `backend/services/hf_daily_curation_service.py::HFDailyCurationService.reconcile`

## Card revision stays pinned while a curation job is active

Each curation job works against a pinned model-card revision. If a newer revision appears while a job is active, the pass only updates last_seen_at and trending_score; the next hourly pass observes and queues the new revision after the job ends. Re-pinning mid-job would let the job's output describe a different card than it read.

Code: `backend/services/hf_trending_model_curation_service.py::HFTrendingModelCurationService._reconcile_once`

## Catalog admission check and reservation happen without an await

CatalogAdmissionMiddleware compares and increments its active counter with no await in between, so admission is atomic on the worker's event loop without a lock, and over-limit requests get an immediate 503 with Retry-After instead of queuing. Inserting an await between the check and the increment would break the limit.

Code: `backend/services/catalog_admission.py::CatalogAdmissionMiddleware.__call__`

## Codex curation jobs are production-only

Codex add-evals and enrich-paper jobs mutate the catalog. Only immutable production releases may enable them; staging leaves them disabled because staging plays a read-only catalog role. Enabling them on staging would let a second environment write curation results.

Code: `backend/config.py::Settings.codex_add_evals_enabled`

## Commit before slow Hub calls during reconciliation

Reconciliation commits its session before the namespace-wide HF Jobs list call. Holding a pooled connection idle in transaction across that slow call starved public requests of database connections on 2026-10-13. Rows are re-read after the call because a callback may have finished a job meanwhile.

After the slow HF Jobs list call, reconciliation re-reads the active job rows because a runner callback may have completed a job while the call was in flight; acting on the stale snapshot would overwrite that completion.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService.reconcile`

## Commit job completion before dispatching the next job

complete() commits the terminal job state before calling dispatch_next. Queued rows are the durable dispatch backlog, so if dispatch fails after the commit the successor stays queued and is picked up later, instead of a terminal job being stranded without its successor.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService.complete`

## Completed legacy curation jobs satisfy scheduled curation

Before scheduled curation workflows existed, papers were curated through manual PaperCurationJob rows. When deciding which priority papers are still pending, completed jobs of each stage count alongside completed or satisfied workflows, so papers curated by hand are not re-curated.

Code: `backend/services/curation_priority_service.py::pending_daily_papers`

## Curation HF Jobs are launched with an explicit short name

The Hugging Face Hub rejects job names longer than 100 characters, and huggingface_hub derives a name from the image reference when none is passed, which overflows for long digest-pinned images. Curation dispatch always passes an explicit name of the form pwc-enrich-paper-<job id>.

Code: `backend/tests/curation/test_paper_curation_dispatch.py::test_hf_dispatch_retries_with_bounded_exponential_backoff`

## Curation HF Jobs get an explicit short name

huggingface_hub 1.33 and later derive an HF Job name from the image reference when none is given; for the digest-pinned curator image that name exceeds the Hub's 100-character limit and the launch fails. Curation jobs therefore always pass an explicit name pwc-<kind>-<id>.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService._run_job_with_retry`

## Curation Jobs namespace has no default

codex_jobs_namespace deliberately defaults to empty and must be configured per deployment. Launching into the wrong Hugging Face organization fails with a generic Hub 403 and leaves no remote Job to inspect, so a guessed default would produce hard-to-diagnose failures.

Code: `backend/config.py::Settings.codex_jobs_namespace`

## Curation flags every changed existing evaluation as manual-or-legacy

Historical evaluation rows have no trustworthy author or source provenance column. When a curation job changes an existing evaluation row, it is conservatively flagged as manual-or-legacy and the job marked requires_prominent_review, so automatic corrections to possibly hand-curated data are prominent in the dashboard and trace instead of assumed to be automation-owned.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService._apply_authorized`

## Curation jobs get a larger leaderboard-lookup budget than taxonomy searches

Frontier LLM model cards list 40+ benchmarks, and the add-evals skill asks the agent to look up each name plus common variants. A curation job therefore allows 150 leaderboard lookups but only 30 taxonomy and catalog searches; a shared limit of 30 left paper 131976 (Ripple-65B) with no evals.

Code: `backend/routers/codex_curation_callbacks.py::QUERY_LIMITS`

## Curation never re-adds an evaluation a curator removed

If a paper had a row deleted from a leaderboard, curators removed it as incompatible and told the authors. Automatic curation skips new evaluations for that paper on that board and reports the skip instead of putting the row back.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService._apply_evaluations`

## Curation of external papers waits for prepared Markdown

First-party release sites often refuse the curation runner's own fetches, so external (non-arXiv) papers are read from a prepared Markdown copy. Admin Markdown job kinds, including enrichment, wait until that Markdown is ready; otherwise enrichment would tag the paper without having read the page.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService.context`

## Curation org lookups fail fast with two attempts

Organization lookups against the Hugging Face API run inside the curator's synchronous apply request. The client is built with attempts=2 so a rate-limited lookup fails quickly and the organization is skipped, instead of holding the request open through long rate-limit backoffs.

Code: `backend/services/curation_organization_service.py::CurationOrganizationService.hf_client`

## Curation queue runs lower priority numbers first

Paper curation workflows are ordered by an integer priority where lower runs first. The unprioritized backlog uses the column default of 100, HF daily papers use 10 and arXiv papers trending on X use 5, so X-trending papers are curated ahead of daily papers and both ahead of the backlog.

Code: `backend/services/curation_priority_service.py::X_TRENDING_PRIORITY`

## Curation scheduler lanes, caps and pause scopes

Model-release-radar resolutions are a scheduled trigger: they obey the scheduled pause and global capacity and are dispatched in the same lane as trending-model resolutions rather than getting a lane of their own.

Benchmark-gap jobs share the scheduled pause and global capacity with daily and trending paper work, but are dispatched from their own lane capped at BENCHMARK_GAP_MAX_ACTIVE so that the constant daily paper backlog cannot starve them.

The apply_or_verification_failures and terminal_failure_rate health breakers are computed only from daily and trending paper stages. They pause those stages but do not hold back the daily benchmark-gap overseer, which is unrelated to the failures they measure.

New external-paper workflows run in the admin lane but are capped at EXTERNAL_PAPER_MAX_ACTIVE concurrent jobs, and new-benchmark re-checks (policy versions new-benchmark-<dataset id>) share the admin lane under the same kind of cap, so a large backfill cannot take every worker from interactive admin jobs and scheduled daily work.

Re-checks queued when a new leaderboard appears use policy versions new-benchmark-<dataset id> and run in the admin lane capped at NEW_BENCHMARK_MAX_ACTIVE, like external-paper backfills, so they cannot crowd out interactive admin and scheduled daily work.

The single daily review-benchmark-gaps overseer job takes any free worker slot ahead of the benchmark-gap lane cap and is not blocked by the daily-paper health breakers, so the daily review always runs once capacity exists.

A scheduler pause only holds back queued jobs with a scheduled trigger; admin jobs and benchmark-promotion jobs continue to dispatch during a pause. Status reporting marks only those held scheduled jobs as paused.

Code: `backend/services/codex_add_evals_service.py::RADAR_TRIGGER`, `backend/services/codex_add_evals_service.py::SCHEDULED_TRIGGERS`, `backend/services/codex_add_evals_service.py::SCHEDULED_HEALTH_PAUSES`, `backend/services/codex_add_evals_service.py::EXTERNAL_PAPER_MAX_ACTIVE`, `backend/services/codex_add_evals_service.py::NEW_BENCHMARK_MAX_ACTIVE`, `backend/services/codex_add_evals_service.py::CodexPaperJobService._dispatch_next_locked`, `backend/services/codex_add_evals_service.py::CodexPaperJobService.paper_history`

## Curator image is digest-pinned per deployment

codex_jobs_image has no default. Each deployment pins its own digest of the image built by .github/workflows/build-codex-curator-image.yml, so production and staging cannot silently run a different or floating curator image.

Code: `backend/config.py::Settings.codex_jobs_image`

## Daily backlog frees queued slots without interrupting running jobs

When daily papers are pending after the canary is released, queued historical attempts are deferred to free admission slots, but their queued attempts are kept intact. Workflows with running or dispatching remote jobs, or an active second stage, are never interrupted, since cancelling them wastes paid remote work or strands a half-finished workflow.

Code: `backend/services/hf_daily_curation_service.py::HFDailyCurationService.reconcile`

## Daily cohort is admitted before deferred historical work

Deferred historical workflows only fill capacity left after today's rolling HF daily cohort, including previously deferred daily papers, has been admitted, so fresh daily papers are never queued behind backlog.

Code: `backend/services/hf_daily_curation_service.py::HFDailyCurationService.reconcile`

## Daily curation enqueue reaps orphaned remote Jobs first

Remote HF Jobs that end without calling back, for example during an API outage, keep their rows holding dispatch slots. The scheduled enqueue therefore reconciles job state before reconciling new papers; otherwise such rows are reaped only when the admin page is read and dispatch stalls.

Code: `backend/scripts/enqueue_hf_daily_paper_curation.py::main`

## Discovery dry run persists only its rollout marker

During the staged rollout of trending-model curation, the discovery dry run rolls back its discovery transaction and then commits only `discovery_dry_run_completed` on the rollout state. This guarantees the dry cycle can never publish or queue anything while still advancing the rollout phase.

Code: `backend/services/hf_trending_model_curation_service.py::HFTrendingModelCurationService.reconcile`

## Duplicate identical score evidence is tolerated

Scheduled evaluation proposals need score evidence per task/dataset/metric. Identical repeated entries and entries for rows the curator later dropped are harmless and accepted; only conflicting or missing source cells are rejected, so agent formatting noise does not trip validation.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService._validate_scheduled_policy`

## Evaluation change detection treats None as omitted

EvaluationService's legacy update fields have no explicit set sentinel: None means omitted, not clear. best_rank is recalculated after writes, and create_evaluation copies a paper-native source_url onto external_source_url. Change detection therefore ignores proposed None values for methodology, best_rank, evaluated_on, source_url and external_source_url so post-write verification accepts the derived catalog values.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService._evaluation_changes`

## Every remote curation attempt is its own immutable job row

Automatic retries of failed curation jobs enqueue a new PaperCurationJob row rather than resetting the failed one, so every remote attempt, its error and its trace remain preserved as history.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService._advance_workflow`

## External release merge is retried after add-evals

The merge of an external release paper into its arXiv duplicate can be skipped while the launch page is still being dispatched. It is retried when the add-evals stage completes, so scores add-evals skipped as duplicates are moved onto the canonical paper.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService._advance_workflow`

## Failed or canceled re-checks free their cap slot

Re-check jobs in queued, dispatching, running or completed state hold their paper and count toward the per-benchmark cap. Failed or canceled jobs are excluded, so the paper can be queued again and the slot is freed.

Code: `backend/services/new_benchmark_recheck_service.py::_HELD`

## Flush after claiming a handleless organization

Curation sessions run without autoflush. After applying a profile to a handleless row, the service flushes immediately so later proposals in the same call see the row as handled and do not claim it again or create duplicates.

Code: `backend/services/curation_organization_service.py::CurationOrganizationService._resolve`

## Flush before canary eligibility queries

Production database sessions run with autoflush disabled. _release_canary_backlog flushes first so that its eligibility queries see the workflow transition that triggered the release.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService._release_canary_backlog`

## Image revision applies only to legacy Docker Space images

codex_jobs_image_revision is the Hub revision of a legacy Docker Space curator image and is ignored when codex_jobs_image is a registry digest. Operators should not set it for digest-pinned images.

Code: `backend/config.py::Settings.codex_jobs_image_revision`

## Job completion locks the row for the whole transition

complete() refreshes the job row with SELECT ... FOR UPDATE before inspecting it, because authentication may have loaded the row before another callback finished the job. The lock serializes the complete terminal transition, not just the final status write, so concurrent callbacks cannot both complete a job.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService.complete`

## LLM-suggested release links are cross-checked against page HTML

External resource extraction keeps only GitHub and Hugging Face links that actually appear in the fetched page HTML, so the LLM cannot hallucinate links. GitHub links become official repositories, so page links the LLM did not present as the release's own code are never added back; Hugging Face links are artifacts, so an empty LLM answer falls back to every HF artifact on the page.

Code: `backend/genai_steps/extract_external_resource_metadata.py::extract_external_resource_metadata`

## Late enrich re-runs do not reopen finished workflows

If an enrich-paper job finishes after its workflow's add-evals stage already completed (a late or admin re-run), the workflow is marked completed instead of moved back to running. retry() is responsible for reopening a workflow explicitly before a re-run starts.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService._advance_workflow`

## Mistyped gap-review ids are proposal errors

In review-benchmark-gaps jobs, a decision that references a candidate outside the job's review scope raises a ValueError (a fixable, retryable proposal error) rather than an AutonomousCapabilityDenied. A capability denial would count as a security event and pause the scheduler over what is usually an agent typo.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService._validate_scheduled_capability_boundary`

## Model-paper resolution may create external papers only from first-party sources

RESOLVE_MODEL_PAPER is scoped to trending-model candidates and release-radar signals but can create an external paper as a side effect. That is acceptable because the resolution service refuses to create one unless the source is first-party and not a duplicate of an existing paper.

Code: `backend/services/autonomous_capabilities.py::CAPABILITY_RESOURCE_KINDS`

## New-benchmark re-checks are capped per benchmark

Benchmark-promotion re-checks enqueue add-evals jobs in the admin lane, which dispatches ahead of daily curation. MAX_PER_BENCHMARK (5) caps jobs per new benchmark across runs, and MAX_PER_RUN caps each run, so one popular benchmark cannot starve daily curation; the dispatcher separately caps this lane's active jobs.

Code: `backend/services/new_benchmark_recheck_service.py::MAX_PER_BENCHMARK`

## Only handleless rows can be claimed by name

When matching an HF organization profile to the catalog by name, only a row without an hf_slug can be that organization's entry; a same-named row with another handle is a look-alike or a different organization and is left alone.

Code: `backend/services/curation_organization_service.py::CurationOrganizationService._resolve`

## Only the curation operator may create benchmarks from gaps

Autonomous operators have isolated capability sets. The curation operator gets CREATE_BENCHMARK_FROM_GAP as a narrow exception so gap reviews can add missing benchmarks, while autonomous submission review keeps every taxonomy creation human-only.

Code: `backend/tests/curation/test_policy.py::test_curation_capabilities_are_isolated_from_submission_review`

## Pair-judge candidates are shown in hashed blind order

When the judge grades disagreements between paired Codex and Pi shadow proposals, candidates are ordered by a hash of the pair id, field, value and origin, never by origin alone. A fixed origin order would let the judge infer which agent produced each candidate and bias the grading.

Code: `backend/services/curation_pair_judge.py::disagreement_candidates`

## Paperless curation contexts still include paper.id

The pinned curation runner image prints context paper.id unconditionally. Benchmark-gap jobs have no paper, so their context carries paper: {id: null}; omitting the key would crash the pinned runner.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService.context`

## Pi curation token is limited to Inference Providers scope

The Pi curation agent can read its own Hugging Face token, so curation_pi_hf_token must be a fine-grained token restricted to "Make calls to Inference Providers" with no other Hub permission. A broader token would let a prompt-injected agent act on the Hub.

Code: `backend/config.py::Settings.curation_pi_hf_token`

## Pi enrich stage uses medium thinking

Enrich is tag lookup rather than score extraction. High thinking made the Pi enrich stage 1.6x slower than Codex while its tag precision already led by 5 points, so enrich uses medium thinking while other Pi stages keep high.

Code: `backend/config.py::Settings.curation_pi_enrich_thinking`

## Pi runner jobs are shadow-only comparisons

Curation jobs with runner "pi" are shadow comparison runs paired with a Codex job via paired_job_id. They never apply catalog mutations and are excluded from every scheduled lane and circuit breaker, so their failures or costs cannot affect production curation.

Code: `backend/models/database/curation.py::PaperCurationJob.runner`

## Pi shadow curation jobs are read-only and never retried

Pi runner jobs run as shadows paired with Codex jobs for comparison. They never write to the catalog, so callbacks give them no autonomous run context, and a failed Pi run is itself a comparison result, so the retry endpoint refuses them with 409.

Code: `backend/routers/codex_curation_callbacks.py::retry_job`, `backend/routers/codex_curation_callbacks.py::apply_mutation`

## Pi shadow jobs are exempt from the one-active-job-per-stage index

The partial unique index allowing one active curation job per paper, kind and policy version excludes triggers 'admin' and 'pi-shadow'. Pi shadow jobs must run concurrently beside the Codex job they mirror, so they cannot share the uniqueness constraint.

Code: `backend/models/database/curation.py::PaperCurationJob.__table_args__`

## Pi shadow jobs see their Codex pair's context snapshot

A Pi shadow job is given the context_snapshot captured when its paired Codex job first saw the paper, rather than fresh catalog state. Otherwise catalog changes made by the Codex job would leak into the shadow job and make the comparison between the two proposals unfair.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService.context`

## Pi shadow jobs use their own trigger

Pi shadow jobs mirror a sampled daily curation stage on the Pi harness for comparison. They carry the dedicated pi-shadow trigger so they are excluded from every scheduled lane, health breaker and daily token guardrail and cannot affect production curation scheduling.

Code: `backend/services/codex_add_evals_service.py::PI_SHADOW_TRIGGER`

## Pi shadow runs are sampled, comparison-only and never queued

A sample of daily-curation stages is paired with a second job on an open model through HF Inference Providers. Shadow runs only store validated proposals for comparison, use their own small slot pool, and are skipped rather than queued when the pool is full or any Pi setting is missing, so they never delay or affect production curation.

Code: `backend/config.py::Settings.curation_pi_shadow_sample_rate`

## Pi shadow traces do not touch the Codex trace breaker

The curation scheduler trips a breaker on consecutive Codex trace failures. Pi runs are shadow traffic, so their trace successes and failures neither reset nor increment consecutive_trace_failures; only rows with runner 'codex' do. Otherwise shadow runs could mask or cause Codex breaker pauses.

Code: `backend/services/curation_trace_service.py::CurationTraceService.preapply`, `backend/services/curation_trace_service.py::CurationTraceService.finalize`

## Promoted-benchmark re-checks may write only that benchmark

When a re-check job runs after a benchmark is promoted from a gap candidate, its context names promoted_benchmark and the job may write evaluation rows only for that benchmark, keeping the re-check from changing unrelated leaderboards.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService.context`

## Re-check requires two Markdown mentions or one abstract mention

A full paper often names a benchmark once in related work without reporting results on it. The new-benchmark re-check therefore requires at least two mentions in stored Markdown, but accepts a single mention when only the abstract is available.

Code: `backend/services/new_benchmark_recheck_service.py::MIN_MARKDOWN_MENTIONS`

## Read-path reconciliation is throttled to one Hub call per process per 30 s

Admin pages poll curation job status every few seconds, and reconciliation lists every remote HF Job in the namespace. Read paths therefore share a single reconcile call per process per READ_RECONCILE_INTERVAL_SECONDS (30 s) instead of calling the Hub on every poll.

Code: `backend/services/codex_add_evals_service.py::READ_RECONCILE_INTERVAL_SECONDS`

## Reconcile commits admin releases before the cohort fetch

reconcile commits the release of admin workflows awaiting Markdown before fetching HF daily cohorts. The cohort fetch is slow network I/O, and holding the released rows' locks through it would block admin cancel requests.

Code: `backend/services/hf_daily_curation_service.py::HFDailyCurationService.reconcile`

## Release pages are the paper for blog-only external papers

External papers published only as a blog post or release page have no Markdown or PDF. Curation treats the release page (paper_source document) as the paper, so a missing Markdown or PDF is not missing evidence and enrichment must still tag tasks and add official Hub repositories.

Code: `backend/tests/curation/test_codex_add_evals.py::test_remote_curation_reads_external_release_pages_as_the_paper`

## Release-signal jobs reuse the candidate context shape

The pinned resolve-model-paper runner reads the same candidate fields (id, repo_id, readme_sha, model_card_url) for every resolution job. A release-radar lead is a page about the release rather than a model card, but its lead URL is still passed as model_card_url and the lab/model name as repo_id so the pinned image keeps working without a runner change.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService._release_signal_context`

## Remote curation Jobs use dedicated credentials

Remote paper-curation workers run on Hugging Face Jobs, outside the VPS. They get their own namespace, Hub token and OpenAI key rather than reusing the general hf_token or database credentials, so a compromised or misbehaving remote job cannot reach the database or act with the site's general Hub identity.

Code: `backend/config.py::Settings.codex_jobs_token`

## Resolve the canonical HF handle before matching catalog orgs

The catalog already holds a few look-alike organization rows, for example a second "Stanford University" under a squatted handle. Curation therefore fetches the Hugging Face profile and settles on the canonical handle before consulting the catalog, so proposals do not attach papers to an impostor row.

Code: `backend/services/curation_organization_service.py::CurationOrganizationService._resolve`

## Resolved trending models are revisited until their paper's workflow ends

A trending model may resolve to a paper that already has an active daily curation workflow. Instead of dropping it, each non-dry reconcile pass idempotently revisits resolved candidates whose paper workflow was active, so the candidate is released as soon as that workflow finishes.

Code: `backend/services/hf_trending_model_curation_service.py::HFTrendingModelCurationService._reconcile_once`

## Retry reopens the parent workflow before enqueueing

When an operator retries a terminal job that belongs to a workflow, the workflow is set back to running and flushed before the new job is enqueued, so the workflow-ownership check runs against the reopened workflow before enqueue can commit a new job row.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService.retry`

## Runner callback transport errors are not curation failures

Remote runner failures named after network or decoding errors (URLError, RemoteDisconnected, TimeoutError, ConnectionResetError, IncompleteRead, HTTPError, JSONDecodeError) on the runner's own callbacks to the site are classified as transport failures: they are usually Cloudflare 5xx or empty/HTML edge responses and say nothing about the curation. Applies run inside Codex, whose rejections never use these names. Transport failures are excluded from the daily-stage failure breakers, while a separate transport breaker still pauses scheduling when they dominate, catching systemic issues such as a release that cannot serve its bootstrap bundle.

Code: `backend/services/codex_add_evals_service.py::_TRANSPORT_FAILURE`

## Runner transport breaker pauses all scheduled lanes

Individually retried transport failures are noise, but when more than half of the latest 25 scheduled stages lost their callbacks the runners cannot reach the site at all. That runner_transport_failures pause holds every scheduled lane and takes precedence over the daily-only failure breakers.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService._evaluate_scheduled_health`

## Scheduled applies must match the pre-apply trace exactly

Scheduled curation jobs first store a durable pre-apply trace, which is the reviewable record of what the job intends to change. The apply request is rejected unless its proposal is exactly equal to that stored pre-apply proposal, so nothing is written that reviewers could not see in the trace.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService._validate_scheduled_policy`

## Scheduled curation gets one retry after a validation rejection

A scheduled curation worker gets one chance to correct an ordinary proposal-validation error: the mutation stays open after the first rejection and the error is returned as retry feedback. A second rejected proposal closes the job, bounding agent retries.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService._apply_authorized`

## Scheduled curation requires HTTPS for new project pages only

Scheduled curation rejects project-page links that are not HTTPS, but legacy imported HTTP pages already attached to the paper may be retained unchanged. Rejecting them would make every enrich proposal for such papers fail validation or force removal of legitimate legacy links.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService._validate_scheduled_policy`

## Scheduled evaluations get the paper route as source URL

Scheduled jobs do not choose the catalog source URL of evaluations; the paper route is the only accepted value. Rather than rejecting a mismatched URL and counting a harmless agent formatting mistake toward the circuit breaker, validation overwrites source_url with the expected paper route. Primary arXiv or HF URLs remain in validation evidence and traces.

Code: `backend/services/codex_curation_callback_service.py::CodexCurationCallbackService._validate_scheduled_policy`

## Scheduled token usage loads only summed columns

The scheduled token-usage snapshot queries only finished_at, input_tokens and output_tokens. Loading full PaperCurationJob rows pulled about 1,300 completed jobs with their bootstrap bundles into memory on every dispatch, which is unaffordable on the 16 GB VPS.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService._scheduled_usage_snapshot`

## Scoped query-limit 429s state that the limit is final

Curation agents interpret a bare HTTP 429 as a transient rate limit and sleep and retry. When a job exhausts its scoped query budget the API still returns 429 but the detail explicitly says the limit is final for this job, so agents stop instead of waiting.

Code: `backend/routers/codex_curation_callbacks.py::_consume_query`

## Source-ready historical work resumes in spare capacity

After daily admission, reconcile releases historical workflows whose Markdown is now ready, using capacity left over. Blocked daily papers must not prevent this, and existing awaiting-Markdown workflows may resume even before the canary opens.

Code: `backend/services/hf_daily_curation_service.py::HFDailyCurationService.reconcile`

## The first canary cohort has a fixed size

Before the canary is released, reconcile creates up to codex_curation_canary_limit workflows once. Later reconciliations never add to an existing canary cohort, so the canary's health verdict is based on a fixed, known sample.

Code: `backend/services/hf_daily_curation_service.py::HFDailyCurationService.reconcile`

## The live HF daily cohort is authoritative for active workflows

When a paper already has a queued, running or deferred workflow, including one created by a conference backfill under the same policy, the live HF daily cohort date and order overwrite the existing ones, and its jobs are reprioritised accordingly.

Code: `backend/services/hf_daily_curation_service.py::HFDailyCurationService.reconcile`

## Thumbnail state blocks completion only for admin jobs

The VPS queues thumbnail generation at enqueue time. Scheduled runners are told not to wait for it, so for scheduled triggers (and resolve-model-paper jobs) a missing or failed thumbnail does not block completion; only admin jobs treat thumbnail failure as a completion error.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService.complete`

## Token guardrail never replaces an operator or security pause

When daily scheduled token usage exceeds the threshold the scheduler pauses with condition daily_token_guardrail, but only if no other pause condition is set. An operator or security pause takes precedence and is never overwritten by a usage observation, so it cannot be silently lifted when the token pause later expires at UTC rollover.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService._scheduled_usage_allowed`

## Trace decompression is bounded separately from wire size

Curation traces arrive gzip-compressed and are checked against MAX_TRACE_BYTES, but tool output can expand far beyond the compressed size. decode_events reads at most MAX_EXPANDED_TRACE_BYTES + 1 bytes from the gzip stream and rejects anything larger, so an oversized or malicious payload cannot exhaust API worker memory.

Code: `backend/services/curation_trace_service.py::CurationTraceService.decode_events`

## Trace finalization failure does not undo an applied curation

If a curation job's apply succeeded but final trace storage failed, the job is not marked failed, rolled back or rerun. The trace stays retryable and visible to operators, so a storage hiccup never reverts or duplicates a valid catalog mutation.

Code: `backend/services/codex_add_evals_service.py::CodexPaperJobService.complete`

## Trace finalize re-reads the job row under a lock after upload

The server may apply and commit a curation result while the trace upload is running. finalize therefore refreshes the job row with SELECT ... FOR UPDATE after uploading, so the subsequent checks see any result recorded meanwhile and do not overwrite it with stale state.

Code: `backend/services/curation_trace_service.py::CurationTraceService.finalize`

## Workers may only fill an empty mutation result

A curation job's mutation_result may be recorded by the server while it applies the result, including the resolved paper that the thumbnail queue targets. The worker's own account goes into result.json in the trace, and finalize only sets mutation_result when it is empty. This prevents a holder of the job's bearer token from replacing a server-recorded result.

Code: `backend/services/curation_trace_service.py::CurationTraceService.finalize`
