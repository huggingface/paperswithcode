---
name: add-evals
description: Add evaluation results to the paperswithcode database from any source — Hugging Face model cards, arXiv/HF/PapersWithCode paper text, or GitHub repository READMEs — restricted to benchmarks that already exist with a task association and the exact leaderboard metric already configured. Use this whenever the user shares a Hugging Face model URL or repo id, an arXiv id / HF paper / PapersWithCode paper, a GitHub repository URL, or a model release page and asks to add evaluation results, benchmark scores, or leaderboard entries — even when phrased casually like "add scores from this model", "import benchmarks from <hf url>", "ingest the eval table from this paper into the DB", "grab the benchmarks from this repo's README", or "add evaluations for this release". By default import only the model(s) the source paper introduces — never post comparison-table baselines onto other papers as external evals unless the user explicitly asks. If the source is not backed by an arXiv paper, first use the add-external-paper skill to create or update the `source = 'external'` paper row, then attach evaluation rows to that paper. This skill must skip source-only metrics, component scores, subscores, and alternate metric labels unless that metric is already configured for the exact leaderboard; use it instead of generic ingestion guidance whenever the user is trying to populate evaluation results from a model, paper, or repository source.
---

# Add Evaluations

This skill imports evaluation results into the paperswithcode database from any of the common sources that ship benchmark tables: Hugging Face model cards, a paper on Arxiv/Hugging Face/paperswithcode.co, or a Github or project page URL. It is intentionally conservative: it only writes evaluation rows for benchmarks that already exist in the database with a task association and a configured leaderboard metric. It never invents new datasets, tasks, or metrics during the import, and it never imports rows for source-only metric labels that are not already configured on the exact leaderboard.

## Why this exists

Model releases (especially flagship LLMs / VLMs / OCR models) advertise benchmark numbers across several surfaces — the HF model card, the technical report or arXiv paper, the GitHub README and external blog posts/project pages. Any of them can be the only source where a particular table appears, so the import workflow has to be source-agnostic but consistent. The natural workflow is:

- Reuse existing benchmark datasets in the DB by matching names from the source.
- Skip source benchmarks that are not yet in the DB (curate those separately later, not as a side effect).
- Add evaluation rows for the model only on benchmarks that are fully wired up (dataset linked to any task with the specific leaderboard metric being imported).
- Keep imports idempotent and easy to re-run.

This avoids polluting the schema with half-configured benchmarks, false-positive name matches, duplicate evaluation rows, or mixed-metric leaderboards where incomparable component scores are ranked together with canonical scores.

## Pre-flight

Always run from the repo root using the project environment:

```bash
uv run --env-file backend/keys.env ...
```

Confirm the backend is reachable and the admin token is set:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/datasets/1
grep -E '^PWC_ADMIN_API_TOKEN=' backend/keys.env | head -1 | sed 's/=.*/=<redacted>/'
```

If the server is not running, start it (or restart it without asking confirmation per AGENTS.md).

## Common Shortcuts From Recent Curation

### Transformers model docs

When the user gives a Transformers model doc URL such as
`https://github.com/huggingface/transformers/blob/main/docs/source/en/model_doc/<model>.md`,
or points at `data/transformers_model_doc_papers.csv`, treat it as a normal source surface but use the CSV as a resolver:

1. Look up the model doc slug or CSV line in `data/transformers_model_doc_papers.csv`.
2. Use the CSV arXiv/paper mapping when it clearly identifies the source paper.
3. Fetch the raw model doc markdown and parse its evaluation tables.
4. If the doc describes a release with no matching arXiv paper, run `add-external-paper` first and attach the evals to that external row.

For "next N rows" or "lines X-Y of the CSV", process each row independently through this skill and return a compact summary: source row, paper id, rows added, skipped benchmarks, and any blocker. For larger batches, it is fine to spawn one worker subagent per row with this skill loaded, but the parent agent should still merge the final summary and avoid duplicate writes.

### Misattributed or moved evaluations

If the user says existing evals landed on the wrong paper, first create or resolve the correct source row, then move only the matching rows in one transaction. Scope the update by `old_paper_id`, target `model_name` or benchmark set, and optional `external_source_url`; never move all rows from a paper unless the user explicitly asks.

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine

old_paper_id = <old_id>
new_paper_id = <new_id>
model_pattern = "%<model name>%"
new_source_url = "<canonical source URL>"  # or None to preserve row-level sources

with get_engine().begin() as conn:
    before = conn.execute(text("""
        SELECT id, model_name, dataset_id, best_metric
        FROM evaluations
        WHERE paper_id = :old_paper_id AND model_name ILIKE :model_pattern
        ORDER BY id
    """), {"old_paper_id": old_paper_id, "model_pattern": model_pattern}).mappings().all()
    print("moving", len(before), "rows")
    conn.execute(text("""
        UPDATE evaluations
        SET paper_id = :new_paper_id,
            external_source_url = COALESCE(:new_source_url, external_source_url)
        WHERE paper_id = :old_paper_id AND model_name ILIKE :model_pattern
    """), {
        "old_paper_id": old_paper_id,
        "new_paper_id": new_paper_id,
        "model_pattern": model_pattern,
        "new_source_url": new_source_url,
    })
