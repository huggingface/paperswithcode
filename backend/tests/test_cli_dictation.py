import json

from backend.cli import build_parser


def test_endpoint_plan_is_a_dry_run_by_default(capsys):
    args = build_parser().parse_args(
        ["dictation", "endpoint-plan", "--namespace", "nielsr", "--revision", "abc123"]
    )
    assert args.handler(args) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True
    model = plan["endpoint"]["model"]
    assert model["revision"] == "abc123"
    assert (
        model["image"]["vLLM"]["url"]
        == "registry.hf.space/nielsr-pwc-voxtral-vllm:latest"
    )
    assert model["args"][:2] == ["--max-model-len", "2304"]
    assert plan["endpoint"]["compute"]["scaling"] == {
        "minReplica": 0,
        "maxReplica": 1,
        "scaleToZeroTimeout": 60,
    }
