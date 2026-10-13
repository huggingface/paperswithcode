from backend.utils.urls import external_source_url_to_paper_url, parse_arxiv_url
from backend.models.database import Repository as DBRepository
from backend.services.evaluation_service import (
    evaluation_external_flag,
    evaluation_is_external,
    evaluation_public_source_url,
    evaluation_result_url,
)


def test_parse_arxiv_url_supports_html_paths():
    assert parse_arxiv_url("https://arxiv.org/html/2606.13141v1") == (
        "2606.13141",
        "v1",
    )


def test_external_source_url_to_paper_url_rewrites_arxiv_links():
    assert (
        external_source_url_to_paper_url("https://arxiv.org/html/2606.13141v1")
        == "/paper/2606.13141"
    )
    assert (
        external_source_url_to_paper_url("https://arxiv.org/abs/2512.23351")
        == "/paper/2512.23351"
    )


def test_external_source_url_to_paper_url_leaves_non_arxiv_links():
    url = "https://huggingface.co/UsefulSensors/moonshine-streaming-tiny"
    assert external_source_url_to_paper_url(url) == url


def test_evaluation_result_url_prefers_pwc_for_external_arxiv_sources():
    assert (
        evaluation_result_url(
            "https://arxiv.org/html/2606.13141v1",
            40193,
            "2411.13093",
            None,
        )
        == "/paper/2606.13141"
    )


def test_evaluation_is_external_uses_raw_source_url():
    assert evaluation_is_external(
        "https://arxiv.org/html/2606.13141v1",
        "2411.13093",
        40193,
    )
    assert (
        evaluation_public_source_url("https://arxiv.org/html/2606.13141v1")
        == "/paper/2606.13141"
    )


def test_evaluation_is_external_false_for_same_arxiv_paper():
    assert not evaluation_is_external(
        "https://arxiv.org/abs/2411.13093",
        "2411.13093",
        40193,
    )


def test_hugging_face_paper_page_is_the_same_arxiv_paper():
    for url in (
        "https://huggingface.co/papers/2111.12993",
        "https://huggingface.co/papers/2111.12993.md",
        "https://huggingface.co/papers/2111.12993v2/",
    ):
        assert not evaluation_is_external(url, "2111.12993", 80367)
    assert evaluation_is_external(
        "https://huggingface.co/papers/2010.11929.md", "2111.12993", 80367
    )


class _FakePaper:
    def __init__(
        self,
        paper_id: int,
        *,
        source_url: str | None = None,
        conference_url_abs: str | None = None,
        conference_url_pdf: str | None = None,
        hf_models: list[str] | None = None,
    ):
        self.id = paper_id
        self.arxiv_id = None
        self.source_url = source_url
        self.conference_url_abs = conference_url_abs
        self.conference_url_pdf = conference_url_pdf
        self.hf_models = hf_models or []
        self.hf_datasets = []
        self.hf_spaces = []


