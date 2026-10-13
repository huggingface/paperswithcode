---
name: add-conference
description: Add or update conference rows in the paperswithcode repo database. Use this whenever the user asks to add a conference, create a conference page, import accepted papers for a venue (CVPR, ICLR, NeurIPS, ICML, ICRA, etc.), set conference dates/venue/description/hero image, or link papers to a conference edition. Trigger even for casual phrasing like "add CVPR 2027", "create the ICLR 2026 page", "import conference papers from this CSV", or "set the conference thumbnail".
---

# Add a Conference

This skill adds curated rows to the `conferences` table so conference pages at `/conferences/<slug>` render correctly with metadata, hero images, deadlines, and linked papers. Prefer small idempotent migrations plus applying the same change to the live database.

> **Image storage:** seed PNG → `/tmp/paperswithcode_entity_image_seeds/conferences/<slug>.png` → `import_entity_image.py` → SQL bytes served at `/api/v1/conferences/<slug>/image`. Do **not** put conference heroes in `frontend/public/` (that folder is for browser assets only: favicons, `og-image.png`, logos).

When the user says **"similarly add X"** (often with just a venue name and year), run the full workflow below without re-asking — same metadata pattern, thumbnail import, and verification steps as the prior conference in the conversation unless they specify otherwise.

## End-to-End Checklist

For a typical new conference edition:

1. Confirm the conference does not already exist (`slug`, `name`, `year`).
2. Pick a stable slug: `<short-name-lowercase>-<year>` (e.g. `cvpr-2026`, `iclr-2026`, `icra-2026`).
3. Write metadata + migration SQL (or idempotent Python upsert script).
4. Add hero image: save seed PNG under `/tmp/paperswithcode_entity_image_seeds/conferences/<slug>.png`, then import into SQL (see Thumbnail).
5. Apply migration to the live DB.
6. Link papers when the user provides a CSV or asks for import (see Paper linking).
7. Verify API + report production URL.

Skip paper import only when the user explicitly asks for the conference row alone.

## Core Rules

Conferences are normalized venue editions. Each gets its own page at `/conferences/<slug>`.

- **`slug`**: lowercase short name + hyphen + year (`cvpr-2026`, not `CVPR2026`).
- **`name`**: display title including year (e.g. `CVPR 2026`, `ICLR 2026`).
- **`short_name`**: abbreviation without year (`CVPR`, `ICLR`, `NeurIPS`).
- **`year`**: integer edition year.
- **`url`**: official conference homepage.
- **`start_date` / `end_date`**: conference dates when known (`DATE` columns).
- **`venue` / `location`**: physical venue and city/country when known.
- **`description`**: one concise paragraph — what the venue is, what research it covers, and what users can browse on this page. Use relative on-site links when helpful; never hard-code `paperswithcode.co` or localhost inside markdown fields.
- **`hf_url`**: optional Hugging Face dataset or org page for the edition (e.g. `https://huggingface.co/datasets/ai-conferences/CVPR2026`).
- **`image_url`**: leave NULL for new self-hosted images — the API resolves `/api/v1/conferences/<slug>/image` once `image_mime_type` is set. Use an external URL only when you cannot self-host.
- **`image_credit`**: attribution as markdown link, e.g. `[CVPR 2026](https://cvpr.thecvf.com/)`.
- **Paper association:** use `paper_conferences` junction (`source = 'manual'` or importer tag). Display tags on paper pages also use denormalized `papers.proceeding` (e.g. `CVPR 2026`, `CVPR 2026 Oral`).
- **Images:** curated self-hosted heroes are stored in SQL (`image_data` / `image_mime_type`). Do **not** add runtime assets under `frontend/public/images/`.

## Workflow

### 1. Understand the requested conference

- Record full name, short name, year, official URL, dates, venue/location, and any hero image the user attached.
- Search for an existing row by `slug`, `name`, and `year` before creating a new one.
- Check sibling editions (e.g. `cvpr-2025`, `cvpr-2026`) to calibrate description tone and metadata fields.

### 2. Choose metadata

| Field | Example (CVPR 2026) |
|-------|---------------------|
| `name` | `CVPR 2026` |
| `slug` | `cvpr-2026` |
| `short_name` | `CVPR` |
| `year` | `2026` |
| `url` | `https://cvpr.thecvf.com/` |
| `start_date` | `2026-06-03` |
| `end_date` | `2026-06-07` |
| `venue` | `Colorado Convention Center` |
| `location` | `Denver, USA` |
| `hf_url` | `https://huggingface.co/datasets/ai-conferences/CVPR2026` |
| `image_credit` | `[CVPR 2026](https://cvpr.thecvf.com/)` |

### 3. Thumbnail

Conference hero images are DB-backed. Save a seed PNG, import it, then verify the API image endpoint.

**If the user provides an image**, copy it to:

```text
/tmp/paperswithcode_entity_image_seeds/conferences/<slug>.png
```

**Otherwise**, source a suitable logo or venue graphic:

1. Prefer the official conference logo or branding from the conference homepage.
2. Crop to a clear hero image (avoid tiny favicons); PNG is preferred.
3. Save to `/tmp/paperswithcode_entity_image_seeds/conferences/<slug>.png`.
4. Set `image_credit` to the official site or source.

After the conference row exists, import the PNG into SQL:

```bash
uv run --env-file backend/keys.env python backend/database/import_entity_image.py \
    conferences <slug> /tmp/paperswithcode_entity_image_seeds/conferences/<slug>.png
```

