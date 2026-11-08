# Research follows and weekly email

Entity follows are private and keyed by the immutable Hugging Face OAuth subject;
free-text topics can be public (see below).
The Following tab sits beside Trending, Newest, and Most cited, using the same
paper cards and thumbnails. Its bookmarkable feed lives at `/following`; `/settings` manages interests and
explicit weekly-email opt-in. OAuth email access uses the existing
`collect_email=true` flow and accepts only a verified identity email. No
browser-supplied destination is accepted.

The feed shows papers with known publication dates from today through 30 days
ago (UTC), includes task descendants, and combines associations across arXiv
versions. It displays the latest version but excludes a paper if any version
was published before the cutoff. Direct matches weigh two; inherited task
matches weigh one. Distinct matching interests add strength. The feed ranks
matches with the home feed's trending order
(`PaperService.apply_scoped_trending_order`), so it follows
`PWC_TRENDING_RANKING_MODE`. Weekly digests instead rank each interest by
strength, publication date, popularity, then canonical ID; round-robin
selection balances coverage and counts each paper once. Up to 100 interests
may be followed. Feed pages contain 40 entries.

## Free-text topics

Each account may also describe up to ten topics in its own words (up to 300
characters each, edited in `/settings` or from the Following feed). Topics are
shared rows in `research_topics`, keyed by normalized text (lowercase,
collapsed whitespace, trailing punctuation stripped); accounts follow them
through `research_topic_follows`. The API is `GET/POST /me/topics`,
`PUT/DELETE /me/topics/{id}` and `PUT /me/topics/order` (every followed id, in
the account's order, stored in `research_topic_follows.position`; edits keep a
topic's place and new topics go last). Topic names are shown with a capital
first letter (sidebar, cards, match reasons, digests); stored text is unchanged; the older single-topic `/me/topic` reads and
replaces the account's first topic. Jev (`jev-1.14` through
OpenRouter's `systemone` endpoint) scores each paper's card (title, authors,
organizations, venue, task/method/benchmark tags, abstract) against the topic,
and `research_topic_verdicts` keeps the raw score with the card's SHA-256 and
the prompt version. The feed and digest treat a score of at least 0.80 as a
match, applied when reading, so recalibration rewrites nothing. The threshold
and prompt were calibrated on 299 hand-labelled topic/paper pairs across ten
topics (about 90% precision and 43% recall; `reports/topic-calibration/`
locally).

Topic matches join entity matches in one feed, deduplicated by paper and
ranked by the same trending order; the reason line names the topic in quotes.
The feed's `topic_id` parameter (`/following?topic=<id>`) shows one topic's
matches; `topic_only` shows every topic's.
A new topic is backfilled by the per-minute `backfill_research_topics` job:
every paper from the last 90 days, then up to 3,000 older papers ranked by
dense + lexical reciprocal rank fusion, judged once in batches of 500 until a
batch has fewer than five matches. The hourly
`judge_research_topics` job (:54) judges papers in the 90-day window that are
new or whose card changed, against every followed topic. There is no fallback:
failed Jev calls leave pairs unjudged for the next run, a failed backfill
retries up to five times, and CRON health flags papers left unjudged for six
hours. Staging has its own topic tables and no topic CRON, so staging topics
stay pending.

Digests list up to 10 topic matches first under "New on your topics", then
entity follows. Topic matches use the same paper discovery events as entity
follows, so only papers discovered after the topic was set can be emailed;
backfilled papers are feed-only.

Production insert triggers capture discovery independently of mutable
`updated_at`. Paper revisions do not create another paper event. Result
identity is canonical paper + task + dataset + model + harness, excluding
scores. Updates and delete/reinsert corrections do not create new alerts.
Existing result identities are seeded with an old discovery timestamp, so
migration and feed backfill never become an email backlog. Unknown/future
dates and imports older than 30 days do not alert. Tag changes do not create
discovery events.

Weekly windows are half-open, Monday 08:00 UTC to the next Monday 08:00 UTC.
Email events must also be later than the follow and opt-in timestamps. A
result event qualifies only through its followed benchmark. Up to 20 distinct
papers are selected; the starting interest rotates by week when the cap
prevents covering all interests. Unselected events expire with the window.
Summaries use the existing TL;DR or abstract, capped at 60 words with sentence
boundaries preferred. No generation service is called.

The durable outbox freezes each account/week payload before attempting send.
Every attempt rechecks opt-in, destination, and address suppression. An
ambiguous request retries with the same Resend key and payload for less than
23 hours, within the provider's 24-hour idempotency retention. After that it
is marked `uncertain`; reconcile it with Resend before any manual resend.
The hourly job closes old pending outboxes before checking its delivery window,
including accounts that have since opted out. Unattempted old digests expire.
Unsubscribe GET shows confirmation, POST disables email without removing
follows, and List-Unsubscribe supports one-click POST. Signed webhooks verify
the raw payload and reject timestamps outside five minutes. Bounce/complaint
suppression is address-wide and idempotent.

Code: `backend/services/research_follow_service.py` (follows and feed),
`backend/services/research_topic_service.py` (topics, Jev judging, backfill),
`backend/services/research_delivery_service.py` (digest selection, outbox,
Resend), and `backend/routers/research.py` (API and
`POST /api/v1/research/resend-webhook`).

## Public topics

A topic's creator (`research_topics.created_by_hf_subject`, the first account
to follow its text) decides whether it is public (`is_public`, default true for
new topics; topics that existed before public topics shipped start private).
Following a topic means following that exact text: when the creator edits
theirs, they move to another row and followers stay on the old one, which
keeps its creator. A creator-less topic goes to its next follower.

