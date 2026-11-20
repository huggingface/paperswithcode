# ADR 0015: Authors, profiles and organizations

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## A Scholar ID proposed for several PwC authors is held back

Two Wikidata items may carry the same Scholar ID, so only distinct PwC author ids count. When one Scholar ID is proposed for several distinct PwC authors, they are likely duplicates to merge, so every such proposal is marked shared_scholar_id instead of being applied.

Code: `backend/services/google_scholar_link_service.py::decide`

## Adopt an HF full name only when it matches the paper byline

HF profile full names can be nicknames or handles. The sync replaces an author's display name with the HF full name only when it normalizes to the same key as the name the author publishes under on the paper byline.

Code: `backend/services/author_hf_profile_sync_service.py::AuthorHfProfileSyncService._adopt_full_name`

## Ambiguous coauthor name matches are skipped

When two coauthors on one paper normalize to the same name key, an HF claim cannot be attributed to either. The sync maps that key to None and skips both, rather than binding the HF profile to the first match and risking a wrong identity.

Code: `backend/services/author_hf_profile_sync_service.py::AuthorHfProfileSyncService.sync_paper`

## Author claim backfill throttles HF paper API to 1.5 req/s

The Hugging Face papers API allows 500 requests per 5 minutes per IP (about 1.67/s). The author claim backfill defaults to 1.5 requests per second to stay under that limit, with exponential backoff starting at 30 s for up to six attempts.

Code: `backend/services/author_claim_backfill_service.py::DEFAULT_REQUESTS_PER_SECOND`

## Author claims survive arXiv version refresh by exact name or are re-applied from HF

When a new arXiv version replaces a paper's authors, Hugging Face author claims on this or the previous latest version stay attached to the claiming author only if the byline still contains that author's exact name (case-insensitive); the refresh never guesses by fuzzy matching, which could hand a claim to a namesake. If a claimed author's name no longer appears (usually because the author row took a new name from Hugging Face), the claim is dropped and refresh_arxiv_paper re-applies it from Hugging Face's verified paper claims. If the HF papers API is unavailable, the claim stays dropped until the sync_hf_author_profiles CRON sees the paper.

When a new arXiv version replaces a paper's authors, Hugging Face author claims on this or the previous latest version stay attached to the claiming author only if the byline still contains that author's exact name (case-insensitive); the refresh never guesses by fuzzy matching, which could hand a claim to a namesake. If a claimed author's name no longer appears (usually because the author row took a new name from Hugging Face), the claim is dropped and refresh_arxiv_paper re-applies it from Hugging Face's verified paper claims. If the HF papers API is unavailable, the claim stays dropped until the sync_hf_author_profiles CRON sees the paper. The session is flushed before AuthorHfProfileSyncService.sync_paper runs because that sync queries the new author links and the new latest version.

Code: `backend/services/paper_version_refresh_service.py::PaperVersionRefreshService.refresh_arxiv_paper`, `backend/services/paper_version_refresh_service.py::PaperVersionRefreshService._replace_paper_authors`, `backend/services/paper_version_refresh_service.py::_fetch_hf_paper`

## Author photos store source, credit and license for attribution

Author photos are often under licenses such as CC BY that require crediting the photographer next to the image. Each AuthorPhoto therefore stores a mandatory source_url, credit and license (plus optional license_url), and the UI must render that attribution with the photo.

Code: `backend/models/database/papers.py::AuthorPhoto`

## Author-to-organization matching keeps word boundaries

When matching an author name to an organization, the normalised key lowercases and strips punctuation but keeps word breaks. Collapsing them would make a person such as 'Hua Wei' match the organization 'Huawei'.

Code: `backend/services/author_service.py::_org_key`

## Citation counts are written only after a title match

Semantic Scholar lookups by ID, arXiv ID or title search can return a different paper. Before writing citation_count and semantic_scholar_id, the returned title must match the catalog title after normalization; on mismatch the stored Semantic Scholar ID is cleared and the citation count left unchanged.

Code: `backend/services/semantic_scholar_service.py::SemanticScholarService.update_paper_citation_count`

## Citation pages use Semantic Scholar's 1000-row maximum

Semantic Scholar's citations endpoint accepts at most 1000 rows per request. The source-citation method linker pages at that maximum to minimise request count under the rate limit; larger values are rejected by the API.

