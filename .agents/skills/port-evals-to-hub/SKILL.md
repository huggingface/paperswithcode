---
name: port-evals-to-hub
description: Port Papers With Code evaluation results to Hugging Face Hub benchmark leaderboards (`benchmark:official` datasets) by opening `.eval_results/*.yaml` pull requests on model repos, then keep those PRs visible as ranks drift. Use this whenever the user asks which PwC evals can go to the Hub, to open eval-results PRs for model repos or rows of a candidate CSV, to "port", "migrate", or "push" evals from PwC or a paper/model card to an HF dataset leaderboard, to check why a Hub leaderboard lacks results PwC has, or to re-check, sweep, or clean up open eval-results PRs. Not for adding evals to PwC itself (use add-evals).
metadata:
  compatibility: Requires the paperswithcode repository, uv, read access to the production database through backend/keys.env, and an `hf` login whose token may open PRs on Hub model repos.
---

# Port PwC evals to Hub leaderboards

The Hub's [evaluation results feature](https://huggingface.co/docs/hub/eval-results) builds a leaderboard on each official benchmark dataset from `.eval_results/*.yaml` files in model repos, including files in open PRs. This skill finds PwC results that belong on those leaderboards, verifies each one against its source, and opens one PR per model repo that a maintainer can review and merge in a minute.

A PR is only worth opening if the reviewer can see the result on the leaderboard and find the number at the cited source. Most of the rules below exist because one of those two failed.

## Scripts

All scripts live in `.agents/skills/port-evals-to-hub/scripts/` and run from the repository root. Write scripts guard their side effects with `--apply`; without it they only print.

| Script | Purpose |
| --- | --- |
| `hub_leaderboard.py` | Library: leaderboard views, predicted and live ranks, view links, exact benchmark names, eval.yaml task ids, org vs personal account, benchmarks already declared on a repo. |
| `find_candidates.py OUT.csv` | Read-only DB query. Lists PwC evals with an `hf_model_url` on the mapped leaderboards, with status `candidate`, `on_board`, `already_declared`, `personal_account`, `discussions_disabled`, or `repo_missing`; candidates from major labs first, newest models first. |
| `open_eval_prs.py SPEC.json [--apply]` | Checks every result in a spec, prints the PRs, and with `--apply` opens them and appends them to the registry. |
| `sweep_eval_prs.py [--apply]` | Re-checks every registered PR: repoints links to a view where the result is visible, removes invisible results, closes PRs left with none. |

Run `find_candidates.py` with `uv run --env-file backend/keys.env python …`; the Hub-only scripts need just `uv run python …`. The registry defaults to `reports/hf-eval-results-prs.json` (local, not committed).

Opening, editing, or closing PRs posts publicly on other people's repos. The auto-mode classifier may block `--apply`; if it does, show the user the exact command and let them run it, then verify the result.

## 1. Find candidates

