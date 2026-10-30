"""Pinned, database-free Hugging Face Jobs launcher for submission review."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any

from huggingface_hub import HfApi

from backend.config import Settings


REMOTE_SUBMISSION_WORKER = r"""import base64
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import urllib.request
from decimal import Decimal

manifest = json.loads(os.environ["PWC_SUBMISSION_MANIFEST"])
items = manifest["items"]
if (
    len(items) > 25
    or manifest.get("model_alias") != "luna-medium"
    or os.environ.get("PWC_SUBMISSION_MODEL") != "gpt-6-luna"
    or os.environ.get("PWC_SUBMISSION_REASONING_EFFORT") != "medium"
):
    raise SystemExit("invalid submission manifest")

evidence = [
    {
        "pending_edit_id": item["snapshot"]["id"],
        "required_decision": item.get("required_decision"),
        "snapshot": item["snapshot"],
    }
    for item in items
]
identifiers = [str(item["snapshot"]["id"]) for item in items]
action = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "capability", "resource", "reason_code", "rationale", "evidence",
        "confidence", "resolved_payload"
    ],
    "properties": {
        "capability": {"const": "review_submission"},
        "resource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "identifier", "exists"],
            "properties": {
                "kind": {"const": "pending_edit"},
                "identifier": {"enum": identifiers},
                "exists": {"const": True},
            },
        },
        "reason_code": {"enum": ["approve", "reject", "defer"]},
        "rationale": {"type": "string", "minLength": 1, "maxLength": 4000},
        "evidence": {
            "type": "array", "minItems": 1, "maxItems": 50,
            "items": {"type": "string", "minLength": 1, "maxLength": 255},
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "resolved_payload": {"type": ["object", "null"]},
    },
}
schema = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "proposed_actions"],
    "properties": {
        "status": {"enum": ["completed", "rejected"]},
        "proposed_actions": {
            "type": "array", "minItems": len(items), "maxItems": len(items),
            "items": action,
        },
    },
}
prompt = json.dumps(
    {
        "role": "Papers With Code submission reviewer",
        "rules": [
            "Return exactly one decision per pending edit.",
            "Human-only taxonomy items must be deferred.",
            "Never create or mutate tasks, methods, datasets, benchmarks, metrics, or conferences.",
            "External papers may only be approved, rejected, or deferred and must not be enriched.",
            "Resolved payloads may not expand the submitted scope.",
        ],
        "submissions": evidence,
    },
    sort_keys=True,
    separators=(",", ":"),
)
with tempfile.TemporaryDirectory() as directory:
    schema_path = os.path.join(directory, "schema.json")
    result_path = os.path.join(directory, "result.json")
    with open(schema_path, "w", encoding="utf-8") as handle:
        json.dump(schema, handle, sort_keys=True, separators=(",", ":"))
    child_env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
    }
    completed = subprocess.run(
        [
            os.environ.get("PWC_CODEX_EXECUTABLE", "codex"), "exec",
            "--json",
            "--ephemeral",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--color", "never",
            "--sandbox", "read-only",
            "--model", os.environ["PWC_SUBMISSION_MODEL"],
            "--config", "model_reasoning_effort=\"medium\"",
            "--config", "shell_environment_policy.inherit=none",
            "--config", "features.responses_websockets=false",
            "--cd", directory,
            "--output-schema", schema_path,
            "--output-last-message", result_path,
        ],
        env=child_env,
        cwd=directory,
        input=prompt,
        check=False,
        timeout=int(os.environ.get("PWC_SUBMISSION_CODEX_TIMEOUT", "1200")),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit("submission review model failed")
    with open(result_path, encoding="utf-8") as handle:
        result = json.load(handle)

usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
usage_found = False
for line in completed.stdout.splitlines():
    try:
        event = json.loads(line)
    except (TypeError, ValueError):
        continue
    candidate = event.get("usage") if isinstance(event, dict) else None
    if not isinstance(candidate, dict) and isinstance(event, dict):
        item = event.get("item")
        candidate = item.get("usage") if isinstance(item, dict) else None
    if not isinstance(candidate, dict):
        continue
    values = {key: candidate.get(key, 0) for key in usage}
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values.values()):
        raise SystemExit("submission review usage is invalid")
    usage_found = usage_found or {"input_tokens", "output_tokens"} <= set(candidate)
    for key, value in values.items():
        usage[key] = max(usage[key], value)
