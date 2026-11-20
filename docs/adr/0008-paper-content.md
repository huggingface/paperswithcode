# ADR 0008: Paper Markdown, layout OCR and URL extraction

Status: accepted

Decisions moved out of backend code comments. Each section names the code it governs; update or remove a section when that code changes.

## A complete Markdown shard checkpoint overrides provider attempt errors

Provider job attempts for a Markdown shard are grouped by run and shard and arrive newest first. If any attempt has a complete canonical checkpoint, the logical shard counts as successful even when an earlier or late provider attempt reported an error.

Code: `backend/services/paper_markdown_job_monitor.py::_logical_shards`

## A fresh lane converts newly indexed papers in small shards

Papers indexed in the last day go to a separate live-mode slot pair with at most 10 papers per shard, so reader chat gets page-tagged layout within minutes instead of waiting behind a 100-paper live shard of about three hours. A five-paper shard measured 10 minutes including model start-up, so the 2-hour hard bound leaves ample margin at a $3.60 reservation.

Code: `backend/services/paper_markdown_job_profile.py`

## Budget snapshot planned_* keys report the admitted plan

The budget snapshot keeps the legacy planned_jobs and planned_reserved_usd keys for consumers, but they report the affordable (admitted) plan that the scheduler will actually reserve and launch, not desired_jobs. Setting them to the desired plan would overstate exposure and misreport what the scheduler does.

Code: `backend/services/paper_markdown_budget_service.py::paper_markdown_budget_snapshot`

## Detect failed arXiv HTML conversions before accepting scraped Markdown

When arXiv's HTML renderer fails to convert a paper, the scraped page has a figure filename as its <title> and only a caption as body, or returns just the 'Instructions for reporting errors' feedback footer instead of the paper. The Markdown generator matches both shapes (SCRAPED_IMAGE_TITLE and ARXIV_HTML_FEEDBACK) and treats such rows as missing Markdown so they are regenerated from the PDF with OCR rather than kept as stubs.

Code: `backend/scripts/generate_missing_paper_markdown.py::SCRAPED_IMAGE_TITLE`, `backend/scripts/generate_missing_paper_markdown.py::ARXIV_HTML_FEEDBACK`

## Follow alphaXiv viewer pages to the underlying PDF

alphaXiv serves /pdf/<id> as an HTML viewer rather than the PDF bytes. When a download from an alphaXiv host does not start with %PDF-, the downloader extracts the linked PDF file URL from the HTML and fetches that instead, through the same validated client.

Code: `backend/scripts/generate_missing_paper_markdown.py::download_external_pdf`

## Framer pages without body text fall back to a companion post

Some Framer-hosted pages, such as PDF-hosting technical report pages, appear in the site search index with only a site-level title and no body. Extraction then falls back to a companion entry whose slug shares a stem after stripping suffixes like -technical-report or -paper, preferring /post/ announcement entries over /models/ pages.

Code: `backend/utils/url_fetch.py::_framer_search_index_text`

## HF repo URL extraction keeps up to three path segments

Hugging Face dataset and Space URLs have the form datasets/<owner>/<name> and spaces/<owner>/<name>. The repo URL regex captures up to three path segments so those links are not truncated to a bare owner, and canonicalisation decides which segments form the repo id.

Code: `backend/utils/url_fetch.py::_HF_REPO_RE`

## Layout OCR uploads the Markdown object last as the completion marker

Each paper writes several objects to the layout bucket. The Markdown file is appended last to the upload batch because its presence is what marks a paper as complete for resumed runs; reordering would let a killed run leave papers that look done but lack layout blocks.

Code: `backend/scripts/generate_paper_layout_markdown.py::process`

## Layout-only OCR runs still validate the paper title

In layout-only mode the OCR worker regenerates layout data for papers whose canonical Markdown already exists and leaves that Markdown untouched. It still runs validate_markdown_semantics against the paper title on the fresh OCR output, so a wrong or mismatched PDF cannot attach another paper's layout to the canonical Markdown.

Code: `backend/scripts/generate_missing_paper_markdown.py::process`

## Legacy Markdown uploads are chunked from the mutable alias

Older Markdown uploads only have the mutable compatibility alias that the plain Markdown route serves, with no versioned manifest. Chunked reads fall back to a bounded in-process copy of that alias so agents can still read those papers, and the content hash of the copy versions the cursor.

Code: `backend/services/paper_markdown_service.py::read_paper_markdown_chunk`

## Live paper Markdown jobs use a 7h hard bound and 6.5h deadline