PY
```

After moving rows, verify zero matching rows remain on the old paper, the expected count appears on the new paper, and duplicate keys were not created.

## Workflow

### 1. Identify and fetch the evaluation source

Different starting points should converge on the same triple — a model identity, an evaluation table, and a paper row to attach it to. Pick the first source below that the user actually gave you, and then follow the fallback chain until you have an evaluation table:

1. **HF model repo / card** — fetch the card and inspect the metadata. Always invoke `hf` via `uv run` so the venv-installed CLI is used:

   ```bash
   mkdir -p /tmp/<repo_slug>
   uv run hf models card <repo_id> --text > /tmp/<repo_slug>/card.md
   uv run hf models info <repo_id> > /tmp/<repo_slug>/info.json
   ```

   The model card is the primary surface. If it has evaluation tables, that is your source. If it does not, read the `info.json` metadata: the card's `arxiv` tag (e.g. `arxiv:2401.12345`) or `papers` field points at a linked paper, and the card body or repo description often contains a GitHub URL. Fall through to step 2 / 3 with those identifiers.

2. **Paper (arXiv, HF, PDF report, or PapersWithCode paper with an arXiv ID)** — when the source is a paper directly, or the model card was missing evals, read the paper as markdown and inspect linked artifacts:

   ```bash
   uv run hf papers read <arxiv_id> > /tmp/<paper_slug>/paper.md
   uv run hf papers info <arxiv_id> > /tmp/<paper_slug>/paper-info.json
   ```

   Extract evaluation tables from the paper body first. If the paper itself has no usable table, look for official artifacts linked from the paper text and metadata. For PDF reports that need an external paper row, inspect the extracted first pages for a real abstract/opening summary and pass that text verbatim to `add-external-paper`; do not generate a replacement summary when the PDF already contains one. Also distinguish official GitHub repositories from cited dependencies or frameworks before creating the external row, because official repo URLs should be marked official while incidental GitHub links should not be.

   For papers with an arXiv ID, also look for HF models tagged with that paper. The current `uv run hf papers info <arxiv_id>` output does not reliably expose linked models, so use the Hugging Face model search page directly:

   ```bash
   curl -L "https://huggingface.co/models?other=arxiv:<arxiv_id>" > /tmp/<paper_slug>/hf-models.html
   ```

   Treat matching HF model cards as candidate sources only. A model can appear in this search simply because its README/model card mentions the arXiv ID, not because the paper introduced that model. Before parsing evals from any discovered model card, be 100% sure the model was introduced by the paper itself: the model card should clearly present the paper as the model's own technical report/release paper, share the same authors/organization/release context, and not merely cite the paper as related work, a base model, a benchmark source, or background. If this is not certain, do not use that model card as a source; ask the user or skip it.

   For each confirmed introduced model, fetch the model card and metadata as in step 1 and use its evaluation tables as candidate source rows. If the paper has no usable table but lists a GitHub repo, fall through to step 3.

3. **GitHub repository** — when the model card or paper points to a GitHub repo, or the user provided one directly, fetch the README via the `gh` CLI and use it as the source:

   ```bash
   gh repo view <owner>/<repo> --json description,url,homepageUrl > /tmp/<repo_slug>/repo.json
   gh api repos/<owner>/<repo>/readme -H "Accept: application/vnd.github.raw" > /tmp/<repo_slug>/README.md
   ```

   Repo READMEs often contain the most complete benchmark tables for new releases (especially for OCR/VLM/robotics models). Treat README tables exactly like card tables for the rest of the workflow.

   GitHub repositories are also an important source-availability signal. Do not mark a row closed merely because the paper page has no direct HF model link. Inspect the official repo for:

   - direct checkpoint links, release assets, Git LFS pointers, or download scripts;
   - training/evaluation scripts and configs that reproduce the reported checkpoint from public data or listed public artifacts;
   - linked Hugging Face model or dataset repos in the README, docs, shell scripts, config files, or release notes.

   If the official repo clearly releases weights, or clearly provides reproducible scripts for the evaluated model/checkpoint, treat the evaluated row as open (`is_open = true`) even when `hf_model_url` stays unset. Example: a paper whose official GitHub repo contains scripts to reproduce the reported policy checkpoint should not be marked closed just because Hugging Face has no linked model card.

   When the README or repo files mention HF repos that are not linked from the HF paper page, inspect them directly. HF repos without model cards, without `arxiv:` tags, or without README metadata can still be official if the source GitHub repo links them. Use these links for `papers.hf_models` and `evaluations.hf_model_url` only when the source ties them to the evaluated variant.

4. **Benchmark chart image** — when a card, README, or release page has no text score for a benchmark but embeds a results chart, download the image and read it (image viewer / vision). Import only values printed on the chart as numbers for bars clearly labeled as the introduced model; never estimate from bar height or axis gridlines. Apply the same version, split, setting, metric, and scale rules as for a table, and cite the image URL plus the exact panel title, bar label, and printed value (for example `Chart image on https://huggingface.co/org/model: panel "SWE-bench Verified", bar "Model-X (thinking)", printed "74.2"`) as the row's evidence. Prefer a text table whenever one exists. The remote curator follows the same procedure in `remote-paper-curation/SKILL.md`.

You can combine sources when each one carries part of the picture (e.g. the card has the "main" table, the paper has an ablation, the README has the final leaderboard). Track per-row context — which source the score came from, model variant / mode / shot count / metric label / backbone head or task framework / harness notes — so model names and methodology lines you write later are accurate and traceable.

While reading each source, also pin down the **raw model parameter count** for every model row you intend to import, since the database now stores it on each evaluation (`evaluations.num_parameters`, BIGINT). Check, in order: the HF model info JSON (`safetensors.total` or an explicit parameter field), the model card / paper / README headline that states the model size (e.g. "7B parameters", "355B-A22B", "1.5 billion parameters"), and any size column already in the source's own benchmark table. Convert size labels to the raw integer (`7B` -> `7_000_000_000`, `355B-A22B` -> `355_000_000_000` total parameters not active, `1.5B` -> `1_500_000_000`, `355M` -> `355_000_000`). Mixture-of-experts models should use **total** parameters by default; if you store the active count instead, mention it in `methodology` so the meaning of the stored value is unambiguous. If the source does not state the parameter count clearly for that specific variant, do not guess from sibling models, blog headlines, or organization conventions — leave the field unset for that row and report it as missing. Accuracy matters more than coverage here.

While reading each source, also try to pin down the **official Hugging Face model repo URL** for every model row you intend to import, since the database stores it per evaluation (`evaluations.hf_model_url`, TEXT). This is strictly opt-in: only set it when you are **100% certain** the repo is the exact evaluated model — never guess, and prefer leaving it blank over risking a false positive. Apply these rules:

- **Certainty gate.** Only populate `hf_model_url` when the source itself ties the score to that specific repo: the score table is on that model card, the card/README/paper explicitly links the evaluated checkpoint to the repo, or the repo id unambiguously matches the evaluated variant name and size. If a benchmark number could belong to a sibling model, a different size, a base vs instruct variant, or a comparator you are not 100% sure about, leave `hf_model_url` unset for that row.
- **Prefer the official organization.** Use the repo under the model's official HF organization (e.g. `MiniMaxAI/MiniMax-M3`, `Qwen/...`, `deepseek-ai/...`), not community re-uploads, mirrors, finetunes, or third-party conversions, even when those rank higher in search. If only a community mirror exists and no official repo, leave the field unset rather than linking the mirror.
- **Prefer the non-quantized weights.** When the official org publishes several variants of the same checkpoint that differ only by precision/quantization (e.g. a base repo plus `-FP8`, `-float16`, `-INT4`, `-GGUF`, `-AWQ`, `-GPTQ` repos), link the full-precision / non-quantized base repo. Only link a quantized repo when the evaluated row is specifically that quantized variant.
- **Distinct model variants get their own URL.** Different evaluated variants (size, mode, backbone) that have their own official repos should each point at their own repo; do not reuse one repo across rows that are genuinely different models.
- **HF paper linkage is not required.** A repo can be official even when it is not returned by `hf papers info`, has no model card, lacks an `arxiv:` tag, or is absent from the HF paper page. If the paper's official GitHub/project page links the repo and the repo contains the evaluated checkpoint/files, it is eligible for `hf_model_url`.

Closed-source API models (Claude/GPT/Gemini and similar) usually have no downloadable weights repo — leave `hf_model_url` unset for those rows. This field is independent of the paper-level `papers.hf_models` array; keep appending official model URLs there for traceability regardless.

Do not extract Elo scores. Cards, papers, and READMEs increasingly include LLM-judged Elo rankings (e.g. Gemini-judged Elo over olmOCR-Bench / OmniDocBench / XDocParse / OCRArena). These are pairwise-comparison rankings, not the benchmark's native metric, and they are tied to the specific judge model and pool of comparators used at the time of publication. They do not map to any leaderboard metric in this database and they are not comparable across sources, so skip every Elo table outright and only ingest the underlying native-metric tables (Accuracy, Edit Distance, ANLS, Pass@1, Score, etc.). Mention the skipped Elo table in the final report so the user knows it was intentional.

