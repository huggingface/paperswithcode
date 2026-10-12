from unittest.mock import Mock

import pytest

from backend.database.evaluations_setup.paper_eval_import import (
    resolve_scope,
    upsert_evaluation,
    validate_leaderboard,
)


def _scalar_result(value):
    result = Mock()
    result.scalar_one_or_none.return_value = value
    return result


def _mapping_result(value):
    result = Mock()
    result.mappings.return_value.one_or_none.return_value = value
    return result


def test_resolve_scope_requires_every_configured_dataset():
    papers = Mock()
    papers.scalars.return_value.all.return_value = [7]
    datasets = Mock()
    datasets.mappings.return_value = [{"id": 11, "slug": "first"}]
    db = Mock()
    db.execute.side_effect = [papers, _scalar_result(3), datasets]

    with pytest.raises(RuntimeError, match="second"):
        resolve_scope(
            db,
            arxiv_id="2401.00001",
            task_slug="novel-view-synthesis",
            dataset_slugs=["first", "second"],
        )


def test_validate_leaderboard_rejects_unconfigured_metrics():
    db = Mock()
    db.execute.return_value = _mapping_result(
        {"supports_harness": False, "metrics": ["PSNR"]}
    )

    with pytest.raises(RuntimeError, match="Invalid metrics"):
        validate_leaderboard(
            db,
            task_id=1,
            dataset_id=2,
            dataset_slug="benchmark",
            metrics={"PSNR", "SSIM"},
            best_metric="PSNR",
        )


def test_upsert_evaluation_updates_once_and_recalculates_each_metric():
    existing = {
        "id": 9,
        "metrics": {"PSNR": "1"},
        "methodology": "old",
        "is_open": True,
        "source_url": "https://old.example",
        "external_source_url": "https://old.example",
        "num_parameters": None,
        "hf_model_url": None,
    }
    db = Mock()
    db.execute.side_effect = [_mapping_result(existing), Mock()]
    service = Mock()

    status, evaluation_id = upsert_evaluation(
        db,
        service,
        paper_id=1,
        task_id=2,
        dataset_id=3,
        model_name="Model",
        metrics={"PSNR": "30", "SSIM": "0.9"},
        methodology="paper-native",
        best_metric="PSNR",
        source_url="https://arxiv.org/abs/2401.00001",
    )

    assert (status, evaluation_id) == ("updated", 9)
    db.commit.assert_called_once_with()
    assert service.recalculate_ranks.call_count == 2
