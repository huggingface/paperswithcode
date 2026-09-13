# First-Party Papers With Code MCP Hosting Implementation Plan

> Status: implementation-ready after approval of the companion design. Do not
> activate staging or production from a feature branch. Publishing is a separate
> task after both pull requests merge and pass Bugbot review.

**Goal:** Publish the existing read-only Papers With Code MCP catalogue at the
single canonical URL `https://paperswithcode.co/mcp`, with a browser-friendly
documentation page, complete bounded paper continuation, and an independently
deployable VPS service.

**Design:** Follow
[`2026-09-12-first-party-pwc-mcp-hosting-design.md`](../specs/2026-09-12-first-party-pwc-mcp-hosting-design.md).
The Papers With Code repository owns the bounded Markdown API, web page, nginx
dispatch, and host lifecycle. The `huggingface/pwc-cli` repository owns the MCP
package, cursor security, runtime limits, and protocol behavior. The backend is
the only component that can access the private Markdown bucket.

**Stack:** FastAPI, Pydantic, `huggingface_hub`, React/Vite, TanStack Query,
nginx, systemd, Python MCP SDK, pytest, Vitest, Ruff, and TypeScript.

## Branches and pull requests

- Papers With Code: continue in the isolated worktree
  `/root/python_projects/paperswithcode/.worktrees/pwc-mcp-first-party-hosting`
  on `codex/pwc-mcp-first-party-hosting`. Open one feature PR against
  `huggingface/paperswithcode:main`.
- MCP package: PR 6 (`codex/pwc-mcp-server`) is the prerequisite package PR.
  Do not mix the hosting follow-up into it while Bugbot is pending. After PR 6
  merges, create a fresh isolated worktree and branch
  `codex/pwc-mcp-first-party-runtime` from the merged `main`, then open a second
  PR against `huggingface/pwc-cli:main`.
- Never stage the unrelated `/root/python_projects/pwc-cli/standalone_cli/uv.lock`.
- Each task below ends in a narrow commit. Before either PR is opened, inspect
  `git diff --check`, the complete branch diff, and the worktree status.

## Phase 0: Resolve implementation gates

### Task 1: Prove revision-bound, bounded Hugging Face reads

**Inspect:**

- `backend/services/paper_markdown_service.py`
- `backend/keys.env` only through the repository's approved command wrapper
- the pinned `huggingface_hub` version and its official API surface

**Steps:**

1. Check free disk space and confirm no test uses production ports `8000` or
   `8001`.
2. Run a read-only qualification against one known Markdown object with:
   metadata lookup, a small initial range, a nonzero range, and a one-byte
   lookahead. Capture client debug evidence showing transferred bytes remain
   proportional to the requested range.
3. Prove that the range request is bound to an immutable object revision or a
   conditional token. Replace the object between metadata and read in a test
   fixture and confirm the old token fails instead of returning mixed content.
4. Record the exact usable metadata field, conditional/version argument, and
   observed request behavior in the Papers With Code PR description. Do not
   commit bucket names, object keys, credentials, signed URLs, or raw debug logs.
5. The gate established that Buckets are non-versioned and conditional
   `GetObject` is unavailable. Implement the approved prerequisite: immutable
   content-addressed Markdown objects, a per-paper manifest published last, and
   a bounded remote migration for existing canonical objects. Never hash or
   download the whole object on an API request path.

**Verification:**

```bash
uv run --env-file backend/keys.env python -c "import huggingface_hub; print(huggingface_hub.__version__)"
```

Expected: the exact pinned client behavior is recorded and bounded range reads
are proven against immutable content-addressed keys.

### Task 1a: Publish immutable Markdown revisions and migrate existing objects

**Files:**

- Modify: `backend/scripts/generate_missing_paper_markdown.py`
- Create: `backend/scripts/migrate_paper_markdown_versions.py`
- Modify: `backend/tests/test_paper_markdown_backfill.py`
- Create: `backend/tests/test_paper_markdown_version_migration.py`

**Steps:**

