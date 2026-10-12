import asyncio
import json
from pathlib import Path

import pytest
import yaml

import url_extraction_agent.database as database_module
from url_extraction_agent.agent import _masks_hf_exit_status, derive_attempt_complete
from url_extraction_agent.database import (
    _selection_sql,
    canonicalize_github_url,
    canonicalize_project_page_url,
    verify_url_for_persist,
)
from url_extraction_agent.modal_app import MAX_CONTAINERS
from url_extraction_agent.runner import MAX_PAPERS, load_candidates, run_batch
from url_extraction_agent.schema import (
    AgentAttempt,
    PaperCandidate,
    PersistResult,
    ToolEvent,
    URLFindings,
)


def candidate(paper_id: int = 1) -> PaperCandidate:
    return PaperCandidate(
        paper_id=paper_id,
        arxiv_id=f"2601.{paper_id:05d}",
        title="Test paper",
        abstract="Abstract",
        missing_github=True,
        missing_project_page=True,
        priority=1,
        priority_source="recent_hf",
    )


def bash_event(command: str, success: bool = True) -> ToolEvent:
    return ToolEvent(
        tool_name="Bash",
        tool_input={"command": command},
        success=success,
    )


def test_reasoning_is_first_structured_output_property():
    properties = list(URLFindings.model_json_schema()["properties"])
    assert properties == ["reasoning", "github_url", "project_page_url"]


def test_hf_source_commands_cannot_mask_or_truncate_exit_status():
    assert _masks_hf_exit_status(
        "Bash", {"command": "hf papers info 2601.00001 --format json | head"}
    )
    assert _masks_hf_exit_status(
        "Bash", {"command": "hf papers read 2601.00001; echo $?"}
    )
    assert not _masks_hf_exit_status(
        "Bash", {"command": "hf papers info 2601.00001 --format json 2>&1"}
    )


def test_completion_is_derived_from_successful_required_tools():
    paper = candidate()
    findings = URLFindings(
        reasoning="Checked HF metadata and the paper.",
        github_url=None,
        project_page_url=None,
    )
    events = [
        bash_event(f"hf papers info {paper.arxiv_id} --format json"),
        bash_event(f"hf papers read {paper.arxiv_id}"),
    ]

    assert derive_attempt_complete(paper, findings, events) == (True, None)


def test_failed_required_tool_does_not_mark_attempt_complete():
    paper = candidate()
    findings = URLFindings(
        reasoning="Metadata endpoint failed.",
        github_url=None,
        project_page_url=None,
    )
    events = [
        bash_event(f"hf papers info {paper.arxiv_id} --format json", success=False),
        bash_event(f"hf papers read {paper.arxiv_id}"),
    ]

    complete, reason = derive_attempt_complete(paper, findings, events)
    assert complete is False
    assert "metadata" in reason.lower()


def test_arxiv_fetches_can_satisfy_failed_hf_sources():
    paper = candidate()
    findings = URLFindings(
        reasoning="HF was unavailable; arXiv metadata and HTML were checked.",
        github_url=None,
        project_page_url=None,
    )
    events = [
        bash_event(f"hf papers info {paper.arxiv_id} --format json", success=False),
        bash_event(f"hf papers read {paper.arxiv_id}", success=False),
        ToolEvent(
            tool_name="WebFetch",
            tool_input={"url": f"https://arxiv.org/abs/{paper.arxiv_id}"},
            success=True,
        ),
        ToolEvent(
            tool_name="WebFetch",
            tool_input={"url": f"https://arxiv.org/html/{paper.arxiv_id}v1"},
            success=True,
        ),
    ]
    assert derive_attempt_complete(paper, findings, events) == (True, None)


def test_project_page_must_be_fetched_while_github_is_unresolved():
    paper = candidate()
    findings = URLFindings(
        reasoning="Project page had no repository link.",
        github_url=None,
        project_page_url="https://example.org/project",
    )
    events = [
        bash_event(f"hf papers info {paper.arxiv_id} --format json"),
        bash_event(f"hf papers read {paper.arxiv_id}"),
    ]

    complete, reason = derive_attempt_complete(paper, findings, events)
    assert complete is False
    assert "project page" in reason.lower()

    events.append(
        ToolEvent(
            tool_name="WebFetch",
            tool_input={"url": "https://example.org/project"},
            success=True,
        )
    )
    assert derive_attempt_complete(paper, findings, events) == (True, None)


def test_url_canonicalization_rejects_non_repository_and_non_project_hosts():
    assert (
        canonicalize_github_url("https://github.com/org/repo/tree/main")
        == "https://github.com/org/repo"
    )
    assert canonicalize_github_url("https://gitlab.com/org/repo") is None
    assert canonicalize_project_page_url("https://arxiv.org/abs/2601.00001") is None
    assert (
        canonicalize_project_page_url("https://project.example/demo#code")
        == "https://project.example/demo"
    )


