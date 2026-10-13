# Research follows and weekly email

Follows are private and keyed by the immutable Hugging Face OAuth subject.
The Following feed lives at `/following`; `/settings` manages interests and
explicit weekly-email opt-in. OAuth email access uses the existing
`collect_email=true` flow and accepts only a verified identity email. No
browser-supplied destination is accepted.

The feed shows papers with known publication dates from today through 30 days
ago (UTC), includes task descendants, and combines associations across arXiv
versions. It displays the latest version but excludes a paper if any version
was published before the cutoff. Direct matches weigh two; inherited task
matches weigh one. Distinct matching interests add strength. Each interest
ranks by strength, publication date, popularity, then canonical ID; round-robin
selection balances coverage and counts each paper once. Up to 100 interests
may be followed. Feed pages contain 40 entries.

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
Unsubscribe GET shows confirmation, POST disables email without removing
follows, and List-Unsubscribe supports one-click POST. Signed webhooks verify
the raw payload and reject timestamps outside five minutes. Bounce/complaint
suppression is address-wide and idempotent.

## Staging preview

Apply `backend/database/migrations/add_research_follows_staging.sql` as the
schema owner before deploying the reviewed feature commit. It changes only
staging private state. Do not install production event triggers or the digest
timer for the preview. Delivery is always disabled in staging. Production and
staging interests and preferences remain separate.

## Production activation (after staging review)

Apply `backend/database/migrations/add_research_follows.sql` as the database
owner before deploying the merged release. This additive migration installs
shared catalog event capture and isolated private tables. It can be rerun.
An application rollback can leave these additive tables/triggers installed.

Register `send_research_digests` through the installed `pwc-cron` launcher and
its generated systemd units when rolling out production. The hourly timer
sends the Monday 08:00 digest and provides retries for the next 23 hours; all
other executions are no-ops. Never run the source script as a production job.

Keep `PWC_RESEARCH_EMAIL_ENABLED=false` until a Resend account, credentials,
verified sender domain, and tested delivery webhooks are ready. Configure
these in the protected production/backend and production-CRON environment
files, never in source control:

- `PWC_RESEND_API_KEY`
- `PWC_RESEND_FROM`
- `PWC_RESEND_DOMAIN_VERIFIED=true`
- `PWC_RESEND_WEBHOOK_SECRET`
- `PWC_RESEND_WEBHOOKS_READY=true`

Register `https://paperswithcode.co/api/v1/research/resend-webhook` for
`email.bounced`, `email.complained`, and `email.suppressed`. Only after provider
setup and authorized qualification should the delivery flag be enabled.
No credentials, domain activation, or outbound tests are part of this rollout.
