---
name: add-external-paper
description: Add non-ArXiv external papers/resources to the paperswithcode repo database. Use this whenever the user asks to add, index, submit, or populate a paper/resource/release that does not have an arXiv paper, including Hugging Face model cards, GitHub repositories, blog posts, vendor technical reports, external PDFs, project pages, or release announcements. This skill should trigger even when the user casually says "add this repo/model/blog to paperswithcode" or gives a URL such as GitHub, Hugging Face, a company blog, a PDF, or a technical report and wants it to appear as a paper page with tasks, methods, code, project links, HF artifacts, and a thumbnail.
---

# Add External Paper

This skill creates or updates a `papers` row with `source = 'external'` for research outputs that are paper-like but are not backed by an arXiv ID. The goal is a complete local paper page: title, abstract or short summary, publication date, authors when available, appropriate task and method tags from the current taxonomy, official GitHub repository links, project pages, explicit Hugging Face artifacts, and a paper thumbnail.

Use the existing application paths first. Direct SQL is acceptable for fields that have no admin API surface, but keep writes idempotent and scoped.

## Pre-flight

Run commands from the repo root and load the project environment:

```bash
uv run --env-file backend/keys.env ...
```

Confirm the API is reachable and the admin token exists:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/papers/recent?limit=1
grep -E '^PWC_ADMIN_API_TOKEN=' backend/keys.env | sed 's/=.*/=<redacted>/'
```

If the API is unavailable, use the direct database path where the operation
supports it or report the blocker. Do not start or restart deployed services
during data curation.

Use `ADMIN_TOKEN=$(grep '^PWC_ADMIN_API_TOKEN=' backend/keys.env | cut -d= -f2-)` for API writes with `X-Admin-Token`.

## Scope Decision

1. If the source has a real arXiv ID for the same release, do not create an external duplicate. Use the normal arXiv indexing flow, then add repos/artifacts/tags to that arXiv paper.
2. If the source is a paper-like external release with no arXiv ID, create or reuse an external row keyed by canonical `source_url`.
3. If the source is only a related code repo or model card for an existing paper, attach it to the existing paper instead of making a new row. Be strict: citations, base-model references, forks, or benchmark mentions are not enough to claim the source introduces the paper.

An external release may acquire an arXiv paper later. The daily importer then
canonicalizes it onto the arXiv row and leaves the old numeric route as a
redirect. Verify that this merge preserves explicit HF arrays and normalized
`paper_hf_artifacts` links along with evaluations, repositories, project pages,
tasks, and methods; otherwise the paper can silently lose its HF trending
component after canonicalization.

Canonical `source_url` should be the most durable primary surface for the release:

- **The paper PDF whenever one exists**, even when a project page or landing page also exists. Make the PDF the `source_url` and put the project/landing page in `project_pages`. Example: paper 123404 uses `https://sunovivid.github.io/correction-training/paper.pdf` as `source_url` and the project page as a project link.
- Technical report or blog post over a GitHub README when no PDF exists.
- HF model card when the model card is the release surface.
- GitHub repo when the README is the only technical report.

## Collect Source Metadata

Gather evidence before writing. Save temporary source text under `/tmp/<slug>/` when useful.

For GitHub repositories:

```bash
mkdir -p /tmp/<slug>
gh repo view <owner>/<repo> --json nameWithOwner,description,url,homepageUrl,createdAt,pushedAt,repositoryTopics,stargazerCount > /tmp/<slug>/repo.json
gh api repos/<owner>/<repo>/readme -H "Accept: application/vnd.github.raw" > /tmp/<slug>/README.md
```

For Hugging Face models:

```bash
mkdir -p /tmp/<slug>
uv run --env-file backend/keys.env hf models info <repo_id> > /tmp/<slug>/hf-info.json
uv run --env-file backend/keys.env hf models card <repo_id> --text > /tmp/<slug>/card.md
```