Code: `backend/database/methods_setup/link_papers_by_source_citations.py::DEFAULT_PAGE_SIZE`

## Citation paging stops below Semantic Scholar's offset+limit 10000 ceiling

Semantic Scholar's citations endpoint rejects requests where offset + limit reaches 10000, so no source paper can be paged past index 9999. The linker clamps each page's limit to the remaining headroom and stops there; heavily cited source papers therefore only link their first ~10k citers.

Code: `backend/database/methods_setup/link_papers_by_source_citations.py::SEMANTIC_SCHOLAR_CITATIONS_HARD_CAP`

## Common author names need a 70% paper overlap to link a Scholar profile

A PwC author is linked to a Scholar profile when at least half of the sampled papers match, but when several Wikidata researchers share the name the overlap must reach 70%, reducing wrong-person links for common names.

Code: `backend/services/google_scholar_link_service.py::COMMON_NAME_MIN_SHARE`

## Curated organization directory includes auto-featured organizations

The curated directory lists the reviewed manifest plus every organization with at least AUTO_FEATURE_MIN_PAPERS papers. Without the threshold branch, institutions added by backfills such as OpenAlex would never reach the directory.

Code: `backend/services/organization_service.py::OrganizationService.get_organizations`

## Empty author rows with aliases are kept

Author aliases redirect old author URLs to the surviving author. Deleting an empty name-only author row cascades its aliases away, so when no merge target exists and aliases point at the row, the backfill keeps the row instead of deleting it.

Code: `backend/services/author_claim_backfill_service.py`

## Google Scholar links are deduplicated to one row per author

Google Scholar candidates come from Wikidata, and two Wikidata items can carry the same Scholar ID for one PwC author. Confirmed links are therefore collapsed to one row per author before storing, so an author never gets duplicate or conflicting Scholar links.

Code: `backend/scripts/link_google_scholar_profiles.py::store_links`

## HF author-claim backfill phases run in a fixed dependent order

The HF author-claim backfill runs its cleanup phases (claim, split namesakes, merge namesakes, delete empty authors) strictly in the order of PHASES, whatever order --phases lists them in, because each phase operates on the author rows the previous one produced. --phases only selects which phases run.

Code: `backend/scripts/backfill_hf_author_claims.py::main`

## HF extracted_pending and extracted_infirmed claims are not author confirmations

Hugging Face marks its own name-based author guesses with statuses extracted_pending and extracted_infirmed. Those are not confirmed by the author, so the profile sync treats them as unconfirmed and must not bind an HF account to an author from them.

Code: `backend/services/author_hf_profile_sync_service.py::UNCONFIRMED_STATUSES`

## HF identity conflicts are counted, never auto-resolved

If an HF user's id and username match different author rows (a rename collided with an older row), or only the username matches a row bound to a different hf_id (HF reassigned a freed username), the sync counts a conflict and leaves the rows untouched. Author identity is keyed on the stable HF id; the sync never rebinds a row's identity based on username alone.

Code: `backend/services/author_hf_profile_sync_service.py::AuthorHfProfileSyncService._apply_claim`

## HF papers API paging pauses one second per page

The Hugging Face papers API allows 500 requests per 5 minutes. The author profile sync sleeps HF_PAGE_PAUSE_SECONDS (1 s) between pages to stay well below that limit; lowering it risks rate-limit failures during backfills.

Code: `backend/services/author_hf_profile_sync_service.py::HF_PAGE_PAUSE_SECONDS`

## HF-linked authors list only papers they claimed on Hugging Face

paper_authors.claimed records that the author claimed the paper on Hugging Face. Author pages linked to an HF account list only claimed papers, avoiding namesake papers piling onto one profile; authors without an HF account are matched by name.

Code: `backend/models/database/papers.py::PaperAuthor.claimed`

## Organization directory uses a per-worker stale-while-revalidate cache

The public organization directory builds about 200 cards with a top paper each, which takes around a second, while featuring and trending change daily. Each worker caches the cards for a 600-second TTL and, once stale, keeps serving them while a single background thread rebuilds. Deployed workers warm the cache at startup so visitors almost never wait on the query.

Code: `backend/services/organization_service.py`

## Organization stats and top paper come from one query pass

Each organization's paper statistics and top paper are computed in one pass over eligible linked papers. The eligibility predicate trims every abstract, so a separate second pass would add about a second to the directory build.

