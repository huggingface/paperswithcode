---
name: add-task
description: Add or update AI/ML task taxonomy rows in the paperswithcode repo database. Use this whenever the user asks to add a task, create a new benchmark category, add a subtask under an existing task, set task description/keywords/area/image, or expand task coverage; says phrases like "add X as a task", "create a task page for", "similarly add this task", or "we need a task for"; or names a research area (ASR, object detection, agents, tabular learning) that should become a browsable /tasks/ page with keywords and a hero image. After adding the task, recommend standard benchmarks to link next (use add-benchmark when the user wants them ingested).
---

# Add a Task

This skill adds curated rows to the `tasks` table so task pages, paper tagging, and benchmark leaderboards render correctly. Prefer small idempotent migrations plus applying the same change to the live database.

> **Image storage:** seed PNG → `/tmp/paperswithcode_entity_image_seeds/tasks/<slug>.png` → `import_entity_image.py` → SQL bytes served at `/api/v1/tasks/<slug>/image`. Do **not** put task heroes in `frontend/public/` (that folder is for browser assets only: favicons, `og-image.png`, logos).

When the user says **"similarly add X"** (often with just a name and area), run the full workflow below without re-asking — same area, parent, keywords, thumbnail, keyword backfill, and deploy steps as the prior task in the conversation unless they specify otherwise.

When the user asks **"should we add X?"**, briefly judge whether the topic is distinct enough from an existing task slug (e.g. `object-detection` vs `3d-object-detection`, `image-restoration` vs `image-super-resolution`). If yes, add it; if it is only a synonym or a narrow variant of an existing task, say so and suggest updating keywords on the existing row instead.

## End-to-End Checklist

For a typical new top-level task:

1. Confirm the task does not already exist (`slug`, `name`, `keywords`).
2. Pick the right **area** and optional **parent** (subtask vs top-level).
3. Write metadata + migration SQL (or `ensure_task` Python script).
4. Add hero image: save seed PNG under `/tmp/paperswithcode_entity_image_seeds/tasks/<slug>.png`, then import into SQL (see Thumbnail).
5. Apply migration to the live DB.
6. Run keyword backfill so existing papers get tagged (see Keyword linking).
7. Verify API + report production URL.

Skip keyword backfill only when the user explicitly asks for the task row alone.

8. **Recommend benchmarks** the user should add next (do not auto-add unless they ask — use `add-benchmark` for ingestion).

## Core Rules

Tasks are first-class taxonomy nodes. Each task gets its own page at `/tasks/<slug>` with description, linked benchmarks, and paper counts.

- **Top-level tasks** have `parent_id = NULL` and `level = 0`.
- **Subtasks** are child rows with `parent_id` pointing at the parent task and `level = parent.level + 1`. Each subtask has its own page, benchmarks, and evaluations. Example: `language-modeling` (level 0) → `world-knowledge`, `math`, `coding` (level 1).
- **`area_id`** groups tasks for area browse pages. It does **not** drive the "Sister Tasks" sidebar — that uses the explicit `task_sister_tasks` table when curated.
- **`keywords`**: comma-separated phrases used by the keyword matcher to tag papers. Include exact name, hyphenated variants, common abbreviations, and related phrasing researchers use in titles/abstracts. Follow casing rules in `docs/keyword-matching.md` (lowercase for phrases, preserve caps for acronyms like `ASR`, `MOT`, `VLM`).
- **Descriptions**: one concise paragraph — what the task is, typical inputs/outputs, and why it matters. Link related on-site tasks with relative markdown, e.g. `[Object Detection](/tasks/object-detection)`, `[Image Segmentation](/tasks/image-segmentation)`. Never hard-code `paperswithcode.co` or localhost inside markdown fields.
- **Images**: curated self-hosted heroes are stored in SQL (`image_data` / `image_mime_type`) and served at `/api/v1/tasks/{slug}/image`. Do **not** add runtime assets under `frontend/public/images/`. Legacy rows may still have external `image_url` values; new tasks should import a local PNG into the DB (see Thumbnail).

## Workflow

### 1. Understand the requested task

- Record name, target area (Vision, Language, Audio, Video, General, Other), whether it is a **subtask** of an existing task, and any image the user attached.
- Pick a stable slug: lowercase words joined by hyphens (`tabular-learning`, `object-tracking`, `image-super-resolution`). Prefer community naming over internal jargon.
- Search for an existing task by `name`, `slug`, and `keywords` before creating a new row.
- Query sibling tasks in the same area or under the same parent to calibrate description tone and keyword coverage.

Live DB areas:

| Area | Typical use |
|------|-------------|
| `Vision` | Image/video understanding, 3D vision, segmentation, detection |
| `Language` | NLP, LLMs, translation, QA |
| `Audio` | ASR, audio classification, speech/audio understanding |
| `Video` | Video understanding, tracking, video generation |
| `General` | Cross-modal agents, robotics-adjacent, multi-domain |
| `Other` | Tabular, biology, niche domains |

Area lookup in SQL:

```sql
(SELECT id FROM areas WHERE name = 'Vision' LIMIT 1)
-- Language, Audio, Video, General, Other — same pattern
```

### 2. Choose metadata

- **`name`**: display title (e.g. `Tabular Learning`, `Object Tracking`, `Image super-resolution`).
- **`description`**: one paragraph; link related tasks/methods on-site when helpful.
- **`keywords`**: broad coverage for paper tagging — task name, aliases, abbreviations, compound phrases (`multi-object tracking, MOT, visual object tracking`).
- **`area_id`**: resolve by area name (see table above).
- **`parent_id` / `level`**: set only for subtasks. Look up parent by slug; `level = parent.level + 1`.
- **`image_url`**: leave NULL for new self-hosted images — the API resolves `/api/v1/tasks/<slug>/image` once `image_mime_type` is set. Use an external URL only when you cannot self-host.
- **`image_credit`**: attribution as markdown link or plain URL, e.g. `[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)` or a source paper link `[Paper title](/paper/2005.08100)`.
- **`useful_leaderboards`**: optional comma-separated external leaderboard URLs (HF Spaces, community leaderboards) when the user provides them or you find a canonical one for the domain.

### 3. Thumbnail

Task hero images are DB-backed. Save a seed PNG, import it, then verify the API image endpoint.

**If the user provides an image**, copy it to:

```text
/tmp/paperswithcode_entity_image_seeds/tasks/<slug>.png
```

**Otherwise**, find a suitable diagram:

1. Check whether a related task, survey paper, or benchmark homepage has a clear task illustration.
2. For arXiv-backed domains, download `https://arxiv.org/pdf/<arxiv_id>.pdf` and extract a figure with PyMuPDF (`fitz`) — same approach as `add-method`: locate figure captions, crop the main task diagram (not tables-only), render at 3× zoom.
3. Save to `/tmp/paperswithcode_entity_image_seeds/tasks/<slug>.png`.
4. Set `image_credit` to the source.

After the task row exists, import the PNG into SQL:

```bash
uv run --env-file backend/keys.env python backend/database/import_entity_image.py \
    tasks <slug> /tmp/paperswithcode_entity_image_seeds/tasks/<slug>.png
```

Prefer self-hosted DB images for new tasks. External hotlinks are acceptable only when licensing/hosting makes local copy impractical and the user agrees.

No frontend rebuild is needed for entity images — they are served from the backend API.

### 4. Create and apply migration

Add `backend/database/migrations/add_<slug>_task.sql` using `ON CONFLICT (slug) DO UPDATE`.

**Top-level task** example:

```sql
INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    '<Name>',
    '<slug>',
    '<description with [Related Task](/tasks/related)>',
    '<keywords>',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    NULL,
    '[<credit label>](<url>)',
    NULL  -- or comma-separated external leaderboard URLs
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;
```

**Subtask** example — resolve parent first:

```sql
INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id
)
VALUES (
    '<Subtask Name>',
    '<subtask-slug>',
    '<description>',
    '<keywords>',
    (SELECT area_id FROM tasks WHERE slug = '<parent-slug>' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = '<parent-slug>' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = '<parent-slug>' LIMIT 1)
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    updated_at = CURRENT_TIMESTAMP;
```

Alternatively, use the idempotent Python pattern from existing setup scripts (`TaskService.create_task` + update-on-exists), e.g. `backend/database/tasks_setup/add_tabular_learning_task.py`.

Apply to the live DB:

```bash
uv run --env-file backend/keys.env python3 - <<'PY'
from pathlib import Path
from sqlalchemy import text
from backend.database.connection import db_manager

sql = Path("backend/database/migrations/add_<slug>_task.sql").read_text()
with db_manager.engine.begin() as conn:
    conn.execute(text(sql))
PY
```

### 5. Keyword linking

After the task row exists with `keywords`, tag **existing local papers** whose titles/abstracts match:

```bash
# Add-only (safe default): inserts new paper_tasks rows, never removes
uv run --env-file backend/keys.env \
    backend/database/tasks_setup/link_papers_by_task_keywords.py

# Rebuild auto tags for the whole corpus (only when user asks)
uv run --env-file backend/keys.env \
    backend/database/tasks_setup/link_papers_by_task_keywords.py --rebuild
```

This inserts `paper_tasks` rows with `source = 'auto'`. Run this by default when adding a task unless the user opts out.

