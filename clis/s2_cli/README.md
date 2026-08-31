# s2 CLI and Skill

A fast, read-only command-line client for the [Semantic Scholar Graph API](https://api.semanticscholar.org/api-docs/graph), alongside a Skill for coding agents.

Use `s2` to:

- list the papers a work **cites** (`s2 refs`)
- list the papers that **cite** a work (`s2 citations`)
- **search** the Semantic Scholar graph when a paper may not be in a local catalog

This CLI requires an API key. Set `PWC_SEMANTIC_SCHOLAR_API_KEY` or `S2_API_KEY`. Request a key at [Semantic Scholar's API page](https://www.semanticscholar.org/product/api).

```bash
s2 refs "Attention is All You Need"
s2 citations ARXIV:1706.03762 --limit 50
s2 search "image dehazing" --year 2025-2026 --limit 100 --json
```

## Installation

Python 3.10 or newer is required.

With [`uv`](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/huggingface/s2-cli.git
```

Or with [`pipx`](https://pipx.pypa.io/):

```bash
pipx install git+https://github.com/huggingface/s2-cli.git
```

From a clone:

```bash
git clone https://github.com/huggingface/s2-cli.git
cd s2-cli
uv tool install .
```

Confirm the installation:

```bash
s2 version
```

## Add the CLI Skill

Copy [`SKILL.md`](SKILL.md) into your agent's skills directory:

```bash
mkdir -p .agents/skills/s2-cli
curl -LsSf https://raw.githubusercontent.com/huggingface/s2-cli/main/SKILL.md \
  -o .agents/skills/s2-cli/SKILL.md
```

## Quick start

```bash
export S2_API_KEY=...   # or PWC_SEMANTIC_SCHOLAR_API_KEY

s2 refs "Attention is All You Need"
s2 refs 1706.03762 --limit 50 --offset 20
s2 citations ARXIV:1706.03762 --json
s2 citations ARXIV:1706.03762 --limit 1000 --sort-by citation-count --top 20
s2 search "scene graph generation" --limit 100
s2 search "scene graph generation" --year 2025-2026 --limit 100 --json
```

`PAPER` accepts a quoted title, an arXiv ID (`1706.03762`, `arXiv:1706.03762`), a DOI, a 40-character Semantic Scholar paper ID, a prefixed ID (`ARXIV:`, `DOI:`, `CorpusId:`, `PMID:`, `URL:`), or an arXiv / Semantic Scholar URL. Titles are resolved with Semantic Scholar's closest-title match. The matched title, paper ID, arXiv ID, and match score are printed on stderr so a bad match is visible. Pass an ID if the header is wrong.

## Command reference

| Command | Description |
| --- | --- |
| `s2 refs PAPER` | Papers this paper cites (bibliography) |
| `s2 citations PAPER` | Papers that cite this paper |
| `s2 search QUERY` | Relevance search over the Semantic Scholar graph |
| `s2 version` | Show the CLI version |

Shared flags: `--limit`, `--offset`, `--json`, `--jsonl`, `--fields`, `--sort-by citation-count`, and `--top`. `s2 search` also accepts `--year` (`2025` or `2025-2026`). Defaults are `--limit 20`. Search `--limit` maxes at 100; refs/citations max at 1000. There is no `--all`; rerun with `--offset` when stderr prints `# more`.

Citation requests must keep `offset + limit <= 9999`. Highly cited papers are not fully enumerable through this CLI.

## Output and scripting

List commands print lossless TSV (`paperId`, `year`, `cites`, `arxiv`, `title`). Add `--jsonl` for one unnested Semantic Scholar paper object per line. This shape is consistent across search, references, and citations and is the recommended scripting format.

Use `--sort-by citation-count --top N` to sort and trim the fetched page. The CLI prints the bounded scope on stderr. This is not a global ranking: Semantic Scholar's citations endpoint does not offer global citation-count ordering, and citations past offset 9,999 cannot be enumerated.

Add `--json` for the raw Semantic Scholar payload wrapped as:

```json
{
  "schema_version": "v1",
  "paper": {"id": "ARXIV:1706.03762"},
  "data": {}
}
```

`paper` is present on `refs` and `citations`. Search JSON includes abstracts in `data` by default.

Raw JSON paper paths are `.data.data[]` for search,
`.data.data[].citedPaper` for references, and
`.data.data[].citingPaper` for citations.

Stable exit codes:

| Code | Meaning |
| ---: | --- |
| `0` | Success |
| `2` | Invalid usage or missing API key |
| `3` | Network, server, or exhausted rate-limit failure |
| `4` | Not found or invalid API response |

## Configuration

| Variable | Meaning |
| --- | --- |
| `PWC_SEMANTIC_SCHOLAR_API_KEY` | Preferred API key |
| `S2_API_KEY` | Fallback API key if the preferred key is unset |
| `S2_REQUEST_DELAY` | Seconds to wait between requests (default `1.5`) |

The CLI never reads a secondary historical-backfill key. It sends `x-api-key`, honors `Retry-After` on HTTP 429, and identifies itself as `s2-cli/<version>`.

## Development

```bash
uv run --with pytest pytest tests
```
