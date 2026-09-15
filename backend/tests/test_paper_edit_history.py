"""Public history must never expose relationship provenance."""

import pytest

from backend.services.paper_edit_history import public_snapshot


@pytest.mark.parametrize(
    "entity,key,value",
    [
        (
            "paper_tasks",
            "task_id",
            [{"task_id": 1, "source": "internal", "added_by_hf_subject": "private"}],
        ),
        (
            "paper_methods",
            "method_id",
            {
                "links": [{"method_id": 1, "added_by_hf_subject": "private"}],
                "evidence": ["private"],
            },
        ),
        (
            "paper_organizations",
            "organization_id",
            [{"organization_id": 1, "added_by_hf_subject": "private"}],
        ),
    ],
)
def test_relationships_expose_only_public_ids(entity, key, value):
    snapshot = {"value": value}
    expected = [{key: 1}]
    assert public_snapshot(entity, snapshot) == expected
    batch = {"sections": {entity.removeprefix("paper_"): snapshot}, "evaluations": []}
    assert (
        public_snapshot("paper_edit_batch", batch)["sections"][
            entity.removeprefix("paper_")
        ]
        == expected
    )


@pytest.mark.parametrize("snapshot", [{}, {"value": None}, {"value": {}}])
def test_empty_artifact_history(snapshot):
    assert public_snapshot("paper_hf_artifacts", snapshot) == {
        "hf_models": [],
        "hf_datasets": [],
        "hf_spaces": [],
    }


def test_artifact_history_keeps_urls_and_scrubs_scan_metadata():
    assert public_snapshot(
        "paper_hf_artifacts",
        {
            "value": {
                "hf_models": ["https://huggingface.co/org/model"],
                "hf_artifacts_scanned_at": "private",
                "links": [{"artifact_id": 123}],
            }
        },
    ) == {
        "hf_models": ["https://huggingface.co/org/model"],
        "hf_datasets": [],
        "hf_spaces": [],
    }