### 6. Optional: sister tasks

When the user wants related tasks shown in the sidebar, insert into `task_sister_tasks`:

```sql
INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, v.ord
FROM tasks t
CROSS JOIN (VALUES ('<sister-slug>', 0), ('<other-sister-slug>', 1)) AS v(slug, ord)
JOIN tasks s ON s.slug = v.slug
WHERE t.slug = '<slug>'
ON CONFLICT DO NOTHING;
```

Sister links are **directed** — configuring A → B does not imply B → A.

### 7. Recommend benchmarks (required in report)

Do **not** silently create benchmark rows unless the user asked. Instead, research and return a curated recommendation list.

To build recommendations:

1. **Query existing datasets** already linked to similar tasks:

```sql
SELECT t.slug AS task_slug, d.name, d.slug, m.name AS metric
FROM task_datasets td
JOIN tasks t ON t.id = td.task_id
JOIN datasets d ON d.id = td.dataset_id
LEFT JOIN task_dataset_metrics tdm ON tdm.task_id = td.task_id AND tdm.dataset_id = td.dataset_id
LEFT JOIN metrics m ON m.id = tdm.metric_id
WHERE t.slug IN ('<similar-task-1>', '<similar-task-2>')
ORDER BY t.slug, d.name;
```

2. **Search `datasets`** by name/slug for benchmarks commonly associated with the new task but not yet linked.
3. **Use domain knowledge** — pick community-standard benchmarks researchers expect on a PapersWithCode task page (e.g. COCO/LVIS for object detection, LibriSpeech for ASR, GLUE/SuperGLUE for classic NLP).
4. For each recommendation, note:
   - Benchmark name and whether it already exists in `datasets`
   - Suggested metric (e.g. `mAP`, `WER`, `Accuracy`)
   - Whether it is already linked to a sibling task (reuse vs new `add-benchmark` work)
   - Source paper if known (for `add-benchmark` provenance)

When the user wants benchmarks ingested, switch to the **`add-benchmark`** skill.

## Database Access

Run Python and project CLIs from the repo root:

```bash
uv run --env-file backend/keys.env python3 ...
```

Keep writes scoped to the requested task. Do not rewrite unrelated task metadata or paper tags.

## Verification

Before reporting done:

1. Task row:

```sql
SELECT t.id, t.slug, t.name, t.area_id, a.name AS area,
       t.parent_id, t.level, t.image_url, t.image_mime_type
FROM tasks t
LEFT JOIN areas a ON a.id = t.area_id
WHERE t.slug = '<slug>';
```

2. Keyword-tagged paper count:

```sql
SELECT COUNT(*) FROM paper_tasks pt
JOIN tasks t ON t.id = pt.task_id
WHERE t.slug = '<slug>';
```

3. Task API (expect `"image_url": "/api/v1/tasks/<slug>/image"` when DB image imported):

```bash
curl -fsS "http://localhost:8000/api/v1/tasks/<slug>" | uv run python3 -m json.tool
curl -fsS -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/v1/tasks/<slug>/image"
```

4. Task datasets (may be empty until benchmarks are added):

```bash
curl -fsS "http://localhost:8000/api/v1/tasks/<slug>/datasets" | uv run python3 -m json.tool
```

If the API is stale, verify the database row directly and report the stale API
response. Do not start or restart deployed services during data curation.

## Reporting Back

Always include:

- **Production task URL**: `https://paperswithcode.co/tasks/<slug>`
- **Hierarchy**: top-level or subtask of `<parent-slug>` (with level)
- **Area** assigned
- **Thumbnail**: confirm `/api/v1/tasks/<slug>/image` returns HTTP 200 after import
- **Keyword linking summary**: how many papers tagged after backfill
- **Recommended benchmarks** — numbered list with:
  - Benchmark name
  - Suggested metric
  - Whether it already exists in DB / is linked to a sibling task
  - One-line rationale
  - Note: "Run `add-benchmark` to ingest these" unless the user already asked to add them

Example recommendation block:

```text
Recommended benchmarks to add next:
1. COCO val2017 (metric: mAP) — already in DB, linked to object-detection; link to this task via add-benchmark
2. LVIS (metric: mAP) — standard open-vocabulary detection benchmark
3. Objects365 — widely used in recent detection papers
```

## Reference: recent task additions

| Slug | Area | Notes |
|------|------|-------|
| `tabular-learning` | Other | Self-hosted thumbnail; tabular foundation model keywords |
| `image-super-resolution` | Vision | Local image; related to image-restoration |
| `autonomous-driving` | General | CVPR coverage batch; keywords for BEV/ADAS |
| `agents` | General | Self-hosted thumbnail; sister links to coding-agents, language-modeling |
