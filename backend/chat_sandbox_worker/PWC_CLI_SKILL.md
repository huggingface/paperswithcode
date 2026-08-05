---
name: pwc-cli
description: "Papers With Code CLI (`pwc`) for searching and reading AI/ML papers, discovering recent and trending research, finding related work and paper lineage, browsing tasks, methods, conferences, and benchmark leaderboards through the public Papers With Code catalog. Use whenever the user asks to find papers, survey literature, compare research, inspect an arXiv paper, explore AI/ML taxonomy or conferences, discover benchmarks or state-of-the-art models, or mentions Papers With Code, `pwc`, or the `pwc-cli`. Prefer this skill for grounded AI/ML research even when the user does not explicitly ask for a CLI command."
---

Install:

```bash
pwc_repo=https://raw.githubusercontent.com/huggingface/pwc-cli/main
curl -LsSf "$pwc_repo/standalone_cli/install.py" | python3
```

The `pwc` CLI is anonymous and read-only. It queries the public
[Papers With Code](https://paperswithcode.co) catalog and requires no token.
Run `pwc --help` or a nested `--help` command when the live parser and this skill
disagree; the parser is authoritative.

Install or refresh this Skill from the locally installed CLI with
`pwc skills add --force`. Use `--global` for `~/.agents/skills`, `--claude` to
also link it for Claude Code, or `--dest PATH` for another harness.

Use compact output for reading and discovery. Add `--json` when programmatic
filtering, joining, or schema-dependent processing is useful.
Use only flags documented for the exact subcommand; do not infer that sibling
commands share flags. For `pwc paper list`, `pwc task list`, and
`pwc method list`, use `--page-size`, never `--limit`.

`PAPER` accepts a modern or legacy arXiv ID, a numeric external-paper ID, or an
exact paper title. Papers with Code supports external papers which are not on arXiv,
hence those papers will have a numeric canonical ID.
Quote titles containing spaces. Title matching is
case-insensitive but exact; ambiguous titles fail with their matching IDs rather
than silently selecting a paper.

## Commands

- `pwc search QUERY` — Search papers by title, topic, author, or arXiv ID. This is powered by hybrid/keyword/semantic search using pgvector. Defaults to hybrid.
  `[--limit 1-100 --page 1-100 --mode hybrid|keyword|semantic --json]`
- `pwc paper info PAPER` — Show metadata, the abstract, predecessors, and successors.
  `--include-resources` adds Markdown sections for GitHub repositories, project pages,
  and Hugging Face artifacts, with official links marked explicitly.
  `[--include-resources --json]`
- `pwc paper read PAPER` — Print stored paper Markdown. The resolved paper must
  have a modern arXiv record. `[--json]`
- `pwc paper list` — List and filter the paper catalog in a paginated manner.
  `[--page 1-100 --page-size 1-100 --search TEXT
  --published-after YYYY-MM-DD --published-before YYYY-MM-DD
  --conference TEXT --all-versions
  --order-by trending|date_published|citation_count
  --order-dir asc|desc --time today|week|month|all_time
  --include-resources --json]`
- `pwc paper recent` — List recently published papers.
  `[--limit 1-100 --json]`
- `pwc paper trending` — List papers with recent repository activity.
  `[--limit 1-100 --max-age-days 1-365 --min-velocity FLOAT --json]`
- `pwc paper related PAPER` — Find embedding- and taxonomy-ranked related work.
  `[--limit 1-20 --json]`
- `pwc paper lineage list PAPER` — Render linked Markdown sections for a paper,
  its predecessors, and its successors. `[--json]`
- `pwc task --name NAME` — Show a task page in CLI form, including its area,
  description, hierarchy, research trends, recommended frameworks, sister
  tasks, subtasks, common methods, benchmarks, and trending papers. `NAME`
  must exactly match a task name, slug, or ID. `[--json]`
- `pwc task list` — List research tasks, optionally filtering by a
  case-insensitive exact area name such as Vision, Audio, or General.
  Rows include direct paper, benchmark, and evaluation counts for each task.
  Interactive output groups visible top-level tasks into Markdown area sections;
  `--group-by-area` forces that view when output is captured, while `--flat`
  forces the paginated table.
  `[--page 1-100 --page-size 1-100 --area NAME_OR_ID --level INTEGER
  --visible-only --group-by-area|--flat
  --order-by name|created_at|level|paper_count
  --order-dir asc|desc --json]`
- `pwc method list` — List research methods, optionally filtering by area or
  introduction year. This subcommand has no `--search` or `--limit` flag; do
  not infer flags from sibling list commands. To find methods by name or topic,
  filter the bounded list with
  `pwc method list --page-size 500 | rg -i -- 'QUERY'`.
  `[--page 1-100 --page-size 1-500 --area NAME_OR_ID
  --introduced-year YEAR
  --order-by name|full_name|introduced_year|created_at|paper_count
  --order-dir asc|desc --json]`
- `pwc conference list` — List conferences with imported papers.
  `[--year YEAR --json]`
- `pwc benchmark list` — Find and rank benchmarks. When `--task` is supplied,
  the default order is task-specific trending activity. Without filters,
  interactive output groups top benchmarks under visible tasks by area;
  `--group-by-area` forces Markdown and `--flat` forces the dataset table.
  Task, search, pagination, ordering, and open-model filters take precedence
  over `--group-by-area` and select task-scoped flat output.
  Rows include the benchmark name, slug, and ID (plus the full name when
  distinct in grouped output); pass the slug or ID to
  `pwc benchmark --name IDENTIFIER` for leaderboard details.
  `[--page 1-100 --page-size 1-100 --search TEXT --task TASK --area NAME_OR_ID
  --benchmarks-per-task 1-10 --group-by-area|--flat
  --include-descendants --min-eval-count INTEGER --is-open true|false
  --order-by trending|name|full_name|created_at|paper_count
  --order-dir asc|desc --json]`
- `pwc benchmark --name NAME` — Show a benchmark's top models, scores, source
  papers, publication dates, and open/closed status. `NAME` must exactly match
  a benchmark name, full name, slug, or ID.
  For multi-metric tradeoffs, require numeric metrics, apply repeatable
  thresholds, sort by one metric, or select a Pareto frontier. Metric names are
  case-insensitive.
  `[--limit 1-100 --is-open true|false
  --require-metrics METRIC[,METRIC]
  --min METRIC=VALUE --max METRIC=VALUE
  --sort METRIC[:asc|desc]
  --pareto METRIC:higher,METRIC:lower --json]`
- `pwc version` — Show the CLI and API contract versions.
- `pwc skills add` — Install the version-matched CLI Skill.
  `[--global --claude --dest SKILLS_DIRECTORY --force]`

## Research workflow

1. Use `pwc benchmark list --task TASK` to discover active benchmarks for a given task,
   then `pwc benchmark --name NAME` to inspect a specific leaderboard.
   For accuracy/latency or other multi-metric questions, use
   `--require-metrics`, thresholds, or `--pareto`; do not infer a tradeoff from
   a leaderboard sorted by one metric.
2. Use `pwc paper info` to inspect promising results. Add `--include-resources`
   when linked GitHub repositories, project pages, or Hugging Face artifacts matter.
   When the paper includes successors, always consider them more state-of-the-art.
3. Use `pwc search` to search more broadly for a topic or a known paper.
   Use the default hybrid mode first; use keyword mode for exact terminology
   and semantic mode for conceptual matches.
4. Go more in-depth with `pwc paper read`. Do not treat search snippets or
   titles as sufficient support for detailed claims.
5. Expand the literature with `pwc paper related` and use
   `pwc paper lineage list` when model or method ancestry matters.
6. Explore the catalog taxonomy with `pwc task list --group-by-area`, inspect a
   specific task with `pwc task --name NAME`, then use
   `pwc method list` and `pwc conference list`; use `--area` or `--year` to
   narrow broad lists.
7. Synthesize only after gathering enough primary evidence. Preserve paper
   titles, identifiers, and URLs in the answer so claims remain traceable.

## Command selection

- Use `pwc benchmark list --task TASK` for finding state-of-the-art (SOTA) for a given task.
- If the task is not supported by PwC, use `pwc search` for relevance-ranked discovery.
- Use `pwc paper info` to gather more info about a specific paper.
- Use `pwc paper list` for structured filters, date windows, conferences, and
  deterministic sorting.
- Use `pwc paper recent` for recency and `pwc paper trending` for current
  repository activity; these are different signals.
- Use area names directly with task and method lists, for example
  `--area Vision`, `--area Audio`, or `--area General`. Area matching is
  case-insensitive; numeric area IDs are also accepted.
- Use `pwc conference list --year YEAR` for a specific conference edition year.
- Use `--include-resources` for linked repositories, project pages, and Hugging
  Face artifacts. Add `--json` when their structured metadata also matters.
- Use `--all-versions` only when individual arXiv versions are relevant.
- Use `--is-open true` to restrict benchmark results to open models.
- Paginate when stderr reports more results. Do not silently treat the first
  page as the complete catalog.

## Output and limits

- Interactive list and search output uses aligned text columns. When stdout is
  piped or captured, the same rows use lossless TSV for agent and script
  processing. Paper info uses labeled metadata and Markdown sections. Benchmark
  details use an aligned table interactively and Markdown when piped or captured.
- `--json` wraps responses as
  `{"schema_version":"v1","data":...}` for stable agent consumption.
- Stable exit codes are `0` success, `2` invalid usage, `3` network/server
  failure, and `4` invalid API response.
- `PWC_API_URL` may select another compatible v1 endpoint. The default is
  `https://paperswithcode.co/api/v1`.

The standalone parser contains no authentication, mutation, ingestion,
publication, image, CRON, embedding, or infrastructure commands. Do not
substitute repository-maintenance commands into a public or sandbox workflow.
