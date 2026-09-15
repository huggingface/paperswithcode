# Chat traces in Trackio

The chat turn, gateway provider-request, and durable lifecycle instrumentation can export to the
private [PwC Trackio Space](https://huggingface.co/spaces/nielsr/pwc-chat-traces).
It uses the Trackio 0.37 HTTP `bulk_log` API and `trackio.trace` payload, without
loading the dashboard SDK into the web server.

## Activation after merge

Deploy the merged change through the normal immutable-release workflow. Chat
changes default to staging; production activation requires explicit authorization.
Set these values in the target environment's protected host configuration:

```dotenv
PWC_CHAT_TRACKIO_ENABLED=true
PWC_CHAT_TRACKIO_URL=https://nielsr-pwc-chat-traces.hf.space
PWC_CHAT_TRACKIO_PROJECT=pwc-chat
PWC_CHAT_TRACKIO_HF_TOKEN=<HF token with write access to the private Space>
```

The token is used both as the private Space bearer credential and as Trackio's
write authorization. Keep it in protected configuration, never in source control.
The URL setting accepts only HTTPS HF Space origins and the exporter does not
follow redirects. The existing staging configuration refresh preserves these
four values. Do not source the development keys file into a deployed process.

When enabled, Trackio replaces Langfuse **for new turn, provider and lifecycle observations**;
it does not require Langfuse credentials or credits. Disabling Trackio restores
the previous Langfuse emission path, subject to `PWC_CHAT_LANGFUSE_ENABLED`.
The existing `langfuse_trace_id` database column and deterministic ID contract
remain unchanged. No database migration is needed.

Langfuse historical reads, incident-content access, user feedback scores, and
Langfuse-based reliability queries remain on their existing APIs. This change
does not migrate those features or historical data. They still need a functioning
Langfuse project; disabling Langfuse makes those reads/feedback unavailable.

## Reading the traces

Open **Traces** in the Space and select project `pwc-chat`. Daily runs are named
`staging-chat-YYYY-MM-DD` and `staging-provider-requests-YYYY-MM-DD` (or the
configured environment). Content-free durable lifecycle events have separate
`staging-lifecycle-YYYY-MM-DD` runs. Search the metadata `trace_id` to correlate them.

Chat traces contain the prompt/answer and the existing tool, title, guardrail,
and lifecycle spans. Provider traces contain the existing content-free request
metadata, TTFT, model, usage and actual cost. Provider calls live in separate runs
because the chat generation already contains aggregate usage; summing both runs
would double-count. Content-free turns keep prompts, answers and tool payloads
out of the export, and user IDs retain their existing hash.

A successful provider request and completed turn should appear within seconds.
Verify their trace ID, parent-child spans and token usage through `get_traces`
after a staging test conversation. The local integration validation run uses
release `trackio-integration-validation` and synthetic content only.

## Delivery and persistence

Export is best effort. Each process has one background worker, a 32-item queue,
and a 2 MiB per-trace payload limit. Transient network/HTTP failures retry three
times with the same log ID, so accepted retries deduplicate in Trackio. Permanent
HTTP/API errors, oversize traces and queue overflow emit content-free warnings
recognized by chat operational alerts. Network I/O never waits on the chat stream.
A normal interpreter shutdown drains for up to five seconds; prolonged Space
outages, forced termination or remaining queued work can lose traces. There is
no durable client-side spool.

The Space has a private bucket mounted at `/data`, `TRACKIO_DIR=/data/trackio`,
`TRACKIO_SQLITE_JOURNAL_MODE=TRUNCATE`, and `TRACKIO_SQLITE_SYNCHRONOUS=FULL`.
The journal settings were necessary for the deployment's restart persistence
check. Preserve these Space settings when updating Trackio.
