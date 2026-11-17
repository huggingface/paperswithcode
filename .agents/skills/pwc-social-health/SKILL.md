---
name: pwc-social-health
description: Audit and grow the Papers with Code social accounts — X (@paperswithcodee, run by the headless X growth agent and its post queue/dashboard) and the Papers with Code LinkedIn company page (an automatic mirror of every X post). Checks that posting, the queue, the dashboard sync, the LinkedIn mirror, stats collection and tokens work; compares which kinds of posts and which phrasings do well or flop on each network; then tunes the agents' steering (prompts, queue) so the accounts grow. Use whenever the user asks how the X or LinkedIn account is doing, which posts work, why reach or followers dropped, whether posting or the LinkedIn mirror is broken, or asks to improve, steer or grow the social accounts — even if they only mention one post or the dashboard.
metadata:
  compatibility: Runs as root on the production host, where the X growth agent lives in /root/x-post-schedule (outside this repository). Needs python3; no database access.
---

# Papers with Code social accounts: health and growth

The accounts are run by automation, so the job is to check that the automation works and to steer it with evidence, not to post by hand.

## How the accounts are run

Everything lives in `/root/x-post-schedule/` on the production host, not in this repository (backups of every edited file sit next to it as `*.bak-<date>[-slug]`).

- `x-post-schedule.timer` runs `run.sh` at :01 and :31. Each run: applies dashboard edits and publishes the queue (`post_x.py sync`); drafts "Tweet it" requests (`request_prompt.md`); posts the queue head when a slot is open (`post_x.py post-next`; every 2 h from 08:00 to 02:59 UTC, at most 10 a day); lets the planning agent (`prompt.md`) top the queue back up to 4 drafts from `pwc-cron x_post_candidates`; mirrors new X posts to LinkedIn (`linkedin_prompt.md` + `post_linkedin.py`); and once an hour snapshots stats (`post_x.py stats` → `stats.jsonl`, `post_linkedin.py stats` → `linkedin-stats.jsonl`).
- `x-post-watch.timer` posts a dashboard "Post now" within a minute.
- Records: `ledger.jsonl` (every X post, rejection and replacement, with `kind`, text, reply and media), `linkedin-ledger.jsonl` (LinkedIn URN per X `post_id`), `queue.json`, logs in `logs/` (`<stamp>.log` planner, `-requests.log`, `-linkedin.log`, `posts.log`, `sync.log`).
- Dashboard: the private Space https://huggingface.co/spaces/nielsr/pwc-x-dashboard (source `space2/`) shows the queue, lets Niels edit, reorder, delete or "Post now", and shows X performance by kind. Edits travel through the private dataset `nielsr/pwc-x-queue`.
- Post kinds: `new_sota`, `open_sota`, `open_release` (open models winning or placing on well-known boards), `trending_paper` (homepage trending, alphaXiv-style explainer), `concept` (method explainer with a method-page screenshot), `top_papers_week`/`top_papers_month`, `lab_league`, and `manual` (Niels's own or pre-agent posts).
- LinkedIn posts the X text unchanged except for the mirror rules in `linkedin_prompt.md` (reply merged in, @handles replaced by names, no accidental hashtags).

## Standing rules from Niels (never steer against these)

Open models only (closed models appear only as the comparison bar); verify public weights before calling anything open; no Artificial Analysis boards; trending papers in homepage rank order; no saturated legacy boards (BBH, MMLU, HellaSwag, …); at most one concept per posting day and SOTA/open-release posts first; every number traceable to the catalog; X posts separate sentences with empty lines. The dated history is in `prompt.md` and the memory notes `x-growth-agent` and `linkedin-company-page`. Read them before proposing a change.

## Workflow

### 1. Collect

```bash
python3 .agents/skills/pwc-social-health/scripts/social_report.py > <scratchpad>/pwc-social.json
```

It is read-only. It returns `findings` (`broken`/`warn`), X and LinkedIn followers (deltas are `null` when the history is shorter than the window) and followers per day, posts in the last 24 h, the queue, the last planner and mirror lines, token expiry, each network's `performance` (per kind: median impressions of the last 5 posts, best post, top and bottom 3 posts), and `posts`: one row per X post of the last 14 days with X and LinkedIn impressions side by side, age, and the LinkedIn mirror delay. Also find the previous audit (memory notes named `social-health-audit-*`) and list what it said to re-check, especially whether its steering change moved the numbers. With no previous note, this audit is the baseline: record the numbers, and steer only on clear evidence.

### 2. Health

Treat each finding as a lead and confirm it in the files before reporting it:

- **No recent X post in the window**: read the newest `posts.log` lines and planner logs. Common causes: empty queue (candidate supply: the planner's last line says `Queued: none` and lists rejections), a failing `pwc-cron x_post_candidates` call, an X API error (402/403), or a stuck `run.lock`.
- **Unmirrored LinkedIn posts or a `Failed:` mirror line**: read the newest `*-linkedin.log`. API errors carry LinkedIn's message; a 401 means the token needs `post_linkedin.py refresh`, and an expired refresh token needs a page admin to redo `auth-url`/`exchange` (never enter credentials yourself).
- **Stale stats**: the hourly lines in `run.sh` stopped or the API call fails; check `logs/stats.log` and `logs/linkedin-stats.log`.
- **Dashboard**: `sync.log` errors mean the Space shows a stale queue or Niels's edits are not applied.
- A green timer proves nothing: `claude -p` runs in `dontAsk` and exits 0 when tools are denied. Judge by the ledgers.

### 3. What does well

Compare per kind and per post, on each network separately; the audiences differ (mid-November 2026, concept explainers flopped on X but were the best LinkedIn posts).

- Use `performance` for the kind mix, then read the full text of the top and bottom posts from `ledger.jsonl` / `linkedin-ledger.jsonl` (match by `post_id`) and name what separates them: a tagged frontier or open lab, an open-vs-closed upset, a famous paper or author, a clear one-line hook, the card or screenshot, time of day.
- Impressions keep growing for about a day: ignore posts younger than 12 h (X) / 24 h (LinkedIn) (`age_h`).
- LinkedIn reach depends on whether a post went out alone. Until 2026-11-17 most posts were mirrored in catch-up bursts (by hand, then a 9-post API catch-up); judge LinkedIn kinds on posts with `mirror_delay_min` under about 60 and say how many there were.
- `flopping` on X is an absolute threshold (`FLOP` = 60 impressions in `post_x.py`): compare kinds with each other too. A kind far below the best kind's median is weak even when it is not flagged.
- Look inside a kind before judging it: it can be bimodal (in November 2026, trending papers naming a famous researcher or lab drew about 7x the reach of untagged ones).
- Watch followers per day, not only impressions: a kind with modest impressions can still bring followers.
- Note candidate supply: if good kinds are rare because the catalog offers few candidates (see rejections in `ledger.jsonl`), the fix is in `backend/services/x_post_candidates.py` (a normal PR), not in the prompt.

### 4. Steer

Make the smallest change the evidence supports, one lever at a time, so the next audit can tell whether it worked:

- **X mix and style**: the "Let the numbers steer the mix" section of `prompt.md` (and `FLOP`/`PERF_DAYS` in `post_x.py`). Add a dated rule with the numbers behind it, like the existing ones.
- **Queue**: a queued draft that the data says will flop can be dropped with `post_x.py unqueue --post-id <id> --reason "<why>"` (never a "Tweet it" request or a draft Niels edited).
- **LinkedIn style**: `linkedin_prompt.md` controls how X posts are adapted. Keep LinkedIn a faithful mirror unless Niels agrees otherwise; adapting the form (a stronger first line, a takeaway line) is in scope when the LinkedIn numbers support it, adding claims is not.
- Before editing any file there, copy it to `<file>.bak-<YYYYMMDD>-<slug>`. Then test the agent's reading of the change cheaply where possible (`post_linkedin.py pending` with `LINKEDIN_DRY_RUN=1 LINKEDIN_PENDING_TEST=<post_id>` for the mirror).

Ask Niels first for anything beyond steering: changing the cadence or posting window, adding or retiring a post kind, deleting or replacing a published post, posting by hand, changing credentials or timers, or breaking a standing rule. Never post, delete, or edit published posts as part of an audit.

### 5. Report and remember

Report: health findings (confirmed only), followers and reach on each network versus the last audit, the best and worst kinds and posts with the reason you see, what you changed (file, backup name, the numbers that justified it), and what the next audit should re-check. Save a short memory note `social-health-audit-<date>` with the baseline numbers and the change, and link it from `x-growth-agent` or `linkedin-company-page` when a rule changed.
