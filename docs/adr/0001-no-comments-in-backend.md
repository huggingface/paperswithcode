# ADR 0001: The backend carries no code comments

Status: accepted

## Context

Most backend comments restated the code, described behavior that had since
changed, or excused a hack so it could be copied elsewhere. The few that
mattered, rationale for non-obvious decisions, were scattered across files and
went stale silently.

## Decision

Backend Python code carries no comments. Rationale for a non-obvious decision
goes in an ADR in this directory, grouped by subsystem and naming the code it
governs. A hack goes in a GitHub issue labelled `comment-debt`, not in a comment
that explains it away. Everything else belongs in names, types, docstrings, and
tests.

Tool directives are not comments: `# noqa`, `# type: ignore`, `# pragma:`,
`# fmt:`, shebangs, encoding lines, and PEP 723 `# /// script` metadata blocks.

`scripts/backend_comments.py check` enforces this with a per-file ratchet against
`backend/comment-baseline.json`, in pre-commit and in the `Backend comment
ratchet` workflow. A file may never gain comments and new files allow none.
`update` lowers the baseline after a cleanup and refuses to raise it.

## Consequences

Remaining comments are removed in later passes with the `delete-comment` skill
(`.agents/skills/delete-comment/SKILL.md`). Comments in
`backend/chat_sandbox_worker/` stay until a worker contract release, because
those files are hashed into the worker contract and executor release digests.
