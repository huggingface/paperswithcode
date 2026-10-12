"""Deterministic coverage for the human annotation and scoring workflow."""

from __future__ import annotations

import json
from pathlib import Path

from backend.scripts.related_papers_annotation import AnnotationServer
from backend.scripts.score_related_papers_annotations import source_metrics
from backend.services.embedding_annotation import (
    build_assignment,
    export_annotations,
    merge_exports,
    validate_adjudicated,
    validate_package,
    write_jsonl,
)


def annotation_row(blind_id: str, source: int, candidate: int) -> dict:
    return {
        "blind_id": blind_id,
        "source_paper_id": source,
        "source_title": f"Source {source}",
        "source_abstract": "Source abstract",
        "candidate_paper_id": candidate,
        "candidate_title": f"Candidate {candidate}",
        "candidate_abstract": "Candidate abstract",
        "source_stratum": "document_length_q1",
        "display_order": candidate,
        "grade": None,
        "notes": None,
    }


def test_80m_bakeoff_contract_is_native_320_dimensions():
    config = json.loads(Path("backend/config/embedding_bakeoff.json").read_text())
    candidate = next(
        row for row in config["candidates"] if row["model"].endswith("80M")
    )
    assert candidate["dimensions"] == [320]


def test_assignment_is_blinded_reproducible_and_contains_qc():
    rows = [annotation_row(f"blind-{number}", 1, number + 2) for number in range(30)]
    first = build_assignment(rows, "ann-1", 0, 2)
    second = build_assignment(rows, "ann-1", 0, 2)
    assert [row["item_id"] for row in first] == [row["item_id"] for row in second]
    assert {row["item_type"] for row in first} == {"real", "duplicate", "trap"}
    assert all("systems" not in row for row in first)


def test_persist_export_merge_and_validate_round_trip(tmp_path: Path):
    rows = [
        annotation_row(f"blind-{number}", number, number + 100) for number in range(8)
    ]
    exports = []
    for index, annotator in enumerate(("ann-a", "ann-b")):
        assignment = build_assignment(rows, annotator, index, 2, overlap=1.0)
        state_path = tmp_path / f"{annotator}.json"
        server = AnnotationServer(
            ("127.0.0.1", 0), "annotate", assignment, state_path, annotator
        )
        base_grades = {row["blind_id"]: row["candidate_paper_id"] % 3 for row in rows}
        for item in assignment:
            grade = (
                0 if item["item_type"] == "trap" else base_grades[item["base_blind_id"]]
            )
            server.save(
                {
                    "item_id": item["item_id"],
                    "status": "graded",
                    "grade": grade,
                    "notes": None,
                }
            )
        server.server_close()
        state = json.loads(state_path.read_text())
        export = tmp_path / f"{annotator}.jsonl"
        export_annotations(assignment, state, export)
        exports.append(export)
    merged = tmp_path / "merged.jsonl"
    summary = merge_exports(exports, merged)
    assert summary["pairs"] == len(rows)
    assert summary["disagreements"] == 0
    assert validate_adjudicated(merged)["judged"] == len(rows)


def test_package_validation_and_scoring_coverage(tmp_path: Path):
    package = tmp_path / "package"
    package.mkdir()
    rows = [annotation_row("a", 1, 2), annotation_row("b", 1, 3)]
    write_jsonl(package / "annotations.jsonl", rows)
    write_jsonl(
        package / "provenance.jsonl",
        [
            {"blind_id": "a", "systems": [{"system": "dense", "rank": 1}]},
            {"blind_id": "b", "systems": [{"system": "dense", "rank": 2}]},
        ],
    )
    write_jsonl(
        package / "sources.jsonl",
        [{"source_paper_id": 1, "stratum": "document_length_q1"}],
    )
    (package / "package_manifest.json").write_text(
        json.dumps(
            {"pair_count": 2, "source_count": 1, "systems": [{"label": "dense"}]}
        )
    )
    assert validate_package(package)["pair_count"] == 2
    incomplete = source_metrics([2, 3, 4, 5], {2: 2, 3: 1})
    assert incomplete["ndcg_at_4"] is None
    assert incomplete["top4_coverage"] == 0.5
    complete = source_metrics([2, 3, 4, 5], {2: 2, 3: 1, 4: 0, 5: 0})
    assert complete["ndcg_at_4"] == 1.0
