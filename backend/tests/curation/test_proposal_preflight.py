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