Code: `backend/services/organization_service.py::OrganizationService.get_organizations`

## Profile projections never expose private submission fields

Submission rows carry private and admin-only fields such as source_ip, admin_note, reviewed_by and conflict_payload. The public profile projection must never include them; tests populate these fields to guard against accidental exposure.

Code: `backend/tests/test_profiles_router.py::_submission_row`

## Reject personal HF accounts that reuse an institution's exact name

OpenAlex institutions are matched to Hugging Face organizations by searching for the institution name, and some personal user accounts carry an institution's exact name. Such handles were reviewed by hand and placed in a rejection set so the setup script never links them as the institution's HF organization. Add newly found impostor handles to that set rather than loosening name matching.

Code: `backend/database/organizations_setup/create_openalex_organizations.py::REJECTED_HF_HANDLES`

## Scholar profile evidence overrides Semantic Scholar evidence

When both are available, the verdict from the author's own Google Scholar publication list (via SerpAPI) decides a link proposal; Semantic Scholar evidence is used only when no SerpAPI evidence exists.

Code: `backend/services/google_scholar_link_service.py::decide`

## Semantic Scholar outages stop the batch without marking papers

A paper Semantic Scholar did not find is marked processed (citation_updated_at set) to avoid repeated lookups, but when the API is unavailable the result is unknown. In that case the batch stops and the paper is left untouched so the next batch retries it, rather than being wrongly marked as checked for a week.

Code: `backend/services/semantic_scholar_service.py::SemanticScholarService.batch_update_citation_counts`

## Semantic Scholar requests are paced at one per second

The Semantic Scholar Graph API allows about one request per second for this client. Citation batches sleep RATE_LIMIT_DELAY (1.0 s) between papers so the batch stays within that limit instead of hitting 429s.

Code: `backend/services/semantic_scholar_service.py`

## SerpAPI Scholar profiles are read newest first

SerpAPI author lookups are paged and budgeted (max_pages). Because PwC papers are mostly recent, profiles are requested sorted by publication date so matching papers appear in the first pages even on long profiles.

Code: `backend/services/google_scholar_link_service.py::SerpApiScholar.profile`

## SerpAPI errors are raised without httpx's URL-bearing messages

The SerpAPI key is passed as a query parameter, and httpx's raise_for_status errors quote the full request URL. The client checks status codes itself and raises messages with only the status and Scholar ID so the key never reaches logs.

Code: `backend/services/google_scholar_link_service.py::SerpApiScholar.profile`

## Snapshot author names before replaying HF claims

The daily HF claim sync renames a linked account's author row to its HF full name. The later split phase still needs the name the legacy paper links were matched by, so replay_claims snapshots the names of HF-linked authors before running the sync. Reordering this loses the original names.

Code: `backend/services/author_claim_backfill_service.py::AuthorClaimCleanup.replay_claims`

## Treat HF placeholder avatars as missing organization logos

Hugging Face organizations without an uploaded logo redirect their avatar to a gravatar placeholder, which fails avatar URL validation in HFOrganizationClient.fetch_logo. The OpenAlex organization setup catches that error, clears logo_url and still creates the organization, so placeholder images are never stored as organization logos and a missing logo never aborts the import.

Code: `backend/database/organizations_setup/create_openalex_organizations.py::main`

## Wikidata Scholar ID queries are sharded by first ID character

The Wikidata Query Service aborts queries after 60 s. Fetching every researcher with a Scholar ID is split into one query per first character of the ID (about 2k people, under 20 s each), keeping each shard well below the limit.

Code: `backend/services/google_scholar_link_service.py::WIKIDATA_QUERY`

## Wikidata Scholar IDs are validated against the 12-character format

Google Scholar user IDs are 12 URL-safe characters, but Wikidata's Scholar ID property also contains junk values. Imported IDs are accepted only when they match ^[A-Za-z0-9_-]{12}$.

Code: `backend/services/google_scholar_link_service.py::SCHOLAR_ID_RE`

## Wikidata requests send an identifying User-Agent

Wikimedia's policy asks automated clients to identify themselves, and anonymous clients risk being blocked. Wikidata Query Service requests send a PapersWithCode-ScholarLinks User-Agent with the site URL.

Code: `backend/services/google_scholar_link_service.py::_fetch_wikidata_shard`
