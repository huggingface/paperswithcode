"""System prompts, round contracts, and bounded task/method catalogs."""

from __future__ import annotations

from datetime import date
from pathlib import Path


from backend.chat_sandbox_worker import (
    agent,
)
from backend.chat_sandbox_worker.contract import (
    BASE_IMAGE,
    CHAT_SANDBOX_REGION,
    CONTROL_PORT,
    IMAGE_PUBLISH_NAME,
    MODAL_APP_NAME,
    MODAL_IMAGE_ID,
    PRODUCTION_MODAL_IMAGE_ID,
    PWC_CLI_VERSION,
    WORKER_CONTRACT_VERSION,
)
from backend.chat_sandbox_worker.prompt import render, sha256
from backend.chat_sandbox_worker.render_method_catalog import (
    render as render_method_catalog,
)
from backend.chat_sandbox_worker.render_task_catalog import (
    render as render_task_catalog,
)
from deploy.release import build_manifest


def test_system_prompt_prevents_unsupported_method_search_flags():
    prompt = render(web_search_enabled=True, hf_username="nielsrogge")

    assert "When comparing papers, prefer a Markdown table." in prompt
    assert (
        "Always favor native paper hyperlinks instead of arXiv links, unless the user "
        "explicitly asks for an arXiv link." in prompt
    )
    method_list = prompt.split("`pwc method list", 1)[1].split("\n", 1)[0]
    assert "[--page-size PAGE_SIZE] [--search SEARCH]" in method_list
    assert "--limit" not in method_list
    assert "Never pipe `pwc paper info` or `pwc paper lineage list`" in prompt
    assert "Paper lineage follows the abstract" in prompt
    assert "Use complete output, or use `--json`" in prompt
    assert "start with `pwc` whether the family is open or closed" in prompt
    assert "Use `hf` first only when" in prompt
    assert "community-only result from one source is not enough evidence" in prompt
    assert "continue with another applicable catalog" in prompt
    assert "If a colloquial task name does not resolve exactly" in prompt
    assert "pwc task list --page-size 100 --flat" in prompt
    assert "retry with the canonical task slug" in prompt
    assert "names an unversioned model family" in prompt
    assert "official external release pages as\nfirst-class model evidence" in prompt
    assert (
        "pwc paper list --organization NAME --order-by date_published --order-dir\n"
        "desc" in prompt
    )
    assert "latest release versus latest technical report" in prompt
    assert "relevance-ranked `pwc search` can surface older papers first" in prompt
    assert "`--order-by date_published --order-dir desc`, or a `--start-date`" in prompt
    assert "report each cited paper's\npublication date" in prompt
    assert "For long-form writing in the chat answer" in prompt
    assert "Write one part per turn, at most about 1,500 words" in prompt
    assert "offer to continue\nwith the next section" in prompt
    assert '"reader_mode":false' in prompt


def test_system_prompt_leads_with_code_and_grounds_implementation_claims():
    prompt = render(web_search_enabled=True, hf_username="nielsrogge")

    assert "lead the answer with the official repository" in prompt
    assert "When code_repository_count is 0" in prompt
    assert (
        "use search_web to look for an official or community implementation" in prompt
    )
    assert "Never rank or rate implementation difficulty" in prompt


def test_reader_system_prompt_profile_is_selected_by_trusted_metadata():
    prompt = render(reader_mode=True)

    assert "## Paper reader mode (reader-v1)" in prompt
    assert "authoritative primary paper" in prompt
    assert "never present its page number as a verified page citation" in prompt
    assert '"reader_mode":true' in prompt
    assert "[repo_id](https://huggingface.co/datasets/<repo_id>)" in prompt