Check HF metadata for `arxiv:` tags. If a tag clearly points to the source paper and the local DB has that arXiv paper, use the arXiv row rather than creating an external row.

For webpages, PDFs, blogs, and vendor reports, try the built-in metadata extractor:

```bash
uv run --env-file backend/keys.env -m backend.genai_steps.extract_external_resource_metadata --url "<source_url>"
```

The extractor returns title, abstract/summary, authors, date, GitHub URLs, and HF artifact URLs. Treat its output as a draft: verify against the source text and fill gaps manually from the page, README, card metadata, release notes, or visible dates. For PDFs, if extraction returns no readable text or only a generated summary, download the PDF and extract text with `pdftotext -layout` (or another structured PDF text extractor already available in the environment) before writing metadata.

## Metadata Rules

- `title`: use the actual release/report title, not browser chrome like `GitHub - owner/repo`.
- `abstract`: use the source's explicit abstract verbatim whenever one is present. For PDFs, inspect the extracted first pages before summarizing; do not replace an abstract-like opening block with a generated summary just because the metadata extractor failed. If there is no explicit abstract, executive summary, TL;DR, or README overview, write a concise 2-5 sentence summary from the source and make it clear in the report that the abstract was manually summarized.
- `date_published`: required for external rows. Use the release/report publication date, not the scrape date. For GitHub-only releases, prefer a dated release/tag or README announcement date over repository creation time. If no credible date can be found, stop and ask the user.
- `authors`: include human authors only. Do not store organization names such as "OpenAI", "Sapient", or "Hugging Face" as authors.
- `github_repository_urls`: official GitHub repositories linked by the source or provided by the user. Only include repos that the source presents as official code/tools for the release; passing a URL here marks the paper-repository relationship as official. If additional GitHub URLs are merely dependencies, citations, examples, or benchmark/framework references, either leave them unlinked or link them separately with `is_official = false` rather than mixing them into this field.
- `hf_artifact_urls`: full `https://huggingface.co/...` URLs for model, dataset, and space artifacts. Store absolute URLs, not bare repo ids.
- `project_pages`: official non-GitHub landing pages, demos, docs, reports, or blog/project pages connected to the release. Do not duplicate the canonical `source_url` as a project page unless it is useful as a project link in addition to being the paper source. For model-family releases, add the family/collection page and technical report as project pages, but keep individual HF model cards in `hf_artifact_urls`; the frontend groups project pages behind one "Project page" action and expands HF artifacts separately.

## Create Or Update The External Row

Prefer a small Python script that uses `ExternalResourceService`, because it normalizes GitHub URLs and classifies HF artifacts into `hf_models`, `hf_datasets`, and `hf_spaces`.

```bash
uv run --env-file backend/keys.env python - <<'PY'
from datetime import date
from backend.database.connection import get_database_session
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)

payload = ExternalResourceInput(
    source_url="<canonical source URL>",
    title="<clean title>",
    abstract="<explicit abstract or short source-grounded summary>",
    authors=["<human author>", "..."],
    date_published=date(YYYY, MM, DD),
    github_repository_urls=["https://github.com/<owner>/<repo>"],
    hf_artifact_urls=[
        "https://huggingface.co/<org>/<model>",
        "https://huggingface.co/datasets/<org>/<dataset>",
        "https://huggingface.co/spaces/<org>/<space>",
    ],
)

session_gen = get_database_session()
db = next(session_gen)
try:
    result = ExternalResourceService(db).add_external_resource(payload)
    print(result.paper.id, result.paper.title)
finally:
    try:
        next(session_gen)
    except StopIteration:
        pass
PY
```

This is idempotent by `(source='external', source_url)`: re-running updates mutable fields and merges links.

If the page can be fetched and the automatic extractor has enough metadata, `add_from_url` is also fine:

