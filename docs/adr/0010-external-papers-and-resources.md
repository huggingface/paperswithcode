# ADR 0010: External papers, repositories and HF artifacts

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## A paper's only repository is official by default

The first and only repository linked to a paper is marked official unless flagged otherwise, because a paper page with a single code link almost always points to the authors' code. Additional repositories are official only when explicitly flagged.

Code: `backend/services/repository_service.py::RepositoryService._associate_repository`

## API process uses its own Hugging Face cache directory

In production the API and the CRON jobs run as different users under the same runtime-data root, and a cache directory created by one can be readable but not writable by the other. The API process therefore points HF_HOME and HF_XET_CACHE at <PWC_RUNTIME_DATA_DIR>/hf-app-cache, separate from the CRON-owned cache, so request-path Hub and Xet writes never fail on permissions.

Code: `backend/services/paper_bucket_service.py::_configure_hugging_face_cache`

## ArXiv uniqueness enforced by partial unique indexes

Uniqueness of (arxiv_id, version) is enforced with partial unique indexes that apply only when arxiv_id is present, instead of a plain UNIQUE constraint. This lets external papers, which have no ArXiv identifier, coexist without colliding on NULLs while ArXiv versions stay unique.

Code: `backend/models/database/papers.py::Paper.__table_args__`

## Bucket copies bind an operation-scoped hf_hub_download cache

HfApi.copy_files downloads small text files through hf_hub_download but exposes no cache_dir parameter, and deployed service users have no writable home directory. copy_paper_to_bucket binds hf_hub_download to a temporary per-operation cache directory with functools.partial so copies work and leave nothing behind.

Code: `backend/services/paper_bucket_service.py::copy_paper_to_bucket`

## Check the Markdown migration lock before paying for a scrape

Firecrawl scrapes cost credits. _prepare checks the bucket's Markdown migration lock before scraping and fails with a retryable markdown_migration_locked error, so a held lock never burns a paid scrape whose result could not be published.

Code: `backend/services/external_page_markdown_service.py::_prepare`

## Configure HF cache env before importing huggingface_hub

huggingface_hub and its compiled Xet dependency read cache configuration from the environment at import time. paper_bucket_service sets HF_HOME and HF_XET_CACHE first and imports httpx and huggingface_hub below that call (with noqa: E402); reordering the imports would silently use the default, possibly unwritable, cache.

Code: `backend/services/paper_bucket_service.py`

## Delete the previous source's Markdown before scraping a new source

When an external paper's source URL changes, the old page's Markdown copy is deleted before the new page is scraped. If the new scrape fails, nothing remains that readers or curation could mistake for the new source.

Code: `backend/services/external_page_markdown_service.py::_prepare`

## Explicit HF artifact links reset the paper's artifact scan marker

Adding explicit HF artifact URLs to a paper clears hf_artifacts_scanned_at. Otherwise a previously completed empty scan would keep the scanner from revisiting the paper and the new links would not be normalised or extended.

Code: `backend/services/external_resource_service.py::ExternalResourceService._link_hf_artifacts`

## Explicit Hugging Face artifact URLs survive canonicalization onto ArXiv papers

External papers have no reliable arxiv_id, so their Hugging Face models, datasets and spaces are stored as explicit URL arrays on the paper. ArXiv papers normally derive artifacts from arxiv_id, but when an external release is later merged onto its ArXiv paper the curated URLs are retained rather than cleared, since derivation may not find them.

Code: `backend/models/database/papers.py::Paper.hf_models`

## Explicitly unofficial repositories are never promoted

update_repositories marks a lone repository official by default. When an operator passes --unofficial on the papers CLI, that intent is explicit, so the CLI calls update_repositories with promote_lone_repository=False; otherwise the single-repository promotion would silently override the operator's choice.

Code: `backend/cli_papers.py::update_paper`

## External PDF archiving at ingestion uses short timeouts

External paper ingestion runs inside request handlers, so archiving the paper PDF uses a 20-second per-request timeout and a 60-second overall deadline instead of the OCR worker's three minutes. A slow host must not hold an API worker; PDFs that time out at ingestion are still archived later by the OCR worker.

Code: `backend/services/external_paper_pdf_archive_service.py`

## External PDF archiving runs after the ingest commit

New external papers have their PDF archived at ingestion, but the download starts only after the database commit. Running it inside the transaction would hold a PostgreSQL transaction and its locks open for the duration of a network download.

Code: `backend/services/external_resource_service.py::ExternalResourceService.add_external_resource`

## External papers expose source_url as url_abs and no generated PDF

ArXiv paper rows derive url_abs and url_pdf from arxiv_id and version. External rows (blogs, technical reports, release pages) return source_url as url_abs and leave url_pdf NULL unless an explicit PDF is known. Clients must not assume every paper has an arXiv-style PDF URL.

