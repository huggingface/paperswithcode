import base64

import pytest

from backend.chat_sandbox_worker.executor_protocol import (
    MAX_COMMAND_BYTES,
    MAX_EXECUTION_OUTPUT_FRAMES,
    MAX_EXECUTION_RESPONSE_FRAMES,
    MAX_FRAME_BYTES,
    MAX_OFFSET,
    MAX_OUTPUT_CHUNK_BYTES,
    MAX_PATH_BYTES,
    MAX_READ_BYTES,
    MAX_TIMEOUT_MS,
    MAX_TOOL_CALL_ID_BYTES,
    PROTOCOL,
    ProtocolError,
    ResponseSequenceValidator,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
    validate_response_sequence,
)

OPERATION_IDENTITY = {
    "workspace_id": "workspace-1",
    "workspace_generation": 7,
    "session_id": "session-1",
    "turn_id": "turn-1",
    "execution_id": "execution-1",
    "tool_call_id": "tool-1",
}


def test_request_and_response_known_literals_round_trip() -> None:
    request = {
        "protocol": "sandbox-executor-v1",
        "type": "exec",
        "request_id": "request-7",
        "workspace_id": "workspace-2",
        "workspace_generation": 3,
        "session_id": "session-4",
        "turn_id": "turn-5",
        "execution_id": "execution-9",
        "tool_call_id": "toolu_01ABC",
        "command": "printf 'héllo'",
        "timeout_ms": 30_000,
    }
    request_wire = (
        b'{"protocol":"sandbox-executor-v1","type":"exec",'
        b'"request_id":"request-7","workspace_id":"workspace-2",'
        b'"workspace_generation":3,"session_id":"session-4",'
        b'"turn_id":"turn-5","execution_id":"execution-9",'
        b'"tool_call_id":"toolu_01ABC",'
        b'"command":"printf \'h\xc3\xa9llo\'","timeout_ms":30000}\n'
    )
    response = {
        "protocol": "sandbox-executor-v1",
        "type": "output",
        "request_id": "request-7",
        "workspace_id": "workspace-2",
        "workspace_generation": 3,
        "session_id": "session-4",
        "turn_id": "turn-5",
        "execution_id": "execution-9",
        "tool_call_id": "toolu_01ABC",
        "sequence": 1,
        "stream": "stdout",
        "data": "héllo",
    }
    response_wire = (
        b'{"protocol":"sandbox-executor-v1","type":"output",'
        b'"request_id":"request-7","workspace_id":"workspace-2",'
        b'"workspace_generation":3,"session_id":"session-4",'
        b'"turn_id":"turn-5","execution_id":"execution-9",'
        b'"tool_call_id":"toolu_01ABC",'
        b'"sequence":1,"stream":"stdout","data":"h\xc3\xa9llo"}\n'
    )

    assert PROTOCOL == "sandbox-executor-v1"
    assert encode_request(request) == request_wire
    assert decode_request(request_wire) == request
    assert encode_response(response) == response_wire
    assert decode_response(response_wire) == response


@pytest.mark.parametrize(
    "request_frame",
    [
        {
            "protocol": PROTOCOL,
            "type": "ensure_workspace",
            "request_id": "request-1",
            **OPERATION_IDENTITY,
        },
        {
            "protocol": PROTOCOL,
            "type": "attach_execution",
            "request_id": "request-2",
            **OPERATION_IDENTITY,
            "offset": 4096,
        },
        {
            "protocol": PROTOCOL,
            "type": "cancel_execution",
            "request_id": "request-3",
            **OPERATION_IDENTITY,
        },
        {
            "protocol": PROTOCOL,
            "type": "read_file",
            "request_id": "request-4",
            **OPERATION_IDENTITY,
            "path": "../literal/./path.txt",
            "offset": 5,
            "max_bytes": 8192,
        },
        {
            "protocol": PROTOCOL,
            "type": "health",
            "request_id": "request-5",
            "execution_id": "execution-health",
        },
    ],
)
def test_each_request_type_round_trips_without_resolving_content(
    request_frame: dict[str, object],
) -> None:
    assert decode_request(encode_request(request_frame)) == request_frame


