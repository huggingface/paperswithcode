---
name: s2-cli
description: "Semantic Scholar CLI (`s2`) for on-demand citation graph lookup: papers a work cites, papers that cite a work, and graph search across 200M+ papers. Use whenever the user asks for Semantic Scholar, S2, cited papers, references, bibliography, citing papers, citation count from Semantic Scholar, or papers outside a local catalog. Prefer `s2` over curl or ad-hoc Graph API requests."
---

The `s2` CLI is read-only. It queries the Semantic Scholar Graph API and
requires `S2_API_KEY` or `PWC_SEMANTIC_SCHOLAR_API_KEY`. Run `s2 --help` or a
nested `--help` command when the live parser and this skill disagree; the
parser is authoritative.

Install with `uv tool install git+https://github.com/huggingface/s2-cli.git`.
Use compact TSV for reading. Prefer `--jsonl` for programmatic filtering,
sorting, or joining: it emits one unnested paper object per line with the same
shape for search, references, and citations. Use raw `--json` only when API
edge metadata or other schema-specific fields are required.

`PAPER` accepts a modern or legacy arXiv ID, a DOI, a 40-character Semantic
Scholar paper ID, a prefixed ID (`ARXIV:`, `DOI:`, `CorpusId:`, `PMID:`,
`URL:`), an arXiv or Semantic Scholar URL, or a quoted title. Title matching
uses Semantic Scholar's closest-title endpoint and prints a header with the
matched title, ID, arXiv ID, and match score. If the header is wrong, rerun
with an ID. Do not fall back to `s2 search` to resolve a specific paper.

## Commands

- `s2 refs PAPER [--limit LIMIT] [--offset OFFSET] [--fields FIELDS] [--json|--jsonl]` — papers this paper cites.
- `s2 citations PAPER [--limit LIMIT] [--offset OFFSET] [--fields FIELDS] [--json|--jsonl]` — papers that cite this paper.
- `s2 search QUERY [--limit LIMIT] [--offset OFFSET] [--year YEAR] [--fields FIELDS] [--json|--jsonl]` — search the Semantic Scholar graph.
- `s2 version` — show CLI and API contract versions.

All list commands accept `--sort-by citation-count --top N`. Sorting applies
only to the fetched page and prints that scope on stderr. `--top` requires
`--sort-by`, cannot exceed `--limit`, and can be combined with TSV or
`--jsonl`, not raw `--json`.

Default `--limit` is 20. Search max `--limit` is 100; refs/citations max is
1000. There is no `--all`. When stderr prints `# more: rerun with --offset N`,
pass that offset. Citations must keep `offset + limit <= 9999`.

## Research workflow

1. Use `s2 search QUERY --limit 100 --json` for graph-wide discovery.
2. Run a second `s2 search QUERY --year 2025-2026 --limit 100 --json` for a
   recent slice. Do not treat one search as both the classic and recent lists.
3. Use `s2 refs PAPER` for a bibliography and `s2 citations PAPER` for citing
   work. Quote titles. Prefer `ARXIV:` IDs after the first resolution.
4. For a bounded list ranked by the citing papers' own citation counts, run
   `s2 citations PAPER --limit 1000 --sort-by citation-count --top 20`. Describe
   it as the highest-cited papers in that fetched page, never as a verified
   global ranking.
5. Extract arXiv IDs from the `arxiv` TSV column or `externalIds.ArXiv` in
   JSONL/JSON.
6. Prefer `--jsonl` for scripts. Raw `--json` paths are:
   - search papers: `.data.data[]`
   - references: `.data.data[].citedPaper`
   - citations: `.data.data[].citingPaper`
7. If retrieval cannot establish a requested ranking, state the bounded scope
   or API limitation. Never fill the gap from memory and then call the result
   "most cited", "top", exhaustive, or verified.
8. Do not curl `api.semanticscholar.org` while this CLI is available.

## Output and limits

- Stable exit codes are `0` success, `2` invalid usage or missing key, `3`
  network/rate-limit failure, and `4` not found or invalid API response.
- The citations endpoint does not provide global citation-count ordering.
  Sorting one fetched page is useful but cannot establish the globally most
  cited papers. Citations beyond offset 9,999 cannot be enumerated, so famous
  papers may be impossible to rank exhaustively through this API.
- Default request pacing is 1.5s. Do not page citations of famous papers up to
  the 10k cap unless the user explicitly asks.
