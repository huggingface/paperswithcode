"""``pwc dictation endpoint-plan``: the Voxtral Realtime HF Inference Endpoint.

The ``hf endpoints`` CLI cannot set a custom vLLM image or server arguments,
so this talks to the Endpoints API directly. It prints the planned endpoint
by default and only creates or updates it with
``--execute --confirm DEPLOY_HF_ENDPOINT``.
"""

from __future__ import annotations

import argparse
import json
import os

import httpx

from backend.config import get_settings

ENDPOINTS_API = "https://api.endpoints.huggingface.cloud/v2/endpoint"
MODEL = "mistralai/Voxtral-Mini-4B-Realtime-2602"
# Built from deploy/dictation/Dockerfile by the public, build-only Space
# nielsr/pwc-voxtral-vllm; Endpoints cannot pull private Space images.
DEFAULT_IMAGE = "registry.hf.space/nielsr-pwc-voxtral-vllm:latest"
# 2,304 tokens ≈ 2 minutes of audio at ~17 tokens/s: the server-side session cap.
SERVER_ARGS = [
    "--max-model-len",
    "2304",
    "--gpu-memory-utilization",
    "0.95",
    "--compilation-config",
    '{"cudagraph_mode":"PIECEWISE"}',
]


def endpoint_payload(args: argparse.Namespace) -> dict:
    return {
        "name": args.name,
        "type": "authenticated",
        "provider": {"vendor": "aws", "region": args.region},
        "compute": {
            "accelerator": "gpu",
            "instanceType": args.instance_type,
            "instanceSize": "x1",
            "scaling": {
                "minReplica": 0,
                "maxReplica": args.max_replicas,
                "scaleToZeroTimeout": args.scale_to_zero_timeout,
            },
        },
        "model": {
            "repository": MODEL,
            "revision": args.revision,
            "task": "automatic-speech-recognition",
            "framework": "pytorch",
            "image": {
                "vLLM": {"healthRoute": "/health", "port": 8000, "url": args.image}
            },
            "env": {"VLLM_DISABLE_COMPILE_CACHE": "1"},
            "args": SERVER_ARGS,
        },
    }


def plan_dictation_endpoint(args: argparse.Namespace) -> int:
    payload = endpoint_payload(args)
    if not args.execute:
        print(
            json.dumps(
                {"dry_run": True, "namespace": args.namespace, "endpoint": payload},
                indent=2,
            )
        )
        return 0
    if args.confirm != "DEPLOY_HF_ENDPOINT":
        raise ValueError("--execute requires --confirm DEPLOY_HF_ENDPOINT")
    token = os.environ.get("HF_TOKEN") or get_settings().hf_token
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{ENDPOINTS_API}/{args.namespace}/{args.name}"
    existing = httpx.get(url, headers=headers, timeout=30)
    if existing.status_code == 404:
        response = httpx.post(
            f"{ENDPOINTS_API}/{args.namespace}",
            headers=headers,
            json=payload,
            timeout=60,
        )
    else:
        existing.raise_for_status()
        response = httpx.put(
            url,
            headers=headers,
            json={"compute": payload["compute"], "model": payload["model"]},
            timeout=60,
        )
    response.raise_for_status()
    status = response.json()["status"]
    print(json.dumps({"state": status["state"], "url": status.get("url")}, indent=2))
    return 0


def register_dictation_commands(commands: argparse._SubParsersAction) -> None:
    dictation = commands.add_parser("dictation", help="Voice dictation infrastructure")
    dictation_commands = dictation.add_subparsers(
        dest="dictation_command", required=True
    )
    endpoint = dictation_commands.add_parser(
        "endpoint-plan",
        help="Print or explicitly deploy the scale-to-zero Voxtral Realtime endpoint",
    )
    endpoint.add_argument("--name", default="pwc-voxtral-realtime")
    endpoint.add_argument("--namespace", required=True)
    endpoint.add_argument("--revision", required=True, help="Model commit SHA to pin")
    endpoint.add_argument("--image", default=DEFAULT_IMAGE)
    endpoint.add_argument("--region", default="us-east-1")
    endpoint.add_argument("--instance-type", default="nvidia-l4")
    endpoint.add_argument("--max-replicas", type=int, default=1)
    endpoint.add_argument("--scale-to-zero-timeout", type=int, default=60)
    endpoint.add_argument("--execute", action="store_true")
    endpoint.add_argument("--confirm", choices=["DEPLOY_HF_ENDPOINT"])
    endpoint.set_defaults(handler=plan_dictation_endpoint)
