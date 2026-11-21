---
name: delete-comment
description: Remove code comments from the Papers With Code backend and ratchet the comment baseline down. Classifies every comment as tautology, stale, excuse, or decision record; deletes tautologies and stale notes, files a GitHub issue for each hack an excuse comment hid, and moves decision records into ADRs under docs/adr/. Use whenever the user asks to delete, audit, purge, or triage backend comments, run another comment-cleanup pass, lower the comment baseline, or fix a failing `backend_comments.py check`.
---

# Delete comments

The backend bans comments. `scripts/backend_comments.py check` enforces a
per-file ratchet against `backend/comment-baseline.json`: a file may never gain
comments, and files absent from the baseline allow none. Tool directives
(`# noqa`, `# type: ignore`, `# pragma:`, `# fmt:`, shebangs, encoding lines)
and PEP 723 `# /// script` metadata blocks are exempt. Docstrings are not comments and are out of scope.

Each pass shrinks the baseline. A pass can cover the whole backend or one area;
whatever it leaves stays in the baseline for the next pass.

## Workflow

1. Work in an isolated worktree on a `<agent>/delete-comments-<area>` branch.
2. Inventory: `python3 scripts/backend_comments.py inventory <scratch>/blocks.jsonl`.
   Each line is one comment block (consecutive own-line comments, or one inline
   comment) with `f`, `kind`, `start`, `end`, `text`; its id is `c` plus its
   zero-padded line index. Filter to the area you are cleaning.
   - Keep chat-related files in a separate PR: chat changes need explicit
     authorization to merge and deploy. That is more than paths containing
     `chat`: dictation, external Pi, persistent-executor loadtests, durable
     qualification, OpenRouter user budget, runtime validation, LaTeX papers,
     deployment lifecycle, and `backend/main.py` count too.
   - Leave byte-hashed files alone unless the pass ships with the release they
     feed: `backend/chat_sandbox_worker/` (hashed by `contract.py` and
     `executor_release_manifest.py`) and every `PROMPT_INPUTS` path in
     `deploy/external_pi_runtime.py` (hashed into the external Pi runtime,
     whose rebuild needs ~2.6 GiB free). Re-check both lists each pass.
3. Classify every block with the rubric below. For more than ~250 blocks, shard
   by file and give each shard to a subagent with this file as its brief. Each
   subagent writes one JSON line per block (schema below) to its own output
   file, keeps helper scripts in its own subdirectory, and edits nothing.
   Then run `python3 .agents/skills/delete-comment/scripts/triage.py
   <blocks.jsonl> <classifications-dir> <out-dir>` to get `delete.jsonl`,
   `decision.jsonl`, `excuse.jsonl` and `keep.jsonl`.
4. Act on the classifications:
   - `tautology`, `stale`: delete.
   - `excuse`: delete, and file a GitHub issue describing the hack and the fix.
     Group excuses that share one root cause into one issue. Use the
     `docs/agents/issue-tracker.md` conventions and the `comment-debt` label.
   - `decision`: delete, and add the rationale to the area's ADR in `docs/adr/`
     (see below).
   - `keep`: only for text the program reads at runtime (a file read as text,
     a prompt template, generated code). Leave it and say why in the PR.
5. Delete with the tool, never by hand:
   `python3 scripts/backend_comments.py delete <scratch>/delete.jsonl`, where
   each line is an inventory record. It verifies every target line is still a
   comment before touching the file.
6. `uv run ruff format <changed files>`, `uv run ruff check backend`, compile the
   changed files, and run the tests for the touched modules.
7. `python3 scripts/backend_comments.py update` to lower the baseline, then
   `check` must pass. Commit the baseline with the deletions.
8. Report counts per category, lines removed, issues filed, and ADRs written.

## Rubric

Read the code around each comment before deciding. When torn between
`decision` and `tautology`, ask whether a competent engineer would make a
mistake without this sentence. Only a yes makes it a `decision`.

- **tautology**: restates what the code, names, types, or docstring already
  say. Includes section banners, step narration ("# Build the query"),
  restating a constant's value, test arrange/act/assert labels, and
  commented-out code.
- **stale**: describes code, behavior, files, flags, tickets, or plans that no
  longer exist or no longer match the code; history narration ("previously we
  ...", "moved from X"); finished TODOs; dated "temporary" notes whose date
  passed. Check with `grep` when the comment names a symbol or file.
- **excuse**: licenses a hacky implementation: TODO/FIXME/XXX/HACK, "for now",
  "temporary", "workaround", "quick fix", "not ideal", "best effort",
  justification for swallowing exceptions, "keep in sync with X" duplication,
  copy-pasted logic, magic sleeps or retries papering over races, disabled
  checks. The fix is to change the code, not to explain it.
- **decision**: records an important, non-obvious *why*: an external API or
  library quirk, a security or CVE constraint, a data or persisted contract, a
  performance or memory trade-off on the 16 GB VPS, an ordering or concurrency
  invariant, the source of a magic number, a legal or licensing requirement.

## Classification record

One JSON object per line:

```json
{"id": "c00042", "category": "decision", "reason": "<= 15 words",
 "symbol": "backend/services/foo.py::Bar.baz",
 "adr_area": "paper-trending",
 "adr_title": "Trending decays by HF upvote age, not publish date",
 "adr_body": "1-4 sentences: context, the decision, the consequence.",
 "issue_title": "", "issue_body": ""}
```

`adr_*` fields are required for `decision`. `issue_title` and `issue_body` are
required for `excuse`; the body names the file and symbol, quotes the comment,
describes the hack, and proposes the fix. `symbol` points at the enclosing
function or class, never a line number, so ADRs and issues survive edits.

## ADRs

`docs/adr/` holds one file per subsystem, `NNNN-<subsystem>.md`, listed in
`docs/adr/README.md`; ADR 0001 records the comment ban itself. Map each
record's `adr_area` onto an existing subsystem file before creating a new one.
Each decision is a `## <title>` section: the `adr_body` prose, then a
`Code:` line naming the symbol(s). Sections sharing a title merge into one.
Keep sections sorted by title. Do not record what the code makes obvious, and
remove a section when the code it names is deleted.
