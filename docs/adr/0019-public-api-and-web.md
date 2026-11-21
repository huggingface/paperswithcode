# ADR 0019: Public API, web shell and auth

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## Author photos are served immutable because URLs carry the digest

Author photo URLs embed the digest of the image bytes, so a given URL always maps to the same content. The endpoint therefore sends one-year immutable Cache-Control and CDN-Cache-Control headers; changing a photo must change its URL, never its bytes under the old URL.

Code: `backend/routers/authors.py::get_author_photo`

## Benchmark result page titles fit search-engine title limits

Benchmark results pages rank for '<model> benchmarks' queries. Their titles cap the model name at 40 characters and the whole title at 75 so the name and benchmark list stay within what search engines display before the ' | Papers with Code' suffix.

Code: `backend/services/paper_seo_service.py`

## CSP report endpoint is exempt from CSRF origin checks

Browsers send CSP violation reports as POSTs without an Origin header and sometimes with cookies attached, so the cookie-based CSRF check would reject them. /api/v1/csp-reports is exempt because it only appends the report to a log and never reads the session; any new behaviour on that endpoint that touches session state would invalidate the exemption.

Code: `backend/utils/csrf.py::CSRF_EXEMPT_PATHS`

## CSP report log keeps one rotated predecessor

When the CSP report log exceeds its size cap it is moved to a single .1 file and a fresh log is started, rather than refusing further writes. A report flood therefore shortens retained history instead of hiding every later report, while disk use stays bounded.

Code: `backend/services/csp_report_service.py::append_csp_reports`

## CSP report log writes are serialized with a file lock

Backend workers are separate processes that all append to the same CSP report log. The size check, rotation and append are performed under an exclusive fcntl lock on a sidecar lock file so concurrent workers cannot interleave or rotate under each other.

Code: `backend/services/csp_report_service.py::append_csp_reports`

## Crossref title matches resolve to the earliest publication

Reprints and proceedings copies share a title in Crossref. When several works match the wanted title exactly, the lookup picks the one with the earliest issue date as the original publication.

Code: `backend/services/public_paper_metadata_service.py::PublicPaperSources._crossref_title_search`

## Crossref undated works use [[null]] date-parts

Crossref returns issued.date-parts as [[null]] for works without an issue date. _from_crossref skips null parts so such works get a None published date instead of crashing on int(None).

Code: `backend/services/public_paper_metadata_service.py::_from_crossref`

## Dataset list fields tolerate malformed legacy JSONB

Legacy PwC imports stored JSON null and, for a few datasets, objects in the languages and variants JSONB columns. The Dataset API model coerces any non-list value to None and drops null items rather than validating strictly. Tightening this validator would make a single malformed row fail the whole dataset listing.

Code: `backend/models/evaluations.py::Dataset.coerce_optional_string_list`

## Entity image responses are cached for a week, misses for an hour

Entity images are curated and effectively immutable per slug, so successful responses send public, max-age and s-maxage of 604800 (one week) for browser and CDN caching, matching the thumbnail router. A 404 for a missing image is cached for one hour so clients do not hammer the endpoint but still pick up a newly added image soon.

Code: `backend/utils/entity_images.py::IMAGE_CACHE_HEADERS`, `backend/utils/entity_images.py::IMAGE_MISSING_HEADERS`

## Expired auth sessions are retained for one day

Expired AuthSession rows are not deleted immediately; EXPIRED_ROW_RETENTION keeps them for one day and later logins purge older rows. This lets a just-expired cookie be reported as expired rather than unknown in logs, which distinguishes routine expiry from forged or revoked cookies. Purging at expiry would lose that diagnostic signal.

Code: `backend/services/auth_session_service.py`

## Literal sub-paths are declared before parameterised routes

FastAPI matches routes in declaration order, so a literal path such as /me/topics/order or /research/topics/featured must be declared before /me/topics/{topic_id} or /research/topics/{topic_id}; otherwise the literal segment is parsed as an id.

Code: `backend/routers/research.py::reorder_topics`, `backend/routers/research.py::featured_topics`

## MCP reads the catalog through a loopback-only nginx bridge

In both production and staging, the MCP service reads the PwC catalog through a dedicated nginx server block that listens only on 127.0.0.1. Its traffic never leaves the host and does not share the public per-IP rate limits, which would otherwise throttle all MCP users as a single client.

Code: `backend/tests/mcp/test_nginx_contract.py::test_internal_mcp_api_bridge_is_loopback_only`

## MCP reads the catalog through nginx's loopback bridge

The MCP server's production and staging API URLs point at nginx's loopback bridge (127.0.0.1:8010/8011), never the public https edge. Calls from MCP would otherwise all appear from one IP and consume the per-IP catalog rate limits.

Code: `backend/tests/mcp/test_deployment.py::test_mcp_paths_are_separate_from_site_releases`

## Name lookups require a unique match within one result page

Public metadata lookup by paper name searches arXiv for up to NAME_SEARCH_RESULTS (50) titles. If the page is full, later pages could hold another paper with the same name, so the lookup returns nothing rather than guessing; it also requires exactly one exact name match within the page.

