---
name: verify-evals
description: Audit and verify evaluation rows on a paperswithcode benchmark leaderboard for apples-to-apples comparability. Use this whenever the user asks to verify, audit, check, validate, or clean up evals on a benchmark page — e.g. "verify all evals on ScanNet", "are these leaderboard scores correct?", "check the benchmark page", "audit evals added with add-evals", or after bulk imports before trusting rankings. Also use proactively when reviewing a leaderboard that mixes splits, metrics, evaluation setups, incorrect open/closed-source tags, or shows the same model twice under different variant names (keep only each model's best eval per paper). Cross-check each row against its cited paper, model card, or README using the hf-cli skill; compare against add-evals import rules to spot rows that should be deleted, corrected, or re-sourced — including whether is_open matches evidence of public weights.
---

# Verify Evaluations on a Benchmark

This skill audits **existing** evaluation rows on a configured benchmark leaderboard. It does not add new scores — use `add-evals` for that. The goal is to confirm every row on a benchmark page is **apples-to-apples**: the same metric, the same split, the same evaluation protocol, a score faithful to the source paper or release, and an accurate **open vs closed-source** tag (`is_open`).

Leaderboards rank models against each other. A row that uses validation AP50 next to hidden-test AP50, or a backbone ablation next to a full submission, misleads users even when the number itself is "correct" for some table in the paper.

## Related skills

| Skill | Role in verification |
|-------|----------------------|
| **`hf-cli`** | Read arXiv papers (`uv run hf papers read`), paper metadata, model cards (`uv run hf models card`), and model info JSON. Primary source for checking reported numbers. |
| **`add-evals`** | Defines how rows *should* have been imported — metric filter, split expectations, model naming, `methodology`, `is_open`, `num_parameters`. Verification is essentially running those rules in reverse on existing rows. |
| **`add-benchmark`** | Use only if the leaderboard itself is misconfigured (wrong metric linked, missing task association). Do not fix bad rows by changing the leaderboard definition during verification. |

## Pre-flight

Run from the repo root:

```bash
uv run --env-file backend/keys.env ...
```

Confirm the API is up (any dataset id works; 404 on missing id still means the server responded):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/datasets/276
```

Resolve the benchmark from the user URL or name. Example: `https://paperswithcode.co/benchmark/scannet?task=3d-instance-segmentation` → dataset slug `scannet`, task slug `3d-instance-segmentation`.

```python
from sqlalchemy import text
from backend.database.connection import get_engine

dataset_slug = "scannet"
task_slug = "3d-instance-segmentation"

with get_engine().connect() as conn:
    ds = conn.execute(text(
        "SELECT id, name, slug, introducing_paper_id, paper_url FROM datasets WHERE slug = :slug"
    ), {"slug": dataset_slug}).mappings().first()
    task = conn.execute(text(
        "SELECT id, name, slug FROM tasks WHERE slug = :slug"
    ), {"slug": task_slug}).mappings().first()
    metrics = conn.execute(text(
        "SELECT m.name, m.direction, td.supports_harness "
        "FROM task_dataset_metrics tdm "
        "JOIN metrics m ON m.id = tdm.metric_id "
        "JOIN task_datasets td ON td.task_id = tdm.task_id AND td.dataset_id = tdm.dataset_id "
        "WHERE tdm.task_id = :task_id AND tdm.dataset_id = :dataset_id"
    ), {"task_id": task.id, "dataset_id": ds.id}).mappings().all()
    print(dict(ds), dict(task), [dict(m) for m in metrics])
```

Record the **leaderboard contract** before reviewing rows:

- `dataset_id`, `task_id`
- Allowed metric name(s) — usually one primary metric (e.g. `AP50`)
- `supports_harness` — whether `evaluations.harness` should be populated
- Expected split and protocol for this benchmark (see Step 1 — do not assume hidden test without checking)

## Step 1: Define the apples-to-apples contract

Every row on a leaderboard must match the same contract. Infer it from the benchmark's official definition, existing rows, domain convention, and (for older CV/3D leaderboards) legacy PwC — then apply it uniformly.

### Split (most common failure mode)

Check whether the leaderboard is meant to compare:

| Split | Typical use |
|-------|-------------|
| **Hidden test** | Official benchmark server results (ScanNet, many vision leaderboards) |
| **Public validation** | Ablation tables, development comparisons, papers that never submit to the server |
| **Train / other** | Almost never belongs on a public SOTA leaderboard |

**Rule:** Do not mix splits on one ranked leaderboard. Every row must use the **same** split (and the same score from that split).

Read the paper table caption carefully: "validation set", "test set", "hidden test", "leaderboard submission", "we report on val in the main paper and test in the appendix".

#### Resolving the split when convention is unclear

Do **not** jump straight to "hidden test because ScanNet has a benchmark server." Many curated pages — including legacy PwC — used **validation** for most papers and test only for benchmark submissions.

1. **Official source** — benchmark homepage / server docs (e.g. `kaldir.vc.in.tum.de/scannet_benchmark/`) → hidden test is the server leaderboard.
2. **Existing rows** — tag each row's split from `methodology` and flag mixing before per-row source checks:

```python
# Quick split-mixing audit
for r in rows:
    m = (r["methodology"] or "").lower()
    split = "test" if "hidden test" in m or " test " in m else (
        "val" if "validation" in m or " val " in m else "unclear"
    )
    print(r["model_name"], r["metrics"], split)
```

3. **Legacy PwC score-matching** — stream `evaluation-tables.json` (never load the full file on the VPS; use `ijson`). Match each legacy score to known val/test cells in papers or READMEs to infer which split legacy used. Legacy rows carry **no split label** — only score equality proves it.

```python
import ijson, re
from pathlib import Path

path = Path("data/legacy_pwc_data/evaluation-tables.json")
with open(path, "rb") as f:
    for item in ijson.items(f, "item"):
        if item.get("task") != "<Task Name>":
            continue
        for ds in item.get("datasets", []):
            if "<dataset slug fragment>" not in ds.get("dataset", "").lower():
                continue
            for row in ds.get("sota", {}).get("rows", []):
                print(row.get("model_name"), row.get("metrics"), row.get("paper_url"))
```

Legacy PwC was **not** split-consistent (e.g. ScanNet Mask3D mixed val mAP with test AP50 in one row; ScanNet200 used validation for ODIN/ISBNet/MSTA3D but test mAP for Mask3D). Treat legacy as **historical evidence**, not a mandate to keep mixing.

4. **User choice** — when official docs, legacy, and current rows disagree, report the options with evidence and let the user pick the contract (e.g. "validation for all rows except Mask3D on hidden test"). Document the chosen contract in the audit report and apply it to every row.

**Exception rows:** a contract like "validation except paper X on test" is valid when mirroring legacy or when only one method has an official test submission. List exceptions explicitly; every other row must still match the dominant split.

### Metric

The stored `best_metric` and the sole key in `metrics` must match a metric linked in `task_dataset_metrics` for this `(task_id, dataset_id)`.

Also verify the **source table column** maps to that metric:

- `AP50` / `mAP@50` / `mAP 50` → usually `AP50` when that is the configured metric
- Do not accept component subscores (e.g. MME-P on an `Score`-only leaderboard)
- Do not accept a different quantity (F1 imported as Accuracy, percent OCRBench score without scale normalization)

Cross-check `add-evals` Step 5 — the same exclusion rules apply in reverse.

### Evaluation setup / input modality

Many benchmarks allow only one input representation. Examples:

- ScanNet instance segmentation: mesh-sampled point cloud on hidden test (standard); sensor RGB-D with feature transfer is a **different setup** even on the same split
- Image-text retrieval: I→T vs T→I are separate leaderboards — never mix directions

If setups differ, rows are not comparable even when metric and split match. Prefer **delete** over keeping a row with a long methodology disclaimer unless the user explicitly wants a mixed setup page.

### Model identity

The score must be for the model named in `evaluations.model_name`, using the setup that row claims:

- Primary method vs backbone-only ablation (e.g. `PTv3 + PointGroup` backbone table vs `Mask3D` end-to-end method)
- Correct variant (size, mode, decoder/head suffix when the score is for a downstream system)
- Not a comparator/baseline row unless the leaderboard intentionally tracks comparators (default: paper's **own** best eligible result only, per `add-evals`)

### One best eval per model (no variant duplicates)

A leaderboard should show **each model family once**, with its **best** eligible score — not multiple rows for the same releasing paper under different config names (e.g. `Claude Opus 4.8 (High)` and `Claude Opus 4.8 (Max)` both on paper 97913).

This is **not** caught by the DB unique key `(paper_id, task_id, dataset_id, model_name, harness, best_metric)` because `model_name` differs per variant. The benchmark page also keys display rows on `model_name`, so variant duplicates appear as separate ranked entries even when they represent the same model release.

**Default contract:** one row per `paper_id` on a leaderboard, keeping the highest score that still matches the split/metric/setup contract. Keep the surviving row's `model_name` as the variant that achieved that score (e.g. keep `Claude Opus 4.8 (Max)` at 34.08%, delete `Claude Opus 4.8 (High)` at 33.80%).

**When multiple rows per paper are OK:** only when variants are genuinely different comparable models on this benchmark — e.g. `ViT-B/16` vs `ViT-L/16` are separate size tiers, not reprompted vs non-reprompted runs of the same release. When in doubt, report both options; default to one row per paper for agent/runtime-variant leaderboards (PostTrainBench, DeepSWE, FrontierSWE, etc.).

**Quick variant-duplicate audit** (run in Step 2 before per-row verification):

```python
from collections import defaultdict
from sqlalchemy import text
from backend.database.connection import get_engine

task_id = 14
dataset_id = 810

with get_engine().connect() as conn:
    rows = conn.execute(text("""
        SELECT e.id, e.paper_id, e.model_name, e.best_metric, e.metrics,
               e.harness, e.best_rank, p.title
        FROM evaluations e
        JOIN papers p ON p.id = e.paper_id
        WHERE e.task_id = :task_id AND e.dataset_id = :dataset_id
        ORDER BY e.paper_id, (e.metrics->>e.best_metric)::float DESC NULLS LAST
    """), {"task_id": task_id, "dataset_id": dataset_id}).mappings().all()

by_paper = defaultdict(list)
for r in rows:
    by_paper[r["paper_id"]].append(r)

for paper_id, group in sorted(by_paper.items()):
    if len(group) <= 1:
        continue
    print(f"\npaper_id={paper_id} ({group[0]['title']}) — {len(group)} rows:")
    for r in group:
        score = r["metrics"].get(r["best_metric"])
        print(f"  id={r['id']} rank={r['best_rank']} {r['model_name']} {score}")
    print("  → keep highest score; delete or skip lower variants")
```

For external leaderboard imports that re-sync from a JSON feed, fix the import script to consolidate by `paper_id` before insert — see `_best_entry_per_paper` in `backend/database/evaluations_setup/import_posttrainbench_external_evals.py`. Re-running the import after that change is preferred over hand-deleting rows one by one.

**Worked fix (PostTrainBench, agents task):** five papers had two agent-config variants each (High vs Max, reprompted vs not, etc.). Kept only the highest Accuracy per `paper_id` — e.g. Opus 4.8 (Max) 34.08% over Opus 4.8 (High) 33.80%. Leaderboard dropped from 23 to 18 rows with no duplicate model families.

### Paper attachment

Each row's `paper_id` must be the paper that **introduced or released** the evaluated model, not a survey or unrelated technique paper. The score must appear in that paper (or its official README/model card linked from it).

## Step 2: Inventory all rows on the leaderboard

```python
from sqlalchemy import text
from backend.database.connection import get_engine

task_id = 327
dataset_id = 276

with get_engine().connect() as conn:
    rows = conn.execute(text("""
        SELECT e.id, e.model_name, e.best_metric, e.metrics, e.methodology,
               e.paper_id, e.harness, e.is_open, e.hf_model_url, e.num_parameters,
               e.external_source_url, e.best_rank,
               p.arxiv_id, p.title, p.source
        FROM evaluations e
        JOIN papers p ON p.id = e.paper_id
        WHERE e.task_id = :task_id AND e.dataset_id = :dataset_id
        ORDER BY (e.metrics->>e.best_metric)::float DESC NULLS LAST, e.model_name
    """), {"task_id": task_id, "dataset_id": dataset_id}).mappings().all()
    for r in rows:
        print(r["id"], r["best_rank"], r["model_name"], r["metrics"],
              f"open={r['is_open']}", r["arxiv_id"])
```

Also fetch via API for rank sanity:

```bash
curl -s "http://localhost:8000/api/v1/evaluations/?dataset_id=<dataset_id>&task_id=<task_id>&page_size=100"
```

Flag duplicates on the unique key `(paper_id, task_id, dataset_id, model_name, harness, best_metric)`.

Also run the **variant-duplicate audit** from Step 1 (group by `paper_id`, flag papers with >1 row). Resolve these before per-row source checks so you do not waste time verifying rows that should be deleted anyway.

### Quick open/closed tag scan

Run before per-row verification to catch obvious mis-tags. The API defaults `is_open` to `true`, so missing or wrong closed tags are a common import gap — users rely on `is_open === false` to show the closed-source badge and to hide proprietary rows via Settings.

```python
# Heuristic pre-scan — follow up with source checks in Step 3
CLOSED_NAME_MARKERS = (
    "claude", "gpt-", "gpt ", "gemini", "grok", "o1-", "o3-", "o4-",
)

for r in rows:
    name = (r["model_name"] or "").lower()
    stored = r["is_open"]
    hf_url = r.get("hf_model_url")  # add to Step 2 SELECT if auditing deeply

    if stored is not False and any(m in name for m in CLOSED_NAME_MARKERS):
        print(f"REVIEW is_open: id={r['id']} {r['model_name']} stored={stored} (proprietary name)")

    if stored is False and hf_url:
        print(f"INCONSISTENT: id={r['id']} is_open=false but hf_model_url={hf_url}")

    if stored is not False and not hf_url and any(m in name for m in CLOSED_NAME_MARKERS):
        print(f"LIKELY_WRONG_IS_OPEN: id={r['id']} {r['model_name']}")
```

Also check **consistency across rows for the same model variant**: every eval for the same `(paper_id, model_name)` on different benchmarks should share the same `is_open`. Flag when one leaderboard row is closed and a sibling row for the identical variant is open.

```python
from collections import defaultdict
from sqlalchemy import text
from backend.database.connection import get_engine

with get_engine().connect() as conn:
    cross = conn.execute(text("""
        SELECT paper_id, model_name,
               bool_or(is_open) AS any_open,
               bool_and(is_open) AS all_open,
               count(*) AS n
        FROM evaluations
        WHERE paper_id IN (
            SELECT DISTINCT paper_id FROM evaluations
            WHERE task_id = :task_id AND dataset_id = :dataset_id
        )
        GROUP BY paper_id, model_name
        HAVING bool_or(is_open) AND NOT bool_and(is_open)
    """), {"task_id": task_id, "dataset_id": dataset_id}).mappings().all()
    for row in cross:
        print(f"MIXED is_open across leaderboards: paper_id={row['paper_id']} {row['model_name']}")
```

Name heuristics only narrow the search — always confirm against the primary source in Step 3.

## Step 3: Verify each row against its source

For each row, trace: **stored value → cited source → table row/cell**.

Priority order for sources (same as `add-evals`):

1. **`external_source_url`** on the evaluation row, if set
2. arXiv paper via **`hf-cli`**
3. GitHub README (`gh api repos/<owner>/<repo>/readme …`)
4. HF model card (`uv run hf models card <repo_id> --text`)
5. Legacy corroboration: `data/legacy_pwc_data/evaluation-tables.json` via `ijson` streaming (see Step 1; helpful for split inference on older 3D/CV benchmarks; not authoritative alone)

**VPS / memory:** On the Hetzner VPS (~4GB RAM), never load `papers-with-abstracts.json` or full `evaluation-tables.json` into memory. Stream with `ijson`, fetch individual PDFs to `/tmp`, use `pdftotext` + `rg`. Prefer `gh api …/readme` and targeted SQL queries over bulk dumps.

### Reading papers with hf-cli

Always use the project venv:

```bash
mkdir -p /tmp/verify-<slug>
uv run hf papers read <arxiv_id> > /tmp/verify-<slug>/paper.md
uv run hf papers info <arxiv_id> > /tmp/verify-<slug>/paper-info.json
```

Search the paper for the model name, benchmark name, split, and metric:

```bash
rg -i "AP50|mAP.?50|test|validation|hidden|<model_name>|<benchmark>" /tmp/verify-<slug>/paper.md
```

For PDF-only tables that render poorly in markdown, fetch the PDF and extract text:

```bash
curl -sL "https://arxiv.org/pdf/<arxiv_id>.pdf" -o /tmp/verify-<slug>/paper.pdf
pdftotext /tmp/verify-<slug>/paper.pdf - | rg -i "Table|AP50|test|validation|<model>"
```

### Reading model cards

When the row traces to a HF release:

```bash
uv run hf models card <repo_id> --text > /tmp/verify-<slug>/card.md
uv run hf models info <repo_id> > /tmp/verify-<slug>/info.json
```

Confirm the card's eval table matches the row and that the linked `arxiv:` tag matches `paper_id`.

### Verify open vs closed tags (`is_open`)

Users filter closed-source rows on benchmark and paper pages (`is_open === false` shows a "closed" badge). A row tagged open when weights are proprietary misleads readers; tagging closed when weights are public hides legitimately reproducible results.

Apply the same rules as `add-evals` Step 5 — verification runs them in reverse on the stored boolean.

#### Closed-source (`is_open` should be `false`)

Mark **WRONG_IS_OPEN** (stored `true`, should be `false`) when there is **no evidence of an open-weight release** for the evaluated model variant:

- Source is a blog post, system card, vendor report, or API announcement with pricing/access but no public weights.
- Weights are unavailable, restricted (trusted-access / allowlist / enterprise-only), or inference-only through a vendor API.
- The only linked Hugging Face artifact is a demo Space, dataset, or unrelated base model — not downloadable weights for the evaluated checkpoint.
- The evaluated product is a proprietary model name (`Claude …`, `GPT-…`, `Gemini …`, `Grok …`, etc.) with no accompanying open-weight release in the same source chain.

Recent examples that should be closed unless open weights are evidenced: Claude Opus/Fable/Mythos, GPT-5.x, Gemini 3.x.

#### Open-source (`is_open` should be `true`)

Mark **WRONG_IS_OPEN** (stored `false`, should be `true`) when the evaluated variant has clear open-weight evidence:

- An official Hugging Face **model** repo with downloadable weights for that checkpoint (`uv run hf models info <repo_id>` — confirm `safetensors` / weight files, not just a card).
- An official GitHub release distributing weights or stating they are publicly released under an open license.
- The paper/card/README explicitly open-sources the exact evaluated model and links the artifact.

For academic CV/3D methods, `is_open: true` is typical when the paper links a public GitHub repo with inference code (ScanNet benchmark imports use GitHub presence as the open signal). Absence of a code link alone does not prove closed — check whether weights are actually released vs code-only.

#### Mixed or ambiguous releases

When a lab ships both an API flagship and a separate open research checkpoint, set `is_open` from the **evaluated row's model variant**, not the lab's general policy. If the leaderboard row is for an API-only flagship and a smaller open checkpoint also exists, the flagship row stays closed even if a related open model exists elsewhere.

When genuinely uncertain after checking the primary source plus official linked artifacts, prefer `is_open: false` for major closed vendors and report the ambiguity as **UNVERIFIABLE** for the open tag — do not flip without evidence.

#### Corroborating signals

| Signal | Expected when open | Expected when closed |
|--------|-------------------|---------------------|
| Official HF model repo with weights | Present; may populate `hf_model_url` | Absent or unrelated repo only |
| `hf_model_url` on the eval row | Points to official weights for this variant | Should be unset |
| Vendor domain in source (anthropic.com, openai.com, blog.google, deepmind.google, x.ai) | Only if same release also open-sources weights | Usually closed |
| GitHub repo with released weights/checkpoints | Strong open signal | N/A |

Cross-check `hf_model_url` when set: an eval with `is_open: false` and a populated `hf_model_url` is inconsistent unless the URL points to an unrelated artifact — fix one or both.

#### Per-row open-tag checklist

```
[ ] Checked primary source (paper/card/README) for weight availability
[ ] Checked official HF model repo (if any) — downloadable weights for THIS variant
[ ] Checked GitHub releases / model zoo links from the paper
[ ] Applied variant-level rule (API flagship vs open checkpoint)
[ ] Stored is_open matches evidence; hf_model_url consistent with is_open
[ ] Same (paper_id, model_name) uses same is_open on other leaderboards
```

### What to record per row

| Check | Pass criteria |
|-------|---------------|
| **Score** | Stored value equals the source cell for the claimed setup (allow minor rounding, e.g. 71.2 vs 71.0 only if same split and you document rounding) |
| **Split** | Matches leaderboard contract (test vs val) |
| **Metric** | Source column is the configured leaderboard metric, not a alias or subscore |
| **Setup** | Input modality, framework/head, shot count, pretrain recipe match `model_name` + `methodology` |
| **Paper** | `paper_id` is the introducing/release paper for that model |
| **Provenance** | `methodology` accurately states split, table, and source surface; does not contradict the source |
| **`is_open`** | Matches open-weight evidence for this exact variant (see "Verify open vs closed tags" above); not left at default `true` for proprietary API models |
| **`hf_model_url`** | Set only when open and certain; unset for closed rows; URL must be the official weights repo for the evaluated variant |
| **`num_parameters`** | If set, matches source for that exact variant; if unset, source didn't state it — OK |
| **`harness`** | Null when `supports_harness=false`; populated only when the leaderboard supports it and the source names a runtime |

## Step 4: Classify issues

Use explicit verdicts:

| Verdict | Meaning | Typical action |
|---------|---------|----------------|
| **PASS** | Score, split, metric, setup, paper, and `is_open` all match the contract | Keep |
| **WRONG_SCORE** | Right row identity but incorrect number or typo | Fix via API PUT or delete + re-import with `add-evals` |
| **WRONG_SPLIT** | Score is from a different split than the leaderboard contract | **Update** to the correct split's score via PUT when that cell exists in the source; **delete** only when no comparable score exists for the contract split or the row should not be on this page |
| **WRONG_SETUP** | Different input modality, framework ablation, or non-comparable protocol | **Delete** unless user wants mixed page |
| **WRONG_METRIC** | Component/subscore or different quantity | **Delete** |
| **WRONG_PAPER** | Score belongs on a different paper row | Move scoped rows per `add-evals` misattribution workflow |
| **DUPLICATE** | Same unique key twice | Delete the duplicate |
| **DUPLICATE_VARIANT** | Same `paper_id`, different `model_name` — multiple configs/variants of one model release on the same leaderboard | **Delete** lower-scoring variants; keep the single best row that matches the contract (see Step 1 "One best eval per model") |
| **WRONG_IS_OPEN** | Stored open/closed tag contradicts weight-release evidence for the evaluated variant | **PUT** `is_open` (and fix/clear `hf_model_url` if inconsistent); score/split unchanged |
| **UNVERifiable** | Source missing, table ambiguous, cannot confirm split or open/closed status | Report blocker; do not delete without user confirmation |

**Important:** An honest `methodology` field that says "validation" does not make a validation row OK on a test leaderboard — it confirms the row should be removed or relocated.

### Red flags from 3D instance segmentation audits (ScanNet / ScanNet200)

These patterns recur across benchmarks:

1. **Mixed splits on one page** — e.g. ScanNet200 with Volt/Mask3D on test and ODIN/OneFormer3D/PTv3/ISBNet on validation. Methodology may label the split correctly; the row is still **WRONG_SPLIT** until the whole page uses one contract.
2. **Same paper, two splits** — ODIN Table 1(c) validation AP50 45.3 vs Table 6 test AP50 39.4. Pick one split for the contract; do not rank both on the same leaderboard.
3. **Best-score import vs split contract** — `add-evals` may pick test when it is higher (Mask3D test 38.8 > val 37.0) or test when the paper headlines it (Volt test 47.5), even when other rows use validation. Verification must normalize all rows to the chosen contract.
4. **Backbone ablation rows** — e.g. `Point Transformer V3 + PointGroup + PPT` from a backbone comparison table, not the paper's primary instance method
5. **Legacy PwC imports** — legacy ScanNet200 stored validation for most papers but test mAP for Mask3D; legacy also mixed metrics across splits on ScanNet(v2). Re-verify every score against the paper; use legacy only to infer split policy.
6. **Comparator tables in newer papers** — Volt/Mask3D papers list SPFormer AP50 as a baseline; verify the score belongs to the paper attached to the row
7. **Scale mismatches** — OCRBench `Score` stored as percent instead of native 0–1000 scale (see `add-evals` normalization rules)
8. **Variant duplicates on agent benches** — same model paper listed twice under different runtime/config names (High vs Max, reprompted vs default). Users expect one row per model with the best score; lower variants are **DUPLICATE_VARIANT** even when each score is individually correct.
9. **Default-open proprietary models** — frontier API evals imported without `is_open: false` (Claude, GPT, Gemini on agent/VLM benches). The API default is `true`; verification should flip these when the release has no public weights.
10. **Closed tag with HF link** — `is_open: false` but `hf_model_url` populated, or open tag with only a vendor blog and no weight artifact. Fix both fields together.

**Worked fix (ScanNet200, contract: validation except Mask3D on test):** Volt WRONG_SPLIT — stored 47.5 (test), validation cell is 48.4 (Table 3). PUT `metrics` + `methodology`; other rows already matched or were already validation; Mask3D 38.8 test unchanged.

## Step 5: Run automated checks

```bash
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py
```

This catches metric label mismatches (`best_metric` vs allowed leaderboard metrics). It will not catch wrong splits or setup mixing — that remains manual/source-driven in this skill.

Optionally check rank order matches stored scores for the configured metric direction.

## Step 6: Remediate

Get user confirmation before bulk deletes unless they already asked to "clean up" or "delete wrong rows".

### Delete a row

```bash
source backend/keys.env
curl -s -o /dev/null -w "%{http_code}\n" \
  -X DELETE "http://localhost:8000/api/v1/evaluations/<id>" \
  -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN"
```

Ranks recalculate automatically.

### Fix a score or metadata

Prefer delete + `add-evals` re-import when multiple fields are wrong. For a **WRONG_SPLIT** where the correct split's score exists in the source, PUT the row (score + methodology) rather than delete — same `paper_id` / `model_name`, different table cell.

```bash
source backend/keys.env
curl -s -X PUT "http://localhost:8000/api/v1/evaluations/<id>" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" \
  -d '{
    "metrics": {"AP50": "<correct_value>"},
    "best_metric": "AP50",
    "methodology": "<split, table, source surface — must match the new score>"
  }'
```

Ranks recalculate automatically. For a single numeric typo with correct split/setup, PUT is enough. Delete when the row should not exist on this leaderboard at all.

### Fix open/closed tag

When score, split, and setup are correct but `is_open` is wrong, PUT only the tag (and `hf_model_url` if needed). Do not delete the row.

```bash
source backend/keys.env
curl -s -X PUT "http://localhost:8000/api/v1/evaluations/<id>" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" \
  -d '{"is_open": false}'

# When opening a row and linking weights:
curl -s -X PUT "http://localhost:8000/api/v1/evaluations/<id>" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" \
  -d '{
    "is_open": true,
    "hf_model_url": "https://huggingface.co/org/checkpoint-name"
  }'

# When closing a row — clear a stale HF link:
curl -s -X PUT "http://localhost:8000/api/v1/evaluations/<id>" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" \
  -d '{"is_open": false, "hf_model_url": null}'
```

When the same model variant is wrong on multiple leaderboards, fix every row for that `(paper_id, model_name)` so the tag stays consistent site-wide.

### Consolidate variant duplicates (one best eval per model)

When multiple rows share a `paper_id` and only differ by config suffix (`(High)` vs `(Max)`, reprompted, 1M context, etc.), delete every row except the highest-scoring one that matches the leaderboard contract. Do not rename the survivor unless the source uses a canonical name without the config suffix.

For feed-synced external leaderboards, prefer fixing and re-running the import script (PostTrainBench pattern) so future syncs stay deduplicated:

```bash
uv run --env-file backend/keys.env \
  python backend/database/evaluations_setup/import_posttrainbench_external_evals.py
```

For one-off duplicates added manually, delete the lower variants via the DELETE API above.

### Do not fix during verification

- Do not add new metrics or task-dataset links (`add-benchmark`)
- Do not bulk-import replacement rows unless the user asks — **report first**, then remediate when the user confirms the contract or asks to fix/clean up

## Reporting back

Structure the audit report like this:

### Leaderboard contract

- Benchmark URL, `dataset_id`, `task_id`, configured metric(s), expected split/setup

### Summary

- Total rows, PASS count, issues by verdict

### Row-by-row table

For each evaluation: id, rank, model, stored score, verdict, one-line evidence (source table + split). When `is_open` is wrong or reviewed, add columns: stored `is_open`, expected `is_open`, evidence (e.g. "Anthropic API, no weights" / "official HF repo org/model-7b").

### Recommended actions

- Rows to delete (with reason)
- Rows to fix (with correct value and source)
- Rows to retag open/closed (with evidence and whether `hf_model_url` should change)
- Rows to re-source (wrong paper)
- Metadata gaps (dataset description, missing introducing paper, etc.)

### Skipped / inconclusive

- Rows that could not be verified and what evidence is missing

End with the benchmark URL, e.g. `https://paperswithcode.co/benchmark/scannet?task=3d-instance-segmentation`.

## Quick verification checklist

Copy and use per row:

```
[ ] metric matches task_dataset_metrics for this leaderboard
[ ] split matches leaderboard contract (test vs val)
[ ] setup matches other rows (input, framework, shots)
[ ] score matches source table cell for this model+setup
[ ] paper_id is the releasing paper for this model
[ ] methodology accurately describes split/table/source
[ ] is_open matches weight-release evidence for this exact model variant
[ ] hf_model_url consistent with is_open (official weights repo only when open)
[ ] num_parameters / harness consistent with add-evals rules
[ ] not a duplicate unique key
[ ] not a variant duplicate — at most one row per paper_id (best score kept)
```

## When NOT to use this skill

- **Adding** new evaluation rows → `add-evals`
- **Creating** benchmarks or wiring metrics → `add-benchmark`
- **Moving paper lineage** → `pwc paper lineage add/list/remove`

## Quick reference

```bash
# Leaderboard metrics
curl -s "http://localhost:8000/api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics"

# All evals on a leaderboard
curl -s "http://localhost:8000/api/v1/evaluations/?dataset_id={dataset_id}&task_id={task_id}&page_size=100"

# Read paper
uv run hf papers read <arxiv_id>

# Read model card
uv run hf models card <repo_id> --text

# Validate metric wiring
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py

# Fix split/score on existing row
curl -X PUT "http://localhost:8000/api/v1/evaluations/{id}" \
  -H "Content-Type: application/json" -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" \
  -d '{"metrics": {"AP50": "48.4"}, "best_metric": "AP50", "methodology": "..."}'

# Fix open/closed tag
curl -X PUT "http://localhost:8000/api/v1/evaluations/{id}" \
  -H "Content-Type: application/json" -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN" \
  -d '{"is_open": false}'

# Delete bad row
curl -X DELETE "http://localhost:8000/api/v1/evaluations/{id}" -H "X-Admin-Token: $PWC_ADMIN_API_TOKEN"
```