Do not decide harness handling from benchmark names alone. The database marks each task-dataset leaderboard with `task_datasets.supports_harness`. Only populate `evaluations.harness` when the selected leaderboard has `supports_harness = TRUE`. For Terminal Bench 2.0, SWE-Bench Verified, and SWE-Bench Multilingual, preserve named runtime/framework values such as `Terminus-2`, `OpenHands`, `MiniSWE-Agent`, or `Claude Code` when the source reports them. If the selected leaderboard supports harness values and the primary source plus official linked artifacts do not name the runtime/framework, set `harness = "Not reported"` rather than leaving it blank or using `unknown`. For non-supporting leaderboards, put runtime/framework/tool details in `methodology`, or use a concise `model_name` suffix for clearly distinct non-harness setups such as `(w/ tools)`, `(Agent Swarm)`, or `(w/ python)`.

### 2. Confirm import scope with the user

Sources typically contain several target-model variants and many comparator models. By default, import the best reported result from a model introduced by the source **for each benchmark leaderboard independently**, not one globally selected flagship row and not every ablation row. Benchmark pages rank results per dataset/metric, so the selected model may legitimately vary by benchmark: if one introduced variant wins ImageNet-O and a different introduced variant wins CLEVR Distance, import those two winning rows with their own model names. This keeps benchmark pages focused on the strongest reported result for the paper while avoiding comparator rows and lower-performing ablations. Before importing anything, agree with the user on:

- Which target-model rows are eligible. Sensible defaults:
  - Include only models/configurations introduced by the source paper or release. Exclude baseline/comparator rows such as Opus, GPT, Gemini, K2, GLM, CLIP, OpenCLIP, or previous versions unless the source itself introduced that model or the user explicitly asks for comparators.
  - **No external evals by default.** Every imported row must use the **source paper's `paper_id`** for the model that paper introduces. Do **not** scrape comparison-table baseline scores and attach them to other papers' `paper_id` rows, even when the source paper (e.g. a benchmark paper or SOTA comparison table) reports those numbers. That pattern — scores from paper A posted on paper B with `external_source_url` pointing back at A — is an **external eval** and is out of scope unless the user explicitly asks to import comparators or external evals. Phrases like "do the same for this paper" or "import the eval table" still mean **only the introducing model(s) on that paper**, not every column in the table. When skipping comparator columns, say so in the final report (e.g. `skipped external eval: RealBasicVSR scores from comparison table`).
  - For every source benchmark that survives the DB/metric filter, choose the highest score among eligible target rows using the configured leaderboard metric and direction. Do this per benchmark; do not assume the largest, newest, or most prominently named model is best everywhere.
  - If the best eligible row differs by benchmark because of mode, model size, backbone, compression level, decoding setting, tool use, or runtime setup, preserve that distinction in `model_name` or `harness` as appropriate. The same source paper can therefore produce evaluation rows with different model names across different benchmarks.
  - For multi-mode releases (e.g. Non-Think / High / Max / Thinking), use the best eligible mode per benchmark unless the source marks modes as incomparable for that leaderboard. If the source clearly presents one mode as the only intended comparable leaderboard setting, use that mode and mention the choice in `methodology`.
  - For multi-size product lines (e.g. Flash / Pro) or backbone/data-scale tables (e.g. ViT-B/32 vs ViT-L/14, 1B vs 2.5B), pick the benchmark-wise best eligible target variant by default. Import multiple rows for the same benchmark only when the user asks for family coverage or the source treats variants as separate primary models worth comparing side-by-side.
  - For base-model tables, exclude unless explicitly requested.
- Which benchmark tables to consider (base model, instruct, frontier comparison, modes-comparison) and which surface they come from (card / paper / README).

Ask the user once if anything is ambiguous; otherwise proceed with the defaults above and report exactly what was included and excluded at the end.

### 3. Resolve the source paper

Every evaluation row attaches to a `papers` row, regardless of which surface the numbers came from. Resolve or create the right source row before posting evaluations. Two common cases (for external papers the `source_url` should be the paper PDF when one exists, with the project page as a project link; see `add-external-paper`):

- ArXiv-backed: locate the paper row by `arxiv_id`. The release is usually already imported.
- External tech report / model release (HF model card, HF PDF, blog, vendor page, GitHub release page): use the `add-external-paper` skill first to create or update a `source = 'external'` paper row keyed by the canonical release URL, then return here and attach evals to that row.

**Always check HF model metadata `arxiv:` tags before falling back to an external row.** When the source is a HF model card (or a paper/README linked to a HF model), `uv run hf models info <repo_id>` returns a `tags` list that includes entries like `arxiv:2410.00037`. Each tag is the model's own declared canonical paper. Follow this resolution order:

1. Look up every `arxiv:` tag in the local `papers` table by `arxiv_id` (filtering on `is_latest_version`). If exactly one tag resolves to a local paper, use that paper as the source row and append the HF model URL (`https://huggingface.co/<repo_id>`) to its `hf_models` array for traceability. This is the common case — most flagship model cards list a single canonical paper — and it should be preferred over creating a new external row.
2. If multiple `arxiv:` tags resolve to local papers (ambiguous, e.g. a finetune that tags both its own paper and the base-model paper), pick the one the model card / README clearly identifies as the technical report for this release. If you cannot tell, stop and ask the user; do not guess.
3. If no `arxiv:` tag resolves to a local paper (none present, or all tags are unimported), fall back to the external-row path below. An ArXiv tag pointing at a paper we do not have is not, on its own, a reason to import a new ArXiv row in this skill — defer to the standard ingestion tooling and use an external row in the meantime if needed.

Use an ArXiv row only when it is actually the source for the evaluated model and scores. Do not attach a model-card / README evaluation table to a related technique paper just because the source cites it. If a user says a release "should be external" but the source's own HF metadata, model search, or report clearly resolves to a local canonical ArXiv paper for the same release, use the ArXiv row and mention that choice rather than creating a duplicate external row.

If the source is the primary surface for an unreleased or not-yet-paper-backed model, **pause this workflow and run the `add-external-paper` skill before any evaluation import**. Follow that skill's scope decision and metadata rules to create or update the external paper row with `source = 'external'`, a canonical `source_url`, title, abstract or source-grounded summary, `date_published`, official GitHub/project links, and full HF artifact URLs. After `add-external-paper` verifies the external row, resume this workflow using that row's `paper_id`. Do not post evaluations to a related paper, leave the source row missing, or invent a minimal paper record inside this skill.

Always populate `papers.date_published` for the source row. Scatter plots use this date to place benchmark progress over time, so do not leave external source rows undated. For ArXiv rows, use the paper's publication date. For external reports/blogs/model cards/README releases, use the source publication date from the page metadata, visible page date, release notes, or trusted source metadata; if you cannot determine it confidently, stop and ask the user instead of importing undated evaluations.

