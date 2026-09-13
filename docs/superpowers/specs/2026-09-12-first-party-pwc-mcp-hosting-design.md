# First-Party Papers With Code MCP Hosting Design

## Status and scope

This design replaces the Docker Space as the intended canonical MCP runtime
with a first-party endpoint at `https://paperswithcode.co/mcp`. The same URL is
both a human-readable connection page and the stateless Streamable HTTP MCP
endpoint. The MCP process remains independently deployable from the main site.

The existing `huggingface/pwc-cli` MCP pull request remains the source of the
MCP package and its ten read-only tools. This design adds the production
Papers With Code API capability required for complete paper continuation, the
first-party web page, reverse-proxy routing, and an isolated VPS lifecycle.

The initial web interface is documentation-only. It does not contain a tool
playground, MCP inspector, account flow, or API-key interface.

Reviewed 2026-09-12 against the catalog reader, the local `pwc-cli` MCP
implementation, and the repository nginx/deployment contracts. This remains a
design, not authorization to activate services. The implementation gates below
must be resolved with evidence before production cutover.

## Goals

- Make `https://paperswithcode.co/mcp` the single memorable URL users paste
  into ChatGPT, Claude, Cursor, VS Code, Claude Code, or another MCP client.
- Serve a polished connection and capability page from that same URL in a
  normal browser.
- Run MCP on the Papers With Code VPS as its own immutable service and release
  lifecycle, isolated from the FastAPI backend.
- Preserve anonymous, deterministic, read-only behavior and the tool/resource
  contract defined in `huggingface/pwc-cli` pull request 6.
- Let clients read stored paper Markdown completely through bounded,
  UTF-8-safe continuation without exposing the private Hugging Face Bucket.
- Preserve successful public API behavior for callers that do not request a
  Markdown range, with the documented exception for sanitizing storage errors.
- Retain the Hugging Face Docker Space artifact as a staging/fallback option,
  not as a request-path dependency.

## Non-goals

- No interactive search demo or embedded MCP protocol inspector.
- No OAuth, user accounts, API keys, write tools, or private library tools.
- No embedded language model or agentic retrieval loop.
- No direct private-bucket access from the MCP process.
- No automatic traffic failover from the VPS to the Space in the first
  release.
- No expansion beyond the agreed ten tools and four resource templates.
- No coupling of MCP process restarts to the main backend lifecycle.

## Reference patterns

Levels.io, Nomads.com, and Hotelist use `/mcp` as both the public product page
and the connection URL. Their pages lead with a copyable endpoint, client setup
instructions, tool descriptions, example prompts, and fair-use limits.
alphaXiv uses a separate documentation URL and API endpoint, and provides more
detailed parameter and return documentation. Papers With Code combines the
single-URL simplicity of the former with the precise catalogue documentation
of the latter.

## Public URL contract

`https://paperswithcode.co/mcp` is dispatched by method and explicit MCP
signals:

- `GET` with `Accept: text/html` and no MCP protocol header serves the React
  documentation page.
- `POST` carries JSON-RPC MCP requests to the MCP service.
- `DELETE` reaches MCP and returns its bounded `405` response: this deployment
  creates no sessions and does not promise session termination.
- `OPTIONS` supports explicitly allowed browser integrations.
- `GET` with an MCP protocol header or an acceptable `text/event-stream`
  representation is proxied to MCP. A stateless JSON-response server may return
  `405`; routing a stream request does not promise a persistent SSE stream.
- A non-browser `GET` without an acceptable MCP stream representation receives
  a clear media-type response rather than silently receiving HTML.

Protocol signals always take precedence over HTML so an MCP client cannot be
routed into the SPA. Ordinary browser navigation then selects HTML. The
response includes `Vary: Accept, MCP-Protocol-Version` wherever representation
may differ.

