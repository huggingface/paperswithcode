---
name: add-method
description: Add or update AI/ML method taxonomy rows in the paperswithcode repo database. Use this whenever the user asks to add a method, technique, architecture, attention mechanism, training method, model-family method, or source/visual metadata for a method; says phrases like "make GPT-4 a method", "add X as a method", "similarly add this method", "link papers that cite the source paper", or "update the method source to point to the paper page"; or gives a method name plus a paper, arXiv id, PapersWithCode URL, Hugging Face report, GitHub explainer, blog post, or image for the method thumbnail.
---

# Add a Method

This skill adds curated rows to the `methods` table so method pages, paper pages, and "Introduced" banners render correctly. Prefer small idempotent migrations plus applying the same change to the live database.

> **Image storage:** seed PNG → `/tmp/paperswithcode_entity_image_seeds/methods/<slug>.png` → `import_entity_image.py` → SQL bytes served at `/api/v1/methods/<slug>/image`. Do **not** put method figures in `frontend/public/` (that folder is for browser assets only: favicons, `og-image.png`, logos).

When the user says **"similarly add X"** (often with just a name and source arXiv id), run the full workflow below without re-asking — same area, citation linking, thumbnail, and deploy steps as the prior method in the conversation unless they specify otherwise.

When the user asks **"should we add X?"**, briefly judge whether the technique is distinct enough from an existing method slug (e.g. Fast Conformer vs Conformer, TDT vs RNN-Transducer). If yes, add it; if it is only a hyperparameter variant or product name with no introducing paper, say so and stop.

## End-to-End Checklist

For a typical new method with a source paper:

1. Confirm the method does not already exist (`slug`, `name`, `keywords`).
2. Decide whether the method has an introducing paper at all (see No introducing paper). If it does, confirm the source `papers` row exists (import first if needed).
3. Write metadata + migration SQL.
4. Add hero image: save seed PNG under `/tmp/paperswithcode_entity_image_seeds/methods/<slug>.png`, then import into SQL (see Thumbnail).
5. Apply migration to the live DB.
6. Link papers: **all local papers that cite the source paper** (see Citation linking), or, for a method without an introducing paper, a reviewed candidate set (see No introducing paper).
7. Verify API + report production URL.

Skip citation linking only when the user explicitly asks for the method row alone.

## Core Rules

Method source links should point to the canonical source that introduced the method.

- If the source exists as a local `papers` row, set `methods.source_paper_id` and leave `methods.source_url = NULL`. The API will expose a native route like `/paper/{arxiv_id}` or `/paper/{paper_id}`.
- If the method has no real source paper, use a clear source/explainer URL in `methods.source_url` and `methods.source_title`.
- Do not use an external PDF, arXiv URL, Hugging Face PDF, GitHub README, or blog as `source_url` when the actual source paper already has a local PapersWithCode page.
- If a paper introduced the method, also insert `(source_paper_id, method_id)` into `paper_methods`; the paper detail "Introduced" banner depends on the method appearing in `paper.methods`, not just on `methods.source_paper_id`.

Be careful about provenance. The source paper is the paper that introduced, named, or formally described the method. A later explainer, implementation tutorial, or model card can be useful for `code_snippet_url`, `image_url`, and `image_credit`, but it is not the canonical source if an introducing paper exists.

### No introducing paper

Not every method has an introducing paper. Broad techniques and research areas often grew out of many earlier works before one paper made them popular. Examples are Neural Architecture Search, which started with neuroevolution of network topologies years before Zoph & Le (1611.01578) popularized the term. Others are product or tooling concepts that come from docs or blog posts, such as MCP, function calling and context engineering. Before setting `source_paper_id`, check whether there were clear precursors. A paper that popularized, named or scaled up a technique is not its introducing paper if earlier work already did the same thing. When the user asks to tag a paper "with method X", that paper is not automatically X's source. If the provenance is contested, treat the method as having no introducing paper.

For such methods:

- Keep `source_paper_id = NULL`. Put an authoritative explainer in `source_url` and `source_title`: a well-known survey, a canonical reference, or official docs. Do not insert a `source` evidence row, and do not add an "Introduced" banner.
- Leave `introduced_year = NULL` unless the origin year is well established.
- In the description, credit the seminal and popularizing papers with relative `/paper/...` links instead of calling either one "the original".
- `image_credit` may still point to the paper the figure came from.
- Skip `link_papers_by_source_citations.py`, because there is no source to collect citations from. The hourly `backfill_method_references` CRON also skips methods without a source paper. Instead, collect candidates from titles and abstracts (and from the citers of seminal papers), then review each one. Insert the true positives with `'manual'` evidence, and write the reviewed negatives to `paper_method_exclusions`. The daily keyword backfill honors those exclusions and would otherwise re-link papers that only mention the method in passing. `add_neural_architecture_search_method.sql` is the reference migration.

