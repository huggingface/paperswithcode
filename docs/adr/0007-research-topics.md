# ADR 0007: Research topics, follows and digests

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## A new follower restarts a failed topic backfill

When an account follows a topic whose backfill exhausted its retries (status failed), the backfill status is reset to pending with zero attempts, giving the topic a fresh start instead of leaving it permanently empty.

Code: `backend/services/research_topic_service.py::_add_follow`

## Admin-hidden topics stay followable

Setting research_topics.hidden_at is an admin moderation action that removes a public topic from the homepage, public topic listings and search-engine indexing, but does not delete it or stop accounts from following it, so existing followers keep their digests.

Code: `backend/models/database/research.py::ResearchTopic.hidden_at`

## Date-filtered HNSW recall uses iterative strict-order scan

pgvector's HNSW index scan returns at most hnsw.ef_search (default 40) candidates before filters are applied, so a date-filtered search for older papers can come back short. recall_older sets hnsw.ef_search = 1000 and hnsw.iterative_scan = strict_order for the transaction so the scan keeps going in exact distance order until the filtered result reaches the recall depth.

Code: `backend/services/research_topic_service.py::recall_older`

## Digest send locks the subscription row

deliver_digest selects the subscription FOR UPDATE alongside the digest, so unsubscribe and opt-out requests serialize with an in-flight send and a digest is never sent after the subscriber opted out.

Code: `backend/services/research_delivery_service.py::deliver_digest`

## Editing a topic pins the account's order

When an account edits the text of a followed topic, the replacement follow gets a fresh created_at because follow time drives digest freshness. To keep the edited topic in the same place, the account's current implicit order is first pinned as explicit positions and the new follow reuses the old position.

Code: `backend/services/research_topic_service.py::follow_topic`

## Email suppressions are address-wide

A bounce or complaint suppression from the email provider is recorded per email address and disables every research subscription using that address, including other accounts, so the address is never mailed again.

Code: `backend/services/research_delivery_service.py::record_suppression`

## Email unsubscribe requires a POST from a confirmation page

Email-link scanners prefetch GET URLs in messages. The unsubscribe link therefore serves only a confirmation page on GET, and the opt-out happens on POST, so scanners cannot unsubscribe users.

Code: `backend/routers/research.py::unsubscribe_page`

## Feed benchmark scores are read live, not from events

When rendering the feed without an event window, benchmark entries read current evaluation scores directly. Score corrections therefore show up in the feed without generating new alerts.

Code: `backend/services/research_follow_service.py::matching_entries`

## Follow mutations serialize on a per-account advisory lock

set_follow takes a transaction-scoped PostgreSQL advisory lock keyed on the account subject before mutating follows. This serializes concurrent requests for one account so the bounded follow count cannot be exceeded by racing inserts.

Code: `backend/services/research_follow_service.py::set_follow`

## Following feed matches every version and tolerates taxonomy cycles

The following-feed query matches associations on every paper version, displays the latest version and uses the earliest publication date. Task descendants use recursive UNION rather than UNION ALL so bad parent cycles terminate. A followed topic matches papers through its Jev verdicts and, while that topic's backfill_status is not done, also through its embedding preview.

Code: `backend/services/research_follow_service.py::MATCH_SQL`

## Legacy single-topic endpoints operate on the first followed topic

The /me/topic endpoints predate following several topics and are kept for compatibility. GET and PUT read and replace the account's first topic, while DELETE removes every topic the account follows.

Code: `backend/routers/research.py::topic`

## Missed research digest weeks are never backfilled

A weekly research digest is prepared only within 23 hours after its week ends. Older weeks are skipped, so enabling or re-enabling delivery never resurrects missed weeks or creates a backlog of stale emails.

Code: `backend/services/research_delivery_service.py::prepare_digest`

## New-paper counts look back seven days before the last visit

A paper added to the catalog after the user's last visit was published at most a few days earlier, so the new-paper count considers publication dates from seven days before the last visit, but never further back than the 30 days the feed covers. This bounds the query without missing late-imported papers.

Code: `backend/services/research_follow_service.py::new_paper_cutoff`

## Non-indexable public topics stay followable

A public research topic's indexable flag only controls whether it appears on the homepage and is exposed to search engines. Topics with indexable false remain reachable by link and followable, so hiding a topic is not the same as making it private.

Code: `backend/models/research.py::PublicTopicView.indexable`

## Older-paper lexical recall ORs topic words

Lexical recall of older papers for a research topic rewrites the plainto_tsquery AND query into an OR query, because a long free-text topic description rarely has every word in a single paper; dense retrieval and reciprocal rank fusion then rank the broader candidate set.

