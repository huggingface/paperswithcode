# Chat traces in Trackio

The chat turn, gateway provider-request, and durable lifecycle instrumentation can export to the
private [PwC Trackio Space](https://huggingface.co/spaces/nielsr/pwc-chat-traces).
It uses the Trackio 0.37 HTTP `bulk_log` API and `trackio.trace` payload, without
loading the dashboard SDK into the web server.

## Configuration

Production exports to Trackio; staging currently sets none of these values, so
it does not export. The values live in the environment's protected host
configuration (`/etc/paperswithcode/<environment>.env`):

```dotenv
PWC_CHAT_TRACKIO_ENABLED=true
PWC_CHAT_TRACKIO_URL=https://nielsr-pwc-chat-traces.hf.space
PWC_CHAT_TRACKIO_PROJECT=pwc-chat
PWC_CHAT_TRACKIO_HF_TOKEN=<HF token with write access to the private Space>
```

The token is used both as the private Space bearer credential and as Trackio's
write authorization. Keep it in protected configuration, never in source control.
The URL setting accepts only HTTPS HF Space origins and the exporter does not
follow redirects. Do not source the development keys file into a deployed process.

When enabled, Trackio replaces Langfuse **for new turn, provider and lifecycle observations**;
it does not require Langfuse credentials or credits. Disabling Trackio restores
the previous Langfuse emission path, subject to `PWC_CHAT_LANGFUSE_ENABLED`.
The existing `langfuse_trace_id` database column and deterministic ID contract
remain unchanged. No database migration is needed.

Langfuse historical reads, incident-content access, and Langfuse-based
reliability queries remain on their existing APIs and still need a functioning
Langfuse project. User thumbs ratings are stored in the `chat_feedback` table;
with Trackio enabled each rating is mirrored as a `feedback/thumbs_up` metric in
the daily `<environment>-feedback-YYYY-MM-DD` run (`exported_to = 'trackio'`).

## Reading the traces

Open **Traces** in the Space and select the week's project, for example
`pwc-chat-2026-W43` (see [weekly project rotation](#weekly-project-rotation)). Daily runs are named
`<environment>-chat-YYYY-MM-DD` and `<environment>-provider-requests-YYYY-MM-DD`,
for example `production-chat-2026-10-20`. Durable lifecycle observations are
logged as content-free numeric metrics in separate `<environment>-lifecycle-YYYY-MM-DD`
runs. Search the metadata `trace_id` to correlate them.

Chat traces contain the prompt/answer and the existing tool, title, guardrail,
and lifecycle spans. Provider traces contain the existing content-free request
metadata, TTFT, model, usage and actual cost. Provider calls live in separate runs
because the chat generation already contains aggregate usage; summing both runs
would double-count. Content-free turns keep prompts, answers and tool payloads
out of the export, and user IDs retain their existing hash.

A successful provider request and completed turn should appear within seconds.
Verify their trace ID, parent-child spans and token usage through `get_traces`
after a test conversation in an environment that exports.

## Delivery and persistence

Export is best effort. Each process has one background worker and a queue
bounded at 512 entries and 64 MiB; the worker batches up to 20 entries (2 MiB)
into one `bulk_log` POST, and a single trace over 2 MiB is dropped. Transient
network/HTTP failures (408, 429, 5xx) get three attempts with the same log IDs, so accepted retries deduplicate in Trackio. Permanent
HTTP/API errors, oversize traces and queue overflow emit content-free warnings
recognized by chat operational alerts. Network I/O never waits on the chat stream.
The final retry warning names the last status code or exception class
(`last_error=HTTP 500`, `last_error=ReadTimeout`), never the response body.

Trace export classifications are `warning` alerts (`chat_telemetry_degraded`),
not critical pages, because they lose observability rather than chat turns. Like
critical runtime classifications, each alerts once on entry, then at most once
per cooldown while it keeps recurring (six hours for warnings, one hour for
critical), with the suppressed count; after 30 quiet minutes a repeating
classification sends one `chat_telemetry_recovered` or `chat_runtime_recovered`
notice.
A normal interpreter shutdown drains for up to five seconds; prolonged Space
outages, forced termination or remaining queued work can lose traces. There is
no durable client-side spool.

The Space has a private bucket mounted at `/data`, `TRACKIO_DIR=/data/trackio`,
`TRACKIO_SQLITE_JOURNAL_MODE=TRUNCATE`, and `TRACKIO_SQLITE_SYNCHRONOUS=FULL`.
The journal settings were necessary for the deployment's restart persistence
check. Preserve these Space settings when updating Trackio.

## Weekly project rotation

Trackio keeps one SQLite file per project under `TRACKIO_DIR`, and a single
`pwc-chat` project grew to a 4 GB `trackio/pwc-chat.db` (about 125 MB a day).
On 2026-10-17 that file was corrupted right after a Space restart; the suspected
cause is Trackio's startup `sync_bucket`, which can rewrite the live multi-GB file
through the `/data` mount. To bound both the rewrite window and the loss from any
one corruption, the exporter writes to `<PWC_CHAT_TRACKIO_PROJECT>-<ISO year>-W<week>`,
for example `pwc-chat-2026-W43`, stored as `trackio/pwc-chat-2026-W43.db`.

The project follows the same UTC date as the run name, so each daily run lives in
exactly one weekly project and `trace_id` correlation is unchanged. Weeks start on
Monday and use the ISO week-numbering year, so 2027-01-03 belongs to
`pwc-chat-2026-W53`. To search across weeks, open each week's project. The
legacy `pwc-chat` project receives no new writes once this change is deployed;
archive it with the step below.

Trackio also writes every trace as JSONL under `traces/<project>/<run>/`, outside
`trackio/`. That JSONL is the durable record; the SQLite DBs are a rebuildable
dashboard index.

### Recovering a corrupted DB

Do the byte-level work on Hugging Face, never on the VPS: the files are multi-GB
and the VPS has limited disk and memory. Replace `<db>` with the damaged file,
for example `pwc-chat-2026-W43.db`, and `<stamp>` with the UTC date.

1. Copy the DB aside, server side, to a prefix outside `trackio/` so Trackio's
   startup sync cannot touch the copy. Copy its journal too if one exists:

   ```bash
   hf buckets cp hf://buckets/nielsr/pwc-chat-traces/trackio/<db> hf://buckets/nielsr/pwc-chat-traces/trackio-corrupt-<stamp>/<db>
   ```

2. Remove the original (and its `<db>-journal`) so Trackio starts a fresh file:

   ```bash
   hf buckets rm --yes nielsr/pwc-chat-traces/trackio/<db>
   ```

3. Restart the Space and confirm a new production turn appears in Traces:

   ```bash
   hf spaces restart nielsr/pwc-chat-traces
   ```

4. Recover the copy in an HF Job with the bucket mounted read-only, writing the
   result to a separate prefix:

   ```bash
   hf jobs run --flavor cpu-upgrade --secrets HF_TOKEN -v hf://buckets/nielsr/pwc-chat-traces:/bucket:ro python:3.12 bash -c 'apt-get update -qq && apt-get install -y -qq sqlite3 && pip install -q huggingface_hub && sqlite3 /bucket/trackio-corrupt-<stamp>/<db> .recover | sqlite3 /tmp/<db> && sqlite3 /tmp/<db> "PRAGMA integrity_check" && hf buckets cp /tmp/<db> hf://buckets/nielsr/pwc-chat-traces/trackio-recovered-<stamp>/<db>'
   ```

Never copy a recovered DB back into `trackio/` while the Space is running. A
recovered DB for a finished week can go straight to `trackio-archive/`. For the
current week, keep the fresh DB; the JSONL still holds the lost traces. Delete the
`trackio-corrupt-<stamp>/` copy once the recovered file has been checked.

### Archiving old weeks

Keep about eight weeks of projects in `trackio/` so the Space's startup sync and
dashboard stay small. Move older DBs to `trackio-archive/`, which Trackio does not
read or sync. Run this from any host with an `hf` token that can write the bucket:

```bash
cutoff=$(date -u -d '8 weeks ago' +%G-W%V); for path in $(hf buckets ls hf://buckets/nielsr/pwc-chat-traces/trackio -q | grep -E '^trackio/pwc-chat(-[0-9]{4}-W[0-9]{2})?\.db(-journal)?$'); do week=$(echo "$path" | grep -oE '[0-9]{4}-W[0-9]{2}' || echo 0000-W00); if [[ "$week" < "$cutoff" ]]; then hf buckets cp "hf://buckets/nielsr/pwc-chat-traces/$path" "hf://buckets/nielsr/pwc-chat-traces/trackio-archive/${path#trackio/}" && hf buckets rm --yes "nielsr/pwc-chat-traces/$path"; fi; done
```

The legacy unrotated `pwc-chat.db` sorts as week `0000-W00` and is archived on the
first run, so run this only after the rotation is live in every environment that
exports to the Space. Restart the Space afterwards so its dashboard drops the archived
projects. To read an archived week, mount the bucket read-only in an HF Job or
download the file; do not copy it back into `trackio/`.
