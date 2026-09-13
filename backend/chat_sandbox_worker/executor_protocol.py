"""Strict wire shapes for the versioned sandbox executor protocol.

This module deliberately performs no command interpretation or path resolution.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any

PROTOCOL = "sandbox-executor-v1"
MAX_FRAME_BYTES = 2 * 1024 * 1024
MAX_COMMAND_BYTES = 64 * 1024
MAX_OUTPUT_CHUNK_BYTES = 64 * 1024
MAX_PATH_BYTES = 4 * 1024
MAX_TOOL_CALL_ID_BYTES = 256
MAX_TIMEOUT_MS = 30 * 1000
MAX_OFFSET = 2**63 - 1
MAX_WORKSPACE_GENERATION = 2**63 - 1
# Execution streams reserve one frame each for acknowledgement and terminal.
# The daemon must never persist more output frames than the shared remainder.
MAX_EXECUTION_RESPONSE_FRAMES = 1024
MAX_EXECUTION_OUTPUT_FRAMES = MAX_EXECUTION_RESPONSE_FRAMES - 2
# Reserve wire space for maximally escaped paths and immutable identities. Base64
# expands three raw bytes to four ASCII bytes with no further JSON expansion.
MAX_READ_BYTES = ((MAX_FRAME_BYTES - 64 * 1024) // 4) * 3
MAX_READ_BASE64_BYTES = 4 * ((MAX_READ_BYTES + 2) // 3)
MAX_REMOTE_READ_BYTES = 1024 * 1024

_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_TOOL_CALL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")


class ProtocolError(ValueError):
    """Raised when a wire frame does not satisfy the executor contract."""


def validate_remote_exec_request(command: object, timeout_ms: object) -> None:
    """Validate the narrower remote envelope before channel acquisition."""

    _bounded_text(command, "command", MAX_COMMAND_BYTES)
    if (
        isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, int)
        or not 1 <= timeout_ms <= MAX_TIMEOUT_MS
    ):
        raise ProtocolError("Invalid timeout")


def validate_remote_read_request(
    path: object, offset: object, max_bytes: object
) -> None:
    """Validate one paginated remote read without shrinking the legacy wire."""

    _bounded_text(path, "path", MAX_PATH_BYTES)
    parsed = PurePosixPath(path)
    if ".." in parsed.parts or (
        parsed.is_absolute() and parsed.parts[:2] != ("/", "workspace")
    ):
        raise ProtocolError("Invalid remote path")
    _nonnegative_integer(offset, "offset", MAX_OFFSET)
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 1 <= max_bytes <= MAX_REMOTE_READ_BYTES
    ):
        raise ProtocolError("Invalid remote read size")


def validate_remote_request(value: dict[str, Any]) -> None:
    """Apply v1 remote-only limits after the legacy envelope is decoded."""

    _validate_request(value)
    if value["type"] == "exec":
        validate_remote_exec_request(value["command"], value["timeout_ms"])
    elif value["type"] == "read_file":
        validate_remote_read_request(value["path"], value["offset"], value["max_bytes"])


def _json_object(frame: bytes) -> dict[str, Any]:
    if not isinstance(frame, bytes):
        raise ProtocolError("Executor frame must be bytes")
    if len(frame) > MAX_FRAME_BYTES:
        raise ProtocolError("Executor frame is too large")
    try:
        text = frame.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProtocolError("Executor frame is not valid UTF-8") from error
    if not text.endswith("\n") or "\n" in text[:-1] or "\r" in text:
        raise ProtocolError("Executor frame must contain exactly one JSON line")

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ProtocolError("Executor frame contains duplicate fields")
            value[key] = item
        return value

    try:
        value = json.loads(
            text[:-1],
            object_pairs_hook=object_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ProtocolError("Executor frame contains a non-finite number")
            ),
        )
    except json.JSONDecodeError as error:
        raise ProtocolError("Executor frame contains invalid JSON") from error
    if not isinstance(value, dict):
        raise ProtocolError("Executor frame must be a JSON object")
    return value


def _identity(value: Any, name: str) -> None:
    if not isinstance(value, str) or _IDENTITY.fullmatch(value) is None:
        raise ProtocolError(f"Invalid {name}")


def _bounded_text(
    value: Any, name: str, maximum: int, *, allow_empty: bool = False
) -> None:
    if not isinstance(value, str) or (not value and not allow_empty):
        raise ProtocolError(f"Invalid or oversized {name}")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise ProtocolError(f"Invalid or oversized {name}") from error
    if size > maximum:
        raise ProtocolError(f"Invalid or oversized {name}")


def _sanitized_text(
    value: Any, name: str, maximum: int, *, allow_empty: bool = False
) -> None:
    _bounded_text(value, name, maximum, allow_empty=allow_empty)
    if any(
        (ord(character) < 0x20 and character not in "\t\n")
        or 0x7F <= ord(character) <= 0x9F
        for character in value
    ):
        raise ProtocolError(f"Invalid control content in {name}")


def decode_read_result_data(value: Any) -> bytes:
    """Decode the canonical byte-safe Read representation."""

    _bounded_text(
        value,
        "read-result base64",
        MAX_READ_BASE64_BYTES,
        allow_empty=True,
    )
    try:
        encoded = value.encode("ascii")
        data = base64.b64decode(encoded, validate=True)
    except (UnicodeEncodeError, binascii.Error) as error:
        raise ProtocolError("Invalid read-result base64") from error
    if base64.b64encode(data) != encoded or len(data) > MAX_READ_BYTES:
        raise ProtocolError("Invalid or oversized read-result base64")
    return data


def _exact_fields(value: dict[str, Any], fields: set[str]) -> None:
    if set(value) != fields:
        raise ProtocolError("Executor frame has missing or extra fields")


def _base(value: dict[str, Any]) -> str:
    if value.get("protocol") != PROTOCOL:
        raise ProtocolError("Unsupported executor protocol")
    kind = value.get("type")
    if not isinstance(kind, str):
        raise ProtocolError("Invalid executor frame type")
    _identity(value.get("request_id"), "request identity")
    _identity(value.get("execution_id"), "execution identity")
    return kind


_OPERATION_IDENTITY_FIELDS = {
    "workspace_id",
    "workspace_generation",
    "session_id",
    "turn_id",
    "execution_id",
    "tool_call_id",
}


def _validate_operation_identity(value: dict[str, Any]) -> None:
    _identity(value.get("workspace_id"), "workspace identity")
    workspace_generation = value.get("workspace_generation")
    if (
        isinstance(workspace_generation, bool)
        or not isinstance(workspace_generation, int)
        or not 1 <= workspace_generation <= MAX_WORKSPACE_GENERATION
    ):
        raise ProtocolError("Invalid workspace generation")
    _identity(value.get("session_id"), "session identity")
    _identity(value.get("turn_id"), "turn identity")
    tool_call_id = value.get("tool_call_id")
    _bounded_text(tool_call_id, "tool-call ID", MAX_TOOL_CALL_ID_BYTES)
    if _TOOL_CALL_ID.fullmatch(tool_call_id) is None:
        raise ProtocolError("Invalid tool-call ID")


def _validate_request(value: dict[str, Any]) -> None:
    kind = _base(value)
    common = {"protocol", "type", "request_id", "execution_id"}
    if kind == "health":
        _exact_fields(value, common)
        return
    operation = common | _OPERATION_IDENTITY_FIELDS
    if kind == "ensure_workspace":
        _exact_fields(value, operation)
    elif kind == "exec":
        _exact_fields(
            value,
            operation
            | {
                "command",
                "timeout_ms",
            },
        )
        _bounded_text(value["command"], "command", MAX_COMMAND_BYTES)
        timeout = value["timeout_ms"]
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int)
            or not 1 <= timeout <= MAX_TIMEOUT_MS
        ):
            raise ProtocolError("Invalid timeout")
    elif kind == "attach_execution":
        _exact_fields(value, operation | {"offset"})
        _nonnegative_integer(value["offset"], "offset", MAX_OFFSET)
    elif kind == "cancel_execution":
        _exact_fields(value, operation)
    elif kind == "read_file":
        _exact_fields(value, operation | {"path", "offset", "max_bytes"})
        _bounded_text(value["path"], "path", MAX_PATH_BYTES)
        _nonnegative_integer(value["offset"], "offset", MAX_OFFSET)
        read_size = value["max_bytes"]
        if (
            isinstance(read_size, bool)
            or not isinstance(read_size, int)
            or not 1 <= read_size <= MAX_READ_BYTES
        ):
            raise ProtocolError("Invalid read size")
    else:
        raise ProtocolError("Unknown executor request type")
    _validate_operation_identity(value)


def _nonnegative_integer(value: Any, name: str, maximum: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= maximum
    ):
        raise ProtocolError(f"Invalid {name}")


def _validate_response(value: dict[str, Any]) -> None:
    kind = _base(value)
    common = {"protocol", "type", "request_id", "execution_id"}
    operation = common | _OPERATION_IDENTITY_FIELDS
    if kind == "acknowledged":
        _exact_fields(value, operation | {"operation"})
        if value["operation"] not in {
            "ensure_workspace",
            "exec",
            "attach_execution",
            "cancel_execution",
            "read_file",
        }:
            raise ProtocolError("Invalid acknowledged operation")
        _validate_operation_identity(value)
    elif kind == "output":
        _exact_fields(value, operation | {"sequence", "stream", "data"})
        _validate_operation_identity(value)
        _nonnegative_integer(value["sequence"], "output sequence", MAX_OFFSET)
        if value["stream"] not in {"stdout", "stderr"}:
            raise ProtocolError("Invalid output stream")
        _sanitized_text(
            value["data"],
            "output chunk",
            MAX_OUTPUT_CHUNK_BYTES,
            allow_empty=True,
        )
    elif kind == "read_result":
        _exact_fields(value, operation | {"path", "offset", "data_base64", "eof"})
        _validate_operation_identity(value)
        _bounded_text(value["path"], "path", MAX_PATH_BYTES)
        _nonnegative_integer(value["offset"], "offset", MAX_OFFSET)
        decode_read_result_data(value["data_base64"])
        if not isinstance(value["eof"], bool):
            raise ProtocolError("Invalid read-result EOF marker")
    elif kind == "health_result":
        _exact_fields(value, common | {"status"})
        if value["status"] not in {"ok", "draining"}:
            raise ProtocolError("Invalid executor health status")
    elif kind == "terminal":
        _exact_fields(value, operation | {"status", "exit_code", "error"})
        _validate_operation_identity(value)
        if value["status"] not in {"completed", "cancelled", "failed"}:
            raise ProtocolError("Invalid terminal status")
        exit_code = value["exit_code"]
        if exit_code is not None and (
            isinstance(exit_code, bool)
            or not isinstance(exit_code, int)
            or not -(2**31) <= exit_code < 2**31
        ):
            raise ProtocolError("Invalid terminal exit code")
        error = value["error"]
        if error is not None:
            _sanitized_text(error, "terminal error", MAX_OUTPUT_CHUNK_BYTES)
        if value["status"] == "completed" and (exit_code is None or error is not None):
            raise ProtocolError("Invalid completed terminal response")
        if value["status"] == "failed" and error is None:
            raise ProtocolError("Invalid failed terminal response")
    else:
        raise ProtocolError("Unknown executor response type")


def _encode(
    value: dict[str, Any], validator: Callable[[dict[str, Any]], None]
) -> bytes:
    if not isinstance(value, dict):
        raise ProtocolError("Executor frame must be a JSON object")
    validator(value)
    try:
        payload = (
            json.dumps(
                value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ProtocolError("Executor frame cannot be encoded") from error
    if len(payload) > MAX_FRAME_BYTES:
        raise ProtocolError("Executor frame is too large")
    return payload


class ResponseSequenceValidator:
    """Incrementally validate one correlated execution response sequence."""

    def __init__(
        self,
        request_id: str,
        *,
        workspace_id: str,
        workspace_generation: int,
        session_id: str,
        turn_id: str,
        execution_id: str,
        tool_call_id: str,
    ):
        _identity(request_id, "request identity")
        _identity(execution_id, "execution identity")
        identity = {
            "workspace_id": workspace_id,
            "workspace_generation": workspace_generation,
            "session_id": session_id,
            "turn_id": turn_id,
            "execution_id": execution_id,
            "tool_call_id": tool_call_id,
        }
        _validate_operation_identity(identity)
        self.identity = {"request_id": request_id, **identity}
        self._acknowledged = False
        self._last_output_sequence: int | None = None
        self._terminal = False
        self._response_frames = 0

    def accept(self, response: dict[str, Any]) -> None:
        self._response_frames += 1
        if self._response_frames > MAX_EXECUTION_RESPONSE_FRAMES:
            raise ProtocolError("Executor response sequence has too many frames")
        if not isinstance(response, dict):
            raise ProtocolError("Executor response must be a JSON object")
        _validate_response(response)
        if any(
            response[field] != expected for field, expected in self.identity.items()
        ):
            raise ProtocolError("Uncorrelated executor response")
        if self._terminal:
            raise ProtocolError("Executor response followed a terminal response")

        kind = response["type"]
        if not self._acknowledged and kind != "acknowledged":
            raise ProtocolError("Executor response sequence must begin acknowledged")
        if kind == "acknowledged":
            if self._acknowledged or self._last_output_sequence is not None:
                raise ProtocolError("Misordered acknowledged response")
            self._acknowledged = True
        elif kind == "output":
            sequence = response["sequence"]
            if (
                self._last_output_sequence is not None
                and sequence <= self._last_output_sequence
            ):
                raise ProtocolError("Output sequence numbers must increase")
            self._last_output_sequence = sequence
        elif kind == "terminal":
            self._terminal = True
        else:
            raise ProtocolError("Non-execution response in execution sequence")

    def finish(self) -> None:
        if not self._acknowledged or not self._terminal:
            raise ProtocolError("Executor response sequence has no terminal response")


def validate_response_sequence(
    responses: list[dict[str, Any]],
    *,
    request_id: str,
    workspace_id: str,
    workspace_generation: int,
    session_id: str,
    turn_id: str,
    execution_id: str,
    tool_call_id: str,
) -> None:
    """Validate a complete, correlated execution response sequence."""
    validator = ResponseSequenceValidator(
        request_id,
        workspace_id=workspace_id,
        workspace_generation=workspace_generation,
        session_id=session_id,
        turn_id=turn_id,
        execution_id=execution_id,
        tool_call_id=tool_call_id,
    )
    for response in responses:
        validator.accept(response)
    validator.finish()


def encode_request(request: dict[str, Any]) -> bytes:
    return _encode(request, _validate_request)


def decode_request(frame: bytes) -> dict[str, Any]:
    request = _json_object(frame)
    _validate_request(request)
    return request


def encode_response(response: dict[str, Any]) -> bytes:
    return _encode(response, _validate_response)


def decode_response(frame: bytes) -> dict[str, Any]:
    response = _json_object(frame)
    _validate_response(response)
    return response
