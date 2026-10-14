---
name: create-thumbnail
description: Create, replace, audit, and publish Papers With Code paper thumbnails for one paper or every paper on a benchmark page. Use this whenever a user asks to add a thumbnail, fix an "Untitled resource" card, use artwork from a source/project/GitHub README, regenerate a paper preview, or find papers on a benchmark with missing, generic, stale, or broken thumbnails. This is the repo-specific end-to-end workflow for source selection, portrait composition, cache-safe publication, and live visual verification.
---

# Create paper thumbnails

Create recognizable paper-card thumbnails from authoritative source material. A thumbnail is not complete merely because a URL exists: blank captures and generic “Untitled resource” cards count as missing.

## Guardrails

Skill scripts live under `.agents/skills/create-thumbnail/` (the canonical, tracked path). `.claude/skills/` is a gitignored symlink layer that may be missing in worktrees.


- Work from the repository root and run repository Python with `uv run --env-file backend/keys.env ...`.
- Read `docs/database.md` before database access.
- Treat thumbnail publication as a data operation. Do not restart services or deploy application code.
- Branch on paper source before choosing an image: arXiv papers use a rendered first page; source/project visuals are only for non-arXiv papers.
- Preserve source artwork faithfully. Do not redraw logos, alter plots, or use generated imagery when an official image or paper page is available.
- Keep the audit read-only until the user has requested creation or replacement.
- Use immutable or content-addressed filenames. A query-string cache marker alone may not bypass the public image proxy.

## 1. Resolve the scope

For a paper URL, resolve the numeric paper ID and inspect its title, source, source URL, arXiv ID/version, repositories, project pages, Hugging Face artifacts, and current `thumbnail_url`.

For a benchmark URL, resolve `datasets.slug`, then collect distinct papers through `evaluations.dataset_id`. Audit every linked paper, not only external rows.

Run the bundled read-only audit:

```bash
uv run --env-file backend/keys.env python \
  .agents/skills/create-thumbnail/scripts/audit_thumbnails.py \
  --paper 109261

uv run --env-file backend/keys.env python \
  .agents/skills/create-thumbnail/scripts/audit_thumbnails.py \
  --benchmark tabarena-v0-1
```

The audit distinguishes:

- `missing_url`: the public paper API has no thumbnail URL.
- `broken`: the URL does not return an image successfully.
- `review_default_external`: an external paper uses the default `external_<id>.jpg` filename. Visually inspect it because it may be a useful PDF render or a generic browser capture.
- `healthy`: reachable image; still inspect when the user reports poor content.

Do not infer visual quality from HTTP status alone. Download candidates and use `view_image` or a montage.

## 2. Choose the thumbnail source

Choose the source from the paper record before inspecting visual candidates.

### ArXiv papers: always render the first page

When the paper has an arXiv ID or `source = 'arxiv'`, use a screenshot/render of the first page of the matching arXiv PDF. Do not substitute a project hero, README image, logo, architecture diagram, model-card image, or generated title card, even when one appears more visually distinctive. The paper page represents the publication, and the first-page convention keeps arXiv-backed cards consistent and verifiable.

Verify that the PDF version matches the title displayed in the catalog. Older arXiv versions can have a different title; use the latest matching version and persist its explicit thumbnail URL when necessary.

### Non-arXiv papers: choose authoritative artwork

Only for papers without an arXiv ID, use this priority order:

1. A clear hero, architecture diagram, logo, or overview image visibly used by the canonical source page.
2. Artwork used in the official project page or official GitHub README.
3. Artwork in an explicit Hugging Face model card for the release.
4. The first page of an official direct PDF.
5. A title card using the real title only when no meaningful artwork or PDF exists.

Prefer a recognizable overview over a dense benchmark chart. Skip artwork wider than about 2:1 (wide pipeline diagrams become unreadable on the portrait card) and use the first page of the PDF instead. Ignore badges, CI shields, unrelated dependencies, citation images, and images from unofficial forks.

For GitHub, inspect both README references and the image assets in the repository tree:

```bash
gh api repos/OWNER/REPO/readme -H 'Accept: application/vnd.github.raw' > /tmp/REPO-README.md
rg -n '<img|!\[' /tmp/REPO-README.md
gh api 'repos/OWNER/REPO/git/trees/HEAD?recursive=1' \
  --jq '.tree[] | select(.type=="blob") | .path' \
  | rg -i '\.(png|jpe?g|webp|svg)$'
```

## 3. Render the portrait thumbnail

Paper cards expect a 400 px wide portrait JPEG. Source images should remain legible rather than being cropped to fill the frame.

For an official raster image, use the bundled deterministic compositor:

```bash
uv run python .agents/skills/create-thumbnail/scripts/compose_thumbnail.py \
  --input /tmp/source-art.png \
  --output /tmp/paper-thumbnail.jpg \
  --title 'OPTIONAL TITLE' \
  --background '#f7f5ff,#fff4ef'
```

The compositor:

- produces a 400×550 RGB JPEG;
- contains the full source image without cropping;
- respects alpha transparency;
- uses a restrained background derived from explicit colors;
- adds text only when requested, usually when a logo lacks the paper/model name.

For every arXiv paper, use the existing repository command to render and publish the first page:

```bash
uv run --env-file backend/keys.env pwc thumbnail PAPER_REFERENCE --json
```

Do not run the raster compositor for an arXiv paper. For a non-arXiv direct PDF, use `ThumbnailService._convert_pdf_to_thumbnail` on the downloaded PDF, then publish the resulting image through the helper below. Inspect the render before publication.

If `pwc thumbnail` or the automatic path yields the blank "Untitled resource" card for a non-arXiv PDF (seen with a 32 MB PDF), download the PDF to a local file, render page 1 with `ThumbnailService._convert_pdf_to_thumbnail` from that local copy, and publish the result with the helper below.

## 4. Publish without stale-cache collisions

Publish a prepared JPEG with the bundled helper:

```bash
uv run --env-file backend/keys.env python \
  .agents/skills/create-thumbnail/scripts/publish_thumbnail.py \
  --paper-id 109261 \
  --image /tmp/paper-thumbnail.jpg
```

The helper validates the image, names it with a content digest, uploads it through `ThumbnailService`, updates only the target paper row, and prints JSON. Content-addressed filenames make a changed image a genuinely new URL, avoiding the stale-image behavior seen when only `&v=` changes.

For the required arXiv first page generated by `pwc thumbnail`, the command already uploads the image and persists a cache-busted URL. If a newer arXiv version is required than the database row currently names, render that version explicitly and publish it under its matching versioned filename or through the custom helper; do not show a first page whose title contradicts the paper page.

## 5. Verify live

Verification has three layers:

1. Fetch `https://paperswithcode.co/api/v1/papers/<id>` and confirm the expected `thumbnail_url`.
2. Fetch the exact public thumbnail URL and confirm HTTP 200, `image/*`, JPEG/RGB, width 400, and portrait height.
3. Download and visually inspect the public response. Inspecting only the local preview can miss stale CDN content.

For benchmark work, rerun the audit and require every linked paper to have a healthy public image. Create a montage of changed thumbnails for a final visual scan.

## Reporting

Report:

- the paper or benchmark URL;
- every paper changed;
- the source used for each image (arXiv PDF/version, or README/project/model-card artwork for a non-arXiv paper);
- the final full-benchmark healthy count when applicable;
- any candidate deliberately left unchanged and why.

Include a rendered image or montage when useful. Data-only thumbnail work does not require a git commit or application deployment.
