---
name: review-submissions
description: Review the outstanding community submissions queue at paperswithcode.co/submissions and approve or reject each one — new external papers, new tasks/methods/benchmarks/metrics/conferences/organizations, and paper edits held back from auto-approval. Use whenever the user asks to go over, triage, clear, review, approve, or reject submissions, pending edits, the submission queue, or user suggestions, even if they only paste the /submissions URL. Verifies each submission against the catalog and its source, creates taxonomy entities that deserve to exist, records decisions with a reason the submitter sees, and checks the result live.
---

# Review submissions

Signed-in users submit suggestions from paper pages and the "Submit" flows. Most
paper edits auto-apply (see `backend/services/pending_edit_auto_approval.py`);
what stays `pending` needs a human decision:

| `edit_type` | Approve does | Typical volume |
| --- | --- | --- |
| `new_external_paper` | creates the paper (needs title + date) | most rows |
| `new_organization` | creates the org and links it to the submission's paper | rare |
| `new_task`, `new_method`, `new_benchmark`, `new_metric`, `new_conference` | **records the decision only** — create the entity yourself first | a few |
| paper edits (`tasks`, `repositories`, `evaluations`, …) | applies the edit; held for an unfamiliar domain, an unconfigured benchmark/metric, or rate guards (reason in `admin_note`) | occasional |

Production is the default environment. This is data curation: no PR or deploy.

## 1. List the queue

```bash
uv run --env-file backend/keys.env python -m backend.cli submissions list \
  --environment production --status pending --limit 100 --json
```

The JSON has `count` and `results` (each with `id`, `edit_type`, `paper_id`,
`hf_username`, `is_author`, `proposed_payload`, `admin_note`). Group rows by
`hf_username` first: users often submit the same paper several times (IEEE +
GitHub + Zenodo + HF copies, or once without and once with a title).

Also pull the submitter's history — a resubmission after a rejection should be
judged against why it was rejected:

```sql
SELECT id, status, edit_type, proposed_payload->>'source_url', user_review_reason
FROM pending_paper_edits WHERE hf_username = :u ORDER BY id;
```

Read `docs/database.md` before querying; read-only SQL through
`uv run --env-file backend/keys.env python -I <scratchpad script>` is fine.

## 2. Verify each row

### `new_external_paper`

1. **Duplicate in the catalog?** `SELECT id, title, source, arxiv_id FROM papers
   WHERE title ILIKE :fragment`. If present → reject, point to `/paper/<id>`.
2. **arXiv copy?** Query `https://export.arxiv.org/api/query` with
   `ti:"…"` and `au:<surname>` (strip diacritics: `Alikasifoglu`, not
   `Alikaşifoğlu`). If one exists and is not indexed, run
   `uv run --env-file backend/keys.env python -m backend.cli paper index <arxiv_id>` and reject with "This paper is
   on arXiv, so we added it from there: /paper/<arxiv_id>."
3. **Resolve title, authors, date, abstract** when the payload lacks them:
   - DOI → `https://api.crossref.org/works/<doi>`; IEEE pages block curl, so
     use Crossref `works?query.bibliographic=<title>`.
   - Zenodo → `https://zenodo.org/api/records/<id>`.
   - HF model → `https://huggingface.co/api/models/<repo>` (check real weights
     exist, base model, and whether it links a technical report).
   - Conference open-access pages (MICCAI, ACL anthology `.bib`, CVF) → fetch
     the HTML; use the PDF's `last-modified` or the proceedings date if no date
     is printed.
   - OpenReview returns a browser challenge to curl: if it is the only source
     and the payload has no title, reject asking for a resubmission with title
     and date.
4. **Is it AI research?** Reject spam, escort/SEO sites, blog tutorials,
   product pages, and unresolvable domains with "This link is not an AI
   research paper or artifact, so we didn't add it."
5. For a set of copies of the same work, approve the most canonical one (the
   report/DOI with title over a bare model card) and reject the rest with
   "Thanks! This is the same paper as your other submission, which we added."

Self-published reports with open weights (Zenodo, HF model cards) are
acceptable; inflated wording in the abstract is not a reason to reject. Fix a
wrong `date_published` (e.g. a submitter's "today" vs the record's real date)
through `resolved_payload`.

### `new_task` / `new_method` / `new_benchmark` / `new_metric` / `new_conference`

Approve only if the entity belongs in the catalog and does not already exist.
Reject when:

- it already exists (link it: `/tasks/<slug>`, `/conferences/<slug>`);
- a task is too broad or overlaps an existing one ("Speech Processing",
  "Noise Reduction", "fine-tuning");
- a "benchmark" is one paper's own ablation or validation protocol rather than
  a dataset other papers report on ("These are validation ablations rather
  than a shared benchmark");
- a "metric" is really a dataset condition (fog density, noise level);
- a "method" is a specific model — models are papers, methods are general
  techniques.

To approve, create the entity first with the matching skill — `add-task`,
`add-method`, `add-benchmark` (also for metrics on a benchmark),
`add-conference` — then record the approval with `result_entity`
(`["task", 1015]`, `["dataset", 3165]`, …) and an `admin_note` like
`Added as /tasks/<slug> (task <id>)`.

### `new_organization`

Approve only if the paper's authors are actually affiliated (check the PDF's
first page). Approval creates the org and links it to the paper.

### Held paper edits

Read `admin_note` for why auto-approval held it. Check the link or evaluation
against the paper itself: approve faithful additions (author's own repo, project
page, evals on a configured leaderboard that match the paper's tables); reject
anything unrelated or unverifiable. Evaluations on unconfigured benchmarks need
the benchmark/metric to exist first (`add-benchmark`), otherwise reject and say
which leaderboard to use.

## 3. Record decisions

Write a decisions file in the scratchpad (format in the script's docstring),
dry-run, then apply:

```bash
uv run --env-file backend/keys.env python \
  .agents/skills/review-submissions/scripts/apply_decisions.py <decisions.json>
uv run --env-file backend/keys.env python \
  .agents/skills/review-submissions/scripts/apply_decisions.py <decisions.json> --apply
```

The script refuses rows that are no longer pending, rows without a
`user_review_reason`, and record-only approvals without `result_entity`.

- `user_review_reason` is shown to the submitter: short, friendly, starts with
  "Thanks!", says what happened and, if relevant, where to go
  (`/paper/<id>`, `/tasks/<slug>`). Approved papers: "Thanks! The paper now has
  a page on Papers with Code."
- `admin_note` is internal: the evidence (Crossref DOI, arXiv check, duplicate
  ids).

Approved external papers are queued for auto-curation (enrich → add-evals) by
the curation scheduler; no extra step is needed.

## 4. Verify and report

- `submissions list --status pending` again: the queue should be empty (or
  report what is left and why — e.g. waiting on the user for a taxonomy call).
- Each new paper responds at `https://paperswithcode.co/api/v1/papers/<id>`
  (send `User-Agent: curl/8.5.0`; Cloudflare blocks default agents).
- Report a table: submission id, type, submitter, decision, resulting
  `/paper/<id>` or entity, one-line reason.

When a judgment call is genuinely ambiguous (a borderline new task, a
benchmark that may or may not be community-wide), ask the user rather than
guessing; everything else, decide.