Code: `backend/services/public_paper_metadata_service.py::NAME_SEARCH_RESULTS`, `backend/services/public_paper_metadata_service.py::PublicPaperSources.by_title`

## OAuth state cookie is host-only on the callback path

The OAuth state cookie is set without a Domain attribute and scoped to the callback path. Both the login handler that sets it and the callback that reads it live on the redirect URI's origin, because staging forwards logins to the auth authority before the cookie is set. Widening it to the shared session domain is unnecessary and would leak the nonce to sibling hosts.

Code: `backend/routers/auth.py::_set_oauth_state_cookie`

## OAuth state is bound to the initiating browser by a cookie

The HF OAuth state nonce is also stored in a pwc_oauth_state cookie and checked at the callback. This binds the state to the browser that started the login and prevents login CSRF, where an attacker completes a login into their own account in the victim's browser. Removing the cookie check would leave the state parameter alone, which does not protect against this attack.

Code: `backend/routers/auth.py::OAUTH_STATE_COOKIE_NAME`

## On-demand page scraping requires a signed-in reader

Scraping an external web page to Markdown spends the server's Firecrawl credits. When no Markdown exists, only a reader with a session triggers on-demand scraping; anonymous readers get a 503 'still being prepared' and rely on the Markdown backfill job, which prepares pages for everyone.

Code: `backend/routers/paper_reader.py`

## Only exactly listed origins get credentialed CORS

The public read CORS middleware credentials only origins listed exactly in allowed_origins. Origins admitted by PWC_EXTRA_ALLOWED_ORIGIN_REGEX (any Hugging Face Space) read the public catalog anonymously like every other origin, because anyone can create a Space and must not be able to make credentialed requests on a user's behalf.

Code: `backend/routers/public_api.py::PublicReadCorsMiddleware.__init__`

## Open-model leader uses the overall leader's metric

In a task page's Best models table the best open model for each benchmark is selected using the same metric as the overall leader. Ranking open models by an open-only primary metric could pick a winner from a different leaderboard or metric and present it as the open leader of this one.

Code: `backend/services/discovery_page_service.py::DiscoveryPageService._task_top_models`

## Paper 404 adds a code field beside the string detail

GET /papers/{id} returns 404 with the unchanged string "detail" plus code "paper_not_in_catalog" so existing clients that read detail as a string keep working while new clients can detect unindexed papers and fall back to /public-metadata. Changing detail to an object would break the public API contract.

Code: `backend/routers/papers.py::get_paper_by_id`

## Paper card serialization keeps every frontend Paper field

FRONTEND_PAPER_FIELDS lists the fields declared by the frontend's public Paper interface and read by feed cards, previews, paper detail, saved papers and chat. A test pins the serialized paper to include them so backend cleanups cannot silently drop a field the public API contract depends on.

Code: `backend/tests/paper/test_cleanup_characterization.py::FRONTEND_PAPER_FIELDS`

## Paper cards link only the authors they display

Paper card relations include author links only for the first CARD_AUTHOR_LINKS (3) authors, matching the three names the frontend PaperCard shows. This keeps long author lists out of feed and list payloads; detail endpoints request the full list. Changing how many names PaperCard displays requires changing the constant.

Code: `backend/services/paper_relation_loader.py::CARD_AUTHOR_LINKS`, `backend/services/paper_relation_loader.py::PaperRelationLoader._load_card_relations`

## Paper detail suggested_questions is always a list

Paper detail responses always carry suggested_questions as a list. An empty list is a signal to the frontend to generate questions on demand, so the backend must not return null or omit the field.

Code: `backend/tests/paper/test_cleanup_characterization.py::test_card_relations_link_displayed_authors_and_exclude_detail_projection`

## Paper sitemap shards are rendered fully before responding

Paper sitemap shards are rendered into a complete body with a Content-Length before the response starts. A streamed, chunked response would hold a database connection open for the whole download by slow crawlers, exhausting the pool on the VPS.

Code: `backend/tests/test_sitemaps.py::test_paper_shard_is_rendered_before_the_response_starts`

## Paper-scoped credentials never fall back to broader identities

When a request presents paper-scoped Bearer credentials, authorization uses only those credentials. If they are invalid the request is rejected; it never falls back to a session cookie or admin identity that happens to accompany the request, so a narrow credential cannot be escalated or confused with a broader one.

Code: `backend/utils/auth.py::_require_mutator`

## Partial route matches stop public CORS lookup

Starlette returns 405 Method Not Allowed for a partial (path-only) match before it considers slash redirects. _is_public_route therefore returns False rather than None on a partial match, so the middleware does not try the redirect variant for a request Starlette will answer with 405.

Code: `backend/routers/public_api.py::PublicReadCorsMiddleware._is_public_route`

## Post-login redirects accept only plain single-slash paths

Browsers treat '//host', '/\\host' and paths whose control characters get stripped (for example '/\t/host') as another origin. The login return-to sanitizer therefore rejects any value whose second character is a slash or backslash or that contains control characters, falling back to '/'. A looser startswith('/') check would allow open redirects.