```python
result = await ExternalResourceService(db).add_from_url(
    source_url="<canonical source URL>",
    date_published=<manual date if extractor cannot infer it>,
    title_override="<optional clean title>",
    abstract_override="<optional summary>",
    github_repository_urls_extra=["https://github.com/<owner>/<repo>"],
    hf_artifact_urls_extra=["https://huggingface.co/<org>/<model>"],
)
```

## Generate Thumbnail

After the external row exists, generate a thumbnail before finishing unless `papers.thumbnail_url` is already set and the cached file still serves. External paper cards and social previews look incomplete without one.

Pick the render source URL in this order:

1. A direct PDF URL linked by the source (for example `https://aclanthology.org/Q19-1026.pdf` when the canonical `source_url` is the HTML landing page).
2. The canonical `source_url` when it is itself a PDF.
3. The canonical `source_url` for HTML pages, blogs, GitHub README surfaces, or HF model cards. `ThumbnailService` falls back to a first-viewport screenshot when no PDF is available.

Prefer PDF first-page rendering over HTML screenshots whenever a credible PDF exists.

```bash
uv run --env-file backend/keys.env python - <<'PY'
import asyncio
from backend.database.connection import get_database_session
from backend.models.database import Paper as DBPaper
from backend.services.thumbnail_service import (
    ThumbnailService,
    build_custom_thumbnail_url,
)

paper_id = <paper_id>
thumbnail_source_url = "<PDF or page URL to render>"

async def main() -> None:
    service = ThumbnailService()
    filename = service.get_external_filename(paper_id)
    existing_url = service.get_external_thumbnail_url(paper_id)
    if existing_url:
        session_gen = get_database_session()
        db = next(session_gen)
        try:
            paper = db.get(DBPaper, paper_id)
            if paper is not None and not paper.thumbnail_url:
                paper.thumbnail_url = existing_url
                db.commit()
            print("thumbnail_url", existing_url, "status=cached")
        finally:
            try:
                next(session_gen)
            except StopIteration:
                pass
        return

    await service.generate_external_thumbnail(
        paper_id,
        thumbnail_source_url,
        force=False,
    )
    thumbnail_url = build_custom_thumbnail_url(filename)

    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper = db.get(DBPaper, paper_id)
        paper.thumbnail_url = thumbnail_url
        db.commit()
        print("thumbnail_url", thumbnail_url, "status=generated")
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass

asyncio.run(main())
PY
```

Verify the image is reachable:

```bash
curl -s "http://localhost:8000/api/v1/papers/<paper_id>" | uv run python -c "import json,sys; p=json.load(sys.stdin); print(p.get('thumbnail_url'))"
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/thumbnails/custom/external_<paper_id>.jpg?fit=fit4"
```

If generation fails because headless Chrome or PDF tooling is unavailable, note the failure in the report. The `preload_thumbnails` cron may backfill later, but do not skip an inline attempt during ingestion.

## Tag With Existing Tasks And Methods

Only use tasks and methods already present in the taxonomy unless the user explicitly asks to expand the taxonomy. If the right concept is missing, choose the closest existing tag and report the gap.

Inspect candidate tasks:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine

terms = ["text generation", "language model", "reasoning", "biology"]
with get_engine().connect() as conn:
    for term in terms:
        rows = conn.execute(text("""
            SELECT id, name, slug, level
            FROM tasks
            WHERE name ILIKE :q OR slug ILIKE :q
            ORDER BY level NULLS LAST, name
            LIMIT 20
        """), {"q": f"%{term}%"}).fetchall()
        print(term, [dict(r._mapping) for r in rows])
PY
```

Inspect candidate methods:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine

terms = ["transformer", "latent reasoning", "hierarchical reasoning", "diffusion"]
with get_engine().connect() as conn:
    for term in terms:
        rows = conn.execute(text("""
            SELECT id, name, slug, keywords
            FROM methods
            WHERE name ILIKE :q OR slug ILIKE :q OR keywords ILIKE :q
            ORDER BY name
            LIMIT 20
        """), {"q": f"%{term}%"}).fetchall()
        print(term, [dict(r._mapping) for r in rows])
PY
```