Look up the paper id with a read-only query, e.g.:

```python
from sqlalchemy import text
from backend.database.connection import get_engine
with get_engine().connect() as conn:
    rows = conn.execute(text(
        "SELECT id, arxiv_id, source, source_url, title FROM papers "
        "WHERE arxiv_id = ANY(:arxiv_ids) OR title ILIKE :t "
        "ORDER BY date_published DESC NULLS LAST LIMIT 5"
    ), {
        "arxiv_ids": ["<arxiv id from HF tags>", "..."],
        "t": "%<model family>%",
    }).fetchall()
    for r in rows:
        print(dict(r._mapping))
```

If no paper row exists for an ArXiv-backed source, use the standard ArXiv/import tooling or ask the user how to proceed; do not silently create an external duplicate for a real ArXiv paper. If no paper row exists for a non-ArXiv source, run `add-external-paper` immediately and only continue once it has created or reused a verified external row. Store HF artifacts as absolute URLs in `hf_models`, `hf_datasets`, and `hf_spaces`, not bare repo ids, because the frontend uses these fields directly as links.

When a release has a canonical ArXiv-backed model search on Hugging Face, prefer that search URL in `hf_models` over enumerating every individual model repo if it better represents the linked model family. Use the form `https://huggingface.co/models?other=arxiv:<arxiv_id>` for a paper-scoped model list, especially for external rows that summarize a collection or release with several official variants. Use individual model URLs such as `https://huggingface.co/org/model` when the source row is truly about one specific model, or when the user explicitly asks to link the exact repos.

### 4. Inventory existing benchmarks

For each benchmark name from the source, check the DB for an existing dataset, any existing task association, and existing leaderboard metrics. The semantic task page is not the comparability boundary for eval import: a result for `DocVQA` should attach to the already-configured `DocVQA` leaderboard even if that leaderboard currently lives under `Image Understanding` rather than a newer or more specific task. Use a single read-only query:

```python
from sqlalchemy import text
from backend.database.connection import get_engine

source_benchmarks = ["MMLU-Pro", "GPQA Diamond", "HLE", ...]  # exact labels from the source

with get_engine().connect() as conn:
    for name in source_benchmarks:
        pattern = "%" + name.replace("-", "%").replace(" ", "%") + "%"
        slug    = "%" + name.lower().replace(" ", "-").replace("_", "-") + "%"
        rows = conn.execute(text(
            "SELECT d.id, d.name, d.slug, "
            "       array_agg(t.name ORDER BY t.name) FILTER (WHERE t.id IS NOT NULL) AS tasks, "
            "       bool_or(COALESCE(td.supports_harness, FALSE)) AS any_supports_harness "
            "FROM datasets d "
            "LEFT JOIN task_datasets td ON td.dataset_id = d.id "
            "LEFT JOIN tasks t ON t.id = td.task_id "
            "WHERE d.name ILIKE :exact OR d.name ILIKE :pattern OR d.slug ILIKE :slug "
            "GROUP BY d.id, d.name, d.slug ORDER BY d.name LIMIT 5"
        ), {"exact": name, "pattern": pattern, "slug": slug}).fetchall()
        print(name, "=>", [dict(r._mapping) for r in rows] or "MISSING")
```

Then for each in-scope dataset id, list the leaderboard metrics that already exist:

```python
rows = conn.execute(text(
    "SELECT t.id AS task_id, t.name AS task_name, "
    "       td.supports_harness, m.name AS metric_name, m.direction "
    "FROM task_dataset_metrics tdm "
    "JOIN tasks t ON t.id = tdm.task_id "
    "JOIN task_datasets td ON td.task_id = tdm.task_id AND td.dataset_id = tdm.dataset_id "
    "JOIN metrics m ON m.id = tdm.metric_id "
    "WHERE tdm.dataset_id = :id"
), {"id": dataset_id}).fetchall()
```

Or via the API: `GET /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics`.

### 5. Apply the import filter

Apply the exclusion rules in this order:

1. Drop any benchmark with no matching dataset row in the DB.
2. Drop any matched benchmark with no task association at all.
3. For each matched benchmark, list the metrics already linked in `task_dataset_metrics` for every `(task_id, dataset_id)` leaderboard before choosing any row to import. Prefer the existing leaderboard whose metric matches the source metric exactly, even if its task label is broad, legacy, or not the task you would choose today. When several tasks are linked to the benchmark with that metric, use the one holding the most evaluations: the database rejects a row that would grow a smaller copy of a leaderboard on another task (`evaluations_single_benchmark_board`), and the error names the right task.
4. Drop any source row whose metric label is not already linked to one of the benchmark's existing leaderboards, unless the row can be converted to an already-linked canonical metric by a source-supported rule. Do not add the source metric to `metrics`, do not create a new `metrics` row, and do not add a `task_dataset_metrics` link in this skill.
5. Only use a canonical metric fallback when it preserves the same quantity, not merely the same benchmark name. For example, if a leaderboard only allows `Score`, an `MME Perception Score` or `MME Cognition Score` row must be skipped unless the source also reports enough official components to compute the overall `Score` and the source defines that sum as the leaderboard score. If a leaderboard only allows `Accuracy`, do not import `F1`, `Recall`, `Edit Distance`, or another table column as `Accuracy`.
6. Treat configured broad or legacy task pages as intentional, but keep metric support as the hard gate. This repo has consolidated narrower multimodal tasks into broad parent tasks such as `Image Understanding` and `Video Understanding`, and some benchmarks may remain under an older task even after a better task page exists. It is fine to add evaluations to those existing leaderboards when the dataset is linked there and the exact source metric is supported. Do not skip solely because the task name is broad or imperfect; skip only when the source metric is not supported/configured, a component/subscore is being mistaken for a canonical total, or the source setup cannot be compared to the configured leaderboard.
7. For each remaining benchmark, set `best_metric` to one of the already-linked metric names exactly as stored in `task_dataset_metrics`. The `metrics` JSON must contain only that selected metric key for the imported row unless every additional metric key is also linked to the same leaderboard and comparable on that page.
   **Idempotency gate:** compare each intended row with the existing evaluations returned in context. If the same introduced model, harness/setup, selected metric, and normalized score already exist on that leaderboard, treat the lane as satisfied and omit it from `evaluations`; do not rewrite a correct row merely to rephrase `methodology` or optional source metadata. When every eligible lane is already satisfied, submit an empty `evaluations` array (plus any genuine benchmark gaps) so the scheduled workflow records an accepted `no_changes` result. Do not manufacture `validation_evidence` for unchanged rows.