- `GET /research/topics/{id}` returns the page header: text, label, creator
  username and avatar (`https://huggingface.co/api/users/<name>/avatar?redirect=true`),
  follower count, and up to eight avatars of followers whose
  `research_subscriptions.show_as_follower` is on (default on for new
  accounts, off for accounts that existed before the change). Private topics
  return 404 unless the viewer created or follows them.
- `GET /research/topics/{id}/papers?order=trending|newest&start_date=&end_date=` lists the topic's
  matches (verdicts at the threshold, or the embedding preview while the
  backfill runs), all time unless `start_date`/`end_date` bound it; the topic page asks for the last month by default, like the homepage date filter.
- `POST /me/topics/{id}/follow` follows a topic by id within the ten-topic
  limit; `PATCH /me/topics/{id}` with `{"is_public": …}` is creator-only;
  `PUT /me/topic-follower-visibility` sets the avatar switch.
- `GET /research/topics/featured` feeds the homepage bubbles: public, not
  hidden, backfill done, at least five matched papers published in the last
  30 days, ordered by followers then recent matches, top eight, cached ten
  minutes.

The SPA page is `/topics/<id>-<slug>` (only the id is read). It is `noindex`
until a public topic has three followers, and whenever an admin hides it.
Moderation hides a topic from the bubbles and search engines without touching
its followers:
`uv run --env-file backend/keys.env python -m backend.scripts.moderate_research_topics list|hide <id>|unhide <id>`.

## Operations

Schema: `backend/database/migrations/add_research_follows.sql` (production:
shared catalog event triggers plus private tables; rerunnable and additive) and
`add_research_follows_staging.sql` (staging private state only, no event
triggers), then `add_research_topics.sql` (topics, verdicts, and the
subscription topic columns, with staging copies). Production and staging interests and preferences stay separate, and
delivery is always disabled in staging.

Production sends through `send_research_digests` (`pwc-cron`). The hourly
`pwc-cron-send-research-digests.timer` sends the Monday 08:00 UTC digest and
retries for the next 23 hours; other executions are no-ops. Never run the source
script as a production job.

Delivery requires `PWC_RESEARCH_EMAIL_ENABLED=true` plus `PWC_RESEND_API_KEY`,
`PWC_RESEND_FROM`, `PWC_RESEND_DOMAIN_VERIFIED=true`,
`PWC_RESEND_WEBHOOK_SECRET`, and `PWC_RESEND_WEBHOOKS_READY=true` in the
protected production backend and production-CRON environment files, never in
source control. The Resend webhook is registered for `email.bounced`,
`email.complained`, and `email.suppressed`.

Review an email without writing the outbox:

```bash
sudo pwc-cron send_research_digests --preview <hf-username> [--html]
sudo pwc-cron send_research_digests --test-to <hf-username>
```

`--preview` renders the past week's Following-feed matches for that account.
`--test-to` sends one `[Test]` digest, only to that account's own opted-in,
unsuppressed address, and requires every delivery gate. Real digests still
contain only updates discovered after each follow and opt-in.
