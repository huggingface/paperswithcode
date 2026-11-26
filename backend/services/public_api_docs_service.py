"""Readable public API documentation for clients that do not run JavaScript."""

import re
from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode

from backend.services.discovery_text_service import markdown_inline_html
from backend.services.spa_shell_service import (
    inject_root_document,
    replace_document_head,
)

GUIDE_PATH = Path(__file__).resolve().parent.parent / "docs" / "public_api_guide.md"
ORIGIN = "https://paperswithcode.co"
TITLE = "Papers with Code API documentation"
DESCRIPTION = (
    "Free, anonymous, read-only API for AI research papers, tasks, benchmarks, "
    "and leaderboard results."
)
_ORDERED_ITEM = re.compile(r"\d+\. ")


@lru_cache(maxsize=1)
def _guide() -> str:
    return GUIDE_PATH.read_text(encoding="utf-8").strip()


def _example_url(path: str, examples: dict) -> str:
    query = {}
    for name, value in examples.items():
        if f"{{{name}}}" in path:
            path = path.replace(f"{{{name}}}", quote(str(value), safe=""))
        else:
            query[name] = str(value).lower() if isinstance(value, bool) else value
    return f"{ORIGIN}{path}" + (f"?{urlencode(query)}" if query else "")


def _parameter_type(schema: dict) -> str:
    if "enum" in schema:
        return " | ".join(str(value) for value in schema["enum"])
    if "anyOf" in schema:
        return " | ".join(
            _parameter_type(option)
            for option in schema["anyOf"]
            if option.get("type") != "null"
        )
    return schema.get("type", "string")


def _endpoint_markdown(path: str, operation: dict) -> str:
    lines = [f"### {operation.get('summary', path)}", "", f"`GET {path}`", ""]
    description = operation.get("description", "").strip()
    if description:
        lines += [description, ""]
    parameters = operation.get("parameters", [])
    if parameters:
        lines += ["Parameters:", ""]
        for parameter in parameters:
            schema = parameter.get("schema", {})
            required = "required" if parameter.get("required") else "optional"
            default = f", default `{schema['default']}`" if "default" in schema else ""
            text = parameter.get("description") or schema.get("description") or ""
            lines.append(
                f"- `{parameter['name']}` ({parameter['in']}, {required}, "
                f"`{_parameter_type(schema)}`{default}): {text}".rstrip(": ")
            )
        lines.append("")
    lines += [
        "Example:",
        "",
        "```",
        f'curl --fail-with-body "{_example_url(path, operation["x-example-parameters"])}"',
        "```",
        "",
    ]
    return "\n".join(lines)


def public_api_markdown(schema: dict) -> str:
    endpoints = "\n".join(
        _endpoint_markdown(path, item["get"]) for path, item in schema["paths"].items()
    )
    return f"{_guide()}\n\n## Endpoints\n\n{endpoints}".rstrip() + "\n"


def markdown_to_html(markdown: str) -> str:
    html: list[str] = []
    paragraph: list[str] = []
    list_tag: str | None = None
    code: list[str] | None = None

    def close_paragraph():
        if paragraph:
            html.append(f"<p>{markdown_inline_html(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list():
        nonlocal list_tag
        if list_tag:
            html.append(f"</{list_tag}>")
            list_tag = None

    for line in markdown.splitlines():
        if code is not None:
            if line.startswith("```"):
                html.append(f"<pre><code>{escape(chr(10).join(code))}</code></pre>")
                code = None
            else:
                code.append(line)
            continue
        stripped = line.strip()
        if stripped.startswith("```"):
            close_paragraph()
            close_list()
            code = []
        elif not stripped:
            close_paragraph()
            if not line.startswith("  "):
                close_list()
        elif match := re.match(r"(#{1,3}) (.+)", stripped):
            close_paragraph()
            close_list()
            level = len(match[1])
            html.append(f"<h{level}>{markdown_inline_html(match[2])}</h{level}>")
        elif stripped.startswith("- ") or _ORDERED_ITEM.match(stripped):
            close_paragraph()
            tag = "ul" if stripped.startswith("- ") else "ol"
            if list_tag != tag:
                close_list()
                html.append(f"<{tag}>")
                list_tag = tag
            item = stripped[2:] if tag == "ul" else _ORDERED_ITEM.sub("", stripped, 1)
            html.append(f"<li>{markdown_inline_html(item)}</li>")
        elif list_tag and line.startswith("  "):
            last = html.pop()
            html.append(
                last.removesuffix("</li>")
                + " "
                + markdown_inline_html(stripped)
                + "</li>"
            )
        else:
            close_list()
            paragraph.append(stripped)
    close_paragraph()
    close_list()
    return "".join(html)


def public_api_shell(shell: str, schema: dict) -> str:
    head = (
        f"<title>{escape(TITLE)}</title>"
        f'<meta name="description" content="{escape(DESCRIPTION, quote=True)}">'
        f'<link rel="canonical" href="{ORIGIN}/docs/api">'
        f'<link rel="alternate" type="text/markdown" href="{ORIGIN}/docs/api.md">'
    )
    document = (
        '<main hidden data-pwc-initial-document="api-docs">'
        f"{markdown_to_html(public_api_markdown(schema))}</main>"
    )
    return inject_root_document(replace_document_head(shell, head), document)
