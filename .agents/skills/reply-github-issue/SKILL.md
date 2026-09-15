---
name: reply-github-issue
description: Apply author feedback to the Papers With Code catalog, then post and verify GitHub issue replies, especially for evaluation-verification threads and author corrections. Bulk requests such as "all unread" cover only PwC catalog issues. Exclude Hugging Face artifact-hosting outreach and unrelated GitHub notifications unless explicitly requested. Verify changes live, link directly to highlighted evaluation rows, mention README badges for current top-three results, and avoid duplicate comments or unintended issue-state changes.
---

# Reply to a GitHub Issue

Resolve author feedback through Papers With Code catalog changes, then write concise, evidence-backed GitHub issue replies. Tailor every reply to the issue and verify both the catalog state and the posted comment.

## Guardrails

- If the user asks only for a draft, review, or report, do not change the catalog or post anything.
- An actionable request to handle or reply to an in-scope issue includes applying the author-requested catalog corrections and posting the verified outcome. Do not ask for permission again for that routine curation. Honor explicit limits such as "reply only" or "no catalog changes". For the user's Papers With Code unread-notification workflow, their standing preference is to mark handled notifications read as described below; honor any request to leave them unread.
- Do not close, reopen, lock, label, assign, or transfer issues unless the user separately asks. Marking a notification read does not change issue state.
- Do not claim that a catalog change is live until it has been verified on the live site or API.
- Do not expose internal database details, credentials, deployment mechanics, or debugging history in a public reply.
- Write one tailored reply per issue. Avoid boilerplate batches that ignore the author's actual message.

## 1. Audit the requested scope before replying in bulk

### Select PwC catalog issues first

With this skill, “all”, “all unread”, “outstanding”, and “check all issues” mean
Papers With Code catalog issues only. Include evaluation-verification threads
and discussions about PwC papers, benchmark scores, protocols, badges, or catalog
metadata. Classify by the issue's actual subject and discussion, not just its
author, repository owner, or mention of an ML paper.

Exclude requests to release models or datasets on Hugging Face, submit or claim
HF paper pages, or answer Hub storage/pricing questions. These are separate
outreach even when NielsRogge opened them. For example, “Verify evals on Papers
with Code” is in scope; “Release SyntheticDoc on Hugging Face” and “Release
artifacts (model, PanTrack dataset) on Hugging Face” are not. Exclude unrelated
issues and pull-request notifications as well. Expand beyond PwC catalog work
only when the user explicitly requests it.

For “unread”, paginate unread notifications first and retain only in-scope issue
threads, including both open and closed issues. Do not expand that request to
read issues or the entire verification campaign. Apply any subsequent issue
search within the selected scope. Leave excluded notifications untouched,
including their read/unread state.

For a named in-scope issue, proceed directly to resolution. For a batch,
establish the complete in-scope set before replying:

1. Include both `is:open` and `is:closed` issues in scoped searches. A closed issue can still
   accept a comment; never change its state just to reply.
2. Paginate through every result. Do not treat the first search page, a
   relevance-ranked result, or a comment-count filter as complete coverage.
3. For each issue, fetch the latest comment. It needs a reply only if that
   comment is from an author or maintainer and no equivalent NielsRogge reply
   follows it. Exclude bot-only comments and ordinary acknowledgements that
   would create a thank-you loop. A prior acknowledgement or promise to fix
   something does not resolve outstanding catalog work: complete that work
   and report the verified outcome without repeating the acknowledgement.
4. Report the resolved PwC target count before posting, with a brief count of
   excluded unrelated notifications when applicable. Keep a separate list of
   issues that request catalog changes; acknowledge those only after resolving
   the catalog state, rather than claiming a correction is live.

For the recurring verification campaign, search the exact title and author,
for example `is:issue is:open author:NielsRogge "Verify evals on Papers with
Code"`, then repeat with `is:closed`. Prefer a paginated GraphQL search that
returns each issue’s last comment, or explicitly paginate the REST search.

## 2. Apply the feedback and verify the result

1. Read the issue body and all current comments. Identify the repository, issue number, author name or handle, requested correction, and any claims that need acknowledgment.
2. Inspect the current Papers With Code paper and evaluation records. Record the paper identifier, evaluation ID, dataset slug, task slug, model, metric, value, and current rank for every row discussed.
3. Turn each actionable author request into a catalog change and apply it before replying. Check the paper, official artifacts, and existing catalog to establish the affected records and intended protocol. Use the relevant curation skill: `verify-evals` for score/protocol corrections and removals, `add-benchmark` for benchmark or leaderboard separation, `add-evals` for missing results, and `enrich-paper` for links or metadata. Read `docs/database.md` before database access and follow repository data-workflow rules.
4. Complete every independent correction supported by the evidence. For example, when an author requests separating single-frame and video-based Human3.6M results, inspect the affected rows, create or update the appropriate leaderboard groups, move the applicable results, and verify the resulting ranks. Do not stop at agreeing that a split would be useful. Investigate claims of empty repositories and correct code-availability metadata where warranted; do not automatically delete valid paper-reported scores just because code is unavailable.
5. When a request is ambiguous, conflicts with source evidence, or cannot be completed with available access, investigate first and ask only for the specific missing detail. Complete the unblocked corrections before asking. State the concrete blocker and leave unresolved work unread; do not substitute a generic acknowledgement or promise for available catalog work.
6. Verify the changed records through the live site or API, including leaderboard membership, scores, ranks, links, and openness metadata as applicable. Confirm exactly what changed. Distinguish additions, corrections, removals, preserved historical results, and cases where no catalog change was needed. Recheck badge eligibility after any rank changes.
7. Re-read the latest issue comments immediately before posting. If an equivalent reply reporting the completed outcome is already present, do not post a duplicate.

