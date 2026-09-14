---
name: reply-github-issue
description: Draft, post, and verify replies to GitHub issues about Papers With Code catalog curation, especially evaluation-verification threads and author corrections. Use whenever the user asks to reply, follow up, thank an author, report catalog fixes, or respond on a "Verify evals on Papers with Code" issue. Resolve live catalog state first, link directly to highlighted evaluation rows, mention README badges for current top-three results, and avoid duplicate comments or unintended issue-state changes.
---

# Reply to a GitHub Issue

Write concise, evidence-backed GitHub issue replies after Papers With Code catalog work. Tailor every reply to the issue and verify both the catalog state and the posted comment.

## Guardrails

- If the user asks only for a draft, review, or report, do not post anything.
- Treat an explicit request to reply, comment, or post as authorization to create the issue comment. For the user's Papers With Code unread-notification workflow, their standing preference is to mark handled notifications read as described below; honor any request to leave them unread.
- Do not close, reopen, lock, label, assign, or transfer issues unless the user separately asks. Marking a notification read does not change issue state.
- Do not claim that a catalog change is live until it has been verified on the live site or API.
- Do not expose internal database details, credentials, deployment mechanics, or debugging history in a public reply.
- Write one tailored reply per issue. Avoid boilerplate batches that ignore the author's actual message.

## 1. Audit the requested scope before replying in bulk

For a named issue, proceed directly to resolution. For a batch, or when the
user says “all”, “outstanding”, or “check all issues”, establish the complete
set before replying:

1. Search both `is:open` and `is:closed` issues. A closed issue can still
   accept a comment; never change its state just to reply.
2. Paginate through every result. Do not treat the first search page, a
   relevance-ranked result, or a comment-count filter as complete coverage.
3. For each issue, fetch the latest comment. It needs a reply only if that
   comment is from an author or maintainer and no equivalent NielsRogge reply
   follows it. Exclude bot-only comments and ordinary acknowledgements that
   would create a thank-you loop.
4. Report the resolved target count before posting. Keep a separate list of
   issues that request catalog changes; acknowledge those only after resolving
   the catalog state, rather than claiming a correction is live.

For the recurring verification campaign, search the exact title and author,
for example `is:issue is:open author:NielsRogge "Verify evals on Papers with
Code"`, then repeat with `is:closed`. Prefer a paginated GraphQL search that
returns each issue’s last comment, or explicitly paginate the REST search.

## 2. Resolve the issue and the result

1. Read the issue body and all current comments. Identify the repository, issue number, author name or handle, requested correction, and any claims that need acknowledgment.
2. Inspect the current Papers With Code paper and evaluation records. Record the paper identifier, evaluation ID, dataset slug, task slug, model, metric, value, and current rank for every row discussed.
3. Confirm exactly what changed. Distinguish additions, corrections, removals, preserved historical results, and cases where no catalog change was needed.
4. Re-read the latest issue comments immediately before posting. If an equivalent reply is already present, do not post a duplicate.

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

In the Papers With Code unread-notification workflow, mark each reviewed, handled issue notification read after verifying the outcome. This includes a successfully verified reply that leaves no outstanding action, an already-answered discussion, and an acknowledgement or closure-only update that requires no reply. For example, the author's closure of `dmis-lab/CVRR#1` after confirming the results and receiving a reply needs only a notification update, not another comment.

Read the current discussion and relevant event before deciding: closure alone does not prove that a correction or question has been resolved. Leave outstanding corrections, author-clarification questions, pending reviews, and uncertain posting failures unread, and report them. Draft-only and read-only requests do not authorize notification changes.

1. Resolve the exact notification thread by its `subject.url` matching the issue's API URL. Paginate the scoped notification results; never mark the entire inbox or repository read.
2. Recheck the thread and discussion immediately before marking it read. If new activity arrived after the reviewed snapshot, review it first.
3. Mark that thread read with `PATCH /notifications/threads/{thread_id}` (for example, `gh api --method PATCH notifications/threads/THREAD_ID --silent`). Use the notification thread ID, not the issue number or event ID.
4. Fetch the thread and verify `unread: false`. If it is already read, make no write. If no matching thread can be found, report that rather than claiming a successful update.
5. Report which issues received replies separately from notifications cleared without a reply, linking the posted comments and noting any issues intentionally left unread.