Use exact locations for `/mcp` and `/mcp/health`. Preserve `/mcp` upstream;
explicitly map public `/mcp/health` to the package's existing `/health` route.
Do not redirect protocol POSTs or let errors fall through to SPA HTML. `/mcp/`
is an internal alias of `/mcp`, preserving method and body; unknown descendants
return `404`. Browser `HEAD` follows HTML selection with no body. Unsupported
methods return `405` with `Allow`; non-stream, non-HTML GETs return `406`.
Honor media-type quality values (`q=0` is not acceptable); test mixed Accept
headers and absent headers. Invalid protocol headers reach protocol validation.
Disable shared HTTP caching for protocol traffic and health; preserve `Vary`
on the HTML response through the SPA internal redirect.

Pin the actual SDK and record its supported protocol versions and discovery
sequence in the release manifest. The package currently declares `2026-07-28`
and several older versions; verify those claims against the locked SDK and
wire tests. Support for older protocol versions over Streamable HTTP does not
imply the deprecated HTTP+SSE transport, whose separate endpoint/event handshake
is outside this release. Do not advertise that transport or SSE resumption.

`GET https://paperswithcode.co/mcp/health` returns bounded public JSON for the
documentation status indicator and uptime checks. It includes service state,
version, and supported protocol version, but no infrastructure details.
Separate process liveness from readiness: return `503` when initialization,
configuration, or a periodically refreshed bounded catalog capability probe
fails. Do not perform catalog I/O per public health request. The page must not
call a merely live process “operational” when the required catalog is unavailable.

## Runtime architecture

The canonical `pwc-mcp` process runs under a dedicated systemd unit on an
unused loopback port, initially `127.0.0.1:8002`. Before adopting that port,
release tooling must verify the active process topology and confirm it is not
already allocated. The process is not exposed directly on a public interface.

Nginx owns the public `/mcp` dispatch:

1. Browser HTML requests follow the existing frontend SPA path and render
   `McpView`.
2. Protocol requests proxy to the loopback MCP service with streaming enabled,
   buffering disabled where required, original Host and Origin preserved, and
   trustworthy client-address headers set by nginx.
3. `/mcp/health` proxies to the MCP health handler and is never answered by the
   SPA catch-all.

The MCP service uses its existing public Papers With Code API client. It never
imports the production backend, opens PostgreSQL, or reads bucket credentials.
This boundary keeps MCP horizontally separable and makes the same package
runnable on the fallback Space.

Staging and production have separate units, release pointers, configuration,
cursor keys, and ports; `8002` is only a proposed production port. Allocate a
distinct staging port after inspection. Make the bind address configurable:
the existing launcher binds `0.0.0.0`, so setting only `PORT` is insufficient.

Set `PWC_API_URL` explicitly per environment and include it in private release
verification. Staging's public `/api/` currently requires an authenticated
session. Its MCP service therefore uses the staging backend's loopback API
(`http://127.0.0.1:8001/api/v1`), after verifying that internal reads work
without browser credentials. This still uses the HTTP catalog contract.
Production uses the production catalog URL. Never silently qualify against
production when staging connectivity fails. Anonymous public staging `/mcp`
and `/mcp/health` need narrow nginx exceptions; retain access controls for all
existing staging pages/APIs and qualify documentation through an authorized
browser if its asset/index routes remain gated.

## Documentation interface

Add a public `McpView` route before the username and wildcard routes. It uses
the established Papers With Code design system and remains fully usable on
mobile.

The page contains:

1. A hero titled “Use Papers With Code in your AI assistant,” a concise value
   statement, current service status, and a prominent copy control for
   `https://paperswithcode.co/mcp`.
2. Setup tabs for ChatGPT, Claude web/desktop, Claude Code, Cursor, VS Code, and
   generic Streamable HTTP clients. Instructions accurately distinguish direct
   remote MCP support from any client that still requires a local bridge.
3. A capability overview for paper discovery, full-text reading, related work,
   lineage, tasks, methods, benchmarks, and evaluations.
4. The complete ten-tool and four-resource catalogue with concise parameter,
   limit, and output summaries.
5. Copyable example prompts for literature search, paper comparison, benchmark
   discovery, and lineage exploration.
6. Limits, anonymous/read-only status, privacy behavior, supported protocols,
   troubleshooting, and server version.
7. Links to the CLI repository, MCP specification, public API documentation,
   and machine-readable `llms.txt` documentation.