def test_selection_ranks_scopes_before_filtering_candidates():
    sql = _selection_sql("github")
    assert sql.index("task_ranked AS") < sql.index("eligible AS")
    assert "WHERE rn <= 20" in sql
    assert "'backlog' AS priority_source" in sql
    assert "p.urls_extracted = FALSE" in sql
    assert "ls.github_url IS NULL OR ls.project_page_url IS NULL" in sql


def test_candidate_artifact_rejects_more_than_100(tmp_path: Path):
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            [
                candidate(index + 1).model_dump(mode="json")
                for index in range(MAX_PAPERS + 1)
            ]
        )
    )
    with pytest.raises(ValueError, match="exceeds"):
        load_candidates(path)


def test_modal_results_are_correlated_when_returned_out_of_order(monkeypatch):
    papers = [candidate(1), candidate(2)]

    class FakeFunction:
        def map(self, inputs, **kwargs):
            assert kwargs["order_outputs"] is False
            assert len(inputs) == 2
            yield AgentAttempt(paper_id=2, arxiv_id=papers[1].arxiv_id).model_dump(
                mode="json"
            )
            yield AgentAttempt(paper_id=1, arxiv_id=papers[0].arxiv_id).model_dump(
                mode="json"
            )

    monkeypatch.setattr(
        "url_extraction_agent.runner.modal.Function.from_name",
        lambda *_args: FakeFunction(),
    )
    results = run_batch(papers)
    assert [result.paper_id for result in results] == [1, 2]
    assert MAX_CONTAINERS == 20


def test_workflow_isolates_modal_discovery_from_vps_persistence():
    workflow_path = (
        Path(__file__).resolve().parents[3]
        / ".github"
        / "workflows"
        / "cron-extract-urls.yml"
    )
    workflow = yaml.safe_load(workflow_path.read_text())
    jobs = workflow["jobs"]
    assert jobs["discover"]["needs"] == "select"
    assert jobs["persist"]["needs"] == "discover"
    assert jobs["persist"]["if"] == "${{ inputs.persist == true }}"
    dispatch_inputs = workflow[True]["workflow_dispatch"]["inputs"]
    assert dispatch_inputs["persist"]["type"] == "boolean"
    assert dispatch_inputs["persist"]["default"] is False
    discover_env = jobs["discover"]["env"]
    assert set(discover_env) == {
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "URL_EXTRACTION_MODAL_SECRET",
    }
    assert (
        discover_env["URL_EXTRACTION_MODAL_SECRET"]
        == "url-extraction-deepseek-v4-flash-deepinfra"
    )
    assert "VPS_SSH_PRIVATE_KEY" not in str(jobs["discover"])


def test_persist_cli_writes_json_stdout_before_nonzero_exit(
    monkeypatch, tmp_path, capsys
):
    input_path = tmp_path / "attempts.json"
    input_path.write_text(
        json.dumps([AgentAttempt(paper_id=1, arxiv_id="2601.00001").model_dump()])
    )

    async def fake_persist_many(_attempts):
        return [
            PersistResult(
                paper_id=1,
                status="retry",
                message="temporary failure",
            )
        ]

    monkeypatch.setattr(database_module, "persist_many", fake_persist_many)
    monkeypatch.setattr(
        "sys.argv",
        [
            "database.py",
            "persist",
            "--input",
            str(input_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        database_module.main()

    assert exc.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "paper_id": 1,
            "status": "retry",
            "github_saved": False,
            "project_page_saved": False,
            "urls_extracted": False,
            "message": "temporary failure",
        }
    ]


def test_persist_cli_writes_json_stdout_on_success(monkeypatch, tmp_path, capsys):
    input_path = tmp_path / "attempts.json"
    input_path.write_text(
        json.dumps([AgentAttempt(paper_id=1, arxiv_id="2601.00001").model_dump()])
    )

    async def fake_persist_many(_attempts):
        return [
            PersistResult(
                paper_id=1,
                status="persisted",
                github_saved=True,
                project_page_saved=True,
                urls_extracted=True,
                message="conclusive attempt committed",
            )
        ]

    monkeypatch.setattr(database_module, "persist_many", fake_persist_many)
    monkeypatch.setattr(
        "sys.argv",
        [
            "database.py",
            "persist",
            "--input",
            str(input_path),
        ],
    )

    database_module.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "persisted"
    assert payload[0]["urls_extracted"] is True


def test_persist_url_verification_keeps_diagnostics_off_stdout(monkeypatch, capsys):
    async def noisy_verify_url(_url):
        print("human-readable validator warning")
        return False

    monkeypatch.setattr(database_module, "verify_url", noisy_verify_url)

    assert asyncio.run(verify_url_for_persist("https://example.com/missing")) is False

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "human-readable validator warning" in captured.err