For methods that do have a source paper, keep in mind that the hourly reference backfill links every local paper citing it. For broad, highly cited sources, that citation signal can be poor: only 41% of NAS citers were NAS papers. So review those citers as well, and write exclusions for the ones that don't belong.

## Workflow

### 1. Understand the requested method

- Record name, abbreviation, source arXiv id, target area (e.g. Audio, Vision, Language), and any image the user attached.
- Pick a stable slug: lowercase words joined by hyphens (`conformer`, `fast-conformer`, `rnn-transducer`, `tdt`). Prefer the name the community uses over internal abbreviations unless the abbreviation is the primary label (e.g. `TDT` with slug `tdt`).
- Search for an existing method by `name`, `slug`, `full_name`, and `keywords` before creating a new row.

### 2. Resolve the source

- Query `papers` by arXiv id or PapersWithCode paper URL.
- If no local paper row exists for a non-ArXiv resource, use the `add-external-paper` skill first, then return here.
- If the user says there is no source paper, or the method has no clear introducing paper (see No introducing paper), set `source_url`/`source_title` and keep `source_paper_id = NULL`.
- For model-family follow-ups (GPT-2 → GPT-3, Conformer → Fast Conformer), use `pwc paper lineage add` when the user also wants predecessor/successor paper links.

### 3. Choose metadata

- **`name`**: short display name (e.g. `Conformer`, `RNN-Transducer`, `TDT`).
- **`full_name`**: expanded form with abbreviation when useful (e.g. `Token-and-Duration Transducer (TDT)`).
- **`description`**: one concise paragraph — what it does, why it matters, one concrete result if grounded in the source. Link related methods on-site, e.g. `[Conformer](/methods/conformer)`, `[RNN-Transducer](/methods/rnn-transducer)`, `[Transformer](/methods/transformer)`. Use relative links only; never hard-code `paperswithcode.co` or localhost inside markdown fields.
- **`keywords`**: exact name, abbreviation, hyphenated variants, common aliases (`RNNT`, `FastConformer`, etc.).
- **`area_id`**: resolve by area name. Live DB areas include `Audio`, `Vision`, `Language`, `Video`, `General`, `Other`. Use the area the user names (e.g. speech/ASR methods → `Audio`).
- **`introduced_year`**: source paper publication year.
- **`code_snippet_url`**: optional pointer to a canonical implementation file (NeMo, ESPnet, torchaudio, official repo) — not the introducing paper PDF.
- **`image_url`**: leave NULL for new self-hosted images — the API resolves `/api/v1/methods/<slug>/image` once `image_mime_type` is set. Use an external URL only when you cannot self-host.
- **`image_credit`**: relative markdown link to the source paper, e.g. `[Paper title](/paper/2005.08100)`.

### 4. Thumbnail

Method figures are DB-backed. Save a seed PNG, import it, then verify the API image endpoint.

**If the user provides an image**, copy it to:

```text
/tmp/paperswithcode_entity_image_seeds/methods/<slug>.png
```

**Otherwise**, extract a figure from the source PDF:

1. Download `https://arxiv.org/pdf/<arxiv_id>.pdf`.
2. Use PyMuPDF (`fitz`) to find figure captions (`Figure 1`, `Figure 2`, …) and large drawing bounding boxes per page.
3. Render the best architecture diagram (not a table-only or caption-only crop) at 3× zoom with `page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip_rect)`.
4. Save to `/tmp/paperswithcode_entity_image_seeds/methods/<slug>.png`.
5. Visually sanity-check the crop — exclude caption text below the figure when possible.

After the method row exists, import the PNG into SQL:

```bash
uv run --env-file backend/keys.env python backend/database/import_entity_image.py \
    methods <slug> /tmp/paperswithcode_entity_image_seeds/methods/<slug>.png
```

Prefer the main architecture diagram (encoder block, lattice, joint network) over alignment heatmaps unless the user asks otherwise.

**Never generate or draw the image.** Do not use AI-generated, matplotlib-drawn, or hand-made illustrations, and never credit one as "Illustration by Papers with Code". Every method image must be a real figure with attribution. When the source paper has no usable figure (classic or pre-arXiv methods, code-only papers), use, in this order:

1. A figure from a later paper that explains the method (survey, follow-up), credited as `[Title](/paper/<id>)`.
2. A Creative Commons or public-domain figure from Wikimedia Commons, credited as a markdown link to its Commons file page, plus author and license in the same string (for example `[Gradient descent](https://commons.wikimedia.org/wiki/File:Gradient_descent.svg), public domain`). Respect share-alike and attribution terms.
3. If neither exists, leave the image empty rather than inventing one, and tell the user.

Skip figures with no open license (company blogs, system cards) unless the user supplies the image.

No frontend rebuild is needed for entity images — they are served from the backend API.

### 5. Create and apply migration

Add `backend/database/migrations/add_<slug>_method.sql` using `ON CONFLICT (slug) DO UPDATE` and the source-paper `paper_methods` insert.

Area lookup examples:

```sql
-- Audio (speech / ASR methods)
(SELECT id FROM areas WHERE name = 'Audio' LIMIT 1)

-- Language (NLP methods; fallback for legacy DBs)
(SELECT id FROM areas WHERE name IN ('Language', 'Natural Language Processing')
 ORDER BY CASE name WHEN 'Language' THEN 0 ELSE 1 END LIMIT 1)

-- Vision
(SELECT id FROM areas WHERE name = 'Vision' LIMIT 1)
```

Example migration shape:

```sql
INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit
)
VALUES (
    '<slug>',
    '<Name>',
    '<Full Name>',
    '<description with [Related Method](/methods/related)>',
    '<keywords>',
    (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
    <year>,
    (SELECT id FROM papers WHERE arxiv_id = '<arxiv_id>'
     ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    '<source paper title>',
    '<implementation URL>',
    NULL,
    '[<source paper title>](/paper/<arxiv_id>)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = '<slug>' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
```

Apply to the live DB:

```bash
uv run --env-file backend/keys.env python3 - <<'PY'
from pathlib import Path
from sqlalchemy import text
from backend.database.connection import db_manager

sql = Path("backend/database/migrations/add_<slug>_method.sql").read_text()
with db_manager.engine.begin() as conn:
    conn.execute(text(sql))
PY
```

If the migration contains paper titles in SQL comments (curated lists), run it with `conn.connection.cursor().execute(sql)` instead. `text()` treats `:word` as a bind parameter, and `exec_driver_sql` fails on `%`.

### 6. Citation linking

After the method row exists with `source_paper_id`, tag every **local** paper that Semantic Scholar lists as citing the source paper:

```bash
# Optional dry-run first
uv run --env-file backend/keys.env python \
    backend/database/methods_setup/link_papers_by_source_citations.py \
    --method-slug <slug>

# Apply links
uv run --env-file backend/keys.env python \
    backend/database/methods_setup/link_papers_by_source_citations.py \
    --method-slug <slug> --write
```

This inserts `paper_methods` rows for citing papers already in our database. Papers not yet imported are skipped (Semantic Scholar may list thousands of citations; only in-DB papers are linked). Run this by default when adding a method unless the user opts out.

The user may also ask to **"link all papers that cite the source paper"** for an existing method — run the same script with `--method-slug`.

## Database Access

Run Python and project CLIs from the repo root:

```bash
uv run --env-file backend/keys.env python3 ...
```

Keep writes scoped to the requested method. Do not rewrite unrelated method metadata or paper tags.

## Verification

Before reporting done:

1. Method row + source paper:

```sql
SELECT m.id, m.slug, m.name, m.source_paper_id, p.arxiv_id
FROM methods m
LEFT JOIN papers p ON p.id = m.source_paper_id
WHERE m.slug = '<slug>';
```

2. Source paper has `paper_methods` row (introduced banner):

```sql
SELECT COUNT(*) FROM paper_methods pm
JOIN methods m ON m.id = pm.method_id
WHERE m.slug = '<slug>' AND pm.paper_id = m.source_paper_id;
```

3. Citation-linked paper count:

```sql
SELECT COUNT(*) FROM paper_methods pm
JOIN methods m ON m.id = pm.method_id
WHERE m.slug = '<slug>';
```

4. Method API (`paper_count` should reflect source + citing papers; expect DB image URL when imported):

```bash
curl -fsS "http://localhost:8000/api/v1/methods/<slug>" | uv run python3 -m json.tool
curl -fsS -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/v1/methods/<slug>/image"
```

5. Source paper lists the method (introduced banner):

```bash
curl -fsS "http://localhost:8000/api/v1/papers/<arxiv_id>?include_resources=true" \
  | uv run python3 -c "import json,sys; p=json.load(sys.stdin); print([(m['slug'], m.get('source_paper_id')) for m in p.get('methods') or [] if m['slug']=='<slug>'])"
```

If the API is stale, verify the database row directly and report the stale API
response. Do not start or restart deployed services during data curation.

## Reporting Back

Always include:

- Production method URL: `https://paperswithcode.co/methods/<slug>`
- Source behavior: native `/paper/<arxiv_id>` via `source_paper_id`, or external `source_url`
- Whether `paper_methods` includes the source paper (introduced banner)
- Citation linking summary: how many Semantic Scholar citations fetched, how many local papers linked (`paper_count` on the method API)
- Thumbnail: confirm `/api/v1/methods/<slug>/image` returns HTTP 200 after import

## Reference: recent Audio methods

| Slug | Source arXiv | Notes |
|------|--------------|-------|
| `conformer` | 2005.08100 | Links to Transformer; user may supply custom thumbnail |
| `fast-conformer` | 2305.05084 | Links to Conformer |
| `rnn-transducer` | 1211.3711 | Lattice figure; foundation for TDT |
| `tdt` | 2304.06795 | Links to RNN-Transducer; joint token+duration heads |