A restrained MCP link is added to the site footer, not the primary navigation.
The status display degrades to “Status unavailable” without blocking or
misrepresenting page content when the health request fails.
Use the shared API layer and TanStack Query with bounded refresh frequency.
The staging page copies its staging endpoint. Maintain a dated client matrix
with tested client versions, required plan/admin settings, transport, and any
bridge commands. Qualify the claimed connection flow in each client before
labeling it supported; otherwise label it unverified. Derive the catalogue from
the pinned discovery schemas or check a documentation snapshot against them.

## MCP contract

The public server preserves exactly these tools:

- `search_papers`
- `list_papers`
- `get_paper_info`
- `read_paper`
- `get_related_papers`
- `get_paper_lineage`
- `get_task`
- `get_method`
- `list_benchmarks`
- `get_benchmark`

It preserves exactly these resource templates and exposes no prompts:

- `pwc://papers/{paper}`
- `pwc://papers/{paper}/markdown`
- `pwc://tasks/{task}`
- `pwc://benchmarks/{benchmark}`

All tools remain anonymous, read-only, and idempotent, with deterministic
ordering for the same catalog snapshot; catalog updates can change results.
Responses retain their versioned MCP-specific structured output and text fallback.

## Cursor-capable Markdown API

Extend `GET /api/v1/research/papers/{paper_id}/read` with optional non-negative
`offset` and positive bounded `limit` query parameters. `offset` is a byte
position and `limit` is a byte count in the stored UTF-8 Markdown object. The
maximum `limit` is the existing public cap, 262,144 bytes. Supplying either
parameter selects chunk mode; omitted offset defaults to zero and omitted
limit defaults to that cap. Chunk mode never appends a truncation notice.

Compatibility rules:

- A request without any chunk parameters preserves the successful current body,
  status, content type, cache policy, and `X-PwC-Truncated` behavior; see the
  explicit error-sanitization exception below.
- A ranged request requires `offset` to be a UTF-8 code-point boundary and
  returns at most `limit` bytes of complete code points starting exactly at
  that byte. A mid-code-point offset is rejected as an invalid range.
- If a positive limit cannot fit the next complete code point, return a bounded
  validation error, not an empty nonterminal chunk or a non-advancing cursor.
  Invalid UTF-8 inside the object fails explicitly rather than silently dropping
  bytes. Preserve bytes without newline normalization or replacement decoding.
- `X-PwC-Next-Offset` is returned only when another chunk exists. Its value is
  the exact next byte position and advances monotonically.
- An offset equal to the object size returns an empty successful terminal
  chunk. An offset beyond the object size is rejected as an invalid range.
- Syntactically invalid, negative, boolean-like, duplicate, or excessive query
  values return sanitized `422` before bucket I/O. Bound offset to signed
  64-bit range. Boundary and object-size validation necessarily require bounded
  storage I/O and return `416`; missing Markdown returns sanitized `404`.
- Successful chunks use `200 text/plain; charset=utf-8` with
  `X-PwC-Truncated: 1` exactly when a next offset exists, otherwise `0`.
  These query parameters are not HTTP Range/206 semantics.
- Chunk responses identify the exact object revision using an opaque
  `X-PwC-Content-Version`. Continuations supply it as `content_version`.
  Require it for nonzero offsets; version mismatch returns `409` with restart
  guidance and no content. Treat `content_version` alone as chunk mode too.
  Cache keys include canonical paper/source, content version, offset, and limit.
  Only version-bound chunks may be publicly cached for at most one hour;
  unversioned initial chunks revalidate, and errors are `no-store`.

The backend opens the private bucket object and performs bounded reads. It may
read a small fixed overlap around a requested boundary to avoid splitting a
UTF-8 code point, but it never downloads the complete object to serve a chunk.
The service determines whether another byte exists with a one-byte bounded
lookahead. Error responses never expose bucket IDs, object keys, or credentials.

