from datetime import date

from backend.models.papers import Paper, Repository
from backend.services.seo_completeness_service import score_paper


def test_completeness_score_reports_factual_missing_fields():
    paper = Paper(
        id="42",
        arxiv_id="2607.24653",
        source="arxiv",
        title="Kimi K3",
        abstract="Full summary",
        authors=["Kimi Team"],
        published=date(2026, 7, 27),
        repositories=[
            Repository(
                id="1",
                url="https://github.com/moonshotai/kimi-k3",
                is_official=True,
            )
        ],
        hf_models=["https://huggingface.co/moonshotai/Kimi-K3"],
    )

    result = score_paper(paper, has_evaluations=True)

    assert result.required_complete
    assert result.valuable["official_repository"]
    assert result.valuable["hugging_face_artifacts"]
    assert result.valuable["benchmark_or_evaluations"]
    assert not result.valuable["tldr"]
    assert not result.valuable["project_page"]