@pytest.mark.parametrize(
    "response_frame",
    [
        {
            "protocol": PROTOCOL,
            "type": "acknowledged",
            "request_id": "request-1",
            **OPERATION_IDENTITY,
            "operation": "exec",
        },
        {
            "protocol": PROTOCOL,
            "type": "read_result",
            "request_id": "request-2",
            **OPERATION_IDENTITY,
            "path": "../literal/path.txt",
            "offset": 2,
            "data_base64": "bGxv",
            "eof": True,
        },
        {
            "protocol": PROTOCOL,
            "type": "health_result",
            "request_id": "request-3",
            "execution_id": "execution-health",
            "status": "ok",
        },
        {
            "protocol": PROTOCOL,
            "type": "terminal",
            "request_id": "request-4",
            **OPERATION_IDENTITY,
            "status": "completed",
            "exit_code": 0,
            "error": None,
        },
    ],
)
def test_each_response_type_round_trips(response_frame: dict[str, object]) -> None:
    assert decode_response(encode_response(response_frame)) == response_frame


def test_read_result_requires_canonical_base64_bytes() -> None:
    response = {
        "protocol": PROTOCOL,
        "type": "read_result",
        "request_id": "request-bytes",
        **OPERATION_IDENTITY,
        "path": "binary.dat",
        "offset": 4,
        "data_base64": "/wDAqQ==",
        "eof": False,
    }

    assert decode_response(encode_response(response)) == response
    for invalid in ("***", "Zh==", "YQ", "w6k", "AA==\x00"):
        with pytest.raises(ProtocolError, match="base64"):
            encode_response({**response, "data_base64": invalid})


def test_rejects_malformed_oversized_and_non_utf8_frames() -> None:
    invalid_frames = [
        b"not-json\n",
        b'{"protocol":"sandbox-executor-v1"}\ntrailing\n',
        b"\xff\n",
        b"{" + b" " * MAX_FRAME_BYTES,
    ]

    for frame in invalid_frames:
        with pytest.raises(ProtocolError):
            decode_request(frame)

    invalid_text = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-1",
        **OPERATION_IDENTITY,
        "command": "\ud800",
        "timeout_ms": 1000,
    }
    with pytest.raises(ProtocolError):
        encode_request(invalid_text)


def test_rejects_missing_extra_and_bad_identity_fields() -> None:
    valid = {
        "protocol": PROTOCOL,
        "type": "cancel_execution",
        "request_id": "request-1",
        **OPERATION_IDENTITY,
    }
    invalid = [
        {key: value for key, value in valid.items() if key != "request_id"},
        {**valid, "unexpected": True},
        {**valid, "request_id": "../request"},
        {**valid, "execution_id": ""},
        {**valid, "tool_call_id": "tool\n2"},
    ]

    for frame in invalid:
        with pytest.raises(ProtocolError):
            encode_request(frame)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("command", "x" * (MAX_COMMAND_BYTES + 1)),
        ("timeout_ms", MAX_TIMEOUT_MS + 1),
    ],
)
def test_rejects_oversized_exec_inputs(field: str, value: object) -> None:
    frame = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-1",
        **OPERATION_IDENTITY,
        "command": "pwd",
        "timeout_ms": 1000,
    }
    frame[field] = value

    with pytest.raises(ProtocolError):
        encode_request(frame)


def test_timeout_is_strictly_bounded_to_thirty_seconds() -> None:
    frame = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-1",
        **OPERATION_IDENTITY,
        "command": "pwd",
        "timeout_ms": 30_000,
    }

    assert MAX_TIMEOUT_MS == 30_000
    assert decode_request(encode_request(frame)) == frame
    with pytest.raises(ProtocolError):
        encode_request({**frame, "timeout_ms": 30_001})