def test_prompt_and_manifest_share_six_round_contract():
    prompt = render(
        current_date=date(2026, 7, 28),
        selected_model="deepseek-ai/DeepSeek-V4-Flash-0731:baseten",
        web_search_enabled=True,
        hf_username="nielsrogge",
    )
    assert '"current_date_utc":"2026-07-28"' in prompt
    assert "at most 6 executed tool-use rounds" in prompt
    assert "hard failure ceilings, not retrieval targets" in prompt
    assert "within 2 rounds and 2 searches" in prompt
    assert "aim to stay within\n400 words" in prompt
    assert "title-based `pwc paper info` lookup can consume a search" in prompt
    assert "If any tool reports a 429" in prompt
    assert "Every Bash command runs with `set -eo pipefail`" in prompt
    assert "global leaderboard as evidence" in prompt
    assert "`rg`'s no-match status" in prompt
    assert "do not place multiple search executions" in prompt
    assert "secure, disposable sandbox" in prompt
    assert "Every Bash command already starts in /workspace" in prompt
    assert "never prefix a command with `cd /workspace`" in prompt
    assert "anonymous, read-only `pwc` CLI" in prompt
    assert "`s2` Semantic Scholar CLI" in prompt
    assert "`s2 citations" in prompt
    assert "use `s2 search` as the broader Semantic Scholar fallback" in prompt
    assert "already installed" in prompt
    assert "deepseek-ai/DeepSeek-V4-Flash-0731:baseten" in prompt
    assert "harness is orchestration, not the model" in prompt
    assert "never identify yourself as Pi or Claude" in prompt
    assert "direct network clients" in prompt
    assert "`command -v <name>` succeeds" in prompt
    visual_instruction = (
        "When `read_me` and `create_view` are available, use them any time the "
        "user asks\nfor a visual explanation or visualization."
    )
    assert visual_instruction in prompt
    assert "use Read only in\n`/workspace`" in prompt
    assert "already included\nverbatim later in this system prompt" in prompt
    assert "Never read, `cat`,\nor otherwise open `/opt/pwc/PWC_CLI_SKILL.md`" in prompt
    assert "HF access is anonymous-only" in prompt
    assert "fix the JSON and call `create_view` once more" in prompt
    assert prompt.index("## Tool usage") < prompt.index(visual_instruction)
    assert "[owner/repo](https://github.com/owner/repo)" in prompt
    assert "Never output a bare repository slug" in prompt
    assert "## Available research areas and representative tasks" in prompt
    assert "## Representative methods in the catalog" in prompt
    assert "`world-action-models` — World Action Models (WAMs)" in prompt
    assert "`on-policy-distillation` — On-Policy Distillation (OPD)" in prompt
    assert "`decision-model` — Decision Model" in prompt
    assert "what a named method is or how it works, look it up" in prompt
    assert "as an existing PwC method" in prompt
    assert "### Audio" in prompt
    assert "### Vision" in prompt
    assert prompt.index("## Available research areas") < prompt.index(
        "## Representative methods"
    )
    assert prompt.index("## Representative methods") < prompt.index("# pwc CLI skill")
    assert "# pwc CLI skill" in prompt
    assert "name: pwc-cli" in prompt
    assert prompt.index("# pwc CLI skill") < prompt.index("# Turn metadata")
    assert '"harness":"PwC research agent"' in prompt
    assert '"agent_harness":"claude"' in prompt
    assert '"sandbox":"secure disposable sandbox with writable /workspace"' in prompt
    assert '"web_search_enabled":true' in prompt
    assert '"hf_username":"nielsrogge"' in prompt
    assert prompt.rstrip().endswith("</turn_metadata>")
    manifest = build_manifest("a" * 40, "staging")
    assert manifest["chat_runtime"]["system_prompt_sha256"] == sha256()
    assert manifest["chat_runtime"]["new_chat_modal_percentage"] == 100
    production = build_manifest("b" * 40, "production")
    assert production["chat_runtime"]["enabled"] is False
    assert production["chat_runtime"]["new_chat_modal_percentage"] == 0
    assert production["chat_runtime"]["default_backend"] == "modal_cli"
    assert (
        production["chat_runtime"]["worker_contract_version"] == WORKER_CONTRACT_VERSION
    )
    assert IMAGE_PUBLISH_NAME == "pwc-chat-v1"
    assert MODAL_APP_NAME == "pwc-chat-sandbox-v1"
    assert BASE_IMAGE.startswith("python:3.12-slim-bookworm@sha256:")
    assert MODAL_IMAGE_ID.startswith("im-")
    assert PRODUCTION_MODAL_IMAGE_ID == "im-LqrG84SxmXoOrwZUsWQdUY"
    assert int(WORKER_CONTRACT_VERSION) >= 97
    assert CHAT_SANDBOX_REGION == "eu-west"
    assert CONTROL_PORT == 8080