No frontend rebuild is needed for entity images — they are served from the backend API.

### 4. Create and apply migration

Add `backend/database/migrations/add_<slug>_conference.sql` using `ON CONFLICT (slug) DO UPDATE`.

Example:

```sql
INSERT INTO conferences (
    name, slug, short_name, year, url,
    start_date, end_date, venue, location,
    description, image_url, image_credit, hf_url
)
VALUES (
    'CVPR 2026',
    'cvpr-2026',
    'CVPR',
    2026,
    'https://cvpr.thecvf.com/',
    '2026-06-03',
    '2026-06-07',
    'Colorado Convention Center',
    'Denver, USA',
    'CVPR (IEEE/CVF Conference on Computer Vision and Pattern Recognition) is a flagship venue for computer vision, video understanding, and related machine learning research.',
    NULL,
    '[CVPR 2026](https://cvpr.thecvf.com/)',
    'https://huggingface.co/datasets/ai-conferences/CVPR2026'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    short_name = EXCLUDED.short_name,
    year = EXCLUDED.year,
    url = EXCLUDED.url,
    start_date = EXCLUDED.start_date,
    end_date = EXCLUDED.end_date,
    venue = EXCLUDED.venue,
    location = EXCLUDED.location,
    description = EXCLUDED.description,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    hf_url = EXCLUDED.hf_url,
    updated_at = CURRENT_TIMESTAMP;
```

Apply to the live DB:

```bash
uv run --env-file backend/keys.env python3 - <<'PY'
from pathlib import Path
from sqlalchemy import text
from backend.database.connection import db_manager

sql = Path("backend/database/migrations/add_<slug>_conference.sql").read_text()
with db_manager.engine.begin() as conn:
    conn.execute(text(sql))
PY
```

For large paper imports, follow the idempotent Python pattern in existing setup scripts instead of raw SQL:

- `backend/database/conferences_setup/import_cvpr2026.py`
- `backend/database/conferences_setup/import_iclr2026.py`
- `backend/database/conferences_setup/import_icra2026.py`

### 5. Paper linking

When importing accepted papers:

1. Upsert the conference row first (step 4).
2. For each paper: create or update the `papers` row, set `proceeding` (e.g. `CVPR 2026`, `CVPR 2026 Oral`, `CVPR 2026 Spotlight`), and insert into `paper_conferences`.
3. Link repos/project pages when present in the source CSV.
4. Run task keyword backfill if new papers were added:

```bash
uv run --env-file backend/keys.env \
    backend/database/tasks_setup/link_papers_by_task_keywords.py
```

Use `source = 'manual'` on `paper_conferences` for admin/script imports unless a dedicated importer tag exists.

### 6. Optional: deadlines

The database is the source of truth for https://paperswithcode.co/ai-deadlines
(the huggingface/ai-deadlines YAML repo is no longer imported). Scheduled sweeps
(`sweep_conference_deadlines` / `refresh_conference_deadlines`) research new
editions and deadline changes; to set or correct an edition's deadlines by hand,
use the audited admin endpoint. The list replaces the edition's deadlines, dates
are local times in each deadline's timezone (write `AoE` for Anywhere on Earth),
and `short_name` creates the edition when the slug does not exist yet:

```bash
curl -X PUT https://paperswithcode.co/api/v1/conferences/<series>-<year>/deadlines \
  -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"short_name": "CVPR", "url": "https://cvpr.thecvf.com/Conferences/2027",
       "deadlines": [
         {"type": "abstract", "label": "Abstract Submission", "date": "2026-11-06 23:59:59", "timezone": "AoE"},
         {"type": "paper", "label": "Paper Submission", "date": "2026-11-13 23:59:59", "timezone": "AoE"}
       ]}'
```

Deadline series and edition slugs follow `<series>-<year>` (e.g. `cvpr-2027`).

## Database Access

Run Python and project CLIs from the repo root:

```bash
uv run --env-file backend/keys.env python3 ...
```

Keep writes scoped to the requested conference edition. Do not rewrite unrelated conference metadata or paper links.

## Verification

Before reporting done:

1. Conference row:

```sql
SELECT id, slug, name, year, image_url, image_mime_type, hf_url
FROM conferences
WHERE slug = '<slug>';
```

2. Linked paper count:

```sql
SELECT COUNT(*) FROM paper_conferences pc
JOIN conferences c ON c.id = pc.conference_id
WHERE c.slug = '<slug>';
```

3. Conference API (expect `"image_url": "/api/v1/conferences/<slug>/image"` when DB image imported):

```bash
curl -fsS "http://localhost:8000/api/v1/conferences/<slug>" | uv run python3 -m json.tool
curl -fsS -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/v1/conferences/<slug>/image"
```

If the API is stale, verify the database row directly and report the stale API
response. Do not start or restart deployed services during data curation.

## Reporting Back

Always include:

- **Production conference URL**: `https://paperswithcode.co/conferences/<slug>`
- **Edition metadata**: year, dates, venue/location when set
- **Thumbnail**: confirm `/api/v1/conferences/<slug>/image` returns HTTP 200 after import
- **Paper import summary**: papers created/updated, `paper_conferences` links added (if applicable)
- **HF link**: `hf_url` when set

## Reference: recent conference additions

| Slug | Notes |
|------|-------|
| `cvpr-2026` | CSV import from `data/cvpr2026_papers.csv`; DB-backed hero image |
| `iclr-2026` | ICLR 2026 edition with HF dataset link |
| `icra-2026` | Robotics venue edition |
