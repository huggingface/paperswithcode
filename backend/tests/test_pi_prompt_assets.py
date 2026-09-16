from pathlib import Path

from backend.chat_sandbox_worker import render_pi_prompt_asset


def test_prompt_publication_includes_pinned_mcp_skill(tmp_path, monkeypatch):
    output = tmp_path / "pi-system-prompt.txt"
    monkeypatch.setattr("sys.argv", ["render_pi_prompt_asset", str(output)])
    monkeypatch.setattr(render_pi_prompt_asset, "render", lambda **_kwargs: "prompt")
    render_pi_prompt_asset.main()
    assert output.read_text() == "prompt"
    skill = Path(render_pi_prompt_asset.__file__).with_name("PWC_MCP_SKILL.md")
    assert output.with_name(skill.name).read_bytes() == skill.read_bytes()
