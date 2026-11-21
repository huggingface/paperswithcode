# ADR 0013: X and social posting

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Archive search end time is clamped to one minute ago

The X full-archive search rejects end times later than ten seconds before the request. archive_window clamps the end of the search window to one minute before now so backfills of recent papers do not fail.

Code: `backend/services/x_thread_discovery_service.py::archive_window`

## Boards led at 97 or above are saturated for X posts

On a 0-100 higher-is-better metric, a leader scoring 97 or more leaves no headroom for a SOTA story, so such boards are not offered as X candidates.

Code: `backend/services/x_post_candidates.py::SATURATED_AT`

## Boards under 8 entries need a frontier model to be postable

Tiny leaderboards without a frontier LLM are usually stale splits, while small new frontier boards (OfficeQA Pro, SLE) posted well. Boards with fewer than 8 entries are postable only if a GPT, Claude, Gemini or Grok model is on them. The bar is kept low because vision, speech and robotics boards never list a frontier LLM (a 20-row bar hid the pi^4 Sintel SOTA on 2026-11-19), and the agent remembers rejections so a weak small board costs only one look.

Code: `backend/services/x_post_candidates.py::SMALL_BOARD`

## Failed thread reviews discard matches and retry next run

If reviewing candidate X posts fails, all matches for that paper are dropped because unreviewed matches are never linked. Like a failed search, the scan is not recorded, so the paper is retried on the next run instead of consuming one of its limited scans.

Code: `backend/services/x_thread_discovery_service.py::discover_x_threads`

## Full-archive X searches are spaced 1.1 seconds apart

X full-archive search allows one request per second per app. Requests are spaced 1.1 seconds apart to stay under the limit with margin.

Code: `backend/services/x_thread_discovery_service.py::ARCHIVE_REQUEST_INTERVAL`

## Luna is told to aim 30 characters under the X limit

GPT-6 Luna miscounts characters when writing posts, so the target length given to it is LUNA_MARGIN (30) characters below the real post limit, leaving room for its counting errors.

Code: `backend/services/x_trending_post_service.py::LUNA_MARGIN`

## New-SOTA X posts feature open models only

The Papers with Code X account posts state-of-the-art results only for open models. New-SOTA wins by closed models are skipped when building candidates; closed results appear only as the beaten baseline in open_sota posts.

Code: `backend/services/x_post_candidates.py::leaderboard_wins`

## Notable lab X handles are verified business or blue accounts

NOTABLE_X_HANDLES maps organization slugs to official X accounts; each handle was looked up on the X API (2026-11-05) and accepted only if it is a business or blue-verified account named after the organization. Organizations mapped to None take their handle from organization_x_handle instead.

Code: `backend/services/x_trending_post_service.py::NOTABLE_X_HANDLES`

## Organization names under three characters never match X accounts

Organizations whose normalized name is shorter than three characters (such as 'AI') are skipped when matching X accounts, because they would match unrelated business accounts.

Code: `backend/services/x_thread_discovery_service.py::organization_matches`

## Paper pages strip every static social tag before injecting per-paper tags

frontend/index.html ships site-wide description, Open Graph and Twitter tags. When injecting paper-specific meta, the server removes every one listed in _STATIC_META_NAMES so crawlers never see a generic tag ahead of or alongside the per-paper one; adding a static tag to index.html requires adding it to this list.

Code: `backend/services/social_meta_service.py::_STATIC_META_NAMES`

## Paper pages strip the site-wide og-image entirely

When injecting per-paper meta into the SPA shell, the generic site-wide og-image.png and other generic social tags are removed rather than left alongside the paper tags. X would otherwise cache the generic image ahead of the per-paper thumbnail, and duplicate tags give crawlers conflicting values.

Code: `backend/tests/paper/test_social_meta.py::test_inject_paper_meta_strips_all_generic_static_tags`

## Paper render failures catch PyMuPDF's mixed exception types

PyMuPDF signals unreadable PDFs with FileDataError, plain RuntimeError, or low-level FzErrorBase, and page-less PDFs raise IndexError. RENDER_ERRORS lists these plus httpx and ValueError so a bad PDF skips the image instead of failing the post.

Code: `backend/services/x_trending_post_service.py::RENDER_ERRORS`

## Paper social tags always declare og:image type and size

Injected paper meta tags include og:image:type, og:image:width and og:image:height for both the local JPEG thumbnail and the Hugging Face preview fallback. Social platforms can then render summary_large_image cards correctly before they have scraped the image asset.

Code: `backend/tests/paper/test_social_meta.py::test_inject_paper_meta_uses_hf_preview_when_arxiv_thumbnail_disk_misses`

## Saturated legacy benchmarks never become X SOTA candidates

Legacy benchmarks such as MMLU, HellaSwag, GSM8K, HumanEval and BBH are saturated and never make a story; the agent rejected them about 40 times in one day (2026-11-17), crowding the SOTA list. By owner decision they are excluded by name from SOTA candidates.