8. Normalize score scale to the existing leaderboard, not just the source table's printed unit. Read the configured metric `scale` before constructing the proposal. When a source prints a percentage but the catalog scale is `0-1`, divide by 100 (`91.9` -> `0.919`, `63.4%` -> `0.634`) and record the normalization in `methodology`. Conversely, never submit the printed percentage unchanged to a `0-1` metric. Before posting a `Score` row, inspect existing rows for that exact `(task_id, dataset_id, best_metric)` and compare the source value's magnitude with the leaderboard's native scale. OCRBench is the important 0-1000 case: model cards and blogs often report the same result as a percentage (for example `86.9%`). When importing OCRBench into dataset `OCRBench` / metric `Score`, convert percent-style values below 100 to native score by multiplying by 10 (`86.9` -> `869`, `91.90` -> `919`) and mention this normalization in `methodology`. Do not do this blindly for every benchmark named `Score`; if the existing leaderboard rows are mostly percent-scale or the source metric is a different quantity, keep the source value or skip and report the ambiguity.
9. For `FPS` rows, prefer an **optimized deployment speed** when the source reports one alongside a baseline runtime number. Papers and READMEs often headline TensorRT, ONNX, Triton, compiled inference, quantization, or cache-assisted speeds in parentheses or a second column (for example `18.6 (100.2)` meaning PyTorch vs TensorRT). Import the optimized figure as the `FPS` value and record the stack in `methodology` (e.g. "TensorRT with language cache; PyTorch Float32 speed is 18.6 FPS"). Do not skip optimized FPS just because it is not the unoptimized reference implementation; do not post two FPS rows for the same model unless the user asks for both setups separately.
10. Record `supports_harness` for the exact selected `(task_id, dataset_id)` row. This flag decides whether the API payload may include `harness`. If it is true, inspect the source notes, footnotes, model card metadata, official blog/report text, and linked official evaluation PRs or result files for a named harness before posting the row.
11. **Image-text retrieval direction is fixed per dataset slug — never mix directions on one leaderboard and never infer direction from existing rows:**
    - **`flickr30k-image-to-text` / `coco-captions-image-to-text`** (`Flickr30K Image-to-Text Retrieval` / `COCO Captions Image-to-Text Retrieval`) → import **image-to-text (I→T)** R@1 only (query image, retrieve caption).
    - **`flickr30k-text-to-image` / `coco-captions-text-to-image`** (`Flickr30K Text-to-Image Retrieval` / `COCO Captions Text-to-Image Retrieval`) → import **text-to-image (T→I)** R@1 only (query caption, retrieve image).
    - Do not import DataComp Table 9 aggregate “Flickr” / “MSCOCO” cells — those are the **arithmetic mean** of I→T and T→I, not either direction.
    - When a paper table lists both directions (TR/IR or image→text / text→image), pick the row matching the target dataset slug; put the other direction on the sibling text-retrieval benchmark if importing both is in scope.
    - Preserve setup suffixes such as `(zero-shot)` when they distinguish rows on the same leaderboard; do not strip `(image retrieval)` / `(text retrieval)` by folding into a shared name unless the directions live on separate benchmark slugs.
12. **Never edit or delete a row owned by a live leaderboard sync.** A row whose `methodology` starts with `Managed by the Papers with Code <source> live sync.` (Vals AI, Artificial Analysis, ARC Prize, Surge, Physics-IQ, and the other hourly syncs) is rewritten from the official leaderboard on every run, so a model-card or paper number must not replace its score, methodology, or other fields, and must not consolidate it away. The curation callback rejects such updates and removals. Do not work around it with a differently named row for the same model on that leaderboard either: the official leaderboard entry is the canonical result there. Skip the lane and report it as `managed by <source> live sync` (remote curators: a `not_applicable` outcome with `task_id`, `dataset_id`, and `metric`). Results for a different model, or on a different leaderboard, are unaffected.

Keep an explicit "skipped" list of names + reasons to report at the end. Use reasons like `metric not configured for leaderboard`, `no DB match`, `no task association`, `component metric only; canonical total not reported`, `external eval / comparator (not requested)`, or `source setup not comparable to configured leaderboard` so future cleanup is easy. Do not change task associations or leaderboard metrics in this pass; if the user explicitly wants to add tasks or metrics, defer to the `add-benchmark` skill instead.

### 6. Optional: minimal benchmark metadata enrichment

For matched benchmarks, normalize `paper_url` to the native `https://paperswithcode.co/paper/{arxiv_id}` form whenever a local paper row exists for the benchmark's introducing paper. Do this through the dataset PUT endpoint:

```bash
curl -s -X PUT "http://localhost:8000/api/v1/datasets/<id>" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"paper_url": "https://paperswithcode.co/paper/<arxiv_id>"}'
```

The `DatasetUpdateRequest` does not expose `introducing_paper_id` / `introducing_paper_title`. If the benchmark is missing those fields and you can confidently identify the source paper row, set them with a single direct SQL update — that is the only acceptable direct-DB write in this skill, and it is consistent with the `add-benchmark` skill:

```python
with get_engine().begin() as conn:
    conn.execute(text(
        "UPDATE datasets SET introducing_paper_id = :pid, "
        "introducing_paper_title = :title, "
        "introduced_year = COALESCE(introduced_year, :year) "
        "WHERE id = :did"
    ), {"pid": paper_id, "title": paper_title, "year": year, "did": dataset_id})
```

If the source paper cannot be confidently identified, leave the dataset alone and report it as a metadata gap.

### 7. Post evaluations via the API

Use `POST /api/v1/evaluations/` with `X-Admin-Token`. Build one row per benchmark using the benchmark-wise best eligible target result selected in step 2. Before posting each row, assert that `best_metric` is in the allowed metric list fetched for that exact `(task_id, dataset_id)` pair and that every key in the outgoing `metrics` object is allowed for that leaderboard. Include `harness` only when the selected leaderboard's `supports_harness` flag is true. The unique key is `(paper_id, task_id, dataset_id, model_name, harness, best_metric)`, so:

- For rows on the introducing paper, set `external_source_url` to that paper's own `source_url` (the PDF for external papers) or leave it unset, so the rows are not shown as external evals. Never point it at a different surface such as the project page.
- Set `paper_id` to the **introducing paper for the evaluated model** (the source paper from step 3). Do **not** post comparison-table baseline scores onto other papers' `paper_id` values as external evals unless the user explicitly requested comparator import. Use `external_source_url` only for traceability on rows that genuinely belong on that `paper_id` (e.g. a score copied from a linked report), not as a way to attach another paper's comparison column to the wrong paper page.
- Use the model name as written in the paper/source, keeping it short, readable, and suitable for display. Normalize typographic/source formatting into plain title-style text: convert subscripts, all-caps size suffixes, and code-style names such as `LayoutLM_BASE`, `LayoutLM<sub>BASE</sub>`, or `BROS_LARGE` to `LayoutLM Base` and `BROS Large`. Never include author-relative labels like `our`, `ours`, `our model`, or `ours model` in `model_name`; those phrases only identify the authors' own method in context and should be replaced with the actual model name or a neutral setup label such as `(full data mix)`, with the source phrasing noted in `methodology` if needed. Put setup details such as "fine-tuned", parameter count, harness, mode, precision, or training recipe in `methodology` unless they are part of the source's actual model name.
- For papers that introduce a backbone or representation model, include the task framework, decoder, or head in `model_name` when the benchmark score is for the backbone inside a downstream system. This keeps leaderboard rows comparable and understandable: use names like `ConvNeXt-XL + UperNet` for ADE20K semantic segmentation or `ConvNeXt-XL + Cascade Mask R-CNN` for COCO detection/instance segmentation. Keep the backbone-only name for classification or direct backbone evaluation rows, and put pretraining/fine-tuning schedules in `methodology`.
- Distinguish variants from the same release with `model_name`, e.g. `DeepSeek-V4-Pro Max` vs `DeepSeek-V4-Flash Max`, `MetaCLIP ViT-B/32 (2.5B data)` vs `MetaCLIP ViT-L/14 (1B data)`, or `ConvNeXt-XL + UperNet` vs `ConvNeXt-XL + Cascade Mask R-CNN`. Do NOT bake harness names or parameter counts into `model_name` — keep `model_name` clean (e.g. `GLM-5.1`, not `GLM-5.1 (Terminus-2)` or `GLM-4.5 (355B)`). Include mode, backbone, data scale, shot count, tool-use suffix, or task framework in `model_name` only when it identifies the benchmark-wise selected setup or affects leaderboard comparability. Parameter counts live in the dedicated `num_parameters` field instead (see below).
- Set `num_parameters` only when the source confidently reports the model's raw parameter count. Send the raw integer total (`7_000_000_000` for a 7B model, `355_000_000_000` for `355B-A22B`, `1_500_000_000` for `1.5B`); the API rejects negative values and the column is a `BIGINT`, so do not pre-format it as `"7B"` or `"7000M"`. Use total parameters for MoE models by default and note `active=<n>` in `methodology` if the source also reports the active count. If a particular row's parameter count is not stated in the primary source or in an official linked artifact for that exact variant, omit the field for that row rather than guessing from a sibling model, the release headline, or organization convention. Two size variants of the same release (e.g. `Flash` vs `Pro`) always become separate rows with their own `num_parameters` values; never reuse one number across both.
- Since the default import scope is the benchmark-wise best eligible target result, model-name suffixes for variants like `(zero-shot)`, `(4x)`, `(16x)`, `(Non-Think)`, `(w/ tools)`, or a backbone/data-scale label should appear when they identify the selected best setup for that benchmark. Do not reuse one generic model name across all rows when different variants supply the winning scores.
- Preserve benchmark shot-count comparability in `model_name`. If the source reports a multi-shot result for a benchmark whose leaderboard commonly compares 1-shot results, append the shot count to the model name, e.g. `Llama 2 70B (8-shot)`, `Llama 2 70B (5-shot)`, or `Llama 2 70B (3-shot)`. Keep plain `Model Name` for 1-shot rows. Mention the exact shot count in `methodology` either way.
- When importing a **zero-shot transfer** result and the source distinguishes it from fine-tuned or in-domain rows, append `(zero-shot)` to `model_name` (e.g. `Grounding DINO 1.5 Pro (zero-shot)`). Omit the suffix for fine-tuned rows; mention the eval protocol in `methodology` either way.
- Set `harness` only for leaderboards where `supports_harness = TRUE`. Use the source-attributed runtime/framework verbatim (`Terminus`, `Terminus-2`, `OpenHands`, `Claude Code`, `SWE-Agent`, etc.). If the source does not report a harness after checking the primary source and official linked artifacts, use `harness = "Not reported"` and mention the missing attribution in the final report.
- Leave `harness` unset (null) on every leaderboard where `supports_harness = FALSE`, even when the setup is agentic or tool-augmented. Capture those details in `methodology`, or in a concise `model_name` suffix only when the setup represents a distinct non-harness condition.
- Two harness variants of the same model on a harness-supporting leaderboard (e.g. `GLM-5.1` with `Claude Code` and `GLM-5.1` with `Terminus-2`) become two separate rows that differ only in `harness`. They are not duplicates.
- Distinguish setups on the same benchmark that are NOT about harness (e.g. `HLE` vs `HLE w/ tools`) via a `model_name` suffix like `(w/ tools)` plus a clear `methodology` description, since the metric is shared. Only do this if the metric/methodology can clearly distinguish the rows — otherwise skip and report.
- Skip component, subscore, split, or alternate-metric rows when their metric is not configured on the selected leaderboard. Examples: skip `MME Perception Score` and `MME Cognition Score` on an `MME` leaderboard that only allows `Score`; skip `MME-P` unless a separate MME-P dataset/leaderboard exists with that metric configured.
- Normalize values to the leaderboard's native scale before posting. For OCRBench `Score`, store the native 0-1000 score (`869`), not the percent-style rendering (`86.9%`) commonly shown in VLM release tables. If you convert a source value, say so in `methodology` so future maintainers can trace why the stored value differs from the printed table.
- For `FPS`, use the optimized deployment speed when the source reports both baseline and optimized numbers (TensorRT, ONNX, compiled inference, language cache, etc.). Put the optimization stack in `methodology` and note the baseline FPS there too when available.
- Always include `methodology` summarizing the source's note for that row (shot count, metric label, mode, harness version, source surface — card/paper/README — etc.) so the row is traceable back to where the number came from.
- Set `hf_model_url` only when you are 100% certain it is the exact evaluated model's official Hugging Face repo (e.g. `https://huggingface.co/MiniMaxAI/MiniMax-M3`); it must start with `https://huggingface.co/`. No false positives: when in doubt, leave it unset. Prefer the official organization over community mirrors/finetunes, and prefer the non-quantized base repo over `-FP8`/`-float16`/`-INT4`/`-GGUF`/`-AWQ`/`-GPTQ` variants unless the row is specifically that quantized variant (see the certainty/official-org/non-quantized rules in step 1). This makes the leaderboard model name link to the model page; it is independent of the paper-level `papers.hf_models` array (keep updating that too). Omit it for closed-source API models or scores pulled from a paper/README with no matching repo.
- Set `is_open` on every row. The API defaults to `true`, but many frontier releases are closed-source API models. Users can hide closed rows via Settings → "Hide closed-source models"; rows missing this flag look like open-weight results. Decide once per imported model variant, then reuse the same boolean on every row for that variant.

#### Closed-source (`is_open = false`)

Set `is_open: false` when there is **no evidence of an open-weight release** for the evaluated model variant. This is the common case for proprietary frontier models from Anthropic (Claude), OpenAI (GPT / o-series), Google (Gemini), xAI (Grok), and similar API-only vendors.

Treat a release as closed-source when any of these hold and none of the open-source signals below apply:

- The source is a blog post, system card, vendor report, or API announcement with pricing/access details but no public weights.
- Weights are unavailable, restricted (trusted-access / allowlist / enterprise-only), unreproducible from public artifacts, or inference-only through a vendor API.
- The only linked Hugging Face artifact is a demo Space, dataset, or unrelated base model — not downloadable weights for the evaluated checkpoint.
- The evaluated product is clearly a proprietary model name (`Claude …`, `GPT-…`, `Gemini …`, etc.) with no accompanying open-weight release in the same source chain.

