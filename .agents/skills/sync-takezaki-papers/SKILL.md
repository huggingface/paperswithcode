---
name: sync-takezaki-papers
description: >-
  Sync the papers Shumpei Takezaki (@shumpeiMaxwell on X) posts about into
  Papers with Code: read his recent posts, index every missing arXiv paper
  (and the arXiv version of journal papers), enrich each paper (code, project
  page, HF artifacts, tags, thumbnail), add its evaluation results to existing
  leaderboards, merge external/arXiv duplicates, and link his explainer thread
  to each paper's X threads section. Use whenever the user asks to check, sync,
  sweep, or process Shumpei's / Takezaki's / @shumpeiMaxwell's recent tweets or
  papers, or asks whether the papers he posted are indexed, enriched, or have
  evals. Also works for another curator account via --handle.
---

# Sync Takezaki papers

Shumpei Takezaki (@shumpeiMaxwell) posts a steady stream of "Title + TL;DR +
arXiv link" explainers, mostly on generative modeling, diffusion/flow
matching, representation learning and world models. This skill makes every
paper he posts a complete Papers with Code page: indexed, enriched, evaluated
where an existing leaderboard fits, and with his post in the X threads card.

Run from the primary checkout (it has `backend/keys.env`). Keep all working
files in the scratchpad, one subdirectory per subagent.

## 1. Get a working X token

The timeline read uses the same OAuth2 user token as `process-x-bookmarks`:

```bash
uv run --env-file backend/keys.env python .agents/skills/process-x-bookmarks/scripts/x_user_token.py --refresh
```

If the refresh fails, follow step 1 of `process-x-bookmarks` (`--link` /
`--finish`). HTTP 402 means X credits are depleted: stop and tell the user.

## 2. Triage the timeline

```bash
uv run --env-file backend/keys.env python .agents/skills/sync-takezaki-papers/scripts/triage_timeline.py \
    --max 200 --out <scratchpad>/takezaki.json
```

- Reads his newest `--max` posts (retweets excluded; X reads are paid, so keep
  `--max` to what the user asked for, about 100 posts per two weeks). Posts are
  cached in `<out>.raw.json`; rerun with `--from-raw <out>.raw.json` after
  indexing instead of fetching again.
- Keeps only threads he started (replies in other people's conversations are
  dropped) and prints one line per arXiv paper: `MISSING`, `UNLINKED` or
  `linked`, with db id, evaluation count and enrichment `gaps`.
- `NON-ARXIV` lines are threads with other links. Decide each by hand:
  - A journal or conference paper (Nature, PMLR, CVF…): search arXiv by title
    (`https://export.arxiv.org/api/query?search_query=ti:"<title>"`) and index
    the arXiv version; he often posts the journal title, which can differ
    from the arXiv title.
  - A real release without a paper (tech report, model card): use
    `add-external-paper` after searching the catalog for duplicates.
  - Personal blog analyses, workshop announcements, talks and study-group
    posts: skip, and list them in the report.
- `<out>.links.json` holds his threads for indexed papers that are not linked
  yet, in `link_threads.py` format.

## 3. Index missing papers

```bash
for id in <missing arXiv ids>; do
  uv run --env-file backend/keys.env python -m backend.cli paper index "$id"
done
```

About a minute per paper; run a long list in the background. It is
idempotent and prints `created: paper=<arXiv> id=<db id>`. Then rerun the
triage with `--from-raw` so the new papers get db ids and appear in
`<out>.links.json`.

## 4. Enrich and add evals

Do both steps for every paper that is new, has `gaps`, or has 0 evaluations.
Skip papers that already have no gaps and some evaluations. Spread the work
over subagents, three or four papers each, every subagent with its own scratch
subdirectory (`<scratchpad>/batchA`, …). Give each subagent the db id, arXiv
id, title and known gaps, and tell it to:

1. follow `enrich-paper` (official repo, project page, HF artifacts, existing
   task/method tags, thumbnail; rejecting website-template and cited-baseline
   repos), then
2. follow `add-evals` (only the paper's own models, only on existing
   benchmarks with the exact metric configured; nothing to add is a valid
   outcome), and
3. report per paper: what changed, eval rows (benchmark, metric, value,
   rank, `is_open`), and why anything was skipped.

Theory and analysis papers often end with tags and a thumbnail only; a gap
that stays open after enrichment (no public code yet) is expected and should
not be retried in the same run.

When reports come back, check `is_open` on every new row: the add-evals rule
counts released weights or public reproduction scripts as open. Flag rows
whose only evidence is an empty HF repo, an anonymized mirror, or a "coming
soon" README in the final report.

## 5. Merge duplicates

A subagent may find that the paper already exists as an external paper (for
example a CVPR open-access row created before the arXiv version), usually
because an eval insert was rejected as a duplicate. With the user's approval,
merge the external row into the arXiv row:

```bash
uv run --env-file backend/keys.env python -c "
from backend.database.connection import db_manager
from backend.database.paper_merge import merge_external_paper_into_arxiv
s = db_manager.session_local()
try:
    print(merge_external_paper_into_arxiv(s, <external_id>, <arxiv_db_id>)); s.commit()
except Exception:
    s.rollback(); raise
finally:
    s.close()
"
```

It moves evaluations, tags, conference, authors and artifacts, and redirects
the old id. Then list the paper's authors (see `docs/database.md`): the merge
moves the external row's author links even when the same person is already
linked, so remove the duplicate links. Keep the author with more papers,
and delete the dropped author rows only if they now have no papers.

## 6. Link his threads

His posts substantively explain the paper, so they are linked under the
outside-curator policy of `process-x-bookmarks`. Add hand-resolved papers
(arXiv versions of journal papers) to `<out>.links.json`, then:

```bash
uv run --env-file backend/keys.env python .agents/skills/process-x-bookmarks/scripts/link_threads.py <out>.links.json --dry-run
uv run --env-file backend/keys.env python .agents/skills/process-x-bookmarks/scripts/link_threads.py <out>.links.json
```

## 7. Verify and report

Rerun the triage with `--from-raw`: every paper should be `linked`, and each
paper's evaluation count should match what the subagents reported. Report to
the user:

- posts scanned and the date range, own paper threads found, and skipped
  threads with one-line reasons
- papers indexed (with `https://paperswithcode.co/paper/<arXiv id>` links)
- a table of papers with evals added (rows, benchmarks, notable ranks)
- a table of papers enriched without evals and what changed
- duplicates merged, borderline `is_open` flags, taxonomy gaps the subagents
  found (candidates for `add-task` / `add-method` / `add-benchmark`)
