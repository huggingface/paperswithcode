import copy

import pytest

from jobs import curation_api


def proposal():
    return {
        "benchmark_gaps": [
            {
                "protocol": {
                    "metrics": [
                        {"name": "PSNR", "definition": "Peak signal-to-noise ratio"}
                    ]
                },
                "blocked_evaluations": [
                    {"metrics": {"PSNR": 30.1}, "best_metric": "PSNR"}
                ],
                "evidence": [
                    {
                        "source_url": "https://example.org/paper",
                        "source_kind": "paper_source",
                    }
                ],
            }
        ]
    }


def test_valid_proposal_is_not_rewritten():
    value = proposal()
    original = copy.deepcopy(value)
    curation_api.check_benchmark_gap_fields(value, None)
    assert value == original


def test_all_fixable_gap_errors_reported_together():
    value = proposal()
    gap = value["benchmark_gaps"][0]
    gap["protocol"]["metrics"][0]["definition"] = ""
    gap["blocked_evaluations"][0]["best_metric"] = "PSNR-test"
    gap["blocked_evaluations"][0]["metrics"] = {"PSNR-test": 30.1}
    manifest = {
        "source_documents": [
            {"url": "https://example.org/paper", "kind": "project_page"}
        ]
    }
    with pytest.raises(ValueError) as exc:
        curation_api.check_benchmark_gap_fields(value, manifest)
    message = str(exc.value)
    for expected in (
        "no apply attempted",
        "definition",
        "best_metric",
        "undefined metric",
        "source_kind",
    ):
        assert expected in message


def test_apply_preflight_does_not_send_trace_or_consume_attempt(tmp_path, monkeypatch):
    value = proposal()
    value["benchmark_gaps"][0]["blocked_evaluations"][0]["best_metric"] = "missing"
    import json

    path = tmp_path / "proposal.json"
    path.write_text(json.dumps(value))
    monkeypatch.setattr("sys.argv", ["curation_api.py", "apply", str(path)])
    monkeypatch.setattr(curation_api, "request_json", lambda _: {})
    monkeypatch.setattr(
        curation_api,
        "_trace_payload",
        lambda p: {"proposal": p, "url_candidates": None},
    )
    calls = []
    monkeypatch.setattr(
        curation_api, "store_trace_with_retry", lambda *args, **kw: calls.append(args)
    )
    monkeypatch.setattr(curation_api, "request", lambda *args, **kw: calls.append(args))
    with pytest.raises(ValueError, match="no apply attempted"):
        curation_api.main()
    assert calls == []


def board(task_id, dataset_id, *metrics):
    return {
        "task": {"id": task_id},
        "dataset": {"id": dataset_id},
        "metrics": [{"name": name} for name in metrics],
    }


def evaluation(task_id, dataset_id, best_metric="Accuracy"):
    return {
        "model_name": "Model",
        "task_id": task_id,
        "dataset_id": dataset_id,
        "best_metric": best_metric,
    }


def test_evaluations_must_target_looked_up_leaderboards(tmp_path, monkeypatch):
    monkeypatch.setattr(
        curation_api, "SEEN_LEADERBOARDS", str(tmp_path / "boards.jsonl")
    )
    curation_api.remember_leaderboards([board(10, 179, "Accuracy")])
    curation_api.remember_leaderboards([board(448, 2013, "Weighted F1")])

    curation_api.check_evaluation_leaderboards({"evaluations": [evaluation(10, 179)]})
    with pytest.raises(ValueError) as exc:
        curation_api.check_evaluation_leaderboards(
            {
                "evaluations": [
                    evaluation(10, 179),
                    evaluation(10, 2013),
                    evaluation(448, 2013),
                ]
            }
        )
    message = str(exc.value)
    assert "no apply attempted" in message
    assert "evaluations[0]" not in message
    assert "task_id 10 + dataset_id 2013 is not a configured leaderboard" in message
    assert "best_metric 'Accuracy' is not configured" in message
    assert "Weighted F1" in message


def test_leaderboard_lookups_are_remembered(tmp_path, monkeypatch):
    monkeypatch.setattr(
        curation_api, "SEEN_LEADERBOARDS", str(tmp_path / "boards.jsonl")
    )
    monkeypatch.setenv("PWC_CURATION_API_URL", "https://paperswithcode.co/api/v1")
    monkeypatch.setenv("PWC_CURATION_JOB_ID", "job")
    monkeypatch.setenv("PWC_CURATION_JOB_TOKEN", "token")
    import io
    import json

    body = {"query": "CochlScene", "leaderboards": [board(10, 179, "Accuracy")]}
    monkeypatch.setattr(
        curation_api.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: io.BytesIO(json.dumps(body).encode()),
    )

    assert curation_api.request_json("leaderboards?q=CochlScene") == body
    curation_api.check_evaluation_leaderboards({"evaluations": [evaluation(10, 179)]})
