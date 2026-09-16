# First-party PwC MCP tools in chat

`PWC_CHAT_PWC_MCP_ENABLED` defaults to false. When enabled in the protected backend
and external Pi worker configuration, chat discovers the twenty reviewed read-only
tools from `https://paperswithcode.co/mcp`, one per read-only `pwc` CLI research
command with every CLI flag as a parameter (huggingface/pwc-cli PR #13). The
server owns their input schemas. Pi exposes them with a `pwc_` prefix (for
example `pwc_search_papers`, `pwc_get_benchmark`, `pwc_list_conferences`) in
place of its three direct catalog tools.

Research turns are MCP-only. Bash and Read are not registered for a normal
research turn, the policy denies them if requested, and no sandbox is created.
The rendered prompt replaces the appended pwc, s2, and hf CLI skills with the
vendored `PWC_MCP_SKILL.md` (pinned to the upstream commit named in
`mcp_research_prompt.ts`). Poster and paper authoring turns keep Bash and Read
for their artifact work; before a trusted paper receipt activates paper limits,
Bash accepts only `pwc-paper` commands and Read only the approved guides.
Legacy Bash/CLI catalog calls retain their contract when the flag is false.

Pi calls the authenticated gateway's `/catalog-mcp` route. Before discovery or
execution, the gateway checks the capability and durable turn claim; it commits
search metering before making an upstream request. Searches and filtered list
searches share the CLI search allowance. General call and output budgets remain
in the Pi policy. No private capability, session, or ownership headers are sent
to the public MCP server. The upstream URL and tool allowlist are fixed; discovery fails closed when any of the twenty tools is missing.

The gateway uses the deployed MCP 2026-07-28 stateless JSON-RPC envelope, with empty
client capabilities. It reuses an HTTP connection pool, requests JSON responses,
rejects redirects, bounds responses to 1 MiB, and imposes a 30-second total deadline.
Client disconnect cancels pending upstream work. No retries or silent direct
catalog fallback occur. Sampling, elicitation and arbitrary server/tool selection
are not exposed. MCP tool errors produce sanitized errors.

Schema discovery runs once per Pi agent initialization. Optional server fields
accept null for strict model schemas; null/empty optional arguments are omitted
before execution. Cursor metadata is placed before large paper text. Existing
chat output budgets can truncate long paper chunks, so this integration does not
promise a complete paper read within one turn. The normal truncation marker must
be respected; continuation cursors do not recover text omitted by chat's budget.

## Staging rollout

After merge and review, install the exact merged deployment tools so external Pi
workers receive the new flag. Apply the reviewed staging nginx template, which
adds only the exact POST gateway route alongside the existing catalog route.
Deploy the merged source to staging with the flag still false, then run:

```
uv run --env-file backend/keys.env python -m deploy.configure_chat_pwc_mcp staging \
  --confirm ENABLE_STAGING_PWC_MCP
pwc-deploy staging <exact-active-sha> --refresh-environment
```

Verify tool discovery, real model tool selection, search budget enforcement,
cancellation, output bounds, no sandbox creation for catalog-only turns, and
latency before production activation. Production remains off until explicitly
authorized. Its installer requires `ENABLE_PRODUCTION_PWC_MCP` and the same
reviewed source/nginx/refresh sequence. Preserve the existing Modal qualification
and spend gates; this feature does not qualify persistent sandbox transport.