Recent examples: Claude Opus/Fable/Mythos, GPT-5.x, Gemini 3.x — all `is_open: false` unless the release also ships open weights.

#### Open-source (`is_open = true`)

Keep `is_open: true` (the API default) when the evaluated variant has clear open evidence. Direct HF linkage is sufficient but not required:

- An official Hugging Face **model** repo with downloadable weights for that checkpoint (not just a paper link or `arxiv:` tag).
- An official GitHub release that distributes weights or states they are publicly released under an open license.
- The paper/card/README explicitly open-sources the exact evaluated model and links the artifact.
- The official GitHub/project repository provides scripts, configs, and documented commands to reproduce the evaluated checkpoint from public code/data/artifacts. This counts as open even if no pretrained HF model card exists.
- The official GitHub/project repository links HF checkpoint or dataset repos that are not linked from the HF paper page because they lack cards, README metadata, or `arxiv:` tags.

Separate `is_open` from `hf_model_url`: a row may be `is_open = true` with no `hf_model_url` when the only evidence is reproducible GitHub code or a non-HF weight release. Conversely, only fill `hf_model_url` when the exact HF repo is known.

When evidence is mixed (API product plus a separate open research checkpoint), set `is_open` from the **evaluated row's model variant**, not the lab's general policy. If the leaderboard row is for an API-only flagship and a smaller open checkpoint also exists, the flagship row stays closed.

When genuinely uncertain after checking the primary source plus official linked artifacts, prefer `is_open: false` for major closed vendors and mention the ambiguity in the final report rather than defaulting to open.

Skeleton:

```python
import json, os, urllib.request, urllib.error
ADMIN_TOKEN = os.environ["PWC_ADMIN_API_TOKEN"]
BASE = "http://localhost:8000/api/v1"

def normalize_score_for_leaderboard(dataset_name, metric, score):
    # OCRBench's configured Score leaderboard uses the native 0-1000 scale.
    # Many VLM release tables print the same number as a percentage.
    if dataset_name == "OCRBench" and metric == "Score":
        numeric = float(str(score).rstrip("%"))
        if numeric < 100:
            scaled = numeric * 10
            return str(int(scaled)) if scaled.is_integer() else f"{scaled:g}"
    return f"{score}".rstrip("%")

def determine_is_open(source_urls, hf_model_repo_ids=None):
    """Return False for proprietary API releases unless open/reproducible artifacts are evidenced."""
    hf_model_repo_ids = hf_model_repo_ids or []
    open_weight_markers = (
        "apache", "mit license", "open weights", "open-weight", "open source weights",
        "model weights are available", "weights available on hugging face",
        "public checkpoint", "checkpoint release", "pretrained weights",
        "reproduce our checkpoint", "training scripts", "evaluation scripts",
        "download weights",
    )
    blob = " ".join(source_urls).lower()
    if any(marker in blob for marker in open_weight_markers):
        return True
    if hf_model_repo_ids:
        return True
    closed_vendors = ("anthropic.com", "openai.com", "blog.google", "deepmind.google", "x.ai")
    if any(v in blob for v in closed_vendors):
        return False
    return True  # non-vendor academic/GitHub releases default open unless proven otherwise

IS_OPEN = determine_is_open(
    source_urls=["<announcement/system card/github readme>"],
    hf_model_repo_ids=[],  # e.g. ["org/open-model-7b"] when weights are official
)

def post_eval(
    paper_id, task_id, dataset_id, dataset_name, model_name, metric, score,
    methodology, harness=None, num_parameters=None, is_open=IS_OPEN,
):
    allowed_metrics = allowed_metrics_by_leaderboard[(task_id, dataset_id)]
    outgoing_metric_keys = {metric}
    if metric not in allowed_metrics or not outgoing_metric_keys <= allowed_metrics:
        raise ValueError(
            f"Metric {metric!r} is not configured for task={task_id}, dataset={dataset_id}"
        )
    normalized_score = normalize_score_for_leaderboard(dataset_name, metric, score)

    body = {
        "paper_id": paper_id,
        "task_id": task_id,
        "dataset_id": dataset_id,
        "model_name": model_name,
        "methodology": methodology,
        "metrics": {metric: normalized_score},
        "best_metric": metric,
        "is_open": is_open,
    }
    if harness:
        body["harness"] = harness
    # Only include num_parameters when the source confidently reports it for
    # this exact variant. Guessing here is worse than leaving the field unset.
    if num_parameters is not None:
        body["num_parameters"] = int(num_parameters)
    req = urllib.request.Request(
        f"{BASE}/evaluations/",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Admin-Token": ADMIN_TOKEN},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
```

Common error responses:

- `400 Failed to create evaluation: No leaderboard defined ...` — the dataset has no metric linked for that task. The benchmark should have been filtered out in step 5; recheck the inventory.
- `400 Metric '<X>' is not allowed ...` — the row escaped the filter. Do not retry with a newly invented metric or a loose fallback; recheck the allowed metrics for that leaderboard and skip the source row if its metric is not configured.
- Scheduled callback validation errors are correctable once within the same job. Read the returned detail, rebuild the whole proposal, and retry once. For an out-of-range value, normalize it to the configured scale. For `one paper-native result per leaderboard`, keep only the best introduced-model lane for that `(task, dataset, metric)` and drop lower-performing or duplicate task-view rows. If an existing-row update cannot be supported by the exact before-state, field diff, and primary evidence, omit that unverifiable update from the corrected complete proposal; never invent a diff or evidence merely to pass validation. Do not repeat an unchanged rejected proposal.
- `401 Unauthorized` — first check that `PWC_ADMIN_API_TOKEN` is loaded and the `X-Admin-Token` header is correct. If the local route is enforcing an HF-admin browser session despite the token, use `EvaluationService` directly from a short `uv run --env-file backend/keys.env python` script instead of changing auth behavior.

Service fallback shape:

```python
from sqlalchemy import text
from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService

is_open = False  # set from determine_is_open(...) before the loop

params = {
    "paper_id": paper_id,
    "task_id": task_id,
    "dataset_id": dataset_id,
    "model_name": model_name,
    "harness": harness,
    "best_metric": best_metric,
}

session_gen = get_database_session()
db = next(session_gen)
try:
    existing = db.execute(text("""
        SELECT id FROM evaluations
        WHERE paper_id=:paper_id AND task_id=:task_id AND dataset_id=:dataset_id
          AND model_name=:model_name
          AND COALESCE(harness, '') = COALESCE(:harness, '')
          AND best_metric=:best_metric
    """), params).first()
    if not existing:
        EvaluationService(db).create_evaluation(
            paper_id=paper_id,
            task_id=task_id,
            dataset_id=dataset_id,
            model_name=model_name,
            methodology=methodology,
            metrics={best_metric: score},
            best_metric=best_metric,
            harness=harness,
            external_source_url=source_url,
            num_parameters=num_parameters,
            is_open=is_open,
        )
finally:
    try:
        next(session_gen)
    except StopIteration:
        pass
```

### 8. Validate and verify

Run the standard validation script (it is a dry-run by default, pass `--fix` only if you really want to mutate):

