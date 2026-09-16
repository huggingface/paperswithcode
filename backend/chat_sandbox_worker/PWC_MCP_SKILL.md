---
name: pwc-mcp
description: "Papers With Code MCP tools for searching and reading AI/ML papers, discovering recent research, finding related work and paper lineage, browsing tasks and methods, and inspecting benchmark leaderboards through the public Papers With Code catalog. Use whenever the user asks to find papers, survey literature, compare research, inspect an arXiv paper, explore AI/ML taxonomy, discover benchmarks or state-of-the-art models, or mentions Papers With Code, the PwC MCP server, or paperswithcode.co/mcp."
compatibility: "Requires an MCP client connected to https://paperswithcode.co/mcp with the Papers With Code tools available."
---

Generated for `pwc-mcp v0.1.0` and MCP protocol `2026-07-28`.

The tools query the public [Papers With Code](https://paperswithcode.co) catalog
anonymously and are read-only. If live tool discovery and this skill disagree,
the discovered tool schemas are authoritative.

Use each tool's structured output directly for filtering, joining, or other
schema-dependent processing.

When the user identifies an author, prefer repeatable structured
`list_papers` calls with the `authors` argument. Add `search` for stated topic
terms and explicit `order_by: "date_published"` and `order_direction: "desc"`
for newest or recent work. Author references accept an exact normalized name,
numeric ID, or `@HF_USERNAME`; multiple authors use AND semantics.

Publication date ranges are inclusive: use `published_after: "YYYY-MM-DD"` and
`published_before: "YYYY-MM-DD"` with `search_papers` or `list_papers`; the
start date must not be later than the end date.

Paper discovery results always include official implementation status and the
total linked repository count. Use `has_official_implementation: true` with
`search_papers` to require a catalog-linked official repository; this filter
fails closed if unconfirmed.

`paper` accepts a modern or legacy arXiv ID, a numeric external-paper ID, an
arXiv, Hugging Face, or Papers With Code URL, or an exact paper title. Title
matching is case-insensitive but exact; ambiguous titles fail with their
matching IDs.

## Tools

- `search_papers({"query": QUERY, "limit": LIMIT, "page": PAGE, "mode": "keyword"|"semantic", "published_after": START_DATE, "published_before": END_DATE, "has_official_implementation": BOOLEAN})` — search papers. Omit optional arguments when they are not needed.
- `get_paper_info({"paper": PAPER})` — show paper metadata, abstract, tasks, methods, repositories, and project pages.
- `read_paper({"paper": PAPER})` — read one stored paper Markdown chunk. If `truncated` is true, call `read_paper` again with the same `paper` and the returned `next_cursor`; repeat until `truncated` is false. Treat the cursor as opaque and use it within one hour.
- `list_papers({"page": PAGE, "limit": LIMIT, "search": SEARCH, "published_after": START_DATE, "published_before": END_DATE, "task": TASK, "method": METHOD, "conference": CONFERENCE, "framework": FRAMEWORK, "organization": ORGANIZATION, "authors": [AUTHOR], "order_by": "date_published"|"citation_count"|"title", "order_direction": "asc"|"desc"})` — list and filter papers. Omit optional arguments when they are not needed.
- `get_related_papers({"paper": PAPER, "limit": LIMIT})` — list related papers.
- `get_paper_lineage({"paper": PAPER})` — list explicit predecessors and successors.
- `get_task({"task": TASK})` — inspect one exact task by ID, slug, or name, including its area, parents, children, and benchmarks.
- `get_method({"method": METHOD})` — inspect one exact method by ID, slug, full name, or name.
- `list_benchmarks({"page": PAGE, "limit": LIMIT, "search": SEARCH, "task": TASK, "include_descendants": BOOLEAN, "minimum_evaluations": MINIMUM_EVALUATIONS, "is_open": BOOLEAN})` — list and filter benchmarks. Omit optional arguments when they are not needed.
- `get_benchmark({"benchmark": BENCHMARK, "limit": LIMIT, "is_open": BOOLEAN})` — inspect one exact benchmark and its leading evaluation rows.

All page numbers start at 1. `limit` is between 1 and 25. Follow `next_page`
when the user asks for more results than one response contains; do not infer
that a missing item does not exist until the relevant pages have been checked.

The MCP server does not expose standalone CLI commands for paper editing,
authentication, skill installation, version display, taxonomy enumeration, or
advanced benchmark metric/parameter/Pareto filtering. Do not invent equivalent
tools. Use the separate `pwc` CLI only when it is available and the user needs
one of those capabilities.

## Research workflow

1. Use `list_benchmarks({"task": TASK})` to discover active benchmarks, then
   `get_benchmark({"benchmark": NAME})` to inspect a leaderboard.
2. Use `get_paper_info({"paper": PAPER})` to inspect promising results. Its
   response includes repositories and project pages.
3. Use exact `list_papers` `authors`, `task`, `method`, `conference`,
   `framework`, and `organization` arguments for known identities or catalog
   associations. Combine them to require every association; do not substitute
   a keyword search. Add `search` for title or abstract topic terms.
4. Use `search_papers` for broader discovery, then `read_paper` for primary
   evidence. Follow every returned continuation cursor needed for the user's
   question.
5. Expand the literature with `get_related_papers` and use
   `get_paper_lineage` when model or method ancestry matters.
6. Preserve paper titles, identifiers, and URLs so claims remain traceable.

## Output and limits

- Tool results use stable, versioned structured output with compact text
  fallbacks. Prefer structured fields over parsing the text fallback.
- Search mode is deterministic: choose `keyword` by default and use `semantic`
  when conceptual similarity is more useful. The MCP server does not support
  the CLI's `hybrid` mode.
- Catalog-filtered paper lists fail closed unless the server confirms every
  requested filter; never treat results from an older server as filtered.
- `read_paper` returns at most one 64 KiB chunk per call. A continuation stays
  pinned to the resolved paper and content version; if the paper changes, start
  reading again from the beginning.
- The hosted service limits each client to 60 total requests and 10 semantic
  searches per minute, with at most four concurrent requests. Respect retry
  metadata instead of trying to work around limits.
- The tools contain no authentication, catalog mutation, ingestion,
  publication, image, embedding, CRON, or infrastructure-maintenance
  operations.