Hugging Face Buckets are non-versioned and their S3-compatible `GetObject` does
not honor `If-Match`, so the implementation uses content-addressed immutable
Markdown objects plus a small per-paper manifest. Writers upload and verify the
immutable SHA-256 object before publishing the manifest; a repair publishes a
new object and switches the manifest last while retaining the old object for
active cursors. Readers resolve the manifest once, validate its bounded schema,
and read only the immutable object it names. Existing canonical objects are
migrated in bounded remote batches before continuation is enabled. The legacy
canonical object remains during the compatibility period, but is never used for
version-bound continuation. Metadata followed by a range read of the mutable
canonical key is not sufficient; do not emulate consistency by hashing or
downloading the whole object on a request path.
Test actual upstream Range behavior and byte counts with the pinned HF client;
`seek()` plus `read(n)` alone is not evidence of bounded network transfer.
Keep range caching separate from the existing non-expiring process LRU.

The existing unparameterized error path interpolates storage details into a
`404`. Sanitizing those messages is an explicit, narrow exception to body
compatibility; preserve successful legacy responses and status semantics.
Document modern arXiv and numeric external-paper support and the current lack
of stored legacy arXiv reads. Version suffixes currently normalize to the stored
base identifier; do not claim access to a requested historical arXiv revision.

## MCP paper continuation

`CatalogClient` gains a paper-chunk operation that calls the ranged API and
returns Markdown, content version, and the next upstream byte offset. Each
canonical paper/version/offset/limit tuple is cached independently for at most
one hour, under both entry-count and total-byte bounds.

`read_paper` performs at most one bounded upstream Markdown read per invocation
(zero on a cache hit). Initial title/slug resolution may make additional catalog
calls; retain a bounded resolution budget and a whole-operation deadline.
Continuation must not repeat the existing up-to-ten-page title search. Its
public cursor is versioned and binds canonical paper/source identity, the
normalized input reference, content revision, byte offset, chunk limit, key ID,
and a fixed expiry one hour after the first chunk. Authenticate and validate
cursor size/schema before lookup. A cursor for another paper, a modified cursor,
an expired cursor, an invalid offset, or a changed document fails clearly without
exposing internal paths or the raw upstream cursor. Cursor integrity is authenticated with a required
deployment secret so clients cannot manufacture arbitrary offsets. The secret
persists across immutable releases; rotation accepts the previous secret for at
least the one-hour cursor/cache lifetime so a routine deployment does not
invalidate an active read. Retain old verification keys until every cursor
issued with them has expired; cache hits must not extend expiry. Use HMAC with
constant-time verification and no storage paths in the payload. “Opaque” means
clients must not interpret the token; signing alone does not encrypt it.
Replaying a valid cursor is supported and idempotent, including the cursor that
returns the terminal chunk. Completion is `truncated=false, next_cursor=null`;
there is no server-side consumed-cursor state. Preserve existing result fields.

The Markdown resource returns content only when the first chunk is terminal.
When more data exists, it fails with guidance to use `read_paper` continuation;
it never presents a prefix as the complete resource.

The legacy unparameterized catalog response remains fail-closed in the MCP
adapter whenever `X-PwC-Truncated: 1` is received.

## Security, privacy, and limits

- Nginx is the only trusted proxy. The MCP service accepts forwarded client
  addresses only from loopback and continues to hash client identities with a
  process-random keyed digest.
  Overwrite incoming `X-Forwarded-For` with nginx's verified peer address;
  do not append an untrusted client-supplied chain. Choose one forwarding-header
  parser: disable Uvicorn proxy rewriting when middleware checks the original
  socket peer. Replace the current broad `is_private` trust check with explicit
  loopback trust. Test forged headers from public and private peers, IPv6, and
  independent client quotas through real nginx.
- Browser Origins use an exact configurable allowlist with no wildcard.
  Origin-less native clients remain supported.
  Configure exact production/staging Hosts as well as Origins, reject `null`
  and lookalike origins, and validate Origin independently of CORS. CORS allows
  only the protocol's required headers/methods, exposes retry/version headers
  needed by supported clients, and does not enable cookie credentials. Match
  the locked SDK's version-specific header requirements in preflight tests.
