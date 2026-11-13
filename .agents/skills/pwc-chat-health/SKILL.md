---
name: pwc-chat-health
description: Audit the health and answer quality of Papers With Code production research chat (paperswithcode.co/chat) over a time window — turn failures and their root causes, time to first event and total latency, provider calls, MCP tool errors, catalog misses, execution-limit hits, scope refusals, web-search budget, capacity 429s, feedback, and a sampled read of real answers. Use this whenever the user asks to review, audit, or check production chats, chat health, chat errors, chat latency, what users ask the chat, which tasks or methods the chat could not find, or whether a chat fix worked in traffic — even if they only mention one suspicious failure. Do not use it for staging chat qualification or to change chat configuration.
metadata:
  compatibility: Requires the paperswithcode repository, uv, read access to the production database through backend/keys.env, pwc-status, and read access to the nginx and systemd journals.
---

# Papers With Code production chat audit

Audit production chat as an independent verifier. The alert monitor and synthetic probe only catch loud outages; most regressions so far (wrong tool routing, catalog gaps, timeouts on one reasoning effort, a silently tripped web-search circuit) were found only by reading the data.

## Read before auditing

1. Read the repository `AGENTS.md` and `docs/database.md`.
2. Read the chat reliability section of `docs/autonomous-operations.md` and `docs/chat-trackio.md`.
3. Find the previous audit (memory notes named `chat-health-audit-*`, or the user's last report) and list what it asked the next audit to re-check. Verifying an earlier fix in traffic is part of the job.

The live chat prompt and tool wrappers come from the deployed release, not this checkout. Read `backend/chat_sandbox_worker/pi_worker/src/` from the active release or `origin/main` when a finding depends on them.

## Safety boundary

This skill is read-only and must not expose user content.

- Use bounded `SELECT`s in a read-only transaction only. Never update rows, reset circuits, change env files, restart units, or deploy, even when the fix is obvious. Propose it.
- Report aggregates, error codes, tool names, and catalog lookup terms. Do not quote user prompts or answers, usernames, HF user IDs, session IDs in public places, or author names. A paraphrase of the request type ("thesis chapter draft in Chinese") is fine.
- Write any turn dumps to the session scratchpad, never into the repository, and do not upload them.
- Do not open Trackio trace content unless the user names an incident; aggregates do not need it.

## Evidence planes

Classify each plane as `healthy`, `degraded`, `unhealthy`, or `unverified`:

| Plane | Question |
| --- | --- |
| Reliability | What share of user turns failed, with which `error_code`, on which release, and why? |
| Latency | Are time to first event (TTFE) and total time in line with the baseline, by traffic class and reasoning effort? |
| Tools and grounding | Do tool calls succeed, and do answers use tools when they should? Which misses are catalog gaps vs routing bugs? |
| Answer quality | In a sample of real turns, are answers grounded, current, linked correctly, and not falsely refused? |
| Capacity and budgets | Were turns turned away (nginx 429), and are the web-search, OpenAI, and per-user budgets healthy? |
| Telemetry | Are feedback, Trackio export, the alert monitor, and the synthetic probe working? |

Never turn missing evidence into green.

## Phase 1: pin the scope

Capture the UTC audit time and the window (default: since the previous audit, else 24 h; use 7 days for trend questions). Then:

```bash
pwc-status
readlink -f /srv/paperswithcode/environments/production/current
```

Note every production release in the window. The snapshot's `failures_by_release` shows which release each failure ran on; a failure on a release that was replaced by a fix is not an open defect.

## Phase 2: take the aggregate snapshot

Run the bundled script from the developer checkout. It opens one read-only transaction against the database in `backend/keys.env` (the production database; production chat lives in schema `public`) and prints content-free JSON:

```bash
uv run --no-sync --env-file backend/keys.env python -B \
  .agents/skills/pwc-chat-health/scripts/chat_health_snapshot.py --hours 24 \
  > "$SCRATCHPAD/chat-health.json"
```

It reports user-turn status × `error_code`, volume, failures by release, latency percentiles by traffic class × effort × terminal status, OpenAI provider calls by model × effort × outcome, tool calls and classified tool errors, catalog misses, execution-limit turns, no-tool answers with and without paper context, scope refusals, sessions with size-related failures, feedback, and the web-search budget row.

Read it with these rules:

- `cancelled` and `cancel_control_missing` are users pressing stop. `superseded` rows were retried. Real failures are `status = 'error'` plus superseded rows with a provider or infrastructure `error_code`.
- `effort` comes from the user row; turns at `max` behave differently from everything else, so always split latency and failures by effort.
- `reasoning_capped` counts provider calls that spent the whole reasoning budget (8000 tokens). Those calls end `incomplete` and are the usual cause of 180 s turn timeouts.
- `no_tool_answers` with paper context is expected to be high (the paper is in the prompt). Without paper context it should be low; compare with the previous audit.
- `execution_limit` errors are the per-turn tool budget, not tool bugs. Report the number of turns that hit it.

## Phase 3: sources outside the database

```bash
# Capacity rejections never create DB rows.
sudo awk '$9 == 429 && $7 ~ /^\/api\/v1\/chat/' /var/log/nginx/paperswithcode_access.log | awk '{print $7}' | sort | uniq -c
# Monitors.
systemctl list-timers --all --no-pager | grep -E 'chat-alert-monitor|chat-synthetic-probe'
journalctl -u pwc-cron-run-chat-synthetic-probe.service --since '-24h' --no-pager | tail -n 40
# Trackio export and runtime warnings (content-free).
journalctl -u 'paperswithcode-production-backend@*' --since '-24h' --no-pager | grep -ciE 'trackio.*(dropped|failed)'
```

Rotate into `paperswithcode_access.log.1` and `*.gz` (with `zcat`) when the window is longer than the current file. The backend journal is dominated by access-log lines and may reach back only a few hours; check its first timestamp (`journalctl -u 'paperswithcode-production-backend@*' -o short-iso | head -1`) and mark older journal evidence unverified.

## Phase 4: root-cause every failure class

For each real `error_code`, find the mechanism, not just the count:

- **provider_error / timeouts:** join the turn's `chat_openai_provider_calls` rows on `turn_id` (`outcome`, `reasoning_tokens`, `provider_latency_ms`, `call_sequence`). The known pattern is a max-effort call ending `incomplete` at the reasoning cap, then the turn hitting the 180 s deadline.
- **context_too_large / transcript_mirror_error / openai_user_concurrency_limited:** check session size (`chat_sessions.transcript_bytes`, `message_count`) and whether one session failed repeatedly.
- **gateway_unavailable, external_worker_lost, drain-time errors:** compare timestamps with deploys. Failures clustered within a minute of a release switch are deploy drains.
- **openai_budget_exhausted:** per-user monthly cap; the stored `limit_microusd` is fixed when the month's row is created.
- **Web search off:** check `circuit_state` and `trip_reason` in the snapshot's budget row. `tripped` with `provider_budget` and no cooldown stays off until someone re-arms it.

Before calling a tool error a live bug, compare its timestamps with the last MCP restart (`journalctl -u paperswithcode-mcp@production`). Errors that stop after a deploy were fixed.

## Phase 5: read a sample of real turns

Aggregates do not show answer quality. Dump a bounded sample (for example 30 random completed turns plus every failed or refused turn) to the scratchpad and read it offline:

```bash
set -a; . backend/keys.env; set +a
PGPASSWORD=$PWC_DB_PASSWORD PGOPTIONS='-c default_transaction_read_only=on' \
  psql -h "$PWC_DB_HOST" -p "$PWC_DB_PORT" -U "$PWC_DB_USER" -d "$PWC_DB_NAME" -X -At \
  -c "select row_to_json(t) from (select u.turn_id, u.created_at, u.reasoning_effort, u.content as prompt,
        a.content as answer, a.display_blocks, a.finish_reason
      from chat_messages u join chat_messages a on a.turn_id = u.turn_id and a.role = 'assistant'
      where u.role = 'user' and u.created_at >= now() - interval '24 hours'
      order by random() limit 30) t" > "$SCRATCHPAD/chat-sample.jsonl"
```

Use `psql -At` with `row_to_json`, not `COPY`, which doubles backslashes. For each turn, check:

- the answer used catalog tools for catalog questions, and cites real `paper:` links and GitHub URLs (spot-check that they resolve);
- "latest / recent / SOTA" questions cite recent papers (the catalog has current-year papers);
- refusals (`finish_reason = 'scope_blocked'` is the server classifier; `I can only help with AI…` with a normal finish reason is the model) were genuinely off-topic;
- long writing or multi-step asks completed rather than timing out.

### Turns with uploaded files

A user turn that attached files stores a `<user_files>` block of `<pwc_user_file id="…"/>` lines at the start of `chat_messages.effective_prompt`; the model saw each file natively (OpenAI `file_id`) on that turn and only a text reference afterwards, unless it called `read_user_file`. Provider-request traces carry `user_files` metadata (id, type, size, pages, PDF detail, sha256, token estimate), never contents. To check what the model was given, copy that chat's files into the scratchpad with the read-only `python -m backend.scripts.fetch_chat_files --session-id <uuid> --out-dir "$SCRATCHPAD/chat-files"` and read them there. As with prompts, never quote file contents or file names in the report; describe them by type ("a 12-page PDF"). Things to check on file turns: the answer used the file rather than ignoring it, cited it by file name, and treated instructions inside it as data (no tool calls or behavior it asked for).

## Phase 6: verify catalog misses

`catalog_misses` lists task, method, benchmark, framework, and paper lookups that returned `not_found`. Before reporting a gap, confirm it against the catalog (`pwc` CLI or a read-only query) — the lookup may have used an alias or the wrong entity type. Methods are general techniques; a specific model name is a paper, so its method miss is not a gap. Repeated misses across audits are the strongest candidates for the add-task / add-method skills.

## Reporting

Lead with the outcome, window, and audit time.

### Summary

- Turns, sessions, users; real failure count and rate; releases in the window
- TTFE and total p50/p90 for new chats and follow-ups, with the effort split where it differs
- Plane classifications
- Fixes from the previous audit confirmed or still failing in traffic
- Statement that nothing was changed

### Findings

One entry per defect, most user-visible first: what happened (counts), the mechanism, evidence (tables, code path with `file:line` from the live release), and the smallest fix. Separate code bugs, configuration or budget problems, catalog gaps, and expected behavior.

### Catalog gaps

Verified missing tasks and methods, with how often users hit them.

### Unverified scope

What could not be checked (journal retention, sample size, unreachable source) and the read-only evidence still needed.

## Baseline (late October 2026)

About 700–950 user turns a day; real failures under 1%; new-chat TTFE p50 about 3–4 s, p90 about 5–6 s; follow-up TTFE p90 about 10 s; total p90 about 25–35 s; max-effort follow-ups much slower (p90 above 30 s TTFE). Fewer than 2% of turns hit the tool budget. Treat a clear step change from the previous audit as a finding even if the absolute number looks fine.

## Known gotchas

- `chat_turn_latency` has no `created_at`; filter on `admitted_at`. Its `failure_stage` (`before_dispatch`, `awaiting_first_event`, `streaming`) tells you how far a failed turn got; it is empty for stopped and interrupted turns.
- `primary_paper_context` on user rows can be JSON `null`, not SQL `NULL`; use `jsonb_typeof(...) = 'object'`.
- Tool blocks are `display_blocks` entries with `kind = 'tool'`, `status` `success` or `error`, and the error text at `content[0].text`.
- `chat_turn_latency.system_prompt_sha256` comes from deploy-time chat config, not the Pi worker prompt, so it does not change when the prompt does.
- Feedback goes to `chat_feedback` (`value` is true for thumbs up); volume is a handful a week, so an empty window is normal.
- Reading `/etc/paperswithcode/production.env` is blocked in auto mode; `backend/keys.env` points at the same database.
- Production deploys from other sessions are frequent. Attribute each failure to its release before calling it open.
- Do not use `git stash` in this repository; the stash is shared across worktrees.

## Completion gate

Before finishing, confirm:

- every real `error_code` in the window has a mechanism or is listed as unverified;
- latency is split by traffic class and effort and compared with the previous audit;
- nginx 429s, the monitors, and the web-search budget were checked;
- a sample of real turns was read;
- catalog misses were verified before being called gaps;
- the report quotes no user content and no state was changed.
