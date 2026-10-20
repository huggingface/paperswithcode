# SEO operations

The application serves crawlable paper HTML, canonical metadata, `robots.txt`,
sitemaps (`/sitemap.xml`, `/sitemaps/…`), archives, and a read-only
completeness report. Google Search Console and Cloudflare account changes are
operator actions and must not be guessed or encoded in source control.

## Completeness report

Run against one canonical route identifier:

```bash
uv run --env-file backend/keys.env python -m backend.scripts.report_seo_completeness \
  --paper 2607.24653
```

Run a bounded publication cohort (`--published-since`/`--published-until`,
`--limit`, `--json`):

```bash
uv run --env-file backend/keys.env python -m backend.scripts.report_seo_completeness \
  --published-since 2026-07-14 --limit 100 --json
```

The command is read-only. Apply any resulting curation through the existing
paper enrichment and evaluation workflows.

## robots.txt and Cloudflare

The origin owns `robots.txt` (`backend/routers/search_discovery.py`): production
allows crawling and declares `Sitemap: https://paperswithcode.co/sitemap.xml`;
staging disallows everything with `noindex`. nginx proxies `/robots.txt`,
`/sitemap.xml`, and `/sitemaps/` to the backend.

After an SEO-affecting release, fetch the public Cloudflare-edge response, not
only the origin, and confirm `Content-Type: text/plain`, no HTML, exactly one
`Sitemap:` directive, and that search crawling remains allowed. If Cloudflare
managed robots/content-signal settings prepend or merge content, adjust them in
Cloudflare; do not copy Cloudflare's crawler list into application source.

## Authorization boundaries

- Apply nginx templates with `sudo pwc-nginx <environment> --confirm …` only after
  explicit authorization for that environment.
- Search Console ownership, sitemap submission, URL inspection, and indexing
  requests require access to the `paperswithcode.co` domain property. If the
  property is unverified, add Google's exact DNS TXT token through the
  authoritative DNS provider; never invent or replace unrelated TXT records.
- Request indexing at most once per important URL after a successful live
  test. Do not use the Indexing API for ordinary paper URLs.
- Keep Search Console screenshots and exports that expose account owners or
  property membership in private operational logs, not the repository.

## Measurement

Before an SEO-affecting production release, record the edge `robots.txt`
response, sitemap index and shard fetch status, raw-HTML link counts for the
homepage and representative entity pages, and the previous 28 days of Search
Console results for the target pages. Afterwards, compare 7-day and 28-day
windows for clicks, impressions, CTR, average position, indexed state,
canonical mismatches, title rewrites, and discovery lag from publication to
first crawl. A sitemap is a discovery hint, not a ranking guarantee.