1. Define a bounded manifest schema containing the canonical paper identity,
   exact SHA-256 content version, immutable object key, byte size, and schema
   version. Reject path traversal and inconsistent digest/key combinations.
2. Make the existing writer materialize the content-addressed object and verify
   any pre-existing object byte-for-byte. Upload canonical compatibility output
   and the immutable revision first, then publish the manifest in a separate
   final bucket mutation. Repairs retain old revisions.
3. Add a resumable remote migration that processes bounded batches, downloads
   at most one canonical Markdown object at a time, validates UTF-8 and size,
   publishes/verifies its immutable revision, and writes the manifest last.
   Persist bounded progress without exposing bucket details.
4. Make reruns idempotent, reject conflicts, and expose dry-run plus explicit
   batch limits. Do not run the corpus migration from the disk-constrained VPS.

**Verification:**

```bash
uv run --env-file backend/keys.env pytest backend/tests/test_paper_markdown_backfill.py backend/tests/test_paper_markdown_version_migration.py -q
uv run --env-file backend/keys.env ruff check backend/scripts/generate_missing_paper_markdown.py backend/scripts/migrate_paper_markdown_versions.py backend/tests/test_paper_markdown_version_migration.py
```

**Commit:** `feat(storage): version paper markdown immutably`

### Task 2: Freeze the MCP SDK wire contract

**Inspect:**

- `/root/python_projects/pwc-cli/mcp_server/pyproject.toml`
- `/root/python_projects/pwc-cli/mcp_server/uv.lock`
- `/root/python_projects/pwc-cli/mcp_server/src/pwc_mcp/app.py`
- `/root/python_projects/pwc-cli/mcp_server/tests/test_app.py`

**Steps:**

1. Record the locked MCP SDK version and the protocol versions it actually
   accepts over stateless Streamable HTTP.
2. Exercise initialize, discovery, tool call, resource read, invalid protocol,
   GET, DELETE, and OPTIONS at the ASGI boundary.
3. Confirm that no deprecated HTTP+SSE handshake or resumption endpoint is
   advertised.
4. Put the resulting tested protocol/client matrix in the two PR descriptions;
   later documentation must use that matrix rather than assumptions.

**Verification:**

```bash
cd /root/python_projects/pwc-cli/mcp_server
uv run pytest tests/test_app.py -q
```

Expected: current tests pass and every claimed protocol version has a reproducible
wire probe before it is listed on the web page.

## Phase 1: Papers With Code API

### Task 3: Add a revision-bound Markdown chunk primitive

**Files:**

- Modify: `backend/services/paper_markdown_service.py`
- Test: `backend/tests/test_research_catalog.py`

**Steps:**

1. Add failing service tests for an immutable content-version token, offset zero,
   nonzero offsets, an exact terminal offset, beyond-end rejection, mid-code-point
   rejection, a limit too small for the next code point, invalid stored UTF-8,
   one-byte lookahead, and an object replaced between metadata and read.
2. Add a small immutable result type such as `PaperMarkdownChunk` carrying
   `markdown`, `content_version`, `next_offset`, and `truncated`.
3. Implement a separate bounded range cache keyed by canonical paper/source,
   revision, offset, and limit. Bound it by entry count, total bytes, and a
   one-hour TTL; do not reuse the existing non-expiring whole-prefix LRU.
4. Implement `read_paper_markdown_chunk(...)` using the qualified Hub revision
   mechanism, bounded overlap for UTF-8 boundary checks, and a one-byte lookahead.
   Preserve bytes exactly and decode strictly.
5. Keep the existing legacy reader behavior intact. Sanitize storage exceptions
   so bucket identifiers, object keys, credentials, and signed URLs cannot cross
   the service boundary.
6. Run the focused tests, then commit.

**Verification:**

```bash
uv run --env-file backend/keys.env pytest backend/tests/test_research_catalog.py -q
uv run --env-file backend/keys.env ruff check backend/services/paper_markdown_service.py backend/tests/test_research_catalog.py
```

**Commit:** `feat(api): add revision-bound paper markdown chunks`

