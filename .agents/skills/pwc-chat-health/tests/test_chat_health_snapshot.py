from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts/chat_health_snapshot.py"
SPEC = spec_from_file_location("chat_health_snapshot", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
chat_health_snapshot = module_from_spec(SPEC)
SPEC.loader.exec_module(chat_health_snapshot)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Execution limit reached. Do not call more tools. Answer now.",
            ("execution_limit", None),
        ),
        (
            "PwC MCP tool error: not_found: Method not found: 3D CNN; papers matching it",
            ("not_found:method", "3D CNN"),
        ),
        (
            "PwC MCP tool error: not_found: Task not found: ship detection. Correct the arguments",
            ("not_found:task", "ship detection"),
        ),
        (
            "PwC MCP tool error: not_found: Paper URL not supported: https://doi.org/10.1/x. Correct",
            ("not_found:paper_url", "https://doi.org/10.1/x"),
        ),
        (
            "PwC MCP tool error: Author 'Jane Doe' not found. Correct the arguments",
            ("not_found:author", None),
        ),
        (
            "PwC MCP tool error: not_found: the requested catalog record does not exist.",
            ("not_found:other", None),
        ),
        (
            "PwC MCP tool error: no_markdown: no stored Markdown is available for this paper.",
            ("no_markdown", None),
        ),
        (
            "This paper has no next page. Omit cursor to read from the beginning.",
            ("cursor_misuse", None),
        ),
        ("PwC MCP request failed (502).", ("upstream", None)),
        ("Something unexpected", ("other", None)),
    ],
)
def test_classify_tool_error(message, expected):
    assert chat_health_snapshot.classify_tool_error(message) == expected