Code: `backend/models/papers.py::Paper`

## GitHub URLs are normalized to lowercase

GitHub owner and repository names are case-insensitive and redirect to the canonical casing. normalize_github_url lowercases both so the same repository written with different casing compares equal and is not stored twice. Normalized URLs are therefore not guaranteed to match GitHub's display casing.

Code: `backend/utils/github_utils.py::normalize_github_url`

## GitHub repository URLs are normalized before upsert

GitHub treats owner and repository names case-insensitively and redirects between spellings. Repository URLs are normalized (lowercased) before lookup and insert so differently cased links to the same repository do not create duplicate rows.

Code: `backend/services/repository_service.py::RepositoryService._upsert_repository`

## Hub artifact URLs are deduplicated case-insensitively

Hugging Face Hub repo ids are case-insensitive, so org/Model and org/model are the same artifact. Paper HF artifact lists are deduplicated on lowercased URLs to avoid attaching one artifact twice.

Code: `backend/services/external_resource_service.py::ExternalResourceService._link_hf_artifacts`

## Hugging Face artifacts are stored explicitly only for external papers

ArXiv papers derive their Hugging Face models, datasets and Spaces at render time from the Hub's arxiv filter using arxiv_id. External papers have no reliable arxiv_id, so their artifact URLs are stored explicitly in hf_models and related fields. ArXiv rows leave these lists empty.

Code: `backend/models/papers.py::Paper`

## Only PDFs that open are archived

The OCR worker trusts an archived external paper PDF and will not re-download it. archive_external_paper_pdf therefore opens the bytes with PyMuPDF and requires at least one page before uploading, so an HTML error page or truncated download is never archived as the paper.

Code: `backend/services/external_paper_pdf_archive_service.py::archive_external_paper_pdf`

## Page status record carries both the framing check and scrape outcome

The per-paper status record in the bucket stores the iframe framing check alongside the scrape status. A record with no status (only a framing check) means no scrape has been attempted yet and is due. When the paper's source URL changes, the scrape fields reset but the framing check, keyed by its own URL, carries over.

Code: `backend/services/external_page_markdown_service.py::retry_due`, `backend/services/external_page_markdown_service.py::_prepare`

## Papers split by source: arxiv rows derive URLs, external rows store source_url

The papers table holds both ArXiv papers (source='arxiv') and external resources such as blog posts, technical reports and model release pages (source='external'). External rows must populate source_url and leave arxiv_id NULL; ArXiv rows leave source_url NULL and derive URLs from arxiv_id plus version. The papers_source_identifier_check constraint enforces that arxiv_id is required exactly for arxiv rows.

arxiv_id is NULL for source='external' rows and required for source='arxiv' rows, enforced in the database by papers_source_identifier_check. Code must not assume every paper has an arxiv_id.

Code: `backend/models/database/papers.py::Paper.source`, `backend/models/database/papers.py::Paper.arxiv_id`

## Project page upsert keeps official sticky and source first-writer

When a project page URL is ingested again, create_or_update_project_page ORs is_official with the stored value, so the page stays official if any source ever marked it official, and never overwrites the stored source, which keeps the first source that created the row. Later lower-trust imports therefore cannot demote an official page or rewrite its provenance.

Code: `backend/services/project_page_service.py::ProjectPageService.create_or_update_project_page`

## Re-ingesting an external paper never changes its source or URL

External papers are identified by their source and canonical URL. A re-ingest updates mutable metadata such as title, abstract and date, but never rewrites source or url. Changing them would orphan the identity used for deduplication and break existing links.

Code: `backend/services/external_resource_service.py::ExternalResourceService.add_external_resource`

## Re-read page status after acquiring the per-process lock

_page_lock serializes scrapes only within one process, while the reader API and the hourly backfill run in different processes. After waiting, _prepare re-reads the status and bucket and returns an already published page instead of scraping again or deleting a copy another worker just wrote.

Code: `backend/services/external_page_markdown_service.py::_prepare`

## Repositories linked from an external source page are official

When an external paper is ingested, GitHub repositories linked directly from its source page are attached with is_official=true. The source page is the authors' own release, so its links are treated as authoritative rather than as community implementations.

Code: `backend/services/external_resource_service.py::ExternalResourceService._link_repositories`

## Repository upserts keep the highest star count and original source

When an existing repository is upserted again, its star count becomes the maximum of the stored and incoming values and its source is left unchanged. This keeps the original provenance (for example pwc_archive or hf_api) and prevents a stale import from lowering star counts.

Code: `backend/services/repository_service.py::RepositoryService._upsert_repository`