Among retained successful production shards, the slowest 100-paper run took 17,220 seconds (4.78 hours). The live profile sets a 7-hour hard timeout, 2.22 hours above that maximum, and a 6.5-hour worker deadline that leaves 30 minutes for checkpoint and cleanup, with a $12.60 worst-case reservation.

Code: `backend/services/paper_markdown_job_profile.py`

## Markdown monitor tracks the latest run per lane

The latest Markdown run is tracked per lane (the run-id prefix). Otherwise the 5-minute live-fresh runs would always be newest and hide the status of the latest hourly live run.

Code: `backend/services/paper_markdown_job_monitor.py::_fetch`

## Paper Markdown is uploaded after its layout files

The paper layout pipeline publishes layout.json and blocks.json before the anchored Markdown file. Readers treat the presence of the anchored Markdown as the signal that the layout set is complete, so uploading it earlier would expose Markdown whose layout files are missing.

Code: `backend/tests/paper/test_markdown_layout.py::test_process_publishes_canonical_markdown_and_layout_from_one_pass`

## Paper layout objects are written before the canonical Markdown marker

The OCR worker treats the existence of a paper's canonical Markdown as the completion checkpoint: a retried shard skips any paper whose Markdown already exists. Layout and block JSON are therefore written before the .md object locally, and the layout bucket upload happens before the canonical checkpoint upload, so a crash between steps never leaves a paper marked complete without its layout.

Code: `backend/scripts/generate_missing_paper_markdown.py::write_layout`, `backend/scripts/generate_missing_paper_markdown.py::main`

## Preserved Markdown outputs are mirrored as empty placeholders

When an OCR shard prepares its local mirror of the bucket, canonical Markdown objects that already exist and are not being repaired are written as empty local files instead of downloaded, because process() only checks for their existence to skip the paper. This keeps job bandwidth and disk bounded; code that needs the content of a preserved object must download it explicitly.

Code: `backend/scripts/generate_missing_paper_markdown.py::BucketContentStore.prepare`

## Repository URLs are deduplicated case-insensitively

GitHub and Hugging Face repository ids are case-insensitive, so the same repository can appear on a page with different casing. Extraction deduplicates on the lowercased canonical URL and keeps the first spelling seen.

Code: `backend/utils/url_fetch.py::_unique_page_urls`

## Rewrite GitHub blob PDF links to github.com raw URLs

External PDF links pointing at github.com/<owner>/<repo>/blob/... are rewritten to github.com/<owner>/<repo>/raw/..., which redirects to the actual file even for Git LFS objects. raw.githubusercontent.com would return only the LFS pointer text for LFS-tracked PDFs, so it is deliberately not used.

Code: `backend/scripts/generate_missing_paper_markdown.py::normalize_external_pdf_url`

## Terminal Markdown jobs without timing are charged a full reservation

The paper Markdown GPU budget computes spend from job timing. When a job is terminal but its timing is missing, the budget charges the full per-job reservation as spent and counts it separately as unknown terminal reservation. Failing conservatively prevents the scheduler from overspending the GPU ceiling when HF Jobs metadata is incomplete.

Code: `backend/services/paper_markdown_budget_service.py::paper_markdown_budget_snapshot`

## Truncated unversioned Markdown is versioned by exactly its servable bytes

When an unversioned Markdown document exceeds the byte bound, it is truncated, any partial multi-byte UTF-8 sequence at the cut is dropped, and the document is treated as ending there. Size and content version hash exactly the bytes a reader can reach, so cursors stay consistent.

Bytes beyond the unversioned Markdown bound are never served, so the content version is the SHA-256 of the truncated bytes only. A reader resuming with a version hash is thus checked against exactly what it could read.

Code: `backend/services/paper_markdown_service.py::_read_unversioned_markdown_chunk`

## Unversioned Markdown chunking is capped at 2 MB per paper

Papers without a versioned Markdown manifest are chunked from a full in-process copy held in the 128-entry lru_cache of _read_paper_markdown_bytes. The per-paper bound is kept at 2 MB so the cache cannot grow to hundreds of megabytes on the 16 GB VPS.

Code: `backend/services/paper_markdown_service.py::PAPER_MARKDOWN_UNVERSIONED_CHUNK_MAX_BYTES`

## Volume-mount failures stay failures despite a replacement's checkpoint

Replacement attempts share the logical shard's progress path. A provider-confirmed volume mount failure never reached that path, so a later replacement's checkpoint must not retroactively turn the failed provider attempt into a success; such attempts keep their failure outcome.

Code: `backend/services/paper_markdown_job_monitor.py::_fetch`
