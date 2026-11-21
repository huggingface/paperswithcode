# ADR 0018: Paper catalog, edits and submissions

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## ASCII feed search uses C collation for ILIKE

Under the database's en_US.UTF-8 collation, ILIKE is about 2.5x slower than under "C", which folds ASCII patterns identically. search_filter applies COLLATE "C" to title and abstract for ASCII search terms on PostgreSQL only; non-ASCII terms keep the default collation for correct case folding.

Code: `backend/services/paper_feed_executor.py::search_filter`

## Account edit lock is always taken before paper locks

Paper edit access uses PostgreSQL transaction-scoped advisory locks shared across all processes: one per account subject and one per paper. Every path, including suspending or approving a grant, must acquire the account lock before any paper lock. A consistent order prevents deadlocks between concurrent edits and grant changes.

Code: `backend/services/paper_edit_access.py::PaperEditAccess.lock_account`

## Auto-applied edits are attributed to the submitter

Catalog mutation events for auto-approved edits name the submitting contributor as actor (role contributor), not a reviewer, so contributor history and bulk revert by account include them. Manually approved edits are attributed to the reviewing admin.

Code: `backend/services/pending_edit_service.py::PendingEditService._approval_event`

## Autonomous review run summaries are committed before the mutation

Autonomous submission review records a run summary for monitoring and audit. The summary is committed before applying the decision, so it stays durable even when manual mode later blocks the mutation. Folding the commit into the mutation transaction would lose the audit record of blocked runs.

Code: `backend/cli_submissions.py::decide_submission`

## Bucket migration is recorded with a conditional upsert

The saved-paper IDs and listing endpoints often run concurrently for the same user, so recording the bucket migration uses INSERT ... ON CONFLICT DO UPDATE guarded by saved_papers_bucket_migrated_at IS NULL. A plain insert would race into unique-constraint errors, and the guard keeps the first migration timestamp.

Code: `backend/services/bookmark_service.py::BookmarkService.record_bucket_migration`

## Catalog mutations recheck write access before committing

A long-running catalog mutation batch can cross a grant expiry or a UTC daily quota boundary between its initial access check and its commit. Write access is therefore checked again after the mutation is applied and before the event is recorded and committed, so expired or over-quota actors cannot publish changes.

Code: `backend/services/catalog_mutation_service.py::CatalogMutationService.mutate`

## Dataset variants tolerate non-list legacy values

Legacy PwC imports stored a JSON object instead of a list of variant names for a few BARS datasets. API models coerce non-list values (objects, bare strings) to null and drop null list items instead of failing, so those rows still serialize.

Code: `backend/tests/test_api_models_tolerate_legacy_rows.py::test_dataset_variants_and_languages_tolerate_non_list_values`

## Deferred autonomous reviews leave the human queue row untouched

When an autonomous review returns defer or needs-human, the pending submission row is deliberately left unchanged so it stays in the human review queue. Execution of the autonomous run is recorded separately in the run ledger rather than by changing the queue row's status.

Code: `backend/cli_submissions.py::decide_submission`

## Evaluation creation is versioned against the paper's evaluation collection

Optimistic concurrency for catalog edits compares a snapshot hash of the edited entity. A new evaluation has no existing row, so creation snapshots and locks the paper-scoped evaluation collection that the editor loaded, detecting concurrent changes to that paper's evaluations instead.

Code: `backend/services/evaluation_curation_service.py::EvaluationCurationService.create`

## Evaluations move to the latest paper version instead of being copied

Leaderboards list evaluation rows from every version of a paper, so when a new arXiv version becomes latest its evaluations are moved from the old version rather than copied; the old version keeps none. Copying would show each result twice on leaderboards.

Code: `backend/services/paper_version_refresh_service.py::PaperVersionRefreshService._copy_curated_links`

## Known-host trust compares hostnames exactly

Auto-approval trusts a host already used by an existing project page. The SQL LIKE query only narrows candidates; each candidate URL's hostname is then compared exactly, so a host that merely appears in another URL's path or query string earns no trust.

Code: `backend/services/pending_edit_auto_approval.py::PendingEditAutoApproval._host_is_trusted`

## Legacy benchmark suggestions keep their old payload shape

Benchmark and task names later became free-text administrative fields, but pending benchmark submissions created before that change still carry the older payload shape with `task_ids`. The validator keeps a path for that shape so stored submissions remain reviewable; removing it breaks review of persisted pending edits.

Code: `backend/services/pending_edit_payloads.py::_validate_new_benchmark`

## Merged papers reset hf_artifacts_scanned_at

When an external release is merged into its ArXiv paper, the explicit Hugging Face artifact links are transferred and then hf_artifacts_scanned_at is cleared on the ArXiv paper. This makes the next HF artifact discovery run rescan the paper and reconcile the transferred links with ArXiv-based discovery instead of treating the paper as already scanned.

Code: `backend/database/paper_merge.py::_merge_hf_artifacts`

## Model releases are moved before deleting the external paper

ModelRelease rows reference papers with a cascading foreign key, so deleting the external paper during a merge would silently delete its model identities. The merge therefore reassigns or dedupes releases by canonical_name onto the ArXiv paper before the external row is removed.

Code: `backend/database/paper_merge.py::merge_external_paper_into_arxiv`

## Most human-only suggestions are record-only on approval

For human-only suggestion types, approval only records the reviewer's decision and an admin creates the entity separately; the one exception is new_organization, whose approval creates the organization. RECORD_ONLY_EDIT_TYPES encodes that split.

Code: `backend/services/pending_edit_service.py::RECORD_ONLY_EDIT_TYPES`