## Scraped pages must be long and title-led to count as a paper

A scraped external page is accepted as paper Markdown only if it has at least 2000 characters (shorter pages are abstract stubs or conference listings) and the paper title matches within the first 4000 characters (a program listing that mentions the paper among hundreds of others is not the paper).

Code: `backend/services/external_page_markdown_service.py::PAGE_MARKDOWN_MIN_CHARS`, `backend/services/external_page_markdown_service.py::TITLE_WINDOW_CHARS`

## Single-segment Hub URLs are profiles, not models

A huggingface.co URL with namespace and name segments is classified as a model, but a bare huggingface.co/<name> is a user or organization profile and is not treated as an artifact link, even though a few legacy canonical models have single-segment ids. This keeps author and org profile links from being attached to papers as models.

Code: `backend/utils/hf_utils.py::classify_hf_artifact_url`

## Space links for arXiv papers point to the HF paper page

The Hugging Face Spaces catalog has no working other=arxiv: filter, unlike models and datasets. When Spaces are a paper's dominant artifact kind, the summary links to huggingface.co/papers/<arxiv id without version>, which lists linked Spaces, instead of a filtered catalog URL.

Code: `backend/services/paper_service.py::PaperService._build_hf_artifact_summary`

## Space metric refresh never expands downloads

Spaces have no downloads counter, and the Hugging Face Hub rejects the entire request with HTTP 400 when an unsupported field is expanded. _HF_METRIC_FIELDS therefore requests only trendingScore and likes for Spaces; adding downloads would make every Space metrics refresh fail.

Code: `backend/utils/hf_utils.py`

## Storage outages never count against a page's scrape attempts

External page Markdown status lives in an HF bucket. When the bucket is unreachable, the page is treated as still pending, the failure is recorded as retryable storage_unavailable with backoff so reads do not re-scrape on every request, and it does not increment the page's attempt_count. Only genuine page failures can exhaust MAX_ATTEMPTS and mark a page unreadable.

Code: `backend/services/external_page_markdown_service.py::web_markdown_pending`, `backend/services/external_page_markdown_service.py::_write_status`, `backend/services/external_page_markdown_service.py::_prepare`

## Venue landing pages and fragment URLs are not scraped as papers

Venue and publisher landing pages (ACL Anthology, ACM DL, DOI resolvers and similar) show an abstract and link an often paywalled PDF, so scraping them yields metadata rather than a paper; they are listed in LANDING_PAGE_HOSTS, mirrored in frontend/src/lib/paperReader.ts. URLs with a fragment point into pages that list many papers and are rejected too.

Code: `backend/services/external_page_markdown_service.py::LANDING_PAGE_HOSTS`, `backend/services/external_page_markdown_service.py::external_page_url`

## bioRxiv API requests send an explicit User-Agent

The bioRxiv API rate-limits (HTTP 429) requests carrying aiohttp's default User-Agent. Metadata requests therefore identify the client with a generic Papers with Code indexer User-Agent and an Accept: application/json header.

Code: `backend/utils/biorxiv.py::_API_HEADERS`

## bioRxiv DOI parsing accepts 10.1101 and 10.64898 prefixes and early URLs

bioRxiv and medRxiv DOIs use the 10.1101/ prefix, but bioRxiv also assigns 10.64898/ to some newer submissions, so both are accepted. Early /content/early/YYYY/MM/DD/<suffix>vN URLs omit the DOI prefix entirely; the parser falls back to matching the date-based suffix and prepends 10.1101/.

bioRxiv early URLs of the form /content/early/YYYY/MM/DD/<suffix>vN omit the 10.1101/ DOI segment. parse_biorxiv_doi falls back to matching the trailing date-based suffix and reconstructs the DOI with the 10.1101/ prefix.

Code: `backend/utils/biorxiv.py::_DOI_IN_URL_RE`, `backend/utils/biorxiv.py::parse_biorxiv_doi`

## bioRxiv PDFs are fetched via Europe PMC or S3, never biorxiv.org

biorxiv.org and medrxiv.org links are Cloudflare-protected against bots, so automated PDF downloads from them fail. When choosing a full-text PDF URL from Europe PMC, links on those hosts are skipped in favour of other mirrors.

Code: `backend/utils/biorxiv.py::fetch_europepmc_pdf_url`

## has_hf_artifacts accepts junction rows or paper URL arrays

Hugging Face artifacts for arXiv papers come from the HF CRON's paper_hf_artifacts junction table, while external papers store explicit hf_models/hf_datasets/hf_spaces URL arrays on the paper. Feed-card badges count both, so every has_hf_artifacts filter must accept either source or filters and badges disagree.

Code: `backend/services/paper_implementation_service.py`
