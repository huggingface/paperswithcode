"""One approved outreach message per repository, grouping its eligible papers."""

import re

from backend.services.github_issue_body_service import (
    GithubIssueDraft,
    outreach_signer,
    render_badge_markdown,
    render_ranking_paragraphs,
    validate_issue_body,
)

# Title of the Hugging Face artifact-release request that the community-science
# paper-parsing pipeline opens from the same account (``Release X on Hugging Face``).
RELEASE_ISSUE_TITLE = re.compile(r"Release .+ on Hugging Face", re.IGNORECASE)


def render_repository_body(papers: list[GithubIssueDraft]) -> str:
    if not papers:
        raise ValueError("No papers to include")
    if len(papers) == 1:
        return papers[0].body
    signer = outreach_signer()
    parts = [
        "Hi,",
        f"{signer} here from the open-source team at Hugging Face.",
        "I've made the following papers and their evaluation results available on Papers with Code:",
    ]
    bullets = []
    for paper in papers:
        title = paper.paper_title.replace("[", r"\[").replace("]", r"\]")
        url = f"https://paperswithcode.co/paper/{paper.paper_id}"
        count = paper.native_evaluation_count
        noun = "evaluation" if count == 1 else "evaluations"
        bullets.append(
            f"- [{title}]({url}) — [{count} paper-native {noun}]({url}#results)."
        )
    parts.append("\n".join(bullets))
    placements = tuple(item for paper in papers for item in paper.ranking_placements)
    parts.extend(render_ranking_paragraphs(placements))
    parts.extend(
        [
            "Would it be possible to verify these results and let me know if any score, model name, benchmark protocol, or openness metadata should be corrected?",
            "You can also edit the task, methods, project page, and GitHub URL directly from each paper page using your Hugging Face account.",
        ]
    )
    badges = []
    seen = set()
    choices = sorted(
        (
            (item, paper.paper_id)
            for paper in papers
            for item in paper.ranking_placements
            if 1 <= item.rank <= 3
        ),
        key=lambda pair: (
            pair[0].rank,
            pair[0].dataset_name,
            pair[1],
            pair[0].evaluation_id,
        ),
    )
    for placement, paper_id in choices:
        if placement.dataset_slug in seen:
            continue
        seen.add(placement.dataset_slug)
        badges.extend(render_badge_markdown(paper_id, (placement,), max_badges=1))
        if len(badges) == 6:
            break
    if badges:
        parts.extend(
            [
                "If you'd like to showcase the results in your repository README, you can copy these live leaderboard badges (or use the “Copy PwC badge” button in the Results section):",
                "\n".join(badges),
            ]
        )
    parts.extend(["Kind regards,", signer])
    body = "\n\n".join(parts)
    if len(body.encode()) > 60000:
        raise ValueError("Grouped issue exceeds the publication size limit")
    for paper in papers:
        validate_issue_body(body, paper.paper_id)
    return body


def render_release_comment(papers: list[GithubIssueDraft]) -> str:
    """The verify-evals message as a follow-up comment on a release issue.

    The release issue already introduces the sender, so the comment drops the
    standalone greeting and introduction and keeps the rest of the message.
    """
    signer = outreach_signer()
    paragraphs = [
        paragraph
        for paragraph in render_repository_body(papers).split("\n\n")
        if paragraph != "Hi," and not paragraph.startswith(f"{signer} here from ")
    ]
    if paragraphs[0].startswith("I've made "):
        paragraphs[0] = (
            "Separately, I've also made " + paragraphs[0][len("I've made ") :]
        )
    body = "\n\n".join(["Hi again,", *paragraphs])
    for paper in papers:
        validate_issue_body(body, paper.paper_id)
    return body
