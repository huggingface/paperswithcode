import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import hub_leaderboard as hub  # noqa: E402
import open_eval_prs  # noqa: E402


def test_task_ids_reads_eval_yaml_tasks():
    yaml = 'name: "Terminal Bench 2.0"\ntasks:\n  - id: terminalbench_2\n    config: default\n  - id: "other"\n'
    assert hub.task_ids(yaml) == ["terminalbench_2", "other"]


def test_predicted_rank_ignores_own_entry_and_respects_direction():
    entries = [
        {"modelId": "a/x", "value": 50},
        {"modelId": "Org/Model", "value": 99},
        {"modelId": "b/y", "value": 30},
    ]
    assert hub.predicted_rank(entries, "org/model", 40) == 2
    lower = [{**e, "lower_is_better": True} for e in entries]
    assert hub.predicted_rank(lower, "org/model", 40) == 2
    assert hub.predicted_rank(lower, "org/model", 20) == 1


def test_link_opens_view_with_result_highlighted():
    url = hub.link(
        "TMaxxx/tmax-9b-v1.1",
        "SWE-bench/SWE-bench_Verified",
        "swe_bench_%_resolved",
        {"max_params": "32B", "base_model": "false"},
    )
    assert url == (
        "https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified?eval_result=TMaxxx/tmax-9b-v1.1"
        "&leaderboard_task_id=swe_bench_%25_resolved&leaderboard_max_params=32B"
        "&leaderboard_base_model=false"
    )


def test_render_uses_exact_names_and_origin():
    results = [
        {
            "dataset": "harborframework/terminal-bench-2.0",
            "task_id": "terminalbench_2",
            "value": 9.36,
        }
    ]
    title, body = open_eval_prs.render(
        "org/m",
        "the model card",
        results,
        {("harborframework/terminal-bench-2.0", "terminalbench_2"): {}},
    )
    assert title == "Add community evaluation results for Terminal-Bench 2.0"
    assert body.startswith("This PR adds community-provided evaluation results")
    assert (
        "- **[Terminal-Bench 2.0](https://huggingface.co/datasets/harborframework/terminal-bench-2.0?"
        in body
    )
    assert "These results were extracted from the model card." in body


def test_render_labels_each_task_of_a_repeated_benchmark():
    hub.NAMES["llamaindex/ParseBench"] = "ParseBench"
    results = [
        {"dataset": "llamaindex/ParseBench", "task_id": task, "value": 1}
        for task in ("mean", "table")
    ]
    views = {("llamaindex/ParseBench", task): {} for task in ("mean", "table")}
    title, body = open_eval_prs.render("org/m", "x", results, views)
    assert title == "Add community evaluation results for ParseBench"
    assert "- **[ParseBench (mean)](" in body and "- **[ParseBench (table)](" in body


def test_result_yaml_quotes_notes():
    r = {"dataset": "a/b", "task_id": "t", "value": 1.5, "notes": 'no tools, "direct"'}
    assert open_eval_prs.result_yaml(r, "https://x", "Model Card") == (
        "- dataset:\n    id: a/b\n    task_id: t\n  value: 1.5\n"
        '  notes: "no tools, \\"direct\\""\n  source:\n    url: https://x\n    name: Model Card\n'
    )


def test_model_card_accepts_card_variants_only():
    repo = "TMaxxx/tmax-2b-v1.1"
    for url in (
        f"https://huggingface.co/{repo}",
        f"https://huggingface.co/{repo}/",
        f"https://huggingface.co/{repo}#evaluation-results",
        f"https://huggingface.co/{repo}/tree/main",
        f"https://huggingface.co/{repo}/blob/main/README.md",
    ):
        assert open_eval_prs.model_card(url) == (repo, "main")
    assert open_eval_prs.model_card(
        f"https://huggingface.co/{repo}/tree/step-0400"
    ) == (repo, "step-0400")
    assert open_eval_prs.model_card(
        f"https://huggingface.co/{repo}/blob/abc123/README.md"
    ) == (repo, "abc123")
    for url in (
        "https://huggingface.co/datasets/TMaxxx/tmax-13k-v1.1",
        "https://huggingface.co/papers/2606.23321",
        "https://huggingface.co/org/model/blob/main/assets/report.pdf",
        "https://arxiv.org/abs/2606.23321",
    ):
        assert open_eval_prs.model_card(url) is None