Code: `backend/services/research_topic_service.py::recall_older`

## Only a topic's first follower controls its public visibility

Research topics are shared by everyone who wrote the same normalized text. The first account to follow a topic is recorded in created_by_hf_subject and is the only account allowed to change is_public; topics created before creators were recorded hand that role to their next follower.

Code: `backend/models/database/research.py::ResearchTopic.created_by_hf_subject`, `backend/services/research_topic_service.py::_add_follow`

## Only public topics reveal their creator

Topic views name a topic's creator to other followers only when the topic is public; private topics never expose who created them.

Code: `backend/services/research_topic_service.py::topic_views`

## Organization suggestions fetch ten to fill five chips

The UI shows five organization suggestion chips and hides organizations the user already follows. Ten organizations are fetched so five remain after filtering.

Code: `backend/services/research_follow_service.py::POPULAR_ORGANIZATION_LIMIT`

## Popular author suggestions are a curated id list

Follow suggestions for authors use a fixed list of well-known researcher ids instead of a data-driven ranking. Citation-based ranks favour coauthors of a few huge papers, so there is no reliable signal for author popularity in the catalog.

Code: `backend/services/research_follow_service.py::POPULAR_AUTHOR_IDS`

## Research digest email delivery is idempotent and bounded by Resend's 24 h key retention

Each weekly research digest is sent with a deterministic Resend idempotency key derived from the subscriber and week end. first_attempt_at is committed before the first POST as a durable checkpoint; transport errors roll back and leave the immutable payload and key pending for bounded retries. Because Resend keeps idempotency keys only 24 hours, a digest whose first attempt is 23 hours old or more is marked uncertain instead of retried, so an ambiguous earlier request can never be delivered twice.

Code: `backend/services/research_delivery_service.py::deliver_digest`

## Research events are not generated from catalog backfill

Research events (alerts) are only attached within a recent discovery window. The initial catalog backfill of a new follow populates the feed only, so following an entity does not flood the user with alerts for historical papers.

Code: `backend/services/research_follow_service.py::matching_entries`

## Research topics that match a catalog task, method or benchmark are rejected

A free-text research topic named like an existing catalog task, method or benchmark would duplicate following that entity. Saving such a topic returns 409 with the matching suggestions so the user follows the catalog entity instead.

Code: `backend/routers/research.py::_save_topic`

## Sample digest covers the last seven days including today

The sample digest preview starts six days before now so that, with render_digest treating end as exclusive, it covers exactly the last seven days including today.

Code: `backend/services/research_delivery_service.py::sample_digest`

## Topic bubbles over-fetch to survive client-side filtering

The public topic bubble query returns up to 20 topics even though only about five are shown. The client hides the viewer's own and already-followed topics, so the server over-fetches to leave enough candidates. Lowering the limit to the displayed count would leave empty bubble rows for active users.

Code: `backend/services/public_topic_service.py::BUBBLE_LIMIT`

## Topic follow order: NULL position until the account reorders

research_topic_follows.position stays NULL until an account explicitly reorders its topics; lists sort by position with NULLs last and then by follow time. After a reorder every follow has a position, so a newly followed topic gets max(position)+1 and lands at the end instead of jumping ahead of the user's chosen order.

Code: `backend/models/database/research.py::ResearchTopicFollow.position`, `backend/services/research_topic_service.py::_add_follow`

## Topic preview uses a longer embedding timeout than search

Saving a research topic waits on a single query embedding to build its preview. The interactive search embedding budget was too tight and left newly saved topics with empty previews, so previews use PREVIEW_EMBEDDING_TIMEOUT_MS (5000 ms).

Code: `backend/services/research_topic_service.py::PREVIEW_EMBEDDING_TIMEOUT_MS`

## Topic saving and backfill degrade gracefully when embedding or LLM calls fail

Saving a research topic never fails because an auxiliary model call failed. If the short LLM label cannot be generated the full text is shown; if the query embedding is unavailable the preview is skipped and the feed fills in once Jev has judged the topic; if older-paper recall cannot embed the topic, backfill judges the current window now and recalls older papers on the retry. Saving the same topic again retries a missing label or preview, and transport or malformed-answer failures while judging leave the topic/paper pairs unjudged for the next run while any other exception is raised as a bug.

Code: `backend/services/research_topic_service.py::judge_papers`, `backend/services/research_topic_service.py::backfill`, `backend/services/research_topic_service.py::summarize`, `backend/services/research_topic_service.py::save_preview`, `backend/services/research_topic_service.py::follow_topic`
