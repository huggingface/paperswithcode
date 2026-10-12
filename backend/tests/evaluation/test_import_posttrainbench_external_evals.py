import json

from backend.database.evaluations_setup.import_posttrainbench_external_evals import (
    AGENT_SPECS,
    SCORES_ASSIGNMENT,
    LeaderboardEntry,
    _best_entry_per_paper,
    parse_scores_payload,
)


def test_parse_scores_payload_extracts_javascript_assignment():
    payload = {"benchmarkWeights": {"example": 1.0}}

    assert (
        parse_scores_payload(
            f"// Generated file.\n{SCORES_ASSIGNMENT}{json.dumps(payload)};\n"
        )
        == payload
    )


def test_best_entry_per_paper_keeps_best_opus_48_variant():
    entries = [
        LeaderboardEntry("opus-4.8", 33.84, 3.58, 2),
        LeaderboardEntry("opus-4.8-max", 32.90, 5.75, 2),
    ]

    kept, skipped = _best_entry_per_paper(entries)

    assert [entry.agent_key for entry in kept] == ["opus-4.8"]
    assert skipped == [
        "Claude Opus 4.8 (Max): lower score (32.9%) than "
        "Claude Opus 4.8 (High) (33.84%)"
    ]


def test_current_agent_specs_resolve_to_one_row_per_release():
    assert len(AGENT_SPECS) == 12
    assert len({spec["paper_id"] for spec in AGENT_SPECS.values()}) == 11