Code: `backend/services/x_post_candidates.py::LEGACY_BOARD`

## Top-papers insight posts skip the LLM rewrite

Insight posts are normally rewritten by the chat model from a template, but top-papers posts are lists that read best as generated. write_with_luna returns their template text unchanged instead of risking a rewrite that reorders or drops entries.

Code: `backend/services/x_insight_post_service.py::write_with_luna`

## Trending-paper candidates are sized to fill the X queue

The X queue holds 20 posts and, on days without SOTA results, fills with trending papers in homepage order. Queued but unposted drafts still count against the limit, so the builder offers 24 trending papers to keep the queue full.

Code: `backend/services/x_post_candidates.py::TRENDING_PAPER_LIMIT`

## Trending-paper candidates mirror the homepage trending window

Trending-paper X candidates must match what visitors see on the homepage trending tab (FeedView), which by default ranks papers published today and the six previous days in UTC. The candidate builder uses the same window so posted papers correspond to the homepage order.

Code: `backend/services/x_post_candidates.py::trending_papers`

## Unavailable X posts are detected from per-id API errors

The X tweets lookup API returns deleted, protected or suspended posts as per-id entries in errors rather than failing the request. The reader collects those resource ids as unavailable so they can be distinguished from posts whose like count simply was not returned.

Code: `backend/services/x_post_likes_service.py::read`

## X SOTA candidates use a 7-day window and limit of 20

The X growth agent checks every SOTA board live and rejects saturated ones. With the 3-day window used by x_insight_post_service it was left with about two candidates at a time, so the candidate builder offers up to 20 SOTA results from the last 7 days.

Code: `backend/services/x_post_candidates.py::SOTA_LIMIT`

## X author matching also checks real names in the handle

X users often display a nickname (for example 'Aaron Huang' for author Wei Huang) while keeping their real name in the handle (@AaronWeiHuang). Author matching therefore also accepts a handle containing the joined first and last name (at least six characters).

Code: `backend/services/x_thread_discovery_service.py::author_matches`

## X avatars use the _bigger size variant

X avatar URLs ending in _normal are 48 px and blur on high-density screens. Previews rewrite them to the _bigger variant.

Code: `backend/services/x_thread_service.py::preview_from_syndication`

## X like velocity uses the GitHub star EMA smoothing

The X like velocity EMA uses ALPHA = 0.75, the same smoothing as the GitHub star velocity EMA, so the two velocity signals are comparable when combined in trending.

Code: `backend/services/x_post_likes_service.py::ALPHA`

## X post previews expand t.co links within the display range

X syndication payloads contain t.co shortlinks and a display_text_range. Previews keep only the visible range and replace each shortlink with its expanded URL; media links fall outside the range and are rendered from mediaDetails instead of as text.

Code: `backend/services/x_thread_service.py::_display_text`

## X posts never feature Artificial Analysis boards

Artificial Analysis is a competing eval indexer, so the Papers with Code X account never posts about its boards: its indexes and arena, benchmarks suffixed -AA, and CritPt, which it hosts. Such boards are filtered out by name before candidates are offered.

Code: `backend/services/x_post_candidates.py::COMPETITOR_BOARD`

## X thread discovery fails only when every search fails

The X thread discovery job logs per-paper search errors but exits 0 when some searches succeed. It exits 1 only when the number of errors equals the number of papers scanned, because that pattern means the job is blind (bad token or exhausted quota) rather than hitting isolated failures. This keeps CRON health red for credential problems without flapping on transient per-paper errors.

Code: `backend/scripts/discover_x_threads.py::main`

## X thread discovery stops on 401, 403 or 429

When X search or review returns 401, 403 or 429, discovery stops the whole run instead of moving to the next paper, because every later request would fail with the same credentials or quota. Other HTTP errors skip only the current paper.

Code: `backend/services/x_thread_discovery_service.py::discover_x_threads`

## X thread search queries include project page paths

Project page URLs are searched with host and path, not host alone. A single host such as a lab's github.io site often serves many projects, so a bare-host query would match posts about unrelated papers.

Code: `backend/services/x_thread_discovery_service.py::build_query`

## X thread snapshots are restored with missing fields left unset

Paper X thread rows are rebuilt from stored snapshots that may predate newer columns in X_THREAD_FIELDS. Restoration reads each field with row.get so absent fields become NULL instead of raising. Switching to strict key access would break restoring or reverting older snapshots.

Code: `backend/services/paper_association_service.py::PaperAssociationService.replace_x_threads`

## X thread video previews cap bitrate at 1 Mbps

Inline X video previews are sidebar-sized, so a 360p (~0.8 Mbps) MP4 is sharp enough. The preview picks the best MP4 at or below 1 Mbps, falling back to the smallest, to save bandwidth.

Code: `backend/services/x_thread_service.py::_MAX_PREVIEW_VIDEO_BITRATE`