## Paper edit authorization purges expired rows on every start

Starting a device authorization serializes on an admission lock and deletes authorizations expired for over a day. Anonymous callers can start authorizations without ever opening the browser, so cleanup happens on admission to keep storage bounded.

Code: `backend/services/paper_edit_authorization.py::PaperEditAuthorizationService.start`

## Paper edit documents ignore the exported current snapshot

PaperEditDocument carries an optional current field holding the exported paper state for reference. Only operations are applied; current is never interpreted as an edit, so clients can round-trip an exported document without accidental overwrites.

Code: `backend/models/paper_edits.py::PaperEditDocument`

## Paper feed totals are cached for 60 seconds

Exact feed totals require scanning every matching paper, while a page is a short index walk. Since feed responses are already HTTP-cacheable for 60 s, totals are cached in-process for the same TTL so infinite scroll counts once rather than per page.

Code: `backend/services/paper_feed_executor.py::COUNT_CACHE_TTL_SECONDS`

## Paper merges copy method links before moving method evidence

paper_method_evidence references its (paper_id, method_id) parent in paper_methods without ON UPDATE CASCADE. When an external paper is merged into its arXiv paper, the target first receives the method links, then evidence rows move, and only afterwards are the source's method links deleted; any other order violates the foreign key.

Code: `backend/services/trending_model_resolution_service.py::TrendingModelResolutionService._upgrade_external_paper`

## Paper merges deduplicate authors by name

An external release row and its arXiv paper often list the same people under different author records. When merging, source authors whose casefolded name already appears on the target are not copied, avoiding duplicate bylines.

Code: `backend/services/trending_model_resolution_service.py::TrendingModelResolutionService._upgrade_external_paper`

## Paper merges keep the arXiv paper's evaluation on conflict

Both the external and arXiv rows have often been curated with the same evaluation entries. When evaluations move from the external paper to the arXiv paper, conflicting entries keep the arXiv paper's copy.

Code: `backend/services/trending_model_resolution_service.py::TrendingModelResolutionService._upgrade_external_paper`

## Pending evaluation proposals are revalidated at apply time

Pending evaluation edit proposals are persisted and may predate canonical command validation. Before the first write they are revalidated with validate_payload and rebuilt as canonical evaluation commands, so legacy or malformed stored payloads cannot bypass current validation.

Code: `backend/services/pending_edit_mutations.py::PendingEditMutationService._paper_evaluations`

## Pending evaluation proposals keep a stricter admission policy

Pending evaluation proposals enforce extra structural checks (task_id and dataset_id must be positive ints, metrics shape) before handing data to the canonical Evaluation models, which own field types, URL normalization and patch presence. The checks look redundant but reject malformed proposals the canonical models would coerce.

Code: `backend/services/pending_edit_payloads.py::_validate_evaluation_operation`

## Reference title matching ignores short fingerprints and prefers the longest

Short title fingerprints such as 'gpt4' or 'nature' are more likely to be a venue, model name or author fragment than a paper title, so fingerprints under 12 characters never count as evidence. Among matching candidates the longest fingerprint wins, so a complete title beats a fragment that happens to equal another paper's title.

When resolving references by title, candidate fingerprints are tried longest first, so a complete title beats a shorter fragment that happens to be another paper's title.

Code: `backend/services/paper_reference_service.py::MIN_TITLE_FINGERPRINT_LENGTH`, `backend/services/paper_reference_service.py::PaperReferenceService.resolve`

## Removing one's own recent additions bypasses mass-removal hold

The mass-removal guard holds edits that remove many values in 24 hours. Values the same editor auto-added to the same paper and field in that window are excluded, since taking them back is a correction rather than a removal of others' data.

Code: `backend/services/pending_edit_auto_approval.py::PendingEditAutoApproval._mass_removal`

## Rollback compares only sections the edit batch recorded

Older paper edit batches were persisted before organizations were captured in snapshots. Rollback snapshots are therefore restricted to the sections present in the stored after_snapshot, so rolling back a legacy batch leaves organization associations untouched instead of wiping them.

Code: `backend/services/paper_edit_service.py::PaperEditService.rollback_snapshot`

## Server records when saved papers first migrated to an HF Bucket

Saved papers live in the user's Hugging Face Bucket, but the Bucket token is stored in a per-browser cookie. The user row records saved_papers_bucket_migrated_at so other devices offer a reconnect instead of running a fresh migration that could duplicate or overwrite data.

Code: `backend/models/database/identity.py`

## Spam rejection reports counts from the pre-lock snapshot

reject_active_as_spam takes its 'before' moderation snapshot without a row lock, before the locked catalog mutation runs, to preserve the historical semantics of the count it returns publicly. Moving the snapshot inside the lock would change that public count.

Code: `backend/services/submitter_moderation_service.py::SubmitterModerationService.reject_active_as_spam`

## Version refresh moves evaluations instead of copying them

Leaderboards list evaluations from every version of a paper, so copying a model's rows to a new arXiv version would show the model twice. The version refresh moves evaluations to the new version, collapses duplicates of the same model (even when spelled differently), and re-ranks any board that lost a row.

Code: `backend/services/paper_version_refresh_service.py::PaperVersionRefreshService._copy_curated_links`

## arXiv requests are spaced at least 3 seconds apart

arXiv's API terms of use require clients to wait 3 seconds between requests, and violations lead to 429s or blocking. ArxivService rate-limits every export API call and PDF download attempt with a 3-second delay; lowering it risks the shared VPS IP being throttled.

Code: `backend/services/arxiv_service.py::RATE_LIMIT_DELAY`
