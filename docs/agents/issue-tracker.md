# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Papers With Code evaluation outreach

For `Verify evals on Papers with Code` outreach, do not create an issue when:

- the target repository is owned by `huggingface`;
- the repository name is `vllm`, `sglang`, or `llama.cpp`;
- the repository already has an open issue authored by `nielsrogge`.

The publisher checks these exclusions before creating an issue. It also reuses
an existing issue containing the paper URL, including closed issues, to avoid
duplicate outreach.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**, the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me`, the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.

## Scheduled evaluation outreach

`create_eval_verification_issues` runs hourly at minute 52 through the installed
`pwc-cron` allowlist. It reads committed catalog results independently of the
asynchronous daily enrichment workers, so manual additions and other evaluation
producers are covered too. The job groups papers by GitHub's canonical repository
ID and waits until native evaluations are at least one hour old and no linked
paper has queued/running curation work.

The exclusions also cover owners `tensorflow`, `pytorch`, `openai`, `anthropic`,
and `anthropics`; repository names `tensorflow` and `pytorch`; and exact repos
`google-research/google-research` and `pwc-1/Paper-9`. Owner/name comparisons are
case insensitive and apply again after redirects. There is no blanket star-count
or repository-age cutoff.

Each run resolves up to 500 repository aliases, checks up to 50 repositories,
and attempts at most 10 issue creations, with ten seconds between attempts.
The overall GitHub request budget is 600. Initial identity discovery finishes
across bounded runs before any messages are composed; identities refresh weekly.
Selection covers all latest papers with native evaluations and official GitHub
links, rather than a time window that could lose work during downtime.

Any open issue by `NielsRogge` blocks outreach. Complete, paginated issue history
also suppresses already-contacted papers, including closed threads and numeric,
arXiv, and versioned paper URLs. Previously contacted papers are omitted from a
new grouped message. Counts, ranks, badges, and official links are refreshed
before posting. Creation requires authenticating as `NielsRogge`, and the job
reads back the issue to verify its exact author, title, and body.

The durable SQLite ledger is
`/var/lib/paperswithcode/production/cron-locks/github-eval-outreach.sqlite3`,
outside log retention and immutable releases. Preserve it during upgrades and
rollbacks. It records covered papers, issue URLs, retry times, and an exact
pre-POST checkpoint. HTTP 422 rejections (including collaborators-only issue
creation) wait 30 days; open/ineligible repositories wait a day. Other API
failures stop the batch. Rate limits stop all work until at least the next hour
and honor a later `Retry-After`/reset time.

An uncertain POST is reconciled with GitHub on subsequent runs; it is never
blindly retried. Missing or edited results remain `needs_review`, with a failing
job exit until resolved. Inspect the recorded body, paper IDs, repository, and
GitHub history before operator repair of the ledger. Do not delete the ledger
to clear a failure. The per-ledger lock also serializes direct invocations.

Preview is the default for `python -m backend.scripts.create_eval_verification_issues`:
it performs read-only GitHub/catalog checks and uses an in-memory copy of the
ledger. `--status` reads the last-run summary and pending repository IDs without
network access. `--state-file` permits isolated qualification. The installed
launcher supplies `--execute` and uses `PWC_GITHUB_TOKEN` from the protected CRON
environment. Logs and counts appear under `create_eval_verification_issues` in
the admin CRON dashboard; a successful run is not proof that discovery/backlog
is exhausted—inspect `aliases_remaining` and the durable last-run summary.

To pause publication after rollout, disable the
`pwc-cron-create-eval-verification-issues.timer` through normal operations.
Activating this feature requires merging/deploying its application release and
installing the updated deploy tooling/host timer units; a code-only release does
not update the installed launcher allowlist.