if not usage_found or usage["cached_input_tokens"] > usage["input_tokens"]:
    raise SystemExit("submission review usage is missing")
million = Decimal(1_000_000)
cost = (
    Decimal(usage["input_tokens"] - usage["cached_input_tokens"])
    * Decimal(os.environ["PWC_SUBMISSION_INPUT_USD_PER_MILLION"])
    + Decimal(usage["cached_input_tokens"])
    * Decimal(os.environ["PWC_SUBMISSION_CACHED_INPUT_USD_PER_MILLION"])
    + Decimal(usage["output_tokens"])
    * Decimal(os.environ["PWC_SUBMISSION_OUTPUT_USD_PER_MILLION"])
) / million
if cost > Decimal(os.environ["PWC_SUBMISSION_BUDGET_USD"]):
    raise SystemExit("submission review cost limit exceeded")

actions = {item["resource"]["identifier"]: item for item in result["proposed_actions"]}
if len(result["proposed_actions"]) != len(items) or set(actions) != set(identifiers):
    raise SystemExit("submission review scope mismatch")
for index, item in enumerate(items):
    identifier = str(item["snapshot"]["id"])
    action = actions[identifier]
    decision = {
        "claim_id": item["claim_id"],
        "decision": action["reason_code"],
        "rationale": action["rationale"],
        "evidence": list(action["evidence"]),
        "confidence": float(action["confidence"]),
        "resolved_payload": action["resolved_payload"],
    }
    usage_payload = {
        "input_tokens": usage["input_tokens"] if index == 0 else 0,
        "output_tokens": usage["output_tokens"] if index == 0 else 0,
        "cost_usd": format(cost if index == 0 else Decimal(0), "f"),
    }
    canonical = json.dumps(
        {"decision": decision, "usage": usage_payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    encoded_usage = base64.urlsafe_b64encode(
        json.dumps(usage_payload, sort_keys=True, separators=(",", ":")).encode()
    ).decode()
    request = urllib.request.Request(
        item["callback_url"],
        data=json.dumps(decision, sort_keys=True, separators=(",", ":")).encode(),
        method="POST",
        headers={
            "Authorization": "Bearer " + item["callback_token"],
            "Content-Type": "application/json",
            "X-PWC-Remote-Decision": hmac.new(
                item["callback_token"].encode(), canonical, hashlib.sha256
            ).hexdigest(),
            "X-PWC-Remote-Usage": encoded_usage,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 204:
            raise SystemExit("submission callback failed")
"""


class AutonomousSubmissionJobError(RuntimeError):
    """The remote submission reviewer could not be launched safely."""


@dataclass(frozen=True, slots=True)
class SubmissionJobLaunch:
    job_id: str
    monitoring_url: str


@dataclass(frozen=True, slots=True)
class SubmissionJobStatus:
    job_id: str
    stage: str
    terminal: bool
    successful: bool


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class AutonomousSubmissionJobService:
    ACTIVE_STAGES = frozenset({"SCHEDULING", "RUNNING"})
    TERMINAL_STAGES = frozenset({"COMPLETED", "ERROR", "CANCELED", "DELETED"})

    def __init__(self, settings: Settings, *, hf_api=None):
        self.settings = settings
        self._api = hf_api or HfApi(token=settings.autonomous_submission_hf_token)

    def _validate(self, manifest: dict[str, Any]) -> None:
        settings = self.settings
        if not settings.autonomous_submission_jobs_enabled:
            raise AutonomousSubmissionJobError("Submission Jobs are disabled")
        if (
            not settings.autonomous_submission_hf_namespace
            or not settings.autonomous_submission_hf_token
            or not settings.autonomous_submission_openai_api_key
        ):
            raise AutonomousSubmissionJobError(
                "Submission Jobs require separate HF and OpenAI credentials"
            )
        supplied = manifest.get("signature")
        unsigned = {key: value for key, value in manifest.items() if key != "signature"}
        expected = hmac.new(
            settings.autonomous_submission_callback_secret.encode(),
            _canonical(unsigned),
            hashlib.sha256,
        ).hexdigest()
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected):
            raise AutonomousSubmissionJobError(
                "Submission manifest signature is invalid"
            )
        if not 1 <= len(manifest.get("items", ())) <= 25:
            raise AutonomousSubmissionJobError("Submission manifest batch is invalid")
        if len(_canonical(manifest)) > 1_000_000:
            raise AutonomousSubmissionJobError("Submission manifest is too large")

    def _verify_image(self) -> str:
        image = self.settings.autonomous_submission_job_image
        if re.fullmatch(r".+@sha256:[0-9a-f]{64}", image):
            return image
        raise AutonomousSubmissionJobError("Submission image is not immutable")

    def launch(self, manifest: dict[str, Any]) -> SubmissionJobLaunch:
        self._validate(manifest)
        settings = self.settings
        active = sum(
            str(getattr(getattr(job, "status", None), "stage", ""))
            in self.ACTIVE_STAGES
            and dict(getattr(job, "labels", {}) or {}).get("workflow")
            == "autonomous-submission-review"
            for job in self._api.list_jobs(
                namespace=settings.autonomous_submission_hf_namespace
            )
        )
        if active >= settings.autonomous_submission_max_active_jobs:
            raise AutonomousSubmissionJobError(
                "Submission reviewer already has an active remote Job"
            )
        image = self._verify_image()
        remote = self._api.run_job(
            image=image,
            command=["python", "-c", REMOTE_SUBMISSION_WORKER],
            env={
                "PWC_SUBMISSION_MODEL": "gpt-6-luna",
                "PWC_SUBMISSION_REASONING_EFFORT": "medium",
                "PWC_SUBMISSION_CODEX_TIMEOUT": str(
                    settings.autonomous_submission_codex_timeout_seconds
                ),
                "PWC_SUBMISSION_BUDGET_USD": format(
                    settings.autonomous_submission_run_budget_usd, "f"
                ),
                "PWC_SUBMISSION_INPUT_USD_PER_MILLION": format(
                    settings.autonomous_submission_input_usd_per_million, "f"
                ),
                "PWC_SUBMISSION_CACHED_INPUT_USD_PER_MILLION": format(
                    settings.autonomous_submission_cached_input_usd_per_million, "f"
                ),
                "PWC_SUBMISSION_OUTPUT_USD_PER_MILLION": format(
                    settings.autonomous_submission_output_usd_per_million, "f"
                ),
            },
            secrets={
                "OPENAI_API_KEY": settings.autonomous_submission_openai_api_key,
                "PWC_SUBMISSION_MANIFEST": _canonical(manifest).decode(),
            },
            flavor="cpu-basic",
            timeout=f"{settings.autonomous_submission_job_timeout_seconds}s",
            labels={
                "product": "paperswithcode",
                "workflow": "autonomous-submission-review",
                "run_id": str(manifest["run_id"]),
            },
            namespace=settings.autonomous_submission_hf_namespace,
        )
        job_id = str(remote.id)
        return SubmissionJobLaunch(
            job_id=job_id,
            monitoring_url=(
                "https://huggingface.co/jobs/"
                f"{settings.autonomous_submission_hf_namespace}/{job_id}"
            ),
        )

    def poll(self, job_id: str) -> SubmissionJobStatus:
        if not job_id or len(job_id) > 255:
            raise AutonomousSubmissionJobError("Submission Job ID is invalid")
        remote = self._api.inspect_job(
            job_id=job_id,
            namespace=self.settings.autonomous_submission_hf_namespace,
        )
        stage = str(getattr(getattr(remote, "status", None), "stage", ""))
        if stage not in self.ACTIVE_STAGES | self.TERMINAL_STAGES:
            raise AutonomousSubmissionJobError(
                f"Submission Job returned unknown stage {stage or 'empty'}"
            )
        return SubmissionJobStatus(
            job_id=job_id,
            stage=stage,
            terminal=stage in self.TERMINAL_STAGES,
            successful=stage == "COMPLETED",
        )