def test_pi_prompt_embeds_cli_skills_without_requiring_a_read_tool_call():
    prompt = render(agent_harness="pi")

    assert "pwc task --name TASK" in prompt
    assert "pwc benchmark list --task TASK" in prompt
    assert "/opt/pwc/PWC_CLI_SKILL.md" in prompt
    assert "/opt/pwc/HF_CLI_SKILL.md" in prompt
    assert "/opt/pwc/S2_CLI_SKILL.md" in prompt
    assert "# pwc CLI skill" in prompt
    assert "name: pwc-cli" in prompt
    assert "# s2 CLI skill" in prompt
    assert "# restricted hf CLI skill" in prompt


def test_task_catalog_is_bounded_and_ranked():
    payload = {
        "results": [
            {
                "name": "Vision",
                "tasks": [
                    {
                        "name": "Popular",
                        "slug": "popular",
                        "paper_count": 999,
                    },
                    {
                        "name": "Video Understanding",
                        "slug": "video-understanding",
                        "paper_count": 40,
                    },
                    {"name": "Detection", "slug": "detection", "paper_count": 20},
                    {
                        "name": "Classification",
                        "slug": "classification",
                        "paper_count": 30,
                    },
                    {"name": "Segmentation", "slug": "segmentation", "paper_count": 10},
                ],
            },
            {
                "name": "Audio",
                "tasks": [
                    {"name": "Speech", "slug": "speech", "paper_count": 5},
                ],
            },
        ],
        "all_tasks": [
            {
                "name": "Text Reranking",
                "slug": "text-reranking",
                "level": 2,
                "paper_count": 630,
            }
        ],
    }

    catalog = render_task_catalog(payload, maximum_tasks_per_area=3)

    assert catalog.index("### Audio") < catalog.index("### Vision")
    assert catalog.index("`popular`") < catalog.index("`classification`")
    assert (
        "video understanding includes subtasks like video question answering" in catalog
    )
    assert "`detection`" not in catalog
    assert "`segmentation`" not in catalog
    assert "## Complete task lookup index" in catalog
    assert "`text-reranking` — Text Reranking" in catalog


def test_method_catalog_is_bounded_ranked_and_retains_featured_methods():
    payload = {
        "results": [
            {
                "name": "General",
                "methods": [
                    {
                        "name": "Transformer",
                        "full_name": "Transformer",
                        "slug": "transformer",
                        "paper_count": 100,
                    },
                    {
                        "name": "Dropout",
                        "full_name": "Dropout",
                        "slug": "dropout",
                        "paper_count": 90,
                    },
                    {
                        "name": "World Action Models",
                        "full_name": "World Action Models (WAMs)",
                        "slug": "world-action-models",
                        "paper_count": 5,
                    },
                ],
            },
            {
                "name": "Vision",
                "methods": [
                    {
                        "name": "Vision Transformer",
                        "full_name": "Vision Transformer",
                        "slug": "vision-transformer",
                        "paper_count": 50,
                    }
                ],
            },
        ]
    }

    catalog = render_method_catalog(payload, maximum_methods_per_area=2)

    assert catalog.index("### General") < catalog.index("### Vision")
    assert "`transformer`" in catalog
    assert "`world-action-models`" in catalog
    assert "World Action Models (WAMs)" in catalog
    assert "`dropout`" not in catalog


def test_chat_worker_exposes_parameter_filtered_benchmarks():
    skill = Path(agent.__file__).with_name("PWC_CLI_SKILL.md").read_text()
    image_source = (
        Path(__file__).resolve().parents[2] / "chat_sandbox_worker" / "image.py"
    ).read_text()

    assert PWC_CLI_VERSION == "0.3.0"
    assert "--author AUTHOR" in skill
    assert "--max-parameters SIZE" in skill
    prose = " ".join(skill.split())
    assert "at or below an inclusive parameter" in prose
    assert "when model size is part of the request" in prose
    assert "pwc benchmark --help | grep -F -- '--max-parameters'" in image_source
    assert "pwc paper list --help" in image_source