@pytest.mark.parametrize(
    ("request_type", "field", "value"),
    [
        ("read_file", "tool_call_id", "t" * (MAX_TOOL_CALL_ID_BYTES + 1)),
        ("read_file", "path", "p" * (MAX_PATH_BYTES + 1)),
        ("read_file", "offset", MAX_OFFSET + 1),
        ("read_file", "max_bytes", MAX_READ_BYTES + 1),
        ("attach_execution", "offset", MAX_OFFSET + 1),
    ],
)
def test_rejects_bounded_read_and_attach_values(
    request_type: str, field: str, value: object
) -> None:
    request_frame = {
        "protocol": PROTOCOL,
        "type": request_type,
        "request_id": "request-1",
        **OPERATION_IDENTITY,
        "path": "path.txt",
        "offset": 0,
        "max_bytes": 4096,
    }
    if request_type == "attach_execution":
        del request_frame["path"]
        del request_frame["max_bytes"]
    request_frame[field] = value

    with pytest.raises(ProtocolError):
        encode_request(request_frame)


def test_rejects_oversized_output_chunk() -> None:
    output = {
        "protocol": PROTOCOL,
        "type": "output",
        "request_id": "request-1",
        **OPERATION_IDENTITY,
        "sequence": 0,
        "stream": "stdout",
        "data": "x" * (MAX_OUTPUT_CHUNK_BYTES + 1),
    }

    with pytest.raises(ProtocolError):
        encode_response(output)


@pytest.mark.parametrize(
    "response_frame",
    [
        {
            "protocol": PROTOCOL,
            "type": "output",
            "request_id": "request-1",
            **OPERATION_IDENTITY,
            "sequence": 0,
            "stream": "stdout",
            "data": "safe\x1b[31munsafe",
        },
        {
            "protocol": PROTOCOL,
            "type": "terminal",
            "request_id": "request-1",
            **OPERATION_IDENTITY,
            "status": "failed",
            "exit_code": 1,
            "error": "unsafe\x9bcontent",
        },
        {
            "protocol": PROTOCOL,
            "type": "output",
            "request_id": "request-1",
            **OPERATION_IDENTITY,
            "sequence": 0,
            "stream": "stderr",
            "data": "carriage\rreturn",
        },
    ],
)
def test_rejects_ansi_nul_and_control_response_content(
    response_frame: dict[str, object],
) -> None:
    with pytest.raises(ProtocolError, match="control"):
        encode_response(response_frame)


def test_preserves_sanitized_line_oriented_response_content() -> None:
    response_frame = {
        "protocol": PROTOCOL,
        "type": "output",
        "request_id": "request-1",
        **OPERATION_IDENTITY,
        "sequence": 0,
        "stream": "stdout",
        "data": "one\ttwo\nthree",
    }

    assert decode_response(encode_response(response_frame)) == response_frame


def test_maximum_read_result_is_encodable_at_worst_json_expansion() -> None:
    response_frame = {
        "protocol": PROTOCOL,
        "type": "read_result",
        "request_id": "r" * 128,
        "workspace_id": "w" * 128,
        "workspace_generation": MAX_OFFSET,
        "session_id": "s" * 128,
        "turn_id": "t" * 128,
        "execution_id": "e" * 128,
        "tool_call_id": "c" * MAX_TOOL_CALL_ID_BYTES,
        "path": "\\" * MAX_PATH_BYTES,
        "offset": MAX_OFFSET,
        "data_base64": base64.b64encode(b"x" * MAX_READ_BYTES).decode("ascii"),
        "eof": False,
    }

    wire = encode_response(response_frame)

    assert len(wire) <= MAX_FRAME_BYTES
    assert decode_response(wire) == response_frame


def _execution_response(kind: str, **fields: object) -> dict[str, object]:
    return {
        "protocol": PROTOCOL,
        "type": kind,
        "request_id": "request-1",
        **OPERATION_IDENTITY,
        **fields,
    }


def test_validates_increasing_output_and_exactly_one_terminal_response() -> None:
    responses = [
        _execution_response("acknowledged", operation="exec"),
        _execution_response("output", sequence=4, stream="stdout", data="one"),
        _execution_response("output", sequence=9, stream="stderr", data="two"),
        _execution_response("terminal", status="completed", exit_code=0, error=None),
    ]

    validate_response_sequence(responses, request_id="request-1", **OPERATION_IDENTITY)

    validator = ResponseSequenceValidator("request-1", **OPERATION_IDENTITY)
    for response in responses:
        validator.accept(response)
    validator.finish()