class _FakeQuery:
    def __init__(self, result, rows=None):
        self._result = result
        self._rows = rows or []

    def filter(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def first(self):
        return self._result

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _FakeDB:
    def __init__(self, result, repository_urls=None):
        self._result = result
        self._repository_urls = repository_urls or []

    def get(self, model, ident):
        return self._result

    def query(self, *args, **kwargs):
        if len(args) == 2 and getattr(args[1], "class_", None) is DBRepository:
            return _FakeQuery(
                None,
                [(self._result.id, url) for url in self._repository_urls],
            )
        if len(args) == 2:
            return _FakeQuery(None)
        return _FakeQuery(self._result)


def test_evaluation_is_external_false_for_model_card_source():
    model_url = "https://huggingface.co/UsefulSensors/moonshine-streaming-tiny"
    db = _FakeDB(_FakePaper(40193, hf_models=[model_url]))
    assert not evaluation_is_external(
        model_url,
        "2411.13093",
        40193,
        db,
    )


def test_evaluation_is_external_true_for_independent_source():
    db = _FakeDB(_FakePaper(paper_id=40193))
    assert evaluation_is_external(
        "https://example.com/a-competition-page",
        None,
        40193,
        db,
    )


def test_evaluation_is_external_false_for_file_in_linked_github_repository():
    repository_url = "https://github.com/MoonshotAI/Kimi-K3"
    report_url = "https://github.com/MoonshotAI/Kimi-K3/blob/main/k3_tech_report.pdf"
    db = _FakeDB(
        _FakePaper(paper_id=104584),
        repository_urls=[repository_url],
    )
    assert not evaluation_is_external(
        report_url,
        "2607.24653",
        104584,
        db,
    )
    assert (
        evaluation_result_url(
            report_url,
            104584,
            "2607.24653",
            None,
            db,
        )
        == "https://arxiv.org/pdf/2607.24653.pdf"
    )


def test_evaluation_is_external_true_for_file_in_unrelated_github_repository():
    db = _FakeDB(
        _FakePaper(paper_id=104584),
        repository_urls=["https://github.com/MoonshotAI/Kimi-K3"],
    )
    assert evaluation_is_external(
        "https://github.com/another-org/benchmark/blob/main/results.json",
        "2607.24653",
        104584,
        db,
    )


def test_evaluation_is_external_false_when_source_matches_same_paper():
    source_url = "https://example.com/this-paper"
    db = _FakeDB(_FakePaper(paper_id=40193, source_url=source_url))
    assert not evaluation_is_external(
        source_url,
        None,
        40193,
        db,
    )


def test_evaluation_is_external_false_for_linked_conference_page():
    conference_url = "https://openreview.net/forum?id=kPC83HK4br"
    db = _FakeDB(_FakePaper(paper_id=91859, conference_url_abs=conference_url))
    assert not evaluation_is_external(
        conference_url,
        "2407.06141",
        91859,
        db,
    )


def test_evaluation_is_external_false_for_openreview_forum_pdf_variants():
    db = _FakeDB(
        _FakePaper(
            paper_id=91859,
            conference_url_abs="https://openreview.net/forum?id=kPC83HK4br",
        )
    )
    assert not evaluation_is_external(
        "https://openreview.net/pdf?id=kPC83HK4br",
        "2407.06141",
        91859,
        db,
    )


def test_evaluation_is_external_true_for_unrelated_openreview_submission():
    db = _FakeDB(
        _FakePaper(
            paper_id=91859,
            conference_url_abs="https://openreview.net/forum?id=kPC83HK4br",
        )
    )
    assert evaluation_is_external(
        "https://openreview.net/forum?id=someOtherSubmission",
        "2407.06141",
        91859,
        db,
    )


def test_evaluation_external_flag_prefers_computed_value_over_stored_true():
    source_url = "https://example.com/this-paper"
    db = _FakeDB(_FakePaper(paper_id=40193, source_url=source_url))
    assert not evaluation_external_flag(
        stored_external=True,
        source_url=source_url,
        paper_arxiv_id=None,
        paper_id=40193,
        db=db,
    )


def test_evaluation_external_flag_falls_back_to_stored_when_source_missing():
    assert evaluation_external_flag(
        stored_external=True,
        source_url=None,
        paper_arxiv_id="2411.13093",
        paper_id=40193,
    )


COUNTSE_PAPER_HTML = (
    "https://openaccess.thecvf.com/content/ICCV2025/html/"
    "Liu_CountSE_Soft_Exemplar_Open-set_Object_Counting_ICCV_2025_paper.html"
)
COUNTSE_PAPER_PDF = (
    "https://openaccess.thecvf.com/content/ICCV2025/papers/"
    "Liu_CountSE_Soft_Exemplar_Open-set_Object_Counting_ICCV_2025_paper.pdf"
)
OTHER_CVF_PAPER_PDF = (
    "https://openaccess.thecvf.com/content/ICCV2025/papers/"
    "Some_Other_Paper_ICCV_2025_paper.pdf"
)


def test_evaluation_is_external_false_for_cvf_html_pdf_variants():
    db = _FakeDB(_FakePaper(paper_id=98356, source_url=COUNTSE_PAPER_HTML))
    assert not evaluation_is_external(
        COUNTSE_PAPER_PDF,
        None,
        98356,
        db,
    )


def test_evaluation_is_external_true_for_unrelated_cvf_paper():
    db = _FakeDB(_FakePaper(paper_id=98356, source_url=COUNTSE_PAPER_HTML))
    assert evaluation_is_external(
        OTHER_CVF_PAPER_PDF,
        None,
        98356,
        db,
    )


def test_evaluation_result_url_uses_paper_source_for_cvf_pdf():
    db = _FakeDB(_FakePaper(paper_id=98356, source_url=COUNTSE_PAPER_HTML))
    assert (
        evaluation_result_url(
            COUNTSE_PAPER_PDF,
            98356,
            None,
            COUNTSE_PAPER_HTML,
            db,
        )
        == COUNTSE_PAPER_HTML
    )