- Existing limits remain: 60 total requests per minute per IP, 10 semantic
  searches per minute per IP, four concurrent requests per IP, and at most 25
  list results.
- Catalog calls retain a 25-second timeout and 2 MiB upstream response bound.
- Request bodies remain bounded to 2 MiB. The paper chunk size stays below the
  complete MCP response budget after JSON and text-fallback encoding overhead.
  Set an explicit 2 MiB serialized MCP response ceiling, select a conservative
  fixed chunk limit (initially 64 KiB), and test worst-case escaping and duplicated
  text/structured output. Apply the ceiling to all tools/resources, not just
  Markdown. Return a bounded error instead of truncating structured JSON.
- Operational telemetry records only allowlisted tool name, status, latency,
  response bytes, protocol label, and server version. It excludes queries,
  paper identifiers, cursors, resource URIs, raw IPs, authorization values, and
  bodies.
  Apply this policy to nginx, Uvicorn, SDK exceptions, upstream HTTP logging,
  and monitoring, not only the MCP telemetry middleware. Existing nginx access
  logs contain raw IPs and request paths: override logging for MCP locations.
  Upstream catalog requests still traverse site infrastructure; document its
  separate logging/retention policy rather than claiming end-to-end zero
  logging. Do not forward client cookies or authorization to the catalog.
- The public server exposes no database, bucket, shell, filesystem, write, or
  arbitrary-fetch tool.

Run a single worker per environment initially so process-local quotas are
meaningful. Introduce a global concurrency/admission limit and bounded waiting
queue before exposing anonymous traffic; cap outstanding upstream calls,
cache bytes, and IP limiter entries/TTL. Per-IP limits alone do not protect the
shared backend against many clients. Return bounded `429` with `Retry-After`
for quota exhaustion and `503` for global saturation, before catalog work.
Semantic limits inspect the validated JSON-RPC operation, not a client-supplied
method/name header. Cover batch behavior for each supported protocol version.
Health/preflight handling must not consume tool quotas or create bucket work.

Use a dedicated unprivileged system user with read-only release files, a
restricted environment/secret file, `NoNewPrivileges`, filesystem protections,
and systemd memory/CPU/task limits. Do not load `backend/keys.env`. Treat numeric
global admission and systemd budgets as qualification outputs: record them and
prove spare capacity for both MCP environments on the 16 GB host before launch.
Apply body-size and slow-upload timeouts at nginx and a total operation deadline
in MCP; a 25-second timeout per lookup is not a total deadline. Failures must
release admission slots and have bounded retries. Fix upstream base URLs in
deployment config, reject arbitrary redirects, and never fetch a caller's URL.
Paper text is untrusted source material; describe it as data in tool metadata.

## Release and deployment lifecycle

The Papers With Code application and the MCP package remain separate release
units.

### Papers With Code repository

One feature pull request adds the cursor-capable backend endpoint and frontend
documentation page. Nginx and MCP lifecycle source may live in the same pull
request when they are independently testable, but production activation occurs
only after both application and MCP packages are published.

The application follows the normal immutable `pwc-deploy` release process.
Staging receives the API and documentation route first. The production frontend
may ship the documentation page before MCP cutover only if the page labels the
endpoint unavailable; preferably the coordinated publishing task deploys it
immediately before MCP activation.

### pwc-cli repository

A follow-up pull request rebases the MCP work after pull request 6, consumes the
ranged Markdown API, authenticates continuation cursors, changes the canonical
URL to `https://paperswithcode.co/mcp`, and retains the Space configuration as a
fallback artifact.

The VPS lifecycle uses a dedicated immutable release root and systemd unit,
integrated as an explicit MCP target in the installed `pwc-deploy`, `pwc-status`,
and `pwc-rollback` interfaces. Extend their allowlists/installers/tests instead
of adding a second unmanaged deployment mechanism. Keep nginx changes under
`pwc-nginx`. Record application commit, MCP commit, lock/artifact digest,
supported protocols, API capability requirement, and non-secret config version.
Install the exact artifact from merged, reviewed commits with frozen dependency
resolution; do not install editable sibling checkouts or resolve floating PyPI
dependencies on the host. The package currently has an editable CLI path in
its uv sources, which the release packaging must eliminate.

