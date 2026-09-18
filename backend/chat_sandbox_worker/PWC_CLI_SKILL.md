---
name: pwc-cli
description: "Papers With Code CLI (`pwc`) for searching and reading AI/ML papers, discovering recent and trending research, finding related work and paper lineage, browsing tasks, methods, conferences, organizations, frameworks, and benchmark leaderboards, and submitting authenticated paper edits through the public Papers With Code catalog. Use whenever the user asks to find papers, survey literature, compare research, inspect an arXiv paper, explore AI/ML taxonomy or conferences, discover benchmarks or state-of-the-art models, or mentions Papers With Code, `pwc`, or `pwc-cli`."
---

Generated with `pwc v0.4.2`. Run `pwc skills add --force` to regenerate.

Research commands query the public [Papers With Code](https://paperswithcode.co) catalog anonymously.
Paper editing requires explicit browser authorization through `pwc auth login --paper PAPER`.
Run `pwc --help` or a nested `--help` command when the live parser and this
skill disagree; the parser is authoritative.

Use compact output for reading and discovery. Add `--json` for programmatic
filtering, joining, or schema-dependent processing.

When the user identifies an author, prefer repeatable structured
`pwc paper list --author AUTHOR` filters. Add `--search TEXT` for stated topic
terms and explicit `--order-by date_published --order-dir desc` for newest or
recent work. Author references accept an exact normalized name, numeric ID, or
`@HF_USERNAME`; repeated authors use AND semantics.

Publication date ranges are inclusive: use `--start-date YYYY-MM-DD` and
`--end-date YYYY-MM-DD` with `pwc search` or `pwc paper list`; the start date
must not be later than `--end-date`. The combined flags are
`--start-date YYYY-MM-DD --end-date YYYY-MM-DD`.

Paper discovery commands accept `--implementation-coverage` to add official
implementation status and total linked repository count columns. JSON and
`pwc paper info` always include both fields. Use
`--has-official-implementation` with `pwc search` or `pwc paper list` to require
a catalog-linked official repository; these filters fail closed if unconfirmed.

Use `pwc benchmark --name NAME --max-parameters SIZE` to keep models at or
below an inclusive parameter limit. SIZE accepts values such as `500M`, `1.5B`,
`3B`, and raw integers. Models without one consistent parameter count are
excluded from constrained results.

`PAPER` accepts a modern or legacy arXiv ID, a numeric external-paper ID, or an
exact paper title. Quote titles containing spaces. Title matching is
case-insensitive but exact; ambiguous titles fail with their matching IDs.

## Commands

- `pwc search QUERY [--limit LIMIT] [--page PAGE] [--mode hybrid|keyword|semantic] [--start-date START_DATE] [--end-date END_DATE] [--has-official-implementation] [--implementation-coverage] [--json]` — search papers.
- `pwc paper info PAPER [--include-resources] [--include-evals] [--json]` — show paper metadata including abstract.
- `pwc paper evaluations PAPER [--page PAGE] [--page-size PAGE_SIZE] [--json]` — list one paper's benchmark evaluations.
- `pwc paper read PAPER [--json]` — print stored paper Markdown.
- `pwc paper list [--page PAGE] [--page-size PAGE_SIZE] [--search SEARCH] [--start-date START_DATE] [--end-date END_DATE] [--task TASK] [--method METHOD] [--conference CONFERENCE] [--framework FRAMEWORK] [--organization ORGANIZATION] [--author AUTHOR] [--all-versions] [--order-by trending|date_published|citation_count] [--order-dir asc|desc] [--include-resources] [--has-official-implementation] [--implementation-coverage] [--json]` — list and filter papers.
- `pwc paper recent [--limit LIMIT] [--implementation-coverage] [--json]` — list recent papers.
- `pwc paper trending [--limit LIMIT] [--max-age-days MAX_AGE_DAYS] [--min-velocity MIN_VELOCITY] [--implementation-coverage] [--json]` — list trending papers.
- `pwc paper related PAPER [--limit LIMIT] [--implementation-coverage] [--json]` — list related papers.
- `pwc paper lineage list PAPER [--json]` — list predecessors and successors.
- `pwc paper edit export PAPER [--output OUTPUT]`.
- `pwc paper edit preview PAPER [--file FILE]`.
- `pwc paper edit submit PAPER [--file FILE]`.
- `pwc task [--name NAME] [--json]` — inspect or list research tasks.
- `pwc task list [--page PAGE] [--page-size PAGE_SIZE] [--search SEARCH] [--group-by-area] [--flat] [--area AREA] [--level LEVEL] [--visible-only] [--order-by name|created_at|level|paper_count] [--order-dir asc|desc] [--json]` — list and filter research tasks.
- `pwc method [--name NAME] [--json]` — inspect or list research methods.
- `pwc method list [--page PAGE] [--page-size PAGE_SIZE] [--search SEARCH] [--area AREA] [--introduced-year INTRODUCED_YEAR] [--order-by name|full_name|introduced_year|created_at|paper_count] [--order-dir asc|desc] [--json]` — list and filter research methods.
- `pwc conference [--name NAME] [--json]` — inspect or list conferences.
- `pwc conference list [--year YEAR] [--json]` — list conferences with imported papers.
- `pwc organization [--name NAME] [--json]` — inspect or list research organizations.
- `pwc organization list [--featured-only] [--json]` — list research organizations.
- `pwc framework [--name NAME] [--json]` — inspect or list research frameworks.
- `pwc framework list [--domain DOMAIN] [--category CATEGORY] [--platform PLATFORM] [--json]` — list research frameworks.
- `pwc benchmark [--name NAME] [--limit LIMIT] [--page PAGE] [--is-open true|false] [--max-parameters SIZE] [--require-metrics METRIC[,METRIC]] [--min METRIC=VALUE] [--max METRIC=VALUE] [--sort METRIC[:ASC|DESC]] [--pareto METRIC:HIGHER,METRIC:LOWER] [--json]` — inspect benchmarks.
- `pwc benchmark list [--page PAGE] [--page-size PAGE_SIZE] [--search SEARCH] [--task TASK] [--group-by-area] [--flat] [--area AREA] [--benchmarks-per-task BENCHMARKS_PER_TASK] [--include-descendants] [--min-eval-count MIN_EVAL_COUNT] [--is-open true|false] [--order-by trending|name|full_name|created_at|paper_count] [--order-dir asc|desc] [--json]` — list and filter benchmarks.
- `pwc skills add [--global] [--claude] [--dest DEST] [--force]` — install the version-matched pwc CLI Skill.
- `pwc version` — show CLI and API contract versions.
- `pwc auth login [--paper PAPER] [--no-browser]`.
- `pwc auth status [--paper PAPER]`.
- `pwc auth logout [--paper PAPER]`.

## Research workflow

1. Use `pwc benchmark list --task TASK` to discover active benchmarks, then
   `pwc benchmark --name NAME` to inspect a leaderboard. Add
   `--max-parameters SIZE` when model size is part of the request.
2. Use `pwc paper info` to inspect promising results. Add
   `--include-resources` when repositories, project pages, or Hugging Face
   artifacts matter.
3. Use exact `pwc paper list --author`, `--task`, `--method`, `--conference`,
   `--framework`, and `--organization` filters for known identities or catalog
   associations. Combine them to require every association; do not substitute
   a keyword search. Add `--search` for title or abstract topic terms.
4. Use `pwc search` for broader discovery, then `pwc paper read` for primary
   evidence.
5. Expand the literature with `pwc paper related` and use
   `pwc paper lineage list` when model or method ancestry matters.
6. Preserve paper titles, identifiers, and URLs so claims remain traceable.

## Output and limits

- Interactive output is optimized for people. Benchmark lists remain aligned
  when captured; other captured list output uses lossless TSV. Add `--json` for
  structured agent or script consumption.
- Stable exit codes are `0` success, `2` invalid usage, `3` network/server
  failure, and `4` invalid API response.
- `PWC_API_URL` may select another compatible v1 endpoint. The default is
  `https://paperswithcode.co/api/v1`.
- Catalog-filtered paper lists fail closed unless the server confirms every
  requested filter; never treat results from an older server as filtered.
- Parameter-filtered benchmark details fail closed unless the server confirms
  parameter-filter support and every returned model satisfies the limit.

The research commands contain no authentication, catalog mutation, ingestion,
publication, image, embedding, CRON, or infrastructure-maintenance operations.


## Editing one paper

Use this workflow only when the user requests edits. Research commands remain anonymous.

1. Run `pwc auth login --paper PAPER`. Give the user the browser link and code;
   they sign in with Hugging Face and authorize that paper for one hour. Use
   `--no-browser` on a remote machine. Never extract, print, or copy credentials.
2. Run `pwc paper edit export PAPER --output edits.json` (the output must not
   already exist). It includes paper_id, version, idempotency_key, empty operations,
   and current reference data. Change operations, not current. Preserve the
   exported version and retry key. Documents may contain at most 50 operations
   and 1 MiB of JSON.
3. Add operations of the form `{"section":"tasks","payload":{"task_ids":[1,2]}}`.
   A section operation explicitly replaces that section; preserve unrelated links
   and tags. Omitted sections stay unchanged. Allowed sections and payload keys:
   tasks/task_ids, methods/method_ids, repositories/repositories,
   project_pages/project_pages, hf_artifacts/hf_models+hf_datasets+hf_spaces,
   source_url/source_url (external papers only), and evaluations.
   Repository/project-page entries contain url and is_official.
4. For evaluations, an operation without evaluation_id creates a row. Include
   task_id, dataset_id, metrics (a dictionary of existing metric names to scores),
   model_name, and the evaluation setup where available. One row can contain
   multiple metrics. Add evaluation_id to correct an existing row on this paper;
   omitted update fields stay unchanged. Use source_url and methodology to cite
   precise evidence when available; source references remain optional. Existing
   benchmark/task/metric definitions are required. Do not invent missing IDs or
   create benchmarks. Report unsupported results to the user. No evaluation
   deletion, paper identity changes, organization edits, or rank overrides.
5. Run `pwc paper edit preview PAPER --file edits.json`, inspect the before/after
   changes, then `pwc paper edit submit PAPER --file edits.json`. Publication is
   immediate: no per-batch browser approval. Respect the user's requested scope.
   A batch succeeds completely or makes no changes. The response includes status
   published and a link to the paper's history.
6. Retry an uncertain network result using the exact same document and retry key.
   A 409 means changed data or a reused key with different edits. Fetch a fresh
   export, preserve others' edits, and reconcile. Ask the user if the same score
   has conflicting corrections. Once you intentionally revise a previously
   submitted batch, use a fresh export/key. A 403 may mean expired authorization,
   suspension, or insufficient scope: read the error; do not broaden access.
   A 429 indicates the shared account limit: 20 distinct papers per UTC day and
   30 publications per minute. Do not work around account limits.
7. `pwc auth status --paper PAPER` shows local expiry metadata (revocation is
   checked by the server on use). `pwc auth logout --paper PAPER` revokes access.
   If authorization expires, keep the prepared file and request browser login
   again. Renewing authorization does not require discarding a valid edit document.

Credentials are stored in owner-only files under ~/.config/pwc/edit-credentials,
separately for each API base URL and paper. They never belong in a prompt, edit
file, repository, or command argument. The CLI does not follow edit redirects.