### Task 4: Expose and validate the chunk API contract

**Files:**

- Modify: `backend/routers/research_catalog.py`
- Modify: `backend/tests/test_research_catalog.py`

**Steps:**

1. Add failing HTTP tests for omitted parameters, every valid default, duplicate
   parameters, boolean-like values, signed-64-bit offset overflow, negative or
   zero values, excessive limits, missing continuation versions, stale versions,
   missing Markdown, invalid ranges, and sanitized error bodies.
2. Detect query presence and duplicates from the raw query parameter collection;
   do not rely on FastAPI's last-value behavior. Treat `offset`, `limit`, or
   `content_version` as chunk mode.
3. Preserve the successful no-parameter response byte-for-byte, including its
   truncation notice and current cache headers.
4. In chunk mode, return `200 text/plain; charset=utf-8`,
   `X-PwC-Truncated`, `X-PwC-Content-Version`, and
   `X-PwC-Next-Offset` only when another chunk exists. Never append a notice.
5. Return sanitized `409` on version mismatch, `416` on invalid byte ranges,
   `404` on missing Markdown, and `422` before storage I/O for syntax/limit
   failures. All errors are `Cache-Control: no-store`; only version-bound chunks
   may be publicly cached for at most one hour.
6. Update the OpenAPI parameter descriptions and run focused tests.

**Verification:**

```bash
uv run --env-file backend/keys.env pytest backend/tests/test_research_catalog.py -q
uv run --env-file backend/keys.env ruff check backend/routers/research_catalog.py backend/tests/test_research_catalog.py
```

**Commit:** `feat(api): expose cursor-safe paper markdown reads`

## Phase 2: Browser documentation at `/mcp`

### Task 5: Add a bounded MCP health client

**Files:**

- Create: `frontend/src/lib/mcp.ts`
- Create: `frontend/src/lib/mcp.test.ts`
- Reuse: `frontend/src/lib/apiUrl.ts`

**Steps:**

1. Write failing tests for successful bounded health JSON, `503`, malformed JSON,
   timeouts, and production/staging endpoint selection.
2. Implement typed health parsing and a TanStack Query options factory with a
   modest refresh interval, finite timeout, no aggressive retry, and no page
   failure when health is unavailable.
3. Derive the copied endpoint from the current approved hostname: production
   copies production, staging copies staging, and local development uses its
   current origin.

**Verification:**

```bash
cd frontend
npm test -- src/lib/mcp.test.ts
npm run typecheck
```

**Commit:** `feat(frontend): add MCP health client`

### Task 6: Build the documentation-only MCP view

**Files:**

- Create: `frontend/src/views/McpView.tsx`
- Create: `frontend/src/views/McpView.css`
- Create: `frontend/src/views/McpView.test.tsx`

**Steps:**

1. Write failing view tests for the hero, copy button, operational/unavailable
   states, setup tabs, all ten tool names, all four resource templates, example
   prompts, anonymous/read-only/limits/privacy copy, protocol/server version,
   troubleshooting, and external documentation links.
2. Implement the responsive page using established site tokens and components.
   Do not add a playground, inspector, account flow, or API-key interface.
3. Populate setup tabs only from the dated matrix qualified in Task 2. Mark
   untested clients as unverified and distinguish native remote support from
   local bridge commands.
4. Keep the page useful if health fails and label that state exactly as
   “Status unavailable.”
5. Keep catalogue prose checked against the package's discovery schemas.

**Verification:**

```bash
cd frontend
npm test -- src/views/McpView.test.tsx
npm run lint
npm run typecheck
```

**Commit:** `feat(frontend): add MCP connection documentation`

