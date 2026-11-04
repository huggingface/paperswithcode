"""Strict AA-to-Hub matching and `.eval_results` output for the AA PR job."""

from __future__ import annotations

import yaml

from backend.scripts import sync_aa_eval_results_prs as sync


def test_base_model_name_drops_variant_annotations():
    assert sync.base_model_name("GLM-5.3 (Max)") == "GLM-5.3"
    assert (
        sync.base_model_name("Sarvam M (Reasoning, Based on Mistral Small 3.1)")
        == "Sarvam M"
    )


def test_repo_matches_allows_size_dtype_and_instruct_tails():
    assert sync.repo_matches("Qwen3.8 27B (Xhigh)", "Qwen/Qwen3.8-27B", "Qwen")
    assert sync.repo_matches(
        "Mistral Large 4 (High)", "mistralai/Mistral-Large-4-1T-A52B", "mistralai"
    )
    assert sync.repo_matches("Beam 1.0", "reflection/Beam-1.0-501B-A23B", "reflection")
    assert sync.repo_matches(
        "Nemotron 3.5 Super VL",
        "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16",
        "nvidia",
    )
    assert sync.repo_matches("Kimi K2", "moonshotai/Kimi-K2-Instruct", "moonshotai")


def test_repo_matches_rejects_quantized_base_and_sibling_repos():
    assert not sync.repo_matches("Qwen3.8 27B", "Qwen/Qwen3.8-27B-FP8", "Qwen")
    assert not sync.repo_matches("Kimi K2", "moonshotai/Kimi-K2-Base", "moonshotai")
    assert not sync.repo_matches(
        "MiniMax-M3", "MiniMaxAI/MiniMax-M3.1-Flash", "MiniMaxAI"
    )
    assert not sync.repo_matches(
        "MiMo-V2.6-Pro", "XiaomiMiMo/MiMo-V2.6-Pro-RL", "XiaomiMiMo"
    )
    assert not sync.repo_matches("GLM-5.3", "zai-org/GLM-5.3-Flash", "zai-org")


def test_repo_matches_requires_a_name_boundary_before_the_tail():
    assert not sync.repo_matches(
        "Mistral Large", "mistralai/Mistral-Large-4-1T-A52B", "mistralai"
    )
    assert not sync.repo_matches(
        "Mistral Medium 3", "mistralai/Mistral-Medium-3.5-128B", "mistralai"
    )
    assert sync.repo_matches(
        "Llama 3.1 Tulu3 405B", "allenai/Llama-3.1-Tulu-3-405B", "allenai"
    )


def test_repo_matches_rejects_dated_variants():
    assert not sync.repo_matches(
        "DeepSeek-V2.5 (Dec '24)", "deepseek-ai/DeepSeek-V2.5", "deepseek-ai"
    )
    assert not sync.repo_matches(
        "Mistral Large (Feb '24)", "mistralai/Mistral-Large-Instruct-2407", "mistralai"
    )


class _Model:
    def __init__(self, repo_id):
        self.id = repo_id


class _Api:
    def __init__(self, repos):
        self.repos = repos

    def list_models(self, author):
        return [_Model(r) for r in self.repos if r.startswith(f"{author}/")]


def _aa_model(name, creator, gpqa=0.5):
    return {
        "name": name,
        "model_creator": {"slug": creator},
        "evaluations": {"gpqa": gpqa},
    }


def test_reasoning_variants_skip_instruct_repos_and_ambiguous_base_repos():
    api = _Api(
        [
            "Qwen/Qwen3-VL-8B-Instruct",
            "Qwen/Qwen3-8B",
            "google/gemma-4-31B",
            "google/gemma-4-31B-it",
            "ibm-granite/granite-3.3-8b-instruct",
        ]
    )
    candidates, skipped = sync.match_candidates(
        api,
        [
            _aa_model("Qwen3 VL 8B (Reasoning)", "alibaba"),
            _aa_model("Qwen3 8B (Reasoning)", "alibaba"),
            _aa_model("Gemma 4 31B (Reasoning)", "google"),
            _aa_model("Granite 3.3 8B (Non-reasoning)", "ibm"),
        ],
    )
    assert set(candidates) == {"Qwen/Qwen3-8B", "ibm-granite/granite-3.3-8b-instruct"}
    assert len(skipped) == 2


def test_candidate_keeps_best_variant_per_benchmark():
    benchmark = sync.BENCHMARKS[0]
    candidate = sync.Candidate("org/model")
    candidate.offer(benchmark, 80.0, "Model (Low)")
    candidate.offer(benchmark, 85.5, "Model (Max)")
    candidate.offer(benchmark, 84.0, "Model (High)")
    assert candidate.scores[benchmark.aa_key] == (85.5, "Model (Max)")


def test_score_percent_skips_missing_and_zero_scores():
    benchmark = sync.BENCHMARKS[0]
    assert sync.score_percent({"evaluations": {"gpqa": 0.917}}, benchmark) == 91.7
    assert sync.score_percent({"evaluations": {"gpqa": 0.0}}, benchmark) is None
    assert sync.score_percent({"evaluations": {}}, benchmark) is None


def test_eval_results_yaml_matches_hub_format():
    benchmark = next(b for b in sync.BENCHMARKS if b.aa_key == "terminalbench_v4_0")
    entries = yaml.safe_load(sync.eval_results_yaml(benchmark, 41.9, "GLM-5.3 (Max)"))
    assert entries == [
        {
            "dataset": {
                "id": "harborframework/terminal-bench",
                "task_id": "terminalbench_4",
            },
            "value": 41.9,
            "source": {
                "url": "https://artificialanalysis.ai/evaluations/terminalbench-4-0",
                "name": "Artificial Analysis Terminal-Bench 4.0 leaderboard",
                "user": "ArtificialAnalysis",
            },
            "notes": "GLM-5.3 (Max); mini-swe-agent harness, pass@1 averaged over three repeats.",
        }
    ]


def test_file_path_avoids_existing_eval_results_files():
    benchmark = next(b for b in sync.BENCHMARKS if b.aa_key == "terminalbench_v2_1")
    assert sync.file_path(benchmark, set()) == ".eval_results/terminal-bench-2.1.yaml"
    assert (
        sync.file_path(benchmark, {".eval_results/terminal-bench-2.1.yaml"})
        == ".eval_results/terminal-bench-2.1-artificial-analysis.yaml"
    )