Use the connected GitHub integration first for issue metadata, comments, and posting. Use `gh` only when the integration cannot perform the required operation. Do not blindly retry an uncertain posting failure; fetch the issue comments first to determine whether the comment was created.

## 3. Link directly to highlighted evaluation rows

When an evaluation ID is known, link to its highlighted leaderboard row rather than to a generic benchmark or paper page:

```text
https://paperswithcode.co/benchmark/{dataset_slug}?task={task_slug}&eval={evaluation_id}
```

For example:

```text
https://paperswithcode.co/benchmark/imagenet-256x256?task=image-generation&eval=21566
```

The query order should be `task` followed by `eval`. Use a descriptive Markdown label such as the benchmark and model name. If several rows matter, link each relevant row directly. A paper-page link may supplement these links, but must not replace an evaluation-specific link when the evaluation ID is available.

## 4. Invite authors to copy top-three badges

Check the current live rank of the paper's evaluations. A badge is eligible only when `1 <= best_rank <= 3` on the current leaderboard.

If the paper has at least one current top-three evaluation, include this sentence in the reply:

> Feel free to copy the badges in your README, as this would help the visibility of my website.

Do not include that sentence when no current top-three result exists. Do not infer eligibility from an old issue body or a stale rank; verify it from current catalog data.

When the user asks to provide the badge Markdown itself, use the live, evaluation-specific form generated by the paper page:

```markdown
[![Papers with Code: {SOTA or #rank} on {dataset_name}](https://paperswithcode.co/api/v1/papers/{paper_id}/leaderboard-badge.svg?eval={evaluation_id}&live=1)](https://paperswithcode.co/api/v1/papers/{paper_id}/leaderboard-badge-link?eval={evaluation_id})
```

Prefer the paper page's **Copy PwC badge** output when available, because it already applies the current badge format.

## 5. Compose the reply

Use the issue author's preferred name when it is clear; otherwise address their GitHub handle or omit the greeting. Keep the reply friendly, specific, and brief. Write in the first person when reporting work performed for the catalog.

A typical shape is:

```markdown
Hi {name},

Thanks for {the correction or confirmation}.

I've {specific catalog action}. The updated result is live here: [{benchmark / model}]({direct highlighted evaluation URL}).

{Top-three badge invitation, only when eligible}

Thanks again for helping improve the catalog!
```

Adapt the middle paragraph to the facts:

- For multiple changes, use a short list and attach each direct row link to the relevant item.
- If a historical result remains intentionally, say so plainly and explain the catalog distinction in one sentence.
- If no change was needed, thank the author, state what was verified, and avoid implying that data was edited.
- If only part of the request could be completed, say exactly what is live and what remains unresolved.

Avoid vague phrases such as "fixed everything". Do not mention an evaluation ID as prose unless it helps disambiguate the result; normally it should appear only inside the direct URL.

## 6. Post safely

Before mutating GitHub, state the exact `owner/repository#issue` target in a concise progress update.

Post the prepared body to that issue only. With `gh`, prefer a body file or standard input so Markdown punctuation is not interpreted by the shell:

```bash
gh issue comment ISSUE_NUMBER --repo OWNER/REPOSITORY --body-file PATH
```

For multiple issues, prepare and post separate bodies. A closed issue may accept a comment; do not change its state merely to reply.

## 7. Verify and report

After posting:

1. Fetch the resulting comment or the issue's latest comments.
2. Confirm the repository, issue number, posting account, complete body, direct evaluation links, and top-three badge sentence when eligible.
3. Report the public comment URL to the user.

If posting failed, report the exact failure and whether a comment was created. Leave failed or unresolved work unread.

## 8. Mark handled notifications read

In the Papers With Code unread-notification workflow, mark each in-scope, reviewed, handled issue notification read after verifying the outcome. The scope filter in section 1 applies before any notification mutation; excluded outreach stays untouched. This includes a successfully verified reply that leaves no outstanding action, an already-answered discussion, and an acknowledgement or closure-only update that requires no reply. For example, the author's closure of `dmis-lab/CVRR#1` after confirming the results and receiving a reply needs only a notification update, not another comment.

Read the current discussion and relevant event before deciding: closure alone does not prove that a correction or question has been resolved. Leave outstanding corrections, author-clarification questions, pending reviews, and uncertain posting failures unread, and report them. Draft-only and read-only requests do not authorize notification changes.

1. Resolve the exact notification thread by its `subject.url` matching the issue's API URL. Paginate the scoped notification results; never mark the entire inbox or repository read.
2. Recheck the thread and discussion immediately before marking it read. If new activity arrived after the reviewed snapshot, review it first.
3. Mark that thread read with `PATCH /notifications/threads/{thread_id}` (for example, `gh api --method PATCH notifications/threads/THREAD_ID --silent`). Use the notification thread ID, not the issue number or event ID.
4. Fetch the thread and verify `unread: false`. If it is already read, make no write. If no matching thread can be found, report that rather than claiming a successful update.
5. Report which issues received replies separately from notifications cleared without a reply, linking the posted comments and noting any issues intentionally left unread.
