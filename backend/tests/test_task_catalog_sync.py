"""End-to-end contract for synchronizing the chat task taxonomy snapshot."""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from backend.chat_sandbox_worker.live_task_catalog import fetch_live_task_catalog
from backend.chat_sandbox_worker.prompt import (
    render as render_system_prompt,
)
from backend.chat_sandbox_worker.prompt import (
    sha256 as system_prompt_sha256,
)
from backend.chat_sandbox_worker.update_worker_contract import (
    bump_version,
    set_image_id,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FRAMEWORKS = {
    "domains": [
        {
            "name": "Large Language Models",
            "categories": [
                {
                    "name": "Inference & Serving",
                    "frameworks": [
                        {"slug": "vllm", "name": "vLLM"},
                        {"slug": "llama-cpp", "name": "llama.cpp"},
                    ],
                }
            ],
        }
    ]
}
FRAMEWORK_LINE = (
    "- Large Language Models / Inference & Serving: `vllm` vLLM, `llama-cpp` llama.cpp"
)


def test_sync_command_updates_catalog_and_detects_stale_output(tmp_path: Path):
    tasks = [
        {
            "name": f"Task {index:02d}",
            "slug": f"task-{index:02d}",
            "level": 0,
            "paper_count": index,
        }
        for index in range(49)
    ]
    tasks.append(
        {
            "name": "Text Reranking",
            "slug": "text-reranking",
            "level": 2,
            "paper_count": 630,
        }
    )
    areas = {
        "results": [
            {
                "name": "General",
                "tasks": [tasks[0]],
            }
        ]
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/v1/areas/with-tasks/":
                payload = areas
            elif self.path == "/api/v1/frameworks/":
                payload = FRAMEWORKS
            elif self.path.startswith("/api/v1/tasks/"):
                payload = {
                    "count": len(tasks),
                    "next_page": None,
                    "previous_page": None,
                    "results": tasks,
                }
            else:
                self.send_error(404)
                return
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output = tmp_path / "TASK_CATALOG.md"
    command = [
        sys.executable,
        "-m",
        "backend.chat_sandbox_worker.sync_task_catalog",
        "--api-url",
        f"http://127.0.0.1:{server.server_port}/api/v1",
        "--output",
        str(output),
    ]
    try:
        updated = subprocess.run(command, check=False, capture_output=True, text=True)
        assert updated.returncode == 0, updated.stderr
        assert "`text-reranking` — Text Reranking" in output.read_text()
        assert FRAMEWORK_LINE in output.read_text()

        output.write_text("stale\n")
        stale = subprocess.run(
            [*command, "--check"], check=False, capture_output=True, text=True
        )
        assert stale.returncode == 1
        assert "is stale" in stale.stderr

        subprocess.run(command, check=True)
        current = subprocess.run(
            [*command, "--check"], check=False, capture_output=True, text=True
        )
        assert current.returncode == 0
    finally:
        server.shutdown()
        thread.join()


def test_worker_contract_update_is_bounded_to_staging_fields(tmp_path: Path):
    contract = tmp_path / "contract.py"
    contract.write_text(
        'WORKER_CONTRACT_VERSION = "96"\n'
        'MODAL_IMAGE_ID = "im-old"\n'
        'PRODUCTION_MODAL_IMAGE_ID = "im-production"\n'
    )

    assert bump_version(contract) == "97"
    set_image_id("im-new123", contract)

    updated = contract.read_text()
    assert 'WORKER_CONTRACT_VERSION = "97"' in updated
    assert 'MODAL_IMAGE_ID = "im-new123"' in updated
    assert 'PRODUCTION_MODAL_IMAGE_ID = "im-production"' in updated


def test_live_task_catalog_replaces_the_baked_snapshot(tmp_path: Path):
    pages = {
        1: {
            "count": 2,
            "next_page": 2,
            "previous_page": None,
            "results": [
                {"name": "Image Classification", "slug": "image-classification"}
            ],
        },
        2: {
            "count": 2,
            "next_page": None,
            "previous_page": 1,
            "results": [{"name": "Text Reranking", "slug": "text-reranking"}],
        },
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/v1/frameworks/":
                payload = FRAMEWORKS
            else:
                payload = pages[2 if "page=2" in self.path else 1]
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        catalog = fetch_live_task_catalog(
            f"http://127.0.0.1:{server.server_port}/api/v1"
        )
    finally:
        server.shutdown()
        thread.join()

    baked = tmp_path / "TASK_CATALOG.md"
    baked.write_text("baked catalog without the new task\n")
    prompt = render_system_prompt(catalog_path=baked, task_catalog_text=catalog)

    assert "baked catalog without the new task" not in prompt
    assert "`text-reranking` — Text Reranking" in prompt
    assert FRAMEWORK_LINE in prompt
    assert prompt.count("PWC_TASK_CATALOG_START") == 1
    assert prompt.count("PWC_TASK_CATALOG_END") == 1


def test_system_prompt_requires_task_scoped_benchmark_lookup():
    prompt = render_system_prompt()

    assert "pwc task --name TASK" in prompt
    assert "pwc benchmark list --task TASK" in prompt
    assert "Do not start with `pwc search`" in prompt


def test_prompt_contract_hash_parameterizes_the_live_catalog(tmp_path: Path):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("first task catalog\n")
    second.write_text("second task catalog\n")

    assert system_prompt_sha256(catalog_path=first) == system_prompt_sha256(
        catalog_path=second
    )


def test_task_catalog_sync_workflow_refreshes_the_fallback_without_image_churn():
    workflow = (
        REPOSITORY_ROOT / ".github/workflows/sync-chat-task-catalog.yml"
    ).read_text()

    assert 'cron: "*/15 * * * *"' in workflow
    assert "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: write" in workflow
    assert "uv run --no-project --python 3.12 --env-file backend/keys.env" in workflow
    assert "python -m backend.chat_sandbox_worker.sync_task_catalog" in workflow
    assert 'git add "$DESTINATION"' in workflow
    assert "git push origin HEAD:main" in workflow
    assert "publish_image.py" not in workflow
    assert "pwc-deploy" not in workflow
