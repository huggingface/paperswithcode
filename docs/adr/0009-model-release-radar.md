# ADR 0009: Model release radar and resolution

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Announcing-paper candidates must report results or a release

Title matching for a model's announcing paper only considers papers that have evaluations or a recorded ModelRelease. Titles that merely contain the model tokens, such as 'KNN and ANN-based ...' or 'GPT-4o: ... in piglets', are excluded.

Code: `backend/services/model_release_identity_service.py::announcing_paper_id`

## Announcing-paper lookup gives up past the candidate limit

At most TITLE_CANDIDATE_LIMIT matching papers are fetched per model name. If more exist, a second announcement cannot be ruled out, so the lookup returns no paper instead of picking one of an ambiguous set.

Code: `backend/services/model_release_identity_service.py::announcing_paper_id`

## Article recency uses the visible publication date

Lab CMS metadata can retain a draft's date: Mistral's Timestral post had datePublished 2026-07-15 but displayed October 15, 2026. The radar therefore reads the date readers see on the page ("Month D, YYYY") ahead of structured metadata when judging recency.

Code: `backend/services/model_release_radar_service.py::_VISIBLE_DATE`

## Domain-name matches allow only corporate suffixes

A Hub or GitHub account name matches an organization when it starts with the organization name and appends anything ('RecursiveSI'). A domain may only append a corporate suffix ('mistralai'), so lookalike domains such as kimiupdates.com are not treated as the lab's own.

Code: `backend/services/model_release_signal_service.py::_names_match`

## Failed release resolutions are retried after two days

A failed resolution job is retried when the release is seen again at least two days after the failure. This keeps a transient Job failure from permanently dropping a release while avoiding immediate retry loops.

Code: `backend/services/model_release_signal_service.py::FAILED_RETRY_AFTER`

## Hub repository pages alone do not qualify as a release paper

Repository pages on huggingface.co, hf.co and modelscope.cn (model cards) are not accepted on their own as the paper for a release signal; Hub blog articles are the exception because they are written announcements. Resolution must find a real announcement or report.

Code: `backend/services/model_release_signal_service.py::_HUB_HOSTS`

## Known model families override vendor prefixes for the radar lab

When a leaderboard label starts with a vendor word (for example 'Google Gemini ...'), the canonical lab of a known model family wins over the vendor prefix. This makes the vendor-prefixed label and a bare 'Gemini ...' from another board produce one release-radar signal instead of two.

Code: `backend/services/leaderboard_model_matching_service.py::vendor_label_model`

## Later announced names must be versioned

In launch headlines, later list members count as announced models only if they contain a digit. This keeps versioned models ('Claude Mythos 5.2') while excluding products launched alongside them ('Claude 3.7 Sonnet and Claude Code').

Code: `backend/services/model_release_identity_service.py::_announced_names`

## Model releases keep their identity when an arXiv report appears

A model card can gain an arXiv technical report after its external release page was already curated. Resolution updates the existing ModelRelease row, moving its canonical paper pointer to the arXiv paper and merging aliases, instead of creating a second release.

Code: `backend/services/trending_model_resolution_service.py::TrendingModelResolutionService.apply`

## News-only release signals need two sightings

Web-search extraction of model releases is nondeterministic, so a signal seen only through web search must reappear in a later run before it spends a curation job. Vendor feeds are first-party and qualify on their first sighting.

Code: `backend/services/model_release_signal_service.py::WEB_SEARCH_MIN_SIGHTINGS`

## Only launch headlines announce every listed model

A paper title like 'Comparing GPT-6 Sol and Claude Opus 5.5' mentions models without announcing them. Only titles led by a launch verb (introducing, announcing, meet) announce the later members of an 'X and Y' list; other titles contribute only their leading name, preventing comparison papers from being attributed as model releases.

Code: `backend/services/model_release_identity_service.py::_announced_names`

## Publisher identity from hostnames ignores public TLDs

When deriving the publishing organization from a hostname, public TLDs such as .pro or .news are ignored, while single-company brand TLDs like blog.google count. Adjacent labels are also joined so short names such as x.ai yield xai.

Code: `backend/services/model_release_signal_service.py::_host_tokens`