Apply tags through the admin API when you have an authorized browser session. These endpoints replace the full set, so first read existing tags and merge unless intentionally retagging:

```bash
curl -s "http://localhost:8000/api/v1/papers/<paper_id>?include_resources=true" | uv run python -m json.tool

curl -s -X PUT "http://localhost:8000/api/v1/papers/<paper_id>/tasks?task_ids=<id>&task_ids=<id>" \
  -H "X-Admin-Token: $ADMIN_TOKEN"

curl -s -X PUT "http://localhost:8000/api/v1/papers/<paper_id>/methods?method_ids=<id>&method_ids=<id>" \
  -H "X-Admin-Token: $ADMIN_TOKEN"
```

If the local API rejects `X-Admin-Token` because the endpoint requires an HF admin session, use the CLI instead of hacking auth. It replaces the whole set, so pass the final list of ids:

```bash
uv run --env-file backend/keys.env pwc paper update <paper_id> tasks <task_id> [<task_id> ...]
uv run --env-file backend/keys.env pwc paper update <paper_id> methods <method_id> [<method_id> ...]
```

(`PaperService.update_paper_tasks` / `update_paper_methods` no longer exist; do not call them.)

Prefer a few high-confidence tags over broad keyword stuffing. A good external paper page should usually have 1-4 task tags and 1-5 method tags.

## Add Repositories And Project Pages

`ExternalResourceService` already links GitHub repositories passed in the payload as official. If you need to adjust or add more after creation, use the API:

```bash
curl -s -X PUT "http://localhost:8000/api/v1/papers/<paper_id>/repositories" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"repositories":[{"url":"https://github.com/<owner>/<repo>","is_official":true}]}'

curl -s -X PUT "http://localhost:8000/api/v1/papers/<paper_id>/project-pages" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"project_pages":[{"url":"https://example.com/project","is_official":true}]}'
```

For project pages, include only useful official release surfaces: demo pages, report landing pages, docs, blog/project homepages, and model family pages. Avoid adding every linked dependency, unrelated citation, or social URL.

When a release has multiple official surfaces, put them all in `project_pages`; users see them under one fixed "Project page" action. For HF model families, put the HF collection in `project_pages` and every concrete model/dataset/space card in `hf_artifact_urls` so users can click each artifact instead of being sent only to the first model.

## Add Or Fix HF Artifacts

`ExternalResourceService` synchronizes explicit URLs into both the paper arrays
and the normalized `hf_artifacts` / `paper_hf_artifacts` tables during
ingestion. For an existing row, use the repository CLI instead of updating the
arrays directly:

```bash
uv run --env-file backend/keys.env pwc paper update <paper_id> hf-artifacts \
  --model "https://huggingface.co/<org>/<model>" \
  --dataset "https://huggingface.co/datasets/<org>/<dataset>" \
  --space "https://huggingface.co/spaces/<org>/<space>" \
  --json
```

The command is replace-style, so read and preserve existing artifacts unless
the user asked to remove them. It creates normalized junction rows immediately
and invalidates the discovery checkpoint for authoritative CRON reconciliation.
Do not use direct SQL on only `papers.hf_models`, `hf_datasets`, or `hf_spaces`;
that can leave the paper visible in the UI while excluding it from composite
trending.

## Migrate Existing Evaluations

Use this when the external row is being created because evaluations were already attached to a related but wrong paper, such as a model-family arXiv paper that did not actually introduce the release. Keep the migration narrow and auditable:

1. Query the old paper for candidate rows by `model_name`, benchmark set, or source URL.
2. Confirm the new external row is the canonical source for those rows.
3. Move only the matching evaluations to the new `paper_id`.
4. Preserve `task_id`, `dataset_id`, `metrics`, `best_metric`, `harness`, ranks, and methodology.
5. Set `external_source_url` to the canonical external source when the old rows have no row-level source or still point at the wrong source.

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine

old_paper_id = <old_id>
new_paper_id = <new_external_id>
model_pattern = "%<model name>%"
canonical_source_url = "<external source URL>"

with get_engine().begin() as conn:
    rows = conn.execute(text("""
        SELECT id, model_name, dataset_id, best_metric, external_source_url
        FROM evaluations
        WHERE paper_id = :old_paper_id
          AND model_name ILIKE :model_pattern
        ORDER BY id
    """), {"old_paper_id": old_paper_id, "model_pattern": model_pattern}).mappings().all()
    print("candidate_rows", len(rows))

    conn.execute(text("""
        UPDATE evaluations
        SET paper_id = :new_paper_id,
            external_source_url = :canonical_source_url
        WHERE paper_id = :old_paper_id
          AND model_name ILIKE :model_pattern
    """), {
        "old_paper_id": old_paper_id,
        "new_paper_id": new_paper_id,
        "model_pattern": model_pattern,
        "canonical_source_url": canonical_source_url,
    })
PY
```

After the move, verify counts on both papers and check for duplicate `(paper_id, task_id, dataset_id, model_name, harness, best_metric)` rows. If the user is adding new evaluation rows after the move, return to `add-evals`.

## Verify

Fetch the completed paper with resources:

```bash
curl -s "http://localhost:8000/api/v1/papers/<paper_id>?include_resources=true" | uv run python -m json.tool
```

For model-family releases, explicitly inspect that:

- `project_pages` contains the durable project/collection/report links you expect.
- `hf_models`, `hf_datasets`, and `hf_spaces` contain every individual artifact, not just the first or canonical model.
- Individual model cards were not duplicated as project pages unless the model card is the canonical release surface.
- `thumbnail_url` is set and the custom thumbnail endpoint returns HTTP 200.

Also verify normalization when HF artifacts were added:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine
paper_id = <paper_id>
with get_engine().connect() as conn:
    rows = conn.execute(text("""
        SELECT a.kind, a.repo_id, a.trending_score, a.fetched_at
        FROM paper_hf_artifacts pha
        JOIN hf_artifacts a ON a.id = pha.hf_artifact_id
        WHERE pha.paper_id = :paper_id
        ORDER BY a.kind, a.repo_id
    """), {"paper_id": paper_id}).mappings().all()
    print([dict(row) for row in rows])
PY
```

Every explicit artifact should have a normalized row. A newly inserted artifact
may have a null metric until `update_hf_artifacts` refreshes it, but the junction
must already exist.

If the external paper has since been merged into an arXiv row, resolve the old
numeric route and run these checks against the canonical paper ID. Confirm the
old route redirects successfully and the canonical row retained the same
explicit and normalized HF artifacts.

Check the local route:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "https://paperswithcode.co/paper/<paper_id>"
```

If you changed backend code, restart the backend per `AGENTS.md`. For pure database population, no redeploy is needed, but verify the live page/API after the write.

## Reporting Back

End with a concise report:

- Local paper URL: `https://paperswithcode.co/paper/<paper_id>` for external rows.
- Source URL used as canonical `papers.source_url`.
- Whether the row was created or updated.
- Abstract source: explicit abstract / source summary / manually summarized from README or page.
- Publication date and where it came from.
- Tasks and methods linked, with IDs or slugs.
- GitHub repositories, project pages, and HF artifacts linked.
- Thumbnail status: generated, cached, already present, or failed with reason.
- Existing evaluations migrated, if any, with before/after counts.
- Any taxonomy gaps or missing metadata that should be cleaned up later.

## When Not To Use This Skill

- The source has an arXiv paper and the task is to import that paper. Use the normal ArXiv paper indexing flow.
- The user wants to add a new benchmark/leaderboard/dataset. Use `add-benchmark`.
- The user wants to add benchmark scores/evaluation rows for a model or paper. Use `add-evals` after the paper row exists.
