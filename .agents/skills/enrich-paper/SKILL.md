---
name: enrich-paper
description: >-
  Enrich an existing paperswithcode paper with its official GitHub repository, project page,
  Hugging Face artifacts, existing-taxonomy task/method tags, and a recognizable thumbnail through
  `create-thumbnail`. Use whenever the user asks to enrich a paper, attach its code or project page,
  improve its tags, fill missing links, replace Gemini URL extraction, or complete an arXiv/external
  paper page. Finds authentic URLs from cheap authoritative evidence, preserves existing tags and HF
  normalization, rejects false-positive repos, and fixes thumbnails that are missing, generic,
  “Untitled resource,” stale, broken, wrongly versioned, squat, letterboxed, or otherwise unsuitable.
---

# Enrich a Paper

This skill fills in the two things a freshly imported paper most often lacks:

1. **Code links** — the paper's *own* official GitHub repository and project page URL.
2. **Hugging Face artifacts** — official model, dataset, and Space URLs, synchronized into normalized artifact links.
3. **Taxonomy tags** — `tasks` and `methods` that already exist in the database, matched to what the paper is actually about.
4. **Thumbnail** — an authoritative, recognizable paper-card image, not merely a reachable URL or generic browser capture.

It is the agent-driven replacement for the Gemini URL-extraction cron (`backend/genai_steps/extract_github_and_project_page_url.py` + `backend/database/repos_and_pages_setup/batch_extract.py`). Instead of calling the Gemini API, **you** (the coding agent) fetch a small amount of evidence and reason over it yourself. The whole point is to find *authentic* URLs at low token cost, so prefer cheap structured sources first and only escalate to heavier ones (PDF text, project-page HTML) when something is still missing.

Writes go to the **live database** via existing services / the admin API, exactly like `add-external-paper`. Keep writes idempotent and scoped to the requested paper.

## Core principles

- **Authenticity over recall.** A GitHub or project-page URL is only valid if it is the paper's *own* artifact. Papers routinely cite *other* repos (baselines, datasets, frameworks, related work). A `github.com/...` on page 1 is **not** automatically the paper's repo. When in doubt, leave it out and report it — a false positive is worse than a miss.
- **Cheapest evidence first.** Each step below is more expensive than the last. Stop as soon as you confidently have both URLs. Never dump a whole PDF into your context — the first 2 pages (or the HF markdown) carry the code links.
- **Only existing taxonomy.** Tag with `tasks`/`methods` rows that already exist. Do not invent new ones (that's `add-task` / `add-method`). If the right concept is missing, pick the closest existing tag and report the gap.
- **Complement the crons, don't fight them.** Method tags are *also* added by the Semantic Scholar citation cron (papers that cite a method's source paper) and by the HF import keyword matcher. Your job is content-based tagging for *this* paper; a few high-confidence tags beat keyword stuffing.
- **Leave the paper card looking right.** Thumbnail completion is part of enrichment. A reachable image can still be incomplete when it is blank, generic, says “Untitled resource,” shows stale content, or uses the wrong arXiv-version title. Use the sibling `create-thumbnail` skill for the audit, source selection, composition, cache-safe publication, and live visual verification.

## Pre-flight

Run everything from the repo root with the project environment so the venv and secrets load:

```bash
uv run --env-file backend/keys.env ...
```

Confirm the API is up and grab the admin token + HF token:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/papers/recent?limit=1
ADMIN_TOKEN=$(grep '^PWC_ADMIN_API_TOKEN=' backend/keys.env | cut -d= -f2-)
HF_TOKEN=$(grep '^PWC_HF_TOKEN=' backend/keys.env | cut -d= -f2-)
```

If the API is unavailable, use direct database verification where supported or
report the blocker. Do not start or restart deployed services during curation.

## Step 0 — Resolve the paper row

You need the DB `paper_id` (and `arxiv_id` if any). Accept an arXiv id, a `paperswithcode.co/paper/<id>` URL, or an external paper. Read what's already linked so you can **merge** rather than clobber.

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine

ident = "2509.14033"  # arxiv_id, numeric paper id, or title fragment
with get_engine().connect() as conn:
    row = conn.execute(text("""
        SELECT id, arxiv_id, title, source, source_url, urls_extracted
        FROM papers
        WHERE arxiv_id = :ident OR CAST(id AS TEXT) = :ident OR title ILIKE :like
        ORDER BY is_latest_version DESC NULLS LAST, id DESC
        LIMIT 1
    """), {"ident": ident, "like": f"%{ident}%"}).mappings().first()
    print(dict(row) if row else "NOT FOUND")
PY
```