Use a bounded stop/start MCP-only cutover for the first release. Validate the
candidate on a temporary free loopback port, shut that probe down, then switch
the environment's release pointer and restart only its MCP unit on its reserved
port. Do not require the active service's port to be unused on upgrades. Probe
local readiness/discovery and restore the previous MCP release on failure.
Routine upgrades retain the same nginx upstream; initial activation follows a
successful local probe and separately validated nginx change. Document the
brief MCP outage and client retry behavior. No zero-downtime claim is made,
and the main backend is not restarted. A future dual-slot deployment is a
separate capacity/design decision.

Serialize these operations with the designated publishing task and deployment
lock. Bound release retention by disk headroom, retaining the active and previous
known-good artifacts and compatible keys/config. Verify startup after reboot,
termination deadlines, and automatic rollback when candidate startup fails.

The Space remains non-canonical. It may be deployed for fallback qualification
after the same tests pass, but production traffic never depends on it.

## Qualification and rollout

1. Resolve the storage revision/range-read gate, protocol matrix, staging API
   connectivity, and host capacity budgets. Merge PR 6 and the application PR
   only after their CI and Cursor Bugbot findings are resolved; deploy the
   cursor API and documentation page to staging.
2. Verify successful unparameterized Markdown reads are byte-for-byte compatible
   and legacy storage errors are sanitized without changing status semantics.
3. Merge the `pwc-cli` continuation and canonical-hosting pull request after
   its CI and Cursor Bugbot review are clear.
4. Deploy `pwc-mcp@staging` on its isolated loopback service and install the
   staging nginx routing.
5. Qualify browser HTML and MCP JSON-RPC/SSE content negotiation on the same
   staging URL.
6. Exercise all ten tools, all four resource templates, a multi-chunk Unicode
   paper, invalid/tampered cursors, rate limiting, Origin rejection, and health
   reporting.
7. Verify service restart, independent MCP rollback, and main-backend
   independence.
8. After staging qualification, deploy the exact approved application and MCP
   commits to production, apply the nginx route, and repeat the public smoke
   tests.

Production API capability verification precedes MCP activation. Only then set
the existing `PWC_MCP_UPSTREAM_CURSOR_READY` release gate and publish/activate
the MCP artifact; a repository-variable value alone is not capability evidence.
Use a staged artifact built from the same pinned inputs for staging qualification
before this production gate. Verify ranged response headers and reconstruction
so an old backend silently ignoring new query parameters cannot pass readiness.

The publishing task must inspect active process and nginx state before each
environment change. Cursor Bugbot must finish and every finding must be
resolved before either pull request merges.

## Monitoring and rollback

Uptime monitoring probes `/mcp/health` and performs a lightweight MCP discovery
request without a search term or paper identifier. Alerts contain only
environment, status, latency, protocol, and release version.

MCP rollback repoints only the dedicated MCP release and rechecks local health
and discovery. Nginx rollback removes or restores only the reviewed `/mcp`
locations. If protocol qualification fails after cutover, restore the prior MCP
release or disable protocol routing while leaving the main site operational.
The Space is a manually selected fallback endpoint, not an automatic failover.
When disabled, protocol requests receive bounded `503`, never SPA HTML, and
the documentation shows unavailable status. Preserve the cursor-capable API
while any active MCP release depends on it. If an application rollback removes
that capability, first disable MCP or restore a compatible MCP release; include
this order in the incident runbook. Space qualification uses its own cursor
keys and makes no cross-endpoint continuation guarantee.

Monitor aggregate error/429/503 rates, latency, cache bytes, active upstream
calls, process memory, and disk in addition to liveness. Record a bounded log
retention policy and an alert destination/owner. Run mixed concurrent traffic
including semantic searches and Markdown reads against staging, and require
the agreed main-site latency/error budget to hold before production rollout.

## Test strategy

Backend tests cover:

