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
- Preserve all existing public API behavior for callers that do not request a
  Markdown range.
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
- `DELETE` terminates an MCP session when used by a stateful legacy client;
  stateless clients need no session lifecycle.
- `OPTIONS` supports explicitly allowed browser integrations.
- `GET` with an MCP protocol header or `Accept: text/event-stream` is proxied
  to MCP for server-to-client streaming and legacy compatibility.
- A non-browser `GET` without an acceptable MCP stream representation receives
  a clear media-type response rather than silently receiving HTML.

Protocol signals always take precedence over HTML so an MCP client cannot be
routed into the SPA. Ordinary browser navigation then selects HTML. The
response includes `Vary: Accept, MCP-Protocol-Version` wherever representation
may differ.

`GET https://paperswithcode.co/mcp/health` returns bounded public JSON for the
documentation status indicator and uptime checks. It includes service state,
version, and supported protocol version, but no infrastructure details.

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

All tools remain anonymous, deterministic, read-only, and idempotent. Responses
retain their versioned MCP-specific structured output and text fallback.

## Cursor-capable Markdown API

Extend `GET /api/v1/research/papers/{paper_id}/read` with optional non-negative
`offset` and positive bounded `limit` query parameters. Both represent byte
positions in the canonical UTF-8 Markdown object. The maximum `limit` is the
existing public Markdown response cap.

Compatibility rules:

- A request without either parameter preserves the current body, status,
  content type, cache policy, and `X-PwC-Truncated` behavior.
- A ranged request requires `offset` to be a UTF-8 code-point boundary and
  returns at most `limit` bytes of complete code points starting exactly at
  that byte. A mid-code-point offset is rejected as an invalid range.
- `X-PwC-Next-Offset` is returned only when another chunk exists. Its value is
  the exact next byte position and advances monotonically.
- An offset equal to the object size returns an empty successful terminal
  chunk. An offset beyond the object size is rejected as an invalid range.
- Invalid, negative, boolean-like, or excessive values return the existing
  bounded validation response and never reach bucket I/O.
- Ranged responses include immutable cursor inputs in their cache key and may
  be publicly cached for one hour.

The backend opens the private bucket object and performs bounded reads. It may
read a small fixed overlap around a requested boundary to avoid splitting a
UTF-8 code point, but it never downloads the complete object to serve a chunk.
The service determines whether another byte exists with a one-byte bounded
lookahead. Error responses never expose bucket IDs, object keys, or credentials.

## MCP paper continuation

`CatalogClient` gains a paper-chunk operation that calls the ranged API and
returns Markdown plus the next upstream byte offset. Each canonical paper and
offset pair is cached independently for one hour.

`read_paper` performs one bounded upstream read per invocation. Its public
cursor remains opaque and binds the canonical paper identity to the upstream
byte offset. A cursor for another paper, a modified cursor, an invalid offset,
or an exhausted continuation fails clearly without exposing internal paths or
the raw upstream cursor. Cursor integrity is authenticated with a required
deployment secret so clients cannot manufacture arbitrary offsets. The secret
persists across immutable releases; rotation accepts the previous secret for at
least the one-hour cursor/cache lifetime so a routine deployment does not
invalidate an active read.

The Markdown resource returns content only when the first chunk is terminal.
When more data exists, it fails with guidance to use `read_paper` continuation;
it never presents a prefix as the complete resource.

The legacy unparameterized catalog response remains fail-closed in the MCP
adapter whenever `X-PwC-Truncated: 1` is received.

## Security, privacy, and limits

- Nginx is the only trusted proxy. The MCP service accepts forwarded client
  addresses only from loopback and continues to hash client identities with a
  process-random keyed digest.
- Browser Origins use an exact configurable allowlist with no wildcard.
  Origin-less native clients remain supported.
- Existing limits remain: 60 total requests per minute per IP, 10 semantic
  searches per minute per IP, four concurrent requests per IP, and at most 25
  list results.
- Catalog calls retain a 25-second timeout and 2 MiB upstream response bound.
- Request bodies remain bounded to 2 MiB. The paper chunk size stays below the
  complete MCP response budget after JSON and text-fallback encoding overhead.
- Operational telemetry records only allowlisted tool name, status, latency,
  response bytes, protocol label, and server version. It excludes queries,
  paper identifiers, cursors, resource URIs, raw IPs, authorization values, and
  bodies.
- The public server exposes no database, bucket, shell, filesystem, write, or
  arbitrary-fetch tool.

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

The VPS lifecycle uses a dedicated immutable release root, systemd unit,
deploy command, status command, and rollback command. A deployment installs the
exact reviewed package/lock state, verifies the unused loopback port, starts the
new release, probes health and MCP discovery locally, then atomically exposes it
through the separately reviewed nginx configuration. It does not restart the
main backend.

The Space remains non-canonical. It may be deployed for fallback qualification
after the same tests pass, but production traffic never depends on it.

## Qualification and rollout

1. Merge and deploy the cursor API and documentation page to staging.
2. Verify old unparameterized Markdown reads are byte-for-byte compatible.
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

## Test strategy

Backend tests cover:

- unchanged unparameterized reads;
- offset and limit validation;
- exact-limit and terminal-empty behavior;
- UTF-8 boundaries at the start and end of chunks;
- monotonic next offsets across multiple chunks;
- bounded bucket reads and one-byte lookahead;
- cache headers and non-disclosure in errors.

Frontend tests cover route precedence, endpoint copying, setup-tab content,
tool/resource completeness, health success and failure states, and responsive
semantic markup.

MCP tests cover one-upstream-call-per-chunk behavior, opaque authenticated
cursors, paper binding, tampering, exhaustion, multi-chunk reconstruction,
resource fail-closed behavior, and the existing modern/legacy protocol suite.

Deployment tests cover nginx content negotiation, streaming proxy behavior,
dedicated systemd lifecycle, immutable release identity, local and public
health, MCP discovery, rollback, and proof that the main backend remains
uninterrupted.

## Acceptance criteria

- Navigating to `https://paperswithcode.co/mcp` renders the documentation page.
- Pasting that exact URL into every documented compatible client connects to
  the anonymous read-only MCP server.
- A paper larger than one response can be reconstructed exactly through
  successive `read_paper` calls without any full-object read by the MCP server
  or leakage of bucket credentials.
- Existing API callers observe no behavior change without range parameters.
- MCP and main-site deployment, restart, status, and rollback are independent.
- Staging and production qualification pass with content-free operational
  evidence, and the fallback Space is not on the canonical request path.