Then read existing tasks/methods/repos/project pages so you can merge:

```bash
curl -s "http://localhost:8000/api/v1/papers/<paper_id>?include_resources=true" \
  | uv run python -c "import json,sys; p=json.load(sys.stdin); print('tasks',[(t['id'],t['slug']) for t in p.get('tasks') or []]); print('methods',[(m['id'],m['slug']) for m in p.get('methods') or []]); print('repos',[(r.get('url'),r.get('is_official')) for r in p.get('repositories') or []]); print('project_pages',[pp.get('url') for pp in p.get('project_pages') or []])"
```

If the paper has no arXiv id (external paper), the arXiv-specific steps below don't apply — use the paper's `source_url`, linked GitHub README, or HF model card as the evidence surface instead, and skip straight to URL validation + tagging. If the paper row itself does not exist yet, this is the wrong skill — use `add-external-paper` first, then come back to enrich.

## Part A — GitHub repository & project page URL

Walk the layers in order. Carry forward whatever you've found; only escalate for what's still missing. After each candidate URL, **validate authenticity and liveness** (see "Validating URLs").

### Layer 1 — Hugging Face papers API (cheapest, most authoritative)

If the paper is on HF, authors/maintainers often already linked the repo and project page. Use the HF token to avoid rate limits.

```bash
curl -s -H "Authorization: Bearer $HF_TOKEN" \
  "https://huggingface.co/api/papers/<arxiv_id>" \
  | uv run python -c "import json,sys; d=json.load(sys.stdin); print('githubRepo:', d.get('githubRepo','')); print('projectPage:', d.get('projectPage',''))"
```

`githubRepo` and `projectPage` here are author-curated and can be trusted with light validation. If both are present and live, you're done with Part A.

