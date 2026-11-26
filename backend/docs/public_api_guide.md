# Papers with Code API

Experimental beta. Find papers, explore benchmarks, and bring research results
into scripts, notebooks, and agents. No account or API key is required: access
is free, anonymous, and read-only.

- Base URL: `https://paperswithcode.co/api/v1`
- [OpenAPI description](https://paperswithcode.co/api/v1/openapi.json)
- [Interactive documentation](https://paperswithcode.co/docs/api)
- [Remote MCP server](https://paperswithcode.co/mcp)
- [Feedback and bug reports](https://github.com/huggingface/paperswithcode/issues)

## Your first request

```
curl --fail-with-body "https://paperswithcode.co/api/v1/papers/search?q=attention&page_size=5"
```

Responses are JSON, except paper full text, which is Markdown served as
`text/plain`. Browser requests from any origin are supported for these public
reads: omit cookies and authorization headers.

## Catalog overview

Four resources make up the catalog. Evaluations connect them: each one is a
score a paper reports on a dataset for a task.

- Papers: search, recent and trending papers, with code and project links, and
  full text as Markdown.
- Tasks: the research task taxonomy, from image classification to agents.
- Datasets: benchmarks and the task and metric pairs that form leaderboards.
- Evaluations: reported scores tying a paper to a dataset, task, and metric.

## Traffic limits

- 120 requests/minute per IP address for all catalog reads, with bursts of up
  to 60 more.
- 60 requests/minute per IP address for list and search endpoints, with bursts
  of up to 20 more. These requests also count toward the catalog allowance.

These are sustained rates with short bursts, not fixed-minute quotas. Successful
responses carry a `RateLimit-Policy` header naming the allowances that apply to
the request, for example `"catalog";q=120;w=60, "list";q=60;w=60`. Remaining
counts are not reported, because the limits are enforced at the edge.

Website browsing and scripts on the same network share these limits. Send
requests sequentially, cache results, and avoid parallel crawls. On HTTP 429,
wait at least the `Retry-After` duration, then retry with increasing delays and
jitter. Browser preflight requests do not consume this allowance.

## Pagination

- Catalog lists (`/papers/`, `/tasks/`, `/datasets/`, `/evaluations/`) return
  `count`, `results`, `next_page`, and `previous_page`. Pass `page` and
  `page_size`; stop when `next_page` is null.
- Paper search returns `results`, `next_page`, and `previous_page` but no
  `count`, because results are a relevance ranking.
- Paper listing and search stop at page 100, and `next_page` is null on page 100.
- To list more than 100 pages of papers, use `/papers/` with
  `order_by=date_published` or `order_by=citation_count` and follow
  `next_cursor`: pass it back as `cursor`, keeping the same filters, `order_by`
  and `order_dir`. Cursors have no page limit, so they can walk the whole
  catalog.
- Recent and trending papers return a JSON array bounded by `limit` rather than
  a page object.
- Counts and page contents change as the catalog updates; a listing is not a
  snapshot. Walk large listings slowly and within the traffic limits.

The default `order_by=trending` on `/papers/` ranks papers by recent GitHub and
Hugging Face activity. Without a search, date, conference, task, method,
organization, author, framework, or repository filter, it lists only papers
with a trending score from the last 24 hours. With any of those filters it
covers the whole catalog, and papers without a recent score sort last.

## Identifiers

- Paper endpoints accept an arXiv ID or a numeric catalog paper ID, including
  `/research/papers/{paper_id}/read`. Catalog IDs are returned as strings such
  as `"755"` and are accepted as path or filter values.
- A version suffix such as `1706.03762v5` on `/papers/{paper_id}` is ignored
  and the latest version is returned; its `version` field says which one. Use
  `/papers/arxiv/{arxiv_id}?version=v5` for an exact version. It returns 404
  when the catalog does not hold that version.
- Task and dataset detail accept catalog IDs or slugs. Leaderboard metrics and
  evaluation filters such as `dataset_id` and `task_id` require numeric IDs.
- `public-metadata` responses use `id` for the identifier that was resolved
  (a catalog ID, DOI, or arXiv ID). For catalog papers, `catalog_id` holds the
  catalog ID.

## Field conventions

- Missing fields and null values mean a value is unavailable or was not
  requested; they are never zero scores.
- On papers, `repositories` and `project_pages` are null unless the request
  sets `include_resources=true`. With it, null means there are none.
  `code_repository_count` is filled either way. Relations such as
  `predecessor_papers` are loaded on paper detail only.
- `thumbnail_url` on papers is a path relative to `https://paperswithcode.co`.
  Datasets carry `catalog_url`, the absolute URL of their benchmark page.
- Evaluation `metrics` values are strings exactly as reported. `metric_values`
  holds the same metrics as numbers, or null where a value is not a plain
  number.
- On datasets, `paper_count` is the live number of evaluation rows.
  `num_papers` and `pwc_url` are legacy values from the original
  paperswithcode.com dump.
- On trending papers, `id` and `published` mirror `paper_id` and
  `date_published`, matching the names other paper objects use.

## Reading leaderboards

1. Find a dataset: `/datasets/?q=ImageNet`
2. List its tasks: `/datasets/{dataset_id}/tasks/`
3. Pick a metric: `/datasets/{dataset_id}/tasks/{task_id}/metrics`. A task that
   has no leaderboard on the dataset returns 404.
4. Rank evaluations: `/evaluations/?dataset_id=…&task_id=…&ordering=best_rank`

An evaluation includes reported scores and source information; check metric
direction, split, and evaluation setup before comparing results. Unsupported
`ordering` values return 422 with the allowed values.

## Errors

Check the HTTP status before parsing a result. Every error from the endpoints
below has a top-level `code` string, stable and machine-readable, and a
`detail` field with the human-readable explanation. For validation errors
(`code` = `validation_error`), `detail` is a list of the invalid parameters.

```
{"detail": "Task with ID 999999999 not found", "code": "not_found"}
```

- 400 `bad_request`: invalid request.
- 404 `not_found`, or a more specific code such as `paper_not_in_catalog`:
  record not found.
- 422 `validation_error` or `invalid_request`: invalid parameter type or
  value, or a missing parameter.
- 429 `rate_limited`: traffic limit exceeded; obey `Retry-After`.
- 5xx: temporary server failure; retry with bounded backoff.

## Changelog

Planned breaking changes will be announced here at least 14 days before they
take effect. Urgent security and service-restoration fixes may take effect
immediately. This beta has no uptime or support-response guarantee.

- 2026-11-26: Errors gain a top-level `code`. `/papers/` gains `cursor` and
  `next_cursor`. Trending papers gain `id` and `published`, evaluations gain
  `metric_values`, and datasets gain `catalog_url`. Paper full text and public
  metadata endpoints join the OpenAPI description. Unsupported `ordering`
  values and unlinked leaderboard metrics now return 422 and 404. Search and
  date filters on `/papers/` cover the whole catalog with the default trending
  order.
- Initial experimental beta: core catalog reads, keyword search, public
  schemas, and anonymous browser access.