- unchanged unparameterized reads;
- offset and limit validation;
- exact-limit and terminal-empty behavior;
- UTF-8 boundaries at the start and end of chunks;
- monotonic next offsets across multiple chunks;
- bounded bucket reads and one-byte lookahead;
- cache headers and non-disclosure in errors;
- same-size object replacement between/during chunks, stale revision caches,
  range responses ignored by storage, and no full-object fallback;
- limits 1–3 before a four-byte code point, malformed UTF-8, explicit defaults,
  duplicate/overflow parameters, and numeric external-paper IDs.

Frontend tests cover route precedence, endpoint copying, setup-tab content,
tool/resource completeness, health success and failure states, and responsive
semantic markup.

MCP tests cover one-upstream-call-per-chunk behavior, opaque authenticated
cursors, paper binding, tampering, expiry, terminal replay, multi-chunk reconstruction,
resource fail-closed behavior, and the existing modern/legacy protocol suite.
Also cover key rotation and rollback, alias/title resolution call budgets,
changed content revisions, malformed upstream continuation headers, ignored
range parameters, worst-case encoded response size, and cache eviction.

Deployment tests cover nginx content negotiation, streaming proxy behavior,
dedicated systemd lifecycle, immutable release identity, local and public
health, MCP discovery, rollback, and proof that the main backend remains
uninterrupted.
Exercise actual HTTP responses through nginx: HTML/HEAD, mixed and zero-quality
Accept headers, missing/unsupported versions, initialize/discovery, notification
acknowledgements, GET/DELETE `405`, preflight/Origin/Host rejection, slash aliases,
and bounded errors. Assert no protocol redirect or HTML cache contamination.
Verify staging uses staging data/API, spoofed headers cannot reset quota identity,
logs exclude forbidden fields, saturation does not starve health/main-site work,
and a failed restart leaves a recoverable previous release. After each application
release smoke-test `/health`, `/`, one SPA route, and one API route as well as MCP.

## Acceptance criteria

- Navigating to `https://paperswithcode.co/mcp` renders the documentation page.
- Pasting that exact URL into every documented compatible client connects to
  the anonymous read-only MCP server.
- A paper larger than one response can be reconstructed exactly through
  successive `read_paper` calls without any full-object read by the MCP server
  or leakage of bucket credentials.
  Reads either stay on one content revision or fail explicitly with restart
  guidance, never silently concatenate different revisions.
- Existing API callers retain successful response behavior without range
  parameters; storage-bearing legacy errors are sanitized as documented above.
- MCP and main-site deployment, restart, status, and rollback are independent.
- Staging and production qualification pass with content-free operational
  evidence, and the fallback Space is not on the canonical request path.

## Review evidence and implementation gates

Repository evidence (paths relative to their respective repositories):

- `paperswithcode/backend/services/paper_markdown_service.py`: base-ID object
  naming, bounded reader, UTF-8 trimming, and non-expiring LRU.
- `paperswithcode/backend/routers/research_catalog.py`: 256 KiB cap, appended
  legacy truncation notice, long shared-cache lifetime, and current error body.
- `paperswithcode/deploy/nginx/staging.paperswithcode.co.conf`: staging access
  checks on the API and SPA; both nginx vhosts inherit request access logging.
- `pwc-cli/mcp_server/src/pwc_mcp/{app,catalog,server}.py`: public bind default,
  private-address proxy trust, stateless JSON transport, liveness-only health,
  multi-request reference resolution, and current continuation implementation.
- `pwc-cli/mcp_server/pyproject.toml`: SDK constraint and editable CLI source.

The [source MCP pull request](https://github.com/huggingface/pwc-cli/pull/6)
is an unmerged dependency as observed on 2026-09-12; recheck its final schemas
and commit before implementation. The
[2025-11-25 transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
distinguishes optional GET streams/session deletion from legacy HTTP+SSE.
Use it for that compatibility contract, not as proof of newer-version behavior.

Blocking evidence still required: conditional/version-bound HF range reads;
the locked SDK's full protocol matrix; staging anonymous MCP plus internal API
connectivity; selected resource/latency budgets under load; real client setup
qualification; and failed-deploy/rollback drills. These are implementation and
release checks, not claims validated by this document review.
