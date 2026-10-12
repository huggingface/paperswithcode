from backend.utils.benchmark_hf_url import (
    hf_dataset_repo_to_url,
    pick_hf_dataset_url,
)


def test_single_hf_dataset_is_selected():
    url = pick_hf_dataset_url(
        dataset_name="Claw-Eval",
        dataset_slug="claw-eval",
        hf_dataset_repo_ids=["claw-eval/Claw-Eval"],
    )
    assert url == "https://huggingface.co/datasets/claw-eval/Claw-Eval"


def test_multiple_datasets_match_by_slug():
    url = pick_hf_dataset_url(
        dataset_name="MTEB",
        dataset_slug="mteb",
        hf_dataset_repo_ids=[
            "embeddings-benchmark/mteb",
            "someone/other-benchmark",
        ],
    )
    assert url == "https://huggingface.co/datasets/embeddings-benchmark/mteb"


def test_multiple_datasets_without_match_are_ambiguous():
    url = pick_hf_dataset_url(
        dataset_name="My Benchmark",
        dataset_slug="my-benchmark",
        hf_dataset_repo_ids=[
            "org-alpha/dataset-a",
            "org-beta/dataset-b",
        ],
    )
    assert url is None


def test_hf_dataset_repo_to_url_normalizes():
    assert (
        hf_dataset_repo_to_url("claw-eval/Claw-Eval")
        == "https://huggingface.co/datasets/claw-eval/Claw-Eval"
    )