## Radar feed sources require production reachability and machine-readable dates

RELEASE_SOURCES lists only lab feeds (RSS or sitemaps) that the production host can fetch and that expose machine-readable dates. Labs whose sites block the host or lack such dates are deliberately left out and covered by the web news search instead.

Code: `backend/services/model_release_radar_service.py::RELEASE_SOURCES`

## Radar runs several differently phrased news queries

The Exa news search ranks results by similarity to the query text, so one phrasing surfaces only articles worded like it. The radar issues several varied queries (LLM announcements, frontier models, open weights, multimodal foundation models) to cover different announcement styles.

Code: `backend/services/model_release_radar_service.py::WEB_SEARCH_QUERIES`

## Radar web news search looks back only three days

The model release radar runs every three hours and requests a fixed number of web news results per query. A long lookback window fills that budget with coverage of a single big launch and crowds out smaller releases, so the news search covers only the last three days.

Code: `backend/services/model_release_radar_service.py::WEB_SEARCH_LOOKBACK_DAYS`

## Release lead source stores a feed URL or the literal web-search

Model release radar leads persist their origin in the source column as either the vendor feed URL that produced them or the sentinel string "web-search" for leads found by the web search provider. Code distinguishing vendor-feed leads from search leads depends on this value contract.

Code: `backend/models/database/curation.py::ModelReleaseSignal.source`

## Release radar copies signal fields before the session closes

queue_release_signals commits, and SQLAlchemy expires ORM rows on commit; the session is then closed before the queued signals are logged. The scan script therefore copies lab, model name and lead URL into plain dicts immediately after queueing. Logging the ORM rows later would raise DetachedInstanceError or trigger lazy reloads on a closed session.

Code: `backend/scripts/scan_model_releases.py::main`

## Release radar dispatches at most 30 resolve jobs a day

Leaderboard syncs report every unmatched model, so the radar backlog can reach hundreds. The curation runner handles about 150 or more jobs a day and resolve jobs mostly succeed, so capping radar at 30 per day leaves room for other curation while clearing a backlog in about a week.

Code: `backend/services/model_release_signal_service.py::MAX_RADAR_JOBS_PER_DAY`

## Release radar fails only when every source fails

Individual source errors in the model release radar are logged as warnings and the scan still exits 0. The script exits 1 only when the number of errors equals the number of sources checked, because then the radar is blind and an empty result would be mistaken for 'nothing shipped'. This keeps one flaky lab page from marking the CRON broken while still surfacing a total outage.

Code: `backend/scripts/scan_model_releases.py::main`

## Release signal leads upgrade to official and first-party sources

When a release is sighted again, its lead URL is replaced if the new sighting is the lab's own page and the current lead is not, or if the current lead came from web search and the new one from a vendor feed. The lab's own page is a better curation lead than a news article.

Code: `backend/services/model_release_signal_service.py::record_release_signals`

## Release version guard judges each family by its most specific version

A trending model can carry several names for one family, such as a coarse alias 'Nanbeige4' and the release's own '4.3'. The version-conflict guard keeps only the most specific version per family, so the coarse alias cannot make a paper about the right point release look like a version mismatch.

Code: `backend/services/trending_model_resolution_service.py::release_version_conflict`

## Resolved trending models skip generic external-paper curation

When a trending model is resolved to a new external paper, ingestion is called with queue_curation=False because the resolved candidate starts its own curation workflow pinned to the model card. Queuing the generic workflow too would curate the same paper twice.

Code: `backend/services/trending_model_resolution_service.py::TrendingModelResolutionService._resolve_paper`

## Sitemap lastmod only excludes old pages

Rebuilt sitemaps refresh `<lastmod>` on old pages, so a recent lastmod does not prove a page is new. The radar uses lastmod (or a slug date) only to discard pages older than the cutoff, then fetches the newest candidates and decides recency from the article's own publication date.

Code: `backend/services/model_release_radar_service.py::_collect_sitemap_articles`

## Undated release signals sort by first-seen date

Leaderboard-derived signals carry no publication date. The dispatch order falls back to the first-seen date; ordering by published alone would sort them after every dated signal so they would never run under the daily cap.

Code: `backend/services/model_release_signal_service.py::queue_release_signals`