Code: `backend/routers/auth.py::_safe_redirect_target`

## Public CORS follows slash redirects only when no route matched

When deciding whether a request targets a public route, the middleware tries the router's slash-redirect variant only if no actual route matched. A real private route must never inherit open CORS from a public neighbour whose path differs only by a trailing slash.

Code: `backend/routers/public_api.py::PublicReadCorsMiddleware.__call__`

## Public CORS responses always vary on Origin

Public catalog responses differ for absent, anonymous and credentialed origins, so the middleware always adds Vary: Origin. Without it a shared cache (Cloudflare, browsers) could serve a credentialed origin's headers to another origin or vice versa.

Code: `backend/routers/public_api.py::PublicReadCorsMiddleware.__call__`

## Public schema requires mode=keyword instead of a default

The public OpenAPI projection restricts search mode to keyword and marks it required rather than declaring a default, because the underlying endpoint's default mode differs (it follows paper_search_mode). Declaring default keyword would misdocument what an omitted mode actually does.

Code: `backend/services/public_api_schema.py::public_openapi`

## Rendered discovery links reject any URL containing a backslash

Browsers normalise '/\\host' to '//host', turning an apparently local path into a protocol-relative link to another origin. The discovery text renderer therefore refuses any href containing a backslash before checking for local or http(s) URLs. Dropping the check would let crafted Markdown inject off-site links.

Code: `backend/services/discovery_text_service.py::_safe_href`

## Repair URL schemes collapsed by proxies in path identifiers

The public metadata endpoint accepts arXiv/DOI URLs embedded in the path. Proxies merge the double slash, turning https:// into https:/, so parse_reference restores the scheme before classifying the identifier.

Code: `backend/services/public_paper_metadata_service.py::parse_reference`

## Reserved conference listing slugs

Paths /conferences/{slug}/{listing} with listing in all, oral, spotlight, outstanding or best-paper-finalists are presentation and award listings rendered by ConferenceTaskView, not task filters. These slugs are reserved: they are checked before task slugs, so a task with one of those slugs cannot be filtered on a conference page.

Code: `backend/services/discovery_page_service.py::CONFERENCE_LISTINGS`

## Route preload links follow the requested path, falling back to canonical

Server-rendered discovery pages preload the route chunks for the path actually requested, because nested pages such as /conferences/:slug/:task share their parent's canonical URL but render a different SPA view. Legacy aliases such as /sota/... or top-level /{slug} have no route entry of their own, so preloading falls back to the canonical path's route.

Code: `backend/services/discovery_html_service.py::render_discovery_shell`

## SPA shell uses no-cache, not no-store

The SPA index shell is identical for every visitor and must reflect a deploy immediately. It is served with Cache-Control no-cache, which forces revalidation on each load, rather than no-store, which would also disqualify the page from the browser back/forward cache and slow navigation.

Code: `backend/routers/discovery_pages.py::_spa_document`

## Sitemap shards are rendered fully before responding

Sitemap shards used to be streamed, which kept a pooled database connection and server-side cursor open for as long as a crawler took to download, and the request-scoped session could close under the cursor ("named cursor isn't valid anymore"). Shards of lightweight rows are only a few megabytes of XML, so the whole document is built in the request, the connection released, and then the response sent. Do not reintroduce a StreamingResponse backed by a live cursor.

Code: `backend/routers/sitemaps.py::_xml_response`

## Sitemaps load only narrow paper columns

Sitemap and archive shards cover up to 50,000 papers each. Loading whole Paper rows pulled the abstract and full-text search vector for every paper and grew a production web worker past 1 GB while crawlers walked the shards, so these queries select only SITEMAP_PAPER_COLUMNS.

Code: `backend/services/sitemap_service.py::SITEMAP_PAPER_COLUMNS`

## Slashless aliases are public only if they share the endpoint

A route whose path lacks the trailing slash of a public route is treated as public only when it resolves to the same endpoint function as the canonical public path. Merely resembling a public URL is not enough, so a private route registered at a near-identical path does not get open CORS.

Code: `backend/routers/public_api.py::PublicReadCorsMiddleware._is_public_route`

## Static browse pages must be registered for SEO metadata

Top-level browse pages with fixed copy (for example /ai-deadlines) get their title, heading, description and canonical tag from STATIC_INDEX_PAGES. A new top-level SPA page that is not registered there is served with the generic SPA shell title and no canonical tag, so new browse pages must be added to the map.

Code: `backend/services/discovery_page_service.py::STATIC_INDEX_PAGES`

## arXiv is authoritative for arXiv ID lookups

Lookups by arXiv ID try the Hugging Face papers API first, then arXiv's abstract page, then the export API if the abstract page failed transiently. A Hugging Face failure alone does not mark the lookup unavailable, because arXiv is the authoritative source for arXiv IDs.

Code: `backend/services/public_paper_metadata_service.py::PublicPaperSources.by_arxiv_id`