### Task 7: Wire the route and restrained footer link

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/SiteFooter.tsx`
- Test: `frontend/src/views/McpView.test.tsx`

**Steps:**

1. Add `/mcp` before the `/:username` and wildcard routes.
2. Add “MCP” beside the existing footer utility links; do not add it to primary
   navigation.
3. Add a router regression proving `/mcp` cannot be interpreted as a username
   and the footer link resolves to the view.

**Verification:**

```bash
cd frontend
npm test -- src/views/McpView.test.tsx
npm run lint
npm run typecheck
```

**Commit:** `feat(frontend): route and link the MCP page`

## Phase 3: First-party routing and lifecycle

### Task 8: Encode exact nginx content negotiation

**Files:**

- Modify: `deploy/nginx/paperswithcode.co.conf`
- Modify: `deploy/nginx/staging.paperswithcode.co.conf`
- Modify: `deploy/nginx_validate.py`
- Create: `backend/tests/test_mcp_nginx_contract.py`

**Steps:**

1. Add failing static and disposable-nginx tests for `/mcp`, `/mcp/`,
   `/mcp/health`, unknown descendants, POST/DELETE/OPTIONS, browser HEAD, protocol
   GET, absent Accept, mixed Accept, `q=0`, invalid protocol headers, unsupported
   methods, and SPA non-fallthrough.
2. Route explicit MCP signals before HTML. Proxy protocol requests without
   redirects, preserve body and `/mcp`, map health to `/health`, and return
   bounded `404`, `405`, or `406` responses where specified.
3. Add `Vary: Accept, MCP-Protocol-Version` wherever representation changes;
   disable protocol/health shared caching and proxy buffering as required.
4. Overwrite `X-Forwarded-For` from nginx's verified peer, preserve exact Host
   and Origin, and strip cookie/authorization before upstream catalogue calls.
5. Give MCP locations a privacy-safe access log that excludes IPs, paths, query
   strings, bodies, and headers. Preserve staging access controls outside the
   narrow anonymous MCP protocol/health exception.

**Verification:**

```bash
uv run --env-file backend/keys.env pytest backend/tests/test_mcp_nginx_contract.py -q
uv run --env-file backend/keys.env python deploy/nginx_validate.py --root deploy/nginx
git diff --check
```

**Commit:** `feat(deploy): route the first-party MCP endpoint`

### Task 9: Add an immutable MCP component lifecycle

**Files:**

- Create: `deploy/mcp_release.py`
- Create: `deploy/mcp_launcher.py`
- Create: `deploy/systemd/paperswithcode-mcp@.service`
- Modify: `deploy/cli.py`
- Modify: `deploy/install_deploy_tools.py`
- Modify: `deploy/install_host_layout.py`
- Modify: `deploy/smoke_test.py`
- Create: `backend/tests/test_mcp_deployment.py`

**Steps:**

1. Write failing tests for a separate MCP bare repository, exact SHA resolution,
   immutable source archive, locked runtime creation, release manifest, separate
   environment pointers, distinct config/key files, candidate qualification,
   activation, failed-smoke restoration, rollback, cleanup retention, deploy
   locking, and status output.
2. Extend `pwc-deploy`, `pwc-status`, `pwc-rollback`, and cleanup with an explicit
   `--component mcp` path. Keep the existing site behavior as the default and do
   not add unrelated standalone lifecycle commands.
3. Materialize releases from an exact `huggingface/pwc-cli` commit into a separate
   MCP release root, install from `mcp_server/uv.lock`, and record source SHA,
   lock hash, package/server version, SDK version, supported protocols, health
   schema, API URL, and artifact hashes in the manifest. Never use an editable
   sibling checkout.
4. Install a hardened single-worker systemd template with configurable loopback
   host/port, environment-specific API URL, current and previous cursor keys,
   memory/CPU/process/file limits, restart backoff, private temp space, protected
   system directories, and no bucket/database credentials.
5. Before activation, inspect live listeners and refuse an allocated port. Start
   the candidate on a temporary free loopback port, probe liveness/readiness and
   a minimal initialize/discovery/read-only tool flow, then atomically move the
   environment pointer and bounded-restart the permanent unit.
6. On failure, restore the prior pointer/unit and re-smoke it. Serialize site and
   MCP mutations with the existing deployment lock.
7. Add MCP health and protocol smoke support without making ordinary site deploys
   depend on an unactivated MCP service.

**Verification:**

```bash
uv run --env-file backend/keys.env pytest backend/tests/test_mcp_deployment.py -q
uv run --env-file backend/keys.env pytest backend/tests/test_zero_downtime_deployment.py -q
uv run --env-file backend/keys.env ruff check deploy/mcp_release.py deploy/mcp_launcher.py deploy/cli.py deploy/install_deploy_tools.py deploy/install_host_layout.py deploy/smoke_test.py backend/tests/test_mcp_deployment.py
```

**Commit:** `feat(deploy): manage immutable MCP releases`

### Task 10: Document operations and public behavior

**Files:**

- Modify: `docs/deployment.md`
- Modify: `docs/operations.md`
- Modify: public API documentation or `llms.txt` source located during implementation
- Modify: `docs/superpowers/specs/2026-09-12-first-party-pwc-mcp-hosting-design.md`
  only if implementation evidence requires a design correction

**Steps:**

1. Document the chunk API, content-version requirement, byte semantics, error
   statuses, cache behavior, supported paper identifiers, and legacy truncation
   behavior.
2. Document MCP component deploy/status/rollback commands, release layout,
   environment config, key rotation, health/readiness, capacity budgets, log
   allowlist, Space fallback, and manual nginx activation/rollback.
3. Add staging qualification and production cutover checklists with concrete
   rollback triggers. State that nginx is changed only through `pwc-nginx`.
4. Document the catalogue infrastructure's separate logging policy accurately;
   do not claim end-to-end zero logging.

**Verification:**

```bash
rg -n "content_version|X-PwC-Next-Offset|pwc-deploy.*component mcp|pwc-nginx|cursor key|rollback" docs
git diff --check
```

**Commit:** `docs: document first-party MCP operations`

### Task 11: Finish the Papers With Code pull request

**Steps:**

1. Run the focused backend/deploy suite and the complete relevant frontend suite.
2. Run Ruff, frontend lint, TypeScript, and whitespace checks.
3. Start an isolated backend and frontend on confirmed free non-production ports;
   exercise legacy reads, initial/continued chunk reads, the `/mcp` page, and
   unavailable health behavior.
4. Review the branch diff for secrets, storage details, unsafe nginx fallthrough,
   unbounded caches/queues, and unrelated files.
5. Push `codex/pwc-mcp-first-party-hosting` and open the Papers With Code PR with
   the design link, gate evidence, test output, protocol/client matrix, screenshots,
   rollout order, and explicit “not deployed” status.
6. Wait for Cursor Bugbot. Resolve every comment and rerun affected checks. Do not
   merge or deploy from this implementation task.

**Verification:**

```bash
uv run --env-file backend/keys.env pytest backend/tests/test_research_catalog.py backend/tests/test_mcp_nginx_contract.py backend/tests/test_mcp_deployment.py backend/tests/test_zero_downtime_deployment.py -q
uv run --env-file backend/keys.env ruff check backend/services/paper_markdown_service.py backend/routers/research_catalog.py deploy backend/tests/test_research_catalog.py backend/tests/test_mcp_nginx_contract.py backend/tests/test_mcp_deployment.py
cd frontend && npm test -- src/lib/mcp.test.ts src/views/McpView.test.tsx && npm run lint && npm run typecheck
git diff --check
git status --short
```

## Phase 4: `pwc-cli` MCP runtime follow-up

### Task 12: Replace unsigned character cursors with authenticated byte cursors

**Files:**

- Modify: `mcp_server/src/pwc_mcp/cursors.py`
- Modify: `mcp_server/tests/test_server.py`
- Create or modify: `mcp_server/tests/test_cursors.py`

**Steps:**

1. Add failing tests for schema/version, canonical source and ID, normalized input
   reference, content revision, byte offset, fixed chunk limit, key ID, issuance
   time, fixed one-hour expiry, maximum token size, tampering, wrong paper, expiry,
   replay, current/previous keys, and constant-time signature checking.
2. Implement compact URL-safe cursor payloads authenticated with HMAC. Require a
   deployment secret; accept retained previous keys until all issued cursors
   expire. Do not place paths, bucket details, or raw upstream cursors in payloads.
3. Keep replay idempotent and do not extend expiry on cache hits.

**Verification:**

```bash
cd mcp_server
uv run pytest tests/test_cursors.py tests/test_server.py -q
uv run ruff check src/pwc_mcp/cursors.py tests/test_cursors.py tests/test_server.py
```

**Commit:** `feat(mcp): authenticate paper continuation cursors`

### Task 13: Consume one upstream Markdown chunk per invocation

**Files:**

- Modify: `mcp_server/src/pwc_mcp/catalog.py`
- Modify: `mcp_server/src/pwc_mcp/models.py`
- Modify: `mcp_server/src/pwc_mcp/server.py`
- Modify: `mcp_server/tests/test_catalog.py`
- Modify: `mcp_server/tests/test_server.py`

**Steps:**

1. Add failing tests for initial resolution, no re-resolution on continuation,
   one upstream Markdown request per invocation, cache hits, total-byte and
   entry-count eviction, fixed expiry, revision mismatch, terminal replay,
   non-advancing offsets, and legacy fail-closed truncation.
2. Add a typed catalogue chunk result carrying canonical identity, Markdown,
   revision, next byte offset, and terminal state. Call the new API with a fixed
   conservative 64 KiB limit.
3. Separate the range cache from JSON metadata caching and bound it by bytes,
   entries, and one hour. Bind its key to canonical source/ID, revision, offset,
   and limit.
4. Resolve titles/slugs only on the initial call under a bounded call budget and
   operation deadline. Encode canonical resolution in the cursor so continuation
   never repeats the ten-page search.
5. Preserve `PaperReadResult` fields. Return terminal
   `truncated=false, next_cursor=null`; surface stale revision as restart guidance.
6. Make the Markdown resource return content only when the first chunk is
   terminal; otherwise return bounded guidance to use `read_paper`.

**Verification:**

```bash
cd mcp_server
uv run pytest tests/test_catalog.py tests/test_server.py -q
uv run ruff check src/pwc_mcp/catalog.py src/pwc_mcp/models.py src/pwc_mcp/server.py tests/test_catalog.py tests/test_server.py
```

**Commit:** `feat(mcp): stream complete papers through bounded chunks`

### Task 14: Harden admission, proxy trust, origins, readiness, and response size

**Files:**

- Modify: `mcp_server/src/pwc_mcp/app.py`
- Modify: `mcp_server/tests/test_app.py`

**Steps:**

1. Add failing tests for explicit IPv4/IPv6 loopback proxy trust, forged headers
   from public/private peers, independent client quotas behind real proxy headers,
   exact Host/Origin allowlists, `null` and lookalike origins, origin-less clients,
   locked-SDK preflights, no credentials, and configurable loopback binding.
2. Replace broad `is_private` proxy trust with exact loopback trust and disable
   competing Uvicorn proxy rewriting.
3. Add a bounded global admission semaphore/queue before catalogue work, with
   `503` for saturation. Retain per-IP request, semantic, and concurrency limits,
   but cap identity entries and TTL cleanup deterministically.
4. Enforce a 2 MiB serialized response ceiling for every tool/resource. Test
   worst-case JSON escaping and duplicated text/structured output; return a
   bounded error rather than truncating JSON.
5. Add periodic bounded catalogue readiness probing. Health reads cached state,
   exposes only status/version/protocol, and returns `503` when not ready.
6. Ensure the telemetry allowlist is the only MCP application request log and
   suppress SDK/Uvicorn/upstream content-bearing logs.

**Verification:**

```bash
cd mcp_server
uv run pytest tests/test_app.py -q
uv run ruff check src/pwc_mcp/app.py tests/test_app.py
```

**Commit:** `feat(mcp): harden the hosted runtime boundary`

### Task 15: Make the immutable runtime artifact self-describing

**Files:**

- Modify: `mcp_server/pyproject.toml`
- Modify: `mcp_server/uv.lock`
- Modify: `mcp_server/Dockerfile`
- Modify: `mcp_server/README.md`
- Modify: `mcp_server/SPEC.md`
- Modify: `.github/workflows/pwc-mcp-release.yml`
- Test: `mcp_server/tests/test_app.py`

**Steps:**

1. Pin the SDK/runtime contract used in Task 2 and expose a bounded machine-readable
   build/health descriptor needed by the host release manifest.
2. Make host and port configurable with loopback as the VPS default while keeping
   the Docker Space binding explicit in its container command.
3. Document required cursor keys, exact Host/Origin variables, API URL, limits,
   single-worker operation, health semantics, and the Space fallback role.
4. Keep the Space workflow manual/noncanonical; do not add automatic failover.
5. Re-lock dependencies only through `uv` and review the lock diff.

**Verification:**

```bash
cd mcp_server
uv sync --locked --extra test
uv run pytest -q
uv run ruff check src tests
uv run pyright src
docker build -t pwc-mcp:local .
```

**Commit:** `build(mcp): publish a reproducible hosted artifact`

### Task 16: Finish the `pwc-cli` follow-up pull request

**Steps:**

1. Run the full MCP test/lint/type/build checks and wire probes from Task 2.
2. Run a local MCP process on a confirmed free port against a compatible local or
   staging catalogue API and exercise initialize, discovery, all tools/resources,
   multi-chunk paper completion, cursor replay/tamper/expiry, quotas, saturation,
   health readiness, and shutdown.
3. Review the complete branch diff and confirm `standalone_cli/uv.lock` is absent.
4. Push `codex/pwc-mcp-first-party-runtime` and open the follow-up PR referencing
   PR 6 and the Papers With Code API PR. Include the exact required API contract,
   test output, wire matrix, capacity settings, and explicit “not deployed” status.
5. Wait for Cursor Bugbot, resolve every comment, and rerun affected checks. Do
   not merge or deploy from this implementation task.

**Verification:**

```bash
cd mcp_server
uv run pytest -q
uv run ruff check src tests
uv run pyright src
git diff --check
git status --short
```

## Phase 5: Separate publishing task after both PRs merge

### Task 17: Stage, qualify, and then cut over production

This task is intentionally not authorized by implementation approval. Start it
only after both PRs are merged to `main`, all Bugbot comments are resolved, and
the user requests publication.

**Order:**

1. Fetch merged `origin/main` in both repositories and record exact SHAs.
2. Re-run proportionate checks from both PRs.
3. Install updated Papers With Code deployment tooling from its merged SHA.
4. Inspect `pwc-status`, processes, listeners, disk/memory headroom, and effective
   nginx configuration. Allocate the staging MCP port without touching `8000` or
   `8001`.
5. Configure staging API URL, exact Host/Origin allowlists, and independent cursor
   keys. Deploy the exact merged MCP SHA with `pwc-deploy --component mcp`.
6. Qualify staging directly before nginx, then apply staging routing with
   `pwc-nginx`. Exercise browser HTML/HEAD, MCP POST/GET/DELETE/OPTIONS, health,
   all tools/resources, full paper continuation, version replacement, invalid
   cursors, rate/global limits, real client-address behavior, logs, and every
   client claimed on the page.
7. Hold an observation window and confirm backend latency/error rate, MCP
   saturation, memory, cache bounds, restart stability, and no sensitive logs.
8. Deploy production MCP on the verified production port with production keys and
   API URL. Qualify it directly, then apply production nginx through `pwc-nginx`.
9. Smoke `/health`, `/`, one SPA route, one API route, `/mcp` as browser HTML,
   `/mcp/health`, initialize/discovery, one metadata tool, and a multi-chunk read.
10. Monitor the documented SLOs and rollback triggers. If qualification fails,
    restore nginx first where needed, then `pwc-rollback --component mcp` to the
    exact prior release. Keep the Space as a documented manual fallback only.

**Completion evidence:** exact deployed SHAs, release manifests, smoke output,
client matrix, monitoring snapshot, log audit, and rollback rehearsal are attached
to the publishing report without secrets or content-bearing request data.
