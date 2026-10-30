---
name: process-x-bookmarks
description: >-
  Process the user's X (Twitter) bookmarks into Papers with Code: find every
  bookmarked post that announces a paper, index missing arXiv papers, add
  non-arXiv releases as external papers, enrich each paper (code, project page,
  HF artifacts, tags, thumbnail), and link the announcement thread to
  the paper's X threads section. Use whenever the user asks to check, sweep,
  triage, or process their X/Twitter bookmarks, or to make sure bookmarked paper
  tweets are indexed, enriched, or have their X threads added.
---

# Process X Bookmarks

The user bookmarks paper announcements on X. This skill turns them into
complete paper pages: the paper exists, it is enriched, and the authors'
announcement post shows in its X threads card.

Run everything from the repository root of the primary checkout (it has
`backend/keys.env`). Keep reports and link files in the scratchpad.

## 1. Get a working X user token

Bookmarks need an OAuth 2.0 user-context token; the app-only
`X_API_BEARER_TOKEN` is rejected. Tokens live in `backend/keys.env`
(`X_USER_ACCESS_TOKEN`, valid 2 hours, and `X_USER_REFRESH_TOKEN`).

```bash
uv run --env-file backend/keys.env python .agents/skills/process-x-bookmarks/scripts/x_user_token.py --refresh
```

If the refresh token is missing or rejected, the user must re-authorize once,
in two steps that need no terminal:

1. Run the script with `--link` and put the printed link in your message
   (not only in a tool result the user may not see).
2. The user approves; their browser then fails to load
   `http://localhost:8080/callback?state=…&code=…`. They paste that URL back,
   and you run the script with `--finish '<URL>'` right away (the code expires
   within minutes; a new `--link` invalidates older links).

That callback must be registered on the X app (client ID in
`X_OAUTH_CLIENT_ID`); X answers an unregistered one with a bare "Something went
wrong — You weren't able to give access to the App". Ask the user to close
`backend/keys.env` in their editor first: an open editor buffer has
overwritten the saved tokens before.

X API reads are prepaid. HTTP 402 `credits-depleted` on any endpoint means the
account is out of credits (shared with the `discover_x_threads` CRON); the user
must top up in the X developer console. Stop and tell them.

## 2. Triage the bookmarks

```bash
uv run --env-file backend/keys.env python .agents/skills/process-x-bookmarks/scripts/triage_bookmarks.py \
    --max 200 --out <scratchpad>/x_bookmarks.json
```

The API returns bookmarks newest first and at most the newest 800. Bookmarks
carry no bookmarked-at time, so "recent" means the first `--max` entries; every
later step is idempotent, so re-processing already-handled bookmarks is safe.
X reads are pay-per-use: keep `--max` to what the user asked for. The fetched
bookmarks are saved to `<out>.raw.json` first; rerun with
`--from-raw <out>.raw.json` instead of fetching them again. Each bookmark
without an arXiv link costs one extra timeline read for the self-reply lookup;
pass `--no-replies` when credits are tight, and the script stops the lookups
by itself if credits run out mid-run.

For each bookmark the script follows quotes and retweets to the original post,
and when no arXiv link is visible it reads the poster's own posts in the same
conversation (paper links often sit in a self-reply). It then reports, per
arXiv id: `MISSING` (not indexed), `UNLINKED` (indexed, thread not linked) or
`linked`, plus enrichment `gaps`. Bookmarks with only non-arXiv links
(`other_urls`) need manual review.

Read the JSON and decide each bookmark yourself; the script only gathers
evidence:

- **Paper post**: announces or explains a specific paper or release. Skip
  general commentary, news, memes, job posts, and round-ups of many papers.
- **No arXiv paper**: if the post announces a real release with a technical
  report, model card, blog, or repository, use `add-external-paper`. First
  search the catalog (`pwc search`, title search) to avoid duplicates.
- **arXiv id in the post is not the announced paper** (a cited baseline, a
  related work): drop it.

## 3. Index missing arXiv papers

```bash
uv run --env-file backend/keys.env python -m backend.cli paper index <arxiv_id>
```

It is idempotent and prints the new database id.

## 4. Enrich each paper

For every indexed paper with `gaps` (and every newly indexed or external
paper), run the `enrich-paper` skill. Spread several papers across subagents,
one paper per subagent, and collect what each changed. Do not re-enrich papers
with no gaps unless the bookmark shows something missing (for example the post
links a repository the page lacks).

## 5. Link the X threads

Policy (user decision, 2026-10-30): link posts that introduce, announce or
substantively explain the paper. The poster may be an author, the paper's own
organization, or an outside account such as a paper curator (@_akhaliq,
@omarsar0) whose post describes this paper.

- The thread is the conversation root: if the bookmark is mid-thread, link the
  root post of the same author. Use the quoted original when the bookmark is a
  quote-tweet by someone else.
- When a co-author quote-tweets the original author's announcement, link the
  original.
- Prefer the authors' or organization's own announcement when one exists
  (`author_matches` in the triage output); a substantive outside post can be
  linked next to it.
- Skip replies in other people's conversations, bare posts without content
  about the paper ("out now!"), and posts covering several papers without
  linking this one.
- A paper holds at most 10 threads.

Write `<scratchpad>/x_thread_links.json` as
`[{"paper": "<arXiv id or db id>", "urls": ["https://x.com/<handle>/status/<id>"]}]`,
dry-run, then apply:

```bash
uv run --env-file backend/keys.env python .agents/skills/process-x-bookmarks/scripts/link_threads.py <scratchpad>/x_thread_links.json --dry-run
uv run --env-file backend/keys.env python .agents/skills/process-x-bookmarks/scripts/link_threads.py <scratchpad>/x_thread_links.json
```

The API captures a preview from X's public syndication endpoint and rejects
unavailable posts; report those.

## 6. Verify and report

Re-run the triage on the same `--max` and confirm every kept paper bookmark is
`linked` with no unexpected gaps. Report to the user:

- bookmarks scanned, paper bookmarks found, skipped (with one-line reasons)
- papers indexed and external papers added (with `https://paperswithcode.co/paper/<id>` links)
- papers enriched and what changed
- threads linked, and bookmarks left for their decision
