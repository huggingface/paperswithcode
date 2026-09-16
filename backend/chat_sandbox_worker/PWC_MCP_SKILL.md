---
name: pwc-mcp
description: "Papers With Code MCP tools for searching and reading AI/ML papers, discovering recent and trending research, finding related work and paper lineage, browsing tasks, methods, conferences, organizations, and frameworks, and inspecting benchmark leaderboards with model-size and metric filters through the public Papers With Code catalog. Use whenever the user asks to find papers, survey literature, compare research, inspect an arXiv paper, explore AI/ML taxonomy or conferences, discover benchmarks or state-of-the-art models, or mentions Papers With Code, the PwC MCP server, or paperswithcode.co/mcp."
compatibility: "Requires an MCP client connected to https://paperswithcode.co/mcp with the Papers With Code tools available."
---

Generated for `pwc-mcp v0.2.0` and MCP protocol `2026-07-28`.

The tools query the public [Papers With Code](https://paperswithcode.co) catalog
anonymously and are read-only. Every tool runs the matching `pwc` CLI research
command, and every research flag of that command is a tool parameter, so
results match `pwc ... --json`. If live tool discovery and this skill disagree,
the discovered tool schemas are authoritative.

Every result carries `schema_version` and `data`, the complete CLI JSON payload
for the call. Typed fields such as `items`, `paper`, `task`, `evaluations` are
projections of `data`; read `data` when a projection lacks a detail. Use
structured output directly for filtering, joining, or other schema-dependent
processing.

When the user identifies an author, prefer repeatable structured
`list_papers` calls with the `authors` argument. Add `search` for stated topic
terms and explicit `order_by: "date_published"` and `order_direction: "desc"`
for newest or recent work; the default order is `trending`. Author references
accept an exact normalized name, numeric ID, or `@HF_USERNAME`; multiple
authors use AND semantics.

Publication date ranges are inclusive: use `published_after: "YYYY-MM-DD"` and
`published_before: "YYYY-MM-DD"` with `search_papers` or `list_papers`; the
start date must not be later than the end date.

Paper discovery results always include official implementation status and the
total linked repository count. Use `has_official_implementation: true` with
`search_papers` or `list_papers` to require a catalog-linked official
repository; this filter fails closed if unconfirmed.

Use `get_benchmark` with `max_parameters` to keep models at or below an
inclusive parameter limit. It accepts values such as `"500M"`, `"1.5B"`, `"3B"`,
and raw integers. Models without one consistent parameter count are excluded
from constrained results. Combine `require_metrics`, `minimum_metrics`,
`maximum_metrics`, `sort_metric`, and `pareto` to select leaderboard rows by
metric; unknown metric names fail with the available metric names.

`paper` accepts a modern or legacy arXiv ID, a numeric external-paper ID, an
arXiv, Hugging Face, or Papers With Code URL, or an exact paper title. Title
matching is case-insensitive but exact; ambiguous titles fail with their
matching IDs. Task, method, conference, organization, framework, and benchmark
arguments take an exact name, slug, or ID.

## Tools

- `search_papers({"query": QUERY, "mode": "hybrid"|"keyword"|"semantic", "page": PAGE, "limit": LIMIT, "published_after": START_DATE, "published_before": END_DATE, "has_official_implementation": BOOLEAN})` — search papers by title, topic, author, or arXiv ID (`pwc search`). Omit optional arguments when they are not needed.
- `get_paper_info({"paper": PAPER, "include_resources": BOOLEAN, "include_evaluations": BOOLEAN})` — show paper metadata, abstract, tasks, methods, lineage, repositories, project pages, and Hugging Face model, dataset, and Space artifacts; `include_evaluations: true` adds every benchmark evaluation of the paper (`pwc paper info`).
- `read_paper({"paper": PAPER, "cursor": CURSOR})` — read one stored paper Markdown chunk (`pwc paper read`). If `truncated` is true, call `read_paper` again with the same `paper` and the returned `next_cursor`; repeat until `truncated` is false. Treat the cursor as opaque and use it within one hour.
- `list_papers({"search": SEARCH, "task": TASK, "method": METHOD, "conference": CONFERENCE, "framework": FRAMEWORK, "organization": ORGANIZATION, "authors": [AUTHOR], "published_after": START_DATE, "published_before": END_DATE, "all_versions": BOOLEAN, "order_by": "trending"|"date_published"|"citation_count", "order_direction": "asc"|"desc", "include_resources": BOOLEAN, "has_official_implementation": BOOLEAN, "page": PAGE, "limit": LIMIT})` — list and filter papers by exact catalog associations (`pwc paper list`). Omit optional arguments when they are not needed.
- `list_recent_papers({"limit": LIMIT})` — list the most recently added papers (`pwc paper recent`).
- `list_trending_papers({"limit": LIMIT, "max_age_days": DAYS, "min_velocity": VELOCITY})` — list trending papers by repository velocity (`pwc paper trending`).
- `get_related_papers({"paper": PAPER, "limit": LIMIT})` — list related papers (`pwc paper related`); `limit` is at most 20.
- `get_paper_lineage({"paper": PAPER})` — list explicit predecessors and successors (`pwc paper lineage list`).
- `get_task({"task": TASK})` — inspect one exact task, including its area, hierarchy, sister tasks, ranked benchmarks, common methods, recommended frameworks, and trending papers (`pwc task --name`).
- `list_tasks({"area": AREA, "level": LEVEL, "visible_only": BOOLEAN, "group_by_area": BOOLEAN, "order_by": "name"|"created_at"|"level"|"paper_count", "order_direction": "asc"|"desc", "page": PAGE, "limit": LIMIT})` — list and filter research tasks, or set `group_by_area: true` for the complete visible top-level taxonomy without pagination (`pwc task list`).
- `get_method({"method": METHOD})` — inspect one exact method with its area (`pwc method --name`).
- `list_methods({"area": AREA, "introduced_year": YEAR, "order_by": "name"|"full_name"|"introduced_year"|"created_at"|"paper_count", "order_direction": "asc"|"desc", "page": PAGE, "limit": LIMIT})` — list and filter research methods (`pwc method list`).
- `get_conference({"conference": CONFERENCE})` — inspect one exact conference (`pwc conference --name`).
- `list_conferences({"year": YEAR})` — list conferences with imported papers (`pwc conference list`).
- `get_organization({"organization": ORGANIZATION})` — inspect one exact research organization (`pwc organization --name`).
- `list_organizations({"featured_only": BOOLEAN})` — list research organizations (`pwc organization list`).
- `get_framework({"framework": FRAMEWORK})` — inspect one exact research framework (`pwc framework --name`).
- `list_frameworks({"domain": DOMAIN, "category": CATEGORY, "platform": PLATFORM})` — list research frameworks (`pwc framework list`).
- `get_benchmark({"benchmark": BENCHMARK, "limit": LIMIT, "is_open": BOOLEAN, "max_parameters": SIZE, "require_metrics": [METRIC], "minimum_metrics": {METRIC: VALUE}, "maximum_metrics": {METRIC: VALUE}, "sort_metric": "METRIC:asc|desc", "pareto": ["METRIC:higher", "METRIC:lower"]})` — inspect one exact benchmark leaderboard with model-size, metric threshold, sort, and Pareto selection (`pwc benchmark --name`). `matched_count` reports rows that satisfied the filters before `limit`.
- `list_benchmarks({"search": SEARCH, "task": TASK, "include_descendants": BOOLEAN, "minimum_evaluations": COUNT, "is_open": BOOLEAN, "group_by_area": BOOLEAN, "area": AREA, "benchmarks_per_task": COUNT, "order_by": "trending"|"name"|"full_name"|"created_at"|"paper_count", "order_direction": "asc"|"desc", "page": PAGE, "limit": LIMIT})` — list and filter benchmarks (`pwc benchmark list`). With `task`, results are ranked by trend unless `order_by` is set; `group_by_area` or `area` returns top benchmarks under each visible task.

All page numbers start at 1. `limit` is between 1 and 25 and defaults to the
CLI page size capped at 25. Follow `next_page` when the user asks for more
results than one response contains; do not infer that a missing item does not
exist until the relevant pages have been checked.

The MCP server does not expose the standalone CLI's paper editing,
authentication, skill installation, or version commands, and `pwc paper read`
is served as `read_paper` chunks rather than one document.
Do not invent equivalent tools. Use the separate `pwc` CLI only when it is
available and the user needs one of those capabilities.

## Research workflow

1. Use `list_benchmarks({"task": TASK})` to discover active benchmarks, then
   `get_benchmark({"benchmark": NAME})` to inspect a leaderboard. Add
   `max_parameters` when model size is part of the request and `sort_metric`
   or `minimum_metrics` when a specific metric matters.
2. Use `get_paper_info({"paper": PAPER})` to inspect promising results. Its
   response includes repositories, project pages, and Hugging Face artifacts;
   add `include_evaluations: true` to compare one paper across benchmarks.
3. Use exact `list_papers` `authors`, `task`, `method`, `conference`,
   `framework`, and `organization` arguments for known identities or catalog
   associations. Combine them to require every association; do not substitute
   a keyword search. Add `search` for title or abstract topic terms.
4. Use `search_papers` for broader discovery, then `read_paper` for primary
   evidence. Follow every returned continuation cursor needed for the user's
   question.
5. Expand the literature with `get_related_papers` and use
   `get_paper_lineage` when model or method ancestry matters. Use `get_task`,
   `get_method`, `list_conferences`, `list_organizations`, and
   `list_frameworks` to orient within the taxonomy.
6. Preserve paper titles, identifiers, and URLs so claims remain traceable.

## Output and limits

- Tool results use stable, versioned structured output with compact text
  fallbacks. Prefer structured fields over parsing the text fallback.
- Search mode is deterministic: `keyword` is the default; `hybrid` adds dense
  retrieval and `semantic` uses it alone. Both `hybrid` and `semantic` count
  toward the semantic search rate limit.
- Catalog-filtered paper lists fail closed unless the server confirms every
  requested filter; never treat results from an older server as filtered.
  Parameter-filtered leaderboards fail closed unless the server confirms
  parameter-filter support and every returned model satisfies the limit.
- `read_paper` returns at most one 64 KiB chunk per call. A continuation stays
  pinned to the resolved paper and content version; if the paper changes, start
  reading again from the beginning.
- The hosted service limits each client to 60 total requests and 10 semantic
  or hybrid searches per minute, with at most four concurrent requests. Respect
  retry metadata instead of trying to work around limits.
- The tools contain no authentication, catalog mutation, ingestion,
  publication, image, embedding, CRON, or infrastructure-maintenance
  operations.