```bash
uv run --env-file backend/keys.env python backend/database/validate_evaluation_metrics.py
```

Then verify the imported rows:

```bash
curl -s "http://localhost:8000/api/v1/evaluations/?paper_id=<paper_id>&page_size=100" \
  | uv run python -c "import json,sys; d=json.load(sys.stdin); print(d['count']); [print(e['model_name'], '/', e.get('harness') or '-', e['dataset_name'], e['best_metric'], e['metrics'].get(e['best_metric']), 'open=', e.get('is_open'), 'rank=', e.get('best_rank'), 'params=', e.get('num_parameters') if e.get('num_parameters') is not None else '-') for e in d['results']]"
```

And confirm there are no duplicate `(paper_id, task_id, dataset_id, model_name, harness, best_metric)` rows for the imported paper.

For OCRBench imports, also verify that every imported `Score` value is on the native 0-1000 scale. A simple sanity check is that no newly imported OCRBench `Score` is below 100 unless the source and existing leaderboard rows prove that the benchmark is intentionally percent-scale.

## Reporting back

End by giving the user a concise report:

- The PapersWithCode paper URL for the source row, as the final line of the response. Use `https://paperswithcode.co/paper/{arxiv_id}` for ArXiv rows and `https://paperswithcode.co/paper/{paper_id}` for external rows without an ArXiv ID. Do not use the HF repo id, GitHub URL, or `source_url` path as the local paper route, because repo ids such as `Hcompany/Holo2-235B-A22B` contain slashes and do not resolve as paper identifiers.
- Which source(s) the evaluation table actually came from — model card, paper body, GitHub README, or a combination — so the user can audit the provenance quickly.
- Which model variants were imported and how many rows were posted per variant. For harness-supporting leaderboards, list each `(model, harness)` combination explicitly.
- The list of in-scope benchmarks, with `dataset_id`, `task`, `best_metric`, and `supports_harness`.
- The list of skipped benchmarks or rows with the reason for each (no DB match / no task / metric not configured for leaderboard / component metric only / **external eval or comparator column (default: skip)** / missing source paper / could not distinguish setup).
- Any metric value normalizations applied before import, especially OCRBench percent-style values converted to the native 0-1000 `Score` scale.
- Any benchmark metadata gaps left for follow-up (e.g. missing `introducing_paper_id`, no arXiv source paper, missing source publication date, missing harness attribution for a harness-supporting leaderboard).
- Any harness details from the source that were downgraded into `methodology` or `model_name` because `supports_harness = FALSE`.
- For each imported model variant, the `num_parameters` value used (or "not reported" when the source did not state it confidently). If a count was set, briefly note where it came from (HF `safetensors.total`, model card body, paper, README) and whether it represents total or active parameters for MoE models.
- The `is_open` value used for each imported variant (`true` = open-weight release evidenced; `false` = closed/proprietary API model). If you marked a row closed, note briefly why (e.g. "Anthropic API release, no public weights").
- Whether `hf_model_url` was set for each imported variant and which official repo it points at, or "not set" with the reason (closed-source, no confident official repo, or only community/quantized repos available). Confirm any linked repo is the official org's non-quantized checkpoint.
- Whether the source is part of a model-family chain and should be linked with predecessor/successor papers. If yes, run `uv run --env-file backend/keys.env pwc paper lineage add <predecessor> <successor>` as a follow-up rather than doing ad hoc SQL in this skill.

## When NOT to use this skill

- The user wants to add a brand-new benchmark to the database, link it to a task, or set leaderboard metrics. Use `add-benchmark` for that.
- The user only wants the model card / README / paper summarized, with no intent to populate evaluation rows. Hand off to general tooling instead.

## Quick reference

- Source fetch:
  - Card: `uv run hf models card <repo_id> --text`
  - Model metadata (incl. arXiv tag, linked papers): `uv run hf models info <repo_id>`
  - Paper text: `uv run hf papers read <arxiv_id>`
  - Paper metadata (incl. GitHub repo link): `uv run hf papers info <arxiv_id>`
  - HF models tagged with a paper: `curl -L "https://huggingface.co/models?other=arxiv:<arxiv_id>"` (candidate sources only; verify the paper introduced the model)
  - GitHub README: `gh api repos/<owner>/<repo>/readme -H "Accept: application/vnd.github.raw"`
- API base: `http://localhost:8000/api/v1/`.
- Admin token: `PWC_ADMIN_API_TOKEN` in `backend/keys.env`, header `X-Admin-Token`.
- Endpoints used: `PUT /datasets/{id}`, `GET /datasets/{id}/tasks/{task_id}/metrics`, `POST /evaluations/`, `GET /evaluations/?paper_id=...`.
- Uniqueness for evaluations: `(paper_id, task_id, dataset_id, model_name, harness, best_metric)`.
- Source rows must have `papers.date_published` populated from the source publication date so benchmark scatter plots can place results over time.
- Harness column: optional `evaluations.harness` (VARCHAR(255)) — populate it only when the selected `(task_id, dataset_id)` row has `task_datasets.supports_harness = TRUE`; use the named runtime verbatim (for example `Terminus-2`, `OpenHands`, or `Claude Code`), or `Not reported` when the source omits it after checking primary and official linked sources. Leave null for non-supporting leaderboards and report any downgraded harness-like details.
- Parameter count column: optional `evaluations.num_parameters` (BIGINT, non-negative) — raw integer total parameter count for the model row (e.g. `7000000000` for a 7B model). Populate only when the source confidently states the count for that exact variant; never guess from siblings, headlines, or organization conventions. Use total parameters for MoE models by default and note active counts in `methodology`. Omit the field entirely when the count is unknown.
- HF model link column: optional `evaluations.hf_model_url` (TEXT, must start with `https://huggingface.co/`) — link to the evaluated model's Hugging Face model page (e.g. `https://huggingface.co/MiniMaxAI/MiniMax-M3`). Populate per row only with 100% certainty (no false positives), preferring the official organization repo and the non-quantized base weights over precision/quantization variants (`-FP8`, `-float16`, `-INT4`, `-GGUF`, `-AWQ`, `-GPTQ`). Independent of `papers.hf_models` (paper-level traceability): keep appending the URL there too. Omit when the variant has no confident official HF repo (closed-source API models, or scores from a paper/README with no matching repo).
- Open-source flag: optional `evaluations.is_open` (BOOLEAN, default `true`) — set `is_open: false` on POST for proprietary API models (typical Claude/GPT/Gemini releases) when no open or reproducible artifact is evidenced; keep `true` when official HF/GitHub weights exist, or when the official GitHub/project repo provides public scripts/configs to reproduce the evaluated checkpoint. This does not require `hf_model_url`; papers can have open evals without a direct HF model link.
- FPS rows: when a source reports both baseline and optimized inference speed, import the optimized figure (TensorRT, ONNX, compiled inference, language cache, etc.) and document the stack plus baseline FPS in `methodology`.
- Native benchmark source URL form: `https://paperswithcode.co/paper/{arxiv_id}`.
