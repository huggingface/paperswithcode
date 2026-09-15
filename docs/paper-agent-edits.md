# Agent-assisted paper editing

The public CLI companion change lives in `huggingface/pwc-cli`. Research commands
remain anonymous. Editing starts with `pwc auth login --paper PAPER`: the user
signs in with Hugging Face in a browser, verifies a displayed code, and grants
one hour of access to that paper. There is no automatic renewal or per-batch
approval. All authenticated HF users can publish when direct editing is enabled.

## Permissions and publication

- One immutable database paper ID per CLI grant; authorization is checked again
  inside every mutation transaction, including after suspension or revocation.
- Website and CLI share a maximum of 20 distinct papers per account per UTC day
  and 30 successful publications per minute. Failed batches and previews do not
  consume publication quota. Administrators are exempt from quotas.
- Account-scoped PostgreSQL transaction advisory locks serialize publication,
  quota checks, authorization approval/exchange, and suspension. These locks are
  acquired before paper locks.
- Links, existing task/method tags, and evaluation additions/corrections are
  supported. Links to existing organizations publish directly through the same
  audited workflow; creating or rewriting organization definitions is excluded.
  Evaluation deletion and shared benchmark/metric definition edits require admins.
- Project-page official status is currently shared in the catalog. A contributor
  cannot change it when the page is linked to another paper; linking an existing
  page with its existing status is allowed.
- Source references are optional, matching the existing API. Agent instructions
  encourage source URLs and precise locations in methodology.
- Public history shows HF username, time, and before/after values, excluding
  credentials, internal identity IDs, and internal provenance metadata.
- The admin catalog-audit page provides a UTC daily summary, rollback, and
  suspension/restore controls. Suspension invalidates active grants permanently;
  restoring an account requires new CLI authorization. Rollback remains
  conflict-aware and does not silently overwrite later changes.

## Edit document

`GET /api/v1/papers/{id}/edit-document` exports schema_version, paper_id,
version, idempotency_key, an empty operations array, and current reference data.
Operations are explicit. A supplied link/tag section replaces that section;
omitted sections stay intact. An evaluation without evaluation_id creates a row;
an evaluation with an ID corrects that row and preserves omitted update fields.
One evaluation payload can contain many metrics. At most 50 operations and 1 MiB
are accepted per document; existing benchmark/task/metric definitions are required.

Preview (`POST .../edits/preview`) runs the same application logic in a rolled-back
savepoint. Submit (`POST .../edits`) writes one atomic audited batch. A stale
version returns 409; an identical retry key/document returns the original result.
After an uncertain network result, retry the same document. After a real conflict,
export again, reconcile, and use the new export's key. The CLI never prints its
credential, includes it in a document, or forwards it through a redirect.

Credentials are stored as hashes on the server. The CLI uses mode-0600 credential
files in a mode-0700 directory, keyed by API base URL and paper. Browser approval
uses the existing HF OAuth cookie and same-origin CSRF protection; no HF access
token is handed to the agent. Pending authorizations expire after ten minutes.
Anonymous starts are capped at ten per client IP per minute and 1,000 active
pending authorizations globally. Expired records older than one day are removed
when a new authorization starts. Grant IDs and device secrets have separate roles:
the browser sees the ID, while exchange requires the secret held only by the CLI.

## Release order

1. Merge both reviewed PRs. Apply
   `backend/database/migrations/add_paper_agent_edits.sql` to production before
   deploying this application commit. Apply as the catalog schema owner and ensure
   the runtime role has SELECT/INSERT/UPDATE/DELETE on the two new tables. Do not
   grant staging write access to public.
2. Deploy the reviewed backend/frontend commit through the normal immutable
   release workflow. Enable `PWC_CONTRIBUTOR_DIRECT_EDITS_ENABLED=true` in
   production after verifying the migration and audit controls. The existing
   `PWC_CATALOG_MUTATIONS_ENABLED` switch must also remain enabled. Staging does
   not accept these catalog writes.
3. Publish the companion CLI release. Earlier servers reject unsupported edit
   endpoints; public research commands continue to work.
4. Smoke-test browser consent, one paper's preview/publication/history, account
   suspension, and conflict-aware rollback using a designated test paper/account.

This implementation task does not apply the production migration, deploy, or
publish a CLI release before the PRs are merged.

## Verification

Run repository Python commands with `uv run --env-file backend/keys.env`.
Focused unit tests: `backend/tests/test_paper_edit_policy.py`. Transaction and
HTTP tests: `backend/tests/test_paper_edits_integration.py`. The latter require
an isolated PostgreSQL database with `Base.metadata` installed and
`PWC_EDIT_TEST_DATABASE=pwc_agent_edits_test`; the fixture refuses any other prefix
and truncates only that dedicated database between tests. Do not point it at a
catalog database. These tests cover concurrent quota admission, atomic failures,
retry deduplication, stale edits, scope, consent, expiry, suspension, shared
resources, public history, and rollback.

Frontend: `npm run typecheck`, `npm run lint`, and `npm test -- --run`.
The companion CLI has credential/transport/command tests and a command/skill
contract check. No frontend production build is needed for this change.

Organization example (CLI 0.4.0 accepts this operation without an upgrade):

```json
{"section": "organizations", "payload": {"organization_ids": [123, 456]}}
```

This replaces all organization links for the paper. Export first and preserve
links that should remain; an empty list removes all links. Organization IDs must
refer to existing catalog organizations. Public history shows catalog organization
IDs, while the private audit preserves the contributor attribution for rollback.