The same surface has author/community comments that frequently contain the links (HF often surfaces the official repo here even when the abstract doesn't):

```bash
curl -s -H "Authorization: Bearer $HF_TOKEN" \
  "https://huggingface.co/api/papers/<arxiv_id>?field=comments" \
  | uv run python -c "import json,sys; d=json.load(sys.stdin); [print(c.get('author',{}).get('name'),'=>',c.get('data',{}).get('latest',{}).get('raw','')[:400]) for c in d.get('comments',[])]"
```

Prefer links posted by an author of the paper or its official org; treat random third-party comments with more suspicion.

### Layer 2 — Regex over abstract + HF markdown (cheap text)

The HF markdown rendering of a paper is small and link-rich. Read it and the abstract, and scan for the paper's own GitHub/project links:

```bash
# Markdown version of the paper page (note the .md suffix)
curl -sL -H "Authorization: Bearer $HF_TOKEN" "https://huggingface.co/papers/<arxiv_id>.md" -o /tmp/<arxiv_id>.md
# or: uv run --env-file backend/keys.env hf papers read <arxiv_id> > /tmp/<arxiv_id>.md
```

Patterns the existing pipeline uses (reuse them rather than reinventing):

- GitHub: `\bhttps?://github\.com[^\s]*\b`
- Project page (github.io is a strong signal but not required): `\bhttps?://[a-zA-Z0-9.-]+\.github\.io[^\s]*`

You can also call the repo's own helpers for the abstract-regex + HF-API combo:

```bash
uv run --env-file backend/keys.env python - <<'PY'
import asyncio
from backend.utils.paper_utils import (
    get_abstract, find_github_url, get_github_and_project_page_urls_from_daily_papers,
)
async def main():
    arxiv_id = "<arxiv_id>"
    gh_api, pp_api = await get_github_and_project_page_urls_from_daily_papers(arxiv_id)
    abstract = await get_abstract(arxiv_id)
    gh_abs = await find_github_url(arxiv_id=arxiv_id, abstract=abstract)
    print("hf_api github:", gh_api, "| hf_api project:", pp_api, "| abstract github:", gh_abs)
asyncio.run(main())
PY
```

A GitHub URL stated in the abstract ("code available at …", "we release … at …") is almost always authentic. A bare `github.com` link buried in markdown body text needs the authenticity check before you trust it.

### Layer 3 — First 2 pages of the PDF (only if still missing)

Many papers put the repo/project link in a first-page footnote or under the abstract, not in the HF metadata. Download the PDF and read **only the first two pages** to keep cost down:

```bash
curl -sL "https://arxiv.org/pdf/<arxiv_id>.pdf" -o /tmp/<arxiv_id>.pdf
pdftotext -l 2 -layout /tmp/<arxiv_id>.pdf - 2>/dev/null | head -c 12000
```

If `pdftotext` is unavailable, use the repo helpers (`extract_text_from_pdf` reads the first 2 pages; `extract_hyperlinks_from_pdf` pulls embedded hyperlinks, which often contain the clickable repo link even when the visible text is truncated):

```bash
uv run --env-file backend/keys.env python - <<'PY'
from backend.utils.pdf_utils import extract_text_from_pdf, extract_hyperlinks_from_pdf
print(extract_text_from_pdf("/tmp/<arxiv_id>.pdf", num_pages=2)[:8000])
print("LINKS:", [l["url"] for l in extract_hyperlinks_from_pdf("/tmp/<arxiv_id>.pdf") if "github.com" in l["url"] or "github.io" in l["url"]])
PY
```

Reason over this text yourself (this is the part that used to be the Gemini call). Decide which link, if any, is the paper's own repo/project page. Do **not** feed the whole PDF to anything — first two pages only.

### Layer 4 — Project-page HTML → GitHub (the Step-2 fallback)

Some papers only print a project-page URL and hide the real GitHub link inside the project page's HTML — this is the single highest-value step, because the layers above genuinely can't see it. If you have a project page but **no** GitHub yet, fetch the project page and look for the repo:

```bash
curl -sL "<project_page_url>" | grep -oE 'https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+' | sort -u | head
```

(Or use `WebFetch` on the project page and read off the "Code"/"GitHub" link.)

**Critical: project pages are built from website templates, so the HTML almost always contains a template's GitHub repo that is NOT the paper's code.** Grepping blindly here is the most common false-positive source. Reject these on sight:

- `github.com/eliahuhorwitz/Academic-project-page-template`
- `github.com/nerfies/nerfies.github.io` (and other `*/<name>.github.io` *page-source* repos)
- any `*-project-page`, `*-template`, `*.github.io` repo that is the page's own source rather than the method's code
- starter kits, analytics, or library repos referenced by the page's `<head>`/footer

Accept a repo only when it is plausibly the paper's *own* code. Strong signals: the owner matches the project-page subdomain owner (e.g. page `https://yimingc9.github.io/physiformer` → repo `github.com/yimingc9/PhysiFormer` ✓) or a paper author; the repo name matches the method/paper name; the page links it under a "Code"/"GitHub" button rather than a tiny "website template" credit in the footer. When the page exposes a "Code coming soon" placeholder and only the template repo is present, the correct answer is **no GitHub** — link the project page and move on. Examples seen in the wild: a page whose only GitHub link is `eliahuhorwitz/Academic-project-page-template` ⇒ no repo; a page linking both `owner/Method` and `owner/Method.github.io` ⇒ take `owner/Method`, not the `.github.io` page-source repo.

### Validating URLs (authenticity + liveness)

Before saving, every candidate must pass both:

1. **Liveness** — the URL resolves (HTTP 200). Reuse the repo helper or curl:
   ```bash
   uv run --env-file backend/keys.env python -c "import asyncio; from backend.utils.verify_url import verify_url; print(asyncio.run(verify_url('<url>')))"
   ```
   For GitHub, also confirm the repo exists and isn't a 404/empty redirect: `gh repo view <owner>/<repo> --json url,isArchived,description` (or `curl -sI`).
2. **Authenticity** — it is the paper's own artifact. Strong positive signals: stated in the abstract or a first-page footnote; linked as `githubRepo`/`projectPage` on the HF API; posted by an author/official-org comment; owner/org matches the authors' affiliation or the project page domain; project page and repo cross-link each other. Red flags that mean **reject**: the link sits in References / Related Work / a baseline-comparison table; it points to a well-known third-party project (a dataset, a framework, a different paper's repo); it is a **website-template / page-source repo** found in project-page HTML (`eliahuhorwitz/Academic-project-page-template`, `nerfies/nerfies.github.io`, any `*.github.io` page-source or `*-template` repo — see Layer 4); the owner is clearly unrelated to the authors and the project page. A `github.com` literal is required for a GitHub URL; a project page must *not* be a GitHub repo URL, and HF model/dataset/collection pages are **not** project pages (an HF Space can be only if explicitly presented as the project page).

When unsure, prefer no write and list the candidate under "needs review".

### Saving Part A results

GitHub repos and project pages are saved as **official** (`is_official=true`) and tagged with `source='ai_extraction'` to match the cron's provenance. Use the services directly (they normalize the GitHub URL and skip if an official one already exists):

```bash
uv run --env-file backend/keys.env python - <<'PY'
from backend.database.connection import get_database_session
from backend.services.repository_service import RepositoryService
from backend.services.project_page_service import ProjectPageService
from backend.utils.github_utils import parse_github_url

paper_id = <paper_id>
github_url = "<validated github url or ''>"
project_page_url = "<validated project page url or ''>"

session_gen = get_database_session()
db = next(session_gen)
try:
    if github_url:
        owner, name = parse_github_url(github_url)
        RepositoryService(db).create_repository_for_paper(
            paper_id=str(paper_id), url=github_url, owner=owner, name=name,
            num_stars=0, is_official=True, source="ai_extraction",
            skip_if_official_exists=True,
        )
    if project_page_url:
        ProjectPageService(db).create_project_page_for_paper(
            paper_id=str(paper_id), url=project_page_url,
            is_official=True, source="ai_extraction", skip_if_official_exists=True,
        )
    db.commit()
    print("saved", {"github": github_url, "project_page": project_page_url})
finally:
    try:
        next(session_gen)
    except StopIteration:
        pass
PY
```

After saving, mark the paper's `urls_extracted = TRUE` so the Gemini cron skips it. Set it only when you actually completed Part A — even a clean "nothing to find" result is a valid completion. Do **not** set it after a critical failure like a PDF download / reCAPTCHA error; leave it false so the paper is retried later.

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine
with get_engine().begin() as conn:
    conn.execute(text(
        "UPDATE papers SET urls_extracted = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = :i"
    ), {"i": <paper_id>})
print("urls_extracted set")
PY
```

### Save and verify Hugging Face artifacts

When the source, official repository, project page, or model card identifies
official HF models, datasets, or Spaces, merge them with the existing artifact
arrays and write the full set through the CLI:

```bash
uv run --env-file backend/keys.env pwc paper update <paper_id> hf-artifacts \
  --model "https://huggingface.co/<org>/<model>" \
  --dataset "https://huggingface.co/datasets/<org>/<dataset>" \
  --space "https://huggingface.co/spaces/<org>/<space>" \
  --json
```

This command is replace-style. Preserve existing URLs unless removal is
intentional. It synchronizes `paper_hf_artifacts` immediately and invalidates
the discovery checkpoint. Never update only the paper URL arrays with SQL,
because the UI can then display an HF link that contributes no normalized Hub
metrics to composite trending.

Verify the normalized relationship, not only the API arrays:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine
paper_id = <paper_id>
with get_engine().connect() as conn:
    rows = conn.execute(text("""
        SELECT a.kind, a.repo_id, a.trending_score
        FROM paper_hf_artifacts pha
        JOIN hf_artifacts a ON a.id = pha.hf_artifact_id
        WHERE pha.paper_id = :paper_id
        ORDER BY a.kind, a.repo_id
    """), {"paper_id": paper_id}).mappings().all()
    print([dict(row) for row in rows])
PY
```

## Part B — Task & method tags from the taxonomy

The goal is a small set of high-confidence tags that reflect what the paper does. Read the paper's abstract (and the first PDF pages or HF markdown you already fetched in Part A — don't re-download). You generally do **not** need the full paper for tagging.

### 1. Gather candidate tasks/methods from the DB

Search the live taxonomy for terms drawn from the paper's title/abstract. Cast a slightly wide net here, then narrow:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine

task_terms = ["speech recognition", "asr", "object detection"]      # from the paper
method_terms = ["transformer", "conformer", "rnn-transducer"]       # from the paper

with get_engine().connect() as conn:
    print("== TASKS ==")
    for q in task_terms:
        rows = conn.execute(text("""
            SELECT id, name, slug, level FROM tasks
            WHERE name ILIKE :q OR slug ILIKE :q OR keywords ILIKE :q
            ORDER BY level NULLS LAST, name LIMIT 15
        """), {"q": f"%{q}%"}).fetchall()
        print(q, [(r.id, r.slug) for r in rows])
    print("== METHODS ==")
    for q in method_terms:
        rows = conn.execute(text("""
            SELECT id, name, slug FROM methods
            WHERE name ILIKE :q OR slug ILIKE :q OR keywords ILIKE :q
            ORDER BY name LIMIT 15
        """), {"q": f"%{q}%"}).fetchall()
        print(q, [(r.id, r.slug) for r in rows])
PY
```

You can also lean on the project's own keyword matcher, which is exactly what the HF import cron uses (so your tags stay consistent with the rest of the corpus). Build the patterns with `create_keyword_patterns` (tasks) / `create_keyword_patterns_with_metadata` (methods), then match — the same calls `hf_paper_importer.py` makes:

```bash
uv run --env-file backend/keys.env python - <<'PY'
import asyncio
from sqlalchemy import text
from backend.database.connection import get_engine
from backend.utils.paper_utils import get_abstract, get_title
from backend.utils.keyword_matching import (
    create_keyword_patterns, create_keyword_patterns_with_metadata,
    find_matching_items_simple, find_matching_items_longest_match,
)

async def main():
    arxiv_id = "<arxiv_id>"
    blob = (await get_title(arxiv_id) or "") + ". " + (await get_abstract(arxiv_id) or "")
    with get_engine().connect() as conn:
        tasks = [dict(r._mapping) for r in conn.execute(text(
            "SELECT id, name, slug, keywords FROM tasks WHERE keywords IS NOT NULL"))]
        methods = [dict(r._mapping) for r in conn.execute(text(
            "SELECT id, name, slug, keywords FROM methods WHERE keywords IS NOT NULL"))]
    t_cs, t_ci = create_keyword_patterns(tasks)
    m_cs, m_ci = create_keyword_patterns_with_metadata(methods)
    task_ids = find_matching_items_simple(blob, t_cs, t_ci)          # set of task ids
    method_ids = find_matching_items_longest_match(blob, m_cs, m_ci) # set of method ids
    id2 = lambda items, ids: [(i["id"], i["slug"]) for i in items if i["id"] in ids]
    print("task matches:", id2(tasks, task_ids))
    print("method matches:", id2(methods, method_ids))

asyncio.run(main())
PY
```

`find_matching_items_simple` returns a `set` of task ids; `find_matching_items_longest_match` returns a `set` of method ids. (`apply_task_supersession_rules` is also available to drop a generic task when a more specific one matched — see `hf_paper_importer.py` for how the cron chains these.)

### 2. Decide the final tag set (your judgment)

Use the keyword matches as *candidates*, not gospel — keyword matching over-fires on generic terms (e.g. "transformer", "attention") and misses paraphrases. Apply judgment from the abstract:

- Keep tags the paper is genuinely *about* (its task(s) and the methods it uses or introduces). Drop incidental mentions and baselines it merely compares against.
- Aim for roughly **1–4 task tags** and **1–6 method tags**. Prefer specific over generic when both match (e.g. `3d-object-detection` over `object-detection` if that's the paper's actual task).
- If the paper introduces a method that already exists as a `methods` row, definitely include it. If it introduces a *new* method not in the DB, don't force-fit — report it as a candidate for `add-method`.

### 3. Apply tags (merge, don't clobber)

`pwc paper update <id> tasks|methods` **replaces the entire set** for the paper (and mark task rows `source='manual'`). So you must pass the final desired list of ids — by default the **union of existing tags + your new ones**, or you'll delete tags the crons added.

**One allowed exception — drop clear false positives.** The keyword matcher and citation cron sometimes mis-tag a paper (e.g. a video virtual-try-on paper carrying a `hallucination` method tag because the abstract used the word "hallucinate", or a generic `object-detection` task on a paper that never does detection). If an existing tag is *clearly* wrong for this paper, you may omit it from the final list to remove it. Be conservative: only drop a tag you are confident is a mistake, and **always report every removal with a one-line reason**. When unsure, keep it.

```bash
# ids = sorted union of existing ids (Step 0 read) and your new ones
uv run --env-file backend/keys.env pwc paper update <paper_id> tasks <task_id> [<task_id> ...]
uv run --env-file backend/keys.env pwc paper update <paper_id> methods <method_id> [<method_id> ...]
```

`PaperService.update_paper_tasks` / `update_paper_methods` no longer exist; use the CLI above. The admin API (`PUT /papers/<id>/tasks?task_ids=..&task_ids=..`, same for methods, with `X-Admin-Token: $ADMIN_TOKEN`) works too, but the CLI avoids auth friction. Either way, always pass the merged union.

## Verify

```bash
curl -s "http://localhost:8000/api/v1/papers/<paper_id>?include_resources=true" \
  | uv run python -c "import json,sys; p=json.load(sys.stdin); print('tasks',[t['slug'] for t in p.get('tasks') or []]); print('methods',[m['slug'] for m in p.get('methods') or []]); print('repos',[(r.get('url'),r.get('is_official')) for r in p.get('repositories') or []]); print('project_pages',[pp.get('url') for pp in p.get('project_pages') or []])"
```

Confirm the repo/project page show as official, and that the tags are the merged union (existing ones survived). No redeploy is needed for pure DB enrichment, but verify against the live API.

## Part C — Complete the thumbnail

Before taking thumbnail action, read `../create-thumbnail/SKILL.md` completely and follow it for this paper. Do not duplicate or abbreviate that workflow here; it owns the thumbnail quality and publication contract.

Use its read-only audit first. Then visually inspect the exact public image, because HTTP 200 and a non-null `thumbnail_url` do not prove that the card is useful. Treat these as incomplete:

- a missing or broken URL;
- a generic browser capture or “Untitled resource” card;
- stale source content or the wrong arXiv-version title;
- severe letterboxing, squatting, cropping, or unreadable artwork.

Reuse evidence already collected during enrichment. In particular, inspect hero/overview images from the validated official repository, project page, source page, and HF model card before falling back to a PDF first page. Use `pwc thumbnail` only when the correct paper first page is the best source; otherwise use the `create-thumbnail` compositor and content-addressed publisher.

Finish with the `create-thumbnail` live checks: confirm the API's final URL, fetch that exact public response, validate its image type and portrait geometry, and visually inspect the downloaded public image. If the existing thumbnail is already authoritative and legible, preserve it and report that no replacement was needed.

## Reporting back

End with a concise report:

- Local paper URL: `https://paperswithcode.co/paper/<arxiv_id>` (or `/paper/<paper_id>` for external rows).
- **GitHub repo**: the URL saved + which layer found it (HF API / abstract / PDF first pages / project-page HTML), or "none found" with where you looked. Note any rejected candidates and why (e.g. "skipped github.com/foo/bar — cited baseline, not the paper's repo").
- **Project page**: URL saved + source, or "none".
- **Hugging Face artifacts**: official URLs saved and whether normalized rows
  and Hub metrics were verified.
- **Tasks** added and **methods** added (slugs), distinguishing newly added from pre-existing merged tags, and listing any pre-existing tags you **removed** as false positives with the reason.
- Any taxonomy gaps (a task/method the paper needs that doesn't exist yet → suggest `add-task` / `add-method`) and any `needs review` URL candidates you intentionally did not save.
- Whether `urls_extracted` was set to TRUE.
- **Thumbnail**: whether it was preserved or replaced, the authoritative artwork/PDF source used, old/new URL or dimensions when changed, and confirmation that the exact public response was visually verified.

## When NOT to use this skill

- The paper row doesn't exist yet and has no arXiv ID → use `add-external-paper` first (it also enriches tasks/methods/links during creation).
- The user wants to create a brand-new task or method in the taxonomy → `add-task` / `add-method`.
- The user wants benchmark scores / leaderboard rows → `add-evals`.
- The user only wants to audit or fix paper thumbnails, with no links/tags enrichment → use `create-thumbnail` directly.