1. Check the official benchmark list at `https://huggingface.co/api/datasets?filter=benchmark:official&limit=200`. If a benchmark is missing from `MAPPING` in `find_candidates.py`, read its `eval.yaml`, find the matching PwC dataset and metric, and add a row. Make sure the PwC metric is the one the Hub task measures (for example MMMU-Pro's `mmmu_pro_vision` task is the vision split, not the overall score).
2. Run `find_candidates.py` and work from the `candidate` rows. When the user gives a model, paper, or release instead, collect candidates from its sources directly; the PwC rows are a lead, not the evidence.
3. When the user works in batches ("rows 46–65"), keep row numbers stable within a CSV, and report every skipped row with its reason.

Repo eligibility:
- **Organizations only.** Results in personal-account repos never appear on leaderboards. `namespace_kind` tells them apart. The user prefers major labs (`MAJOR`), but any other Hub organization is fine.
- **The exact evaluated checkpoint.** The repo must hold the weights that produced the number. Skip it when the card says the reported results came from another checkpoint (NorthCUA: scores from SFT checkpoints, repo holds a later post-training step), and don't attach a sibling's or base model's score.
- **Not already declared.** Skip benchmarks the repo declares on main or in any open PR, including PRs from other people.

## 2. Verify every value at its primary source

Read the model card, paper, README, or blog yourself. Never rely only on the PwC row: PwC values have been wrong (tool-integrated scores stored for no-tool boards, fractions for percent boards, a typo'd digit). When PwC is wrong, fix PwC with the add-evals or verify-evals conventions as well.

Skip a result, or the whole repo, when:
- **The score is third-party.** For example a card's † numbers from Artificial Analysis, or scores for the model taken from a benchmark's own paper. The source must be the model's authors.
- **The protocol differs from the board.** Examples: with tools or code execution on a no-tools board (AIME tool-integrated reasoning), inference tricks such as zoom, cropping, verifiers, or agentic refinement on a direct-inference board (ScreenSpot-Pro), a subset of the benchmark (Terminal-Bench run on 88 of 89 tasks), or a different metric or scale. Use the no-tools number when the source gives both, and say so in `notes`.
- **The benchmark is contaminated or may be.** For example a tech report admitting overlap, or training data that visibly contains test items. Raise possible contamination with the user rather than deciding silently.
- **The board mixes metrics or protocols.** For now that means Video-MME-v2: skip it.
- **The checkpoint is unfinished** ("still training", "under revision").

Use the number exactly as the source prints it, in the board's units. DeepSWE uses percent, so a PwC 0.627 becomes 62.7. When the source shows the same score at two precisions, the model card's precise value wins (44.94 over the blog's 44.9).

## 3. Make the number findable

The reviewer must be able to find each number at the cited source. `open_eval_prs.py` warns when the value string is not in the source text. Then write `origin` so the reviewer can find it anyway:
- name the table, row, and column (`Table 6 … (NorthCUA-Pro row, SSP column)`), or quote the sentence (`the model card ("On Terminal-Bench 2.0 it scores 9.36%")`);
- if it appears only in an image or chart, say which figure and bar;
- if the source hides it behind a control (DeepSWE's Models picker, a chart's benchmark toggle), say how to reveal it.

Cite the most direct surface: model card over paper over blog. Use the `source.name` the Hub shows, such as `Model Card`, `Paper (Table 4)`, or `TMax v1.1 blog`.

## 4. Check top-50 visibility

The leaderboard UI shows ranks 1–50 of the selected view only. A view is a "Parameters Size" tier (`max_params`: 1B, 3B, 6B, 12B, 32B, 128B, 500B) plus the "Base only" toggle. That toggle is on by default and hides every model whose card declares `base_model`, which covers most fine-tunes (GUI agents, RL'd terminal agents). `predicted_view` returns the broadest view where a new result would rank in the top 50, and the PR link opens that view (`leaderboard_max_params=…&leaderboard_base_model=false`). Drop a result that is visible nowhere.

Gotchas:
- A model without safetensors `num_parameters` drops out of every size-filtered view. A wrong count misplaces it: tmax-27b-v1.1's index claims 2.6M parameters, so it lands in the ≤1B view. Mention metadata bugs like this to the user.
- A card that lists itself as its own `base_model` is hidden in the default view.
- A PR that edits an existing `.eval_results` file previews main's version until merged, so its result is not on the board yet. That doesn't make it invisible: never close such a PR in a sweep.
- `task_id` must be a task in the benchmark's `eval.yaml` (`terminalbench_2`, `swe_bench_%_resolved`), not the split name. A wrong id returns an empty board, which looks like rank 1. `open_eval_prs.py` refuses unknown ids.

## 5. Open the PRs

Write a spec (see the `open_eval_prs.py` docstring), with one entry per repo and every eligible benchmark in it. Use `notes` for the protocol a reviewer needs in order to judge comparability: harness and version, number of tasks and trials, sandbox, no tools, direct inference on the full input. Then:

```bash
uv run python .agents/skills/port-evals-to-hub/scripts/open_eval_prs.py /path/spec.json            # dry run
uv run python .agents/skills/port-evals-to-hub/scripts/open_eval_prs.py /path/spec.json --apply
```

The PR format follows [meta-models/Muse-Glimmer-30B discussion 8](https://huggingface.co/meta-models/Muse-Glimmer-30B/discussions/8):
- Title: "Add community evaluation results for <exact benchmark names>".
- Body: one bold link per benchmark to the leaderboard view with the result highlighted (`eval_result=<repo>`), followed by "These results were extracted from <origin>." and the feature link and automated-PR note.
- Benchmark names are written the way their authors write them: `SWE-Bench Pro`, `olmOCR-Bench`, `Terminal-Bench 2.0`. Add new names to `NAMES` in `hub_leaderboard.py` when the `eval.yaml` name differs.

To change a file in an existing PR (for example pointing `.eval_results/terminal_bench_2_1.yaml` at the right dataset), commit to `refs/pr/<num>` with `HfApi.create_commit(revision=…)`. Don't open a second PR.

## 6. Verify and sweep

Right after opening, confirm each PR's results with `visible_view` (live rank, which can sit a few places below the prediction), and report a table with PR link, benchmark, value, live rank, and view. Ranks drift as other PRs land, so after each batch run:

```bash
uv run python .agents/skills/port-evals-to-hub/scripts/sweep_eval_prs.py            # dry run
uv run python .agents/skills/port-evals-to-hub/scripts/sweep_eval_prs.py --apply
```

Review the dry run before applying. A sweep may remove a result or close a PR, but only one whose previewable results all fell out of every view. Tell the user which ones it touched.

## Report

For each batch, report:
- the PRs opened, with benchmark, value, rank, and view;
- every skipped row with its reason (third-party, protocol, checkpoint, contamination, personal account, already declared, outside the top 50);
- any PwC corrections made;
- metadata problems seen on model repos;
- where the batch stopped, so the next batch starts at the right row.