def test_execution_sequence_enforces_the_shared_response_frame_budget() -> None:
    maximum = [
        _execution_response("acknowledged", operation="exec"),
        *[
            _execution_response("output", sequence=sequence, stream="stdout", data="x")
            for sequence in range(1, MAX_EXECUTION_OUTPUT_FRAMES + 1)
        ],
        _execution_response("terminal", status="completed", exit_code=0, error=None),
    ]

    assert len(maximum) == MAX_EXECUTION_RESPONSE_FRAMES
    validate_response_sequence(maximum, request_id="request-1", **OPERATION_IDENTITY)
    with pytest.raises(ProtocolError, match="too many frames"):
        validate_response_sequence(
            [
                maximum[0],
                _execution_response("output", sequence=0, stream="stdout", data="x"),
                *maximum[1:],
            ],
            request_id="request-1",
            **OPERATION_IDENTITY,
        )


@pytest.mark.parametrize(
    "responses",
    [
        [
            _execution_response("output", sequence=1, stream="stdout", data="early"),
            _execution_response(
                "terminal", status="completed", exit_code=0, error=None
            ),
        ],
        [_execution_response("terminal", status="completed", exit_code=0, error=None)],
        [
            _execution_response("output", sequence=2, stream="stdout", data="a"),
            _execution_response("output", sequence=2, stream="stdout", data="b"),
            _execution_response(
                "terminal", status="completed", exit_code=0, error=None
            ),
        ],
        [
            _execution_response(
                "terminal", status="completed", exit_code=0, error=None
            ),
            _execution_response("output", sequence=3, stream="stdout", data="late"),
        ],
        [_execution_response("output", sequence=1, stream="stdout", data="open")],
        [
            _execution_response(
                "terminal", status="completed", exit_code=0, error=None
            ),
            _execution_response(
                "terminal", status="completed", exit_code=0, error=None
            ),
        ],
        [
            {
                **_execution_response(
                    "terminal", status="completed", exit_code=0, error=None
                ),
                "execution_id": "execution-other",
            }
        ],
    ],
)
def test_rejects_invalid_output_and_terminal_ordering(
    responses: list[dict[str, object]],
) -> None:
    with pytest.raises(ProtocolError):
        validate_response_sequence(
            responses, request_id="request-1", **OPERATION_IDENTITY
        )


def test_execution_frames_require_full_immutable_identity() -> None:
    request_frame = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-identity",
        "workspace_id": "workspace-1",
        "workspace_generation": 7,
        "session_id": "session-1",
        "turn_id": "turn-1",
        "execution_id": "execution-1",
        "tool_call_id": "tool-1",
        "command": "pwd",
        "timeout_ms": 1000,
    }
    response_frame = {
        "protocol": PROTOCOL,
        "type": "output",
        "request_id": "request-identity",
        "workspace_id": "workspace-1",
        "workspace_generation": 7,
        "session_id": "session-1",
        "turn_id": "turn-1",
        "execution_id": "execution-1",
        "tool_call_id": "tool-1",
        "sequence": 0,
        "stream": "stdout",
        "data": "ok",
    }

    assert decode_request(encode_request(request_frame)) == request_frame
    assert decode_response(encode_response(response_frame)) == response_frame

    missing_turn = {
        key: value for key, value in request_frame.items() if key != "turn_id"
    }
    with pytest.raises(ProtocolError):
        encode_request(missing_turn)
    with pytest.raises(ProtocolError):
        encode_request({**request_frame, "workspace_generation": 0})


@pytest.mark.parametrize(
    ("field", "mismatch"),
    [
        ("request_id", "request-other"),
        ("workspace_id", "workspace-other"),
        ("workspace_generation", 8),
        ("session_id", "session-other"),
        ("turn_id", "turn-other"),
        ("execution_id", "execution-other"),
        ("tool_call_id", "tool-other"),
    ],
)
def test_sequence_rejects_every_cross_identity_mismatch(
    field: str, mismatch: object
) -> None:
    responses = [
        _execution_response("acknowledged", operation="exec"),
        {
            **_execution_response(
                "terminal", status="completed", exit_code=0, error=None
            ),
            field: mismatch,
        },
    ]

    with pytest.raises(ProtocolError, match="Uncorrelated"):
        validate_response_sequence(
            responses, request_id="request-1", **OPERATION_IDENTITY
        )
