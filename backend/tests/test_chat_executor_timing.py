import logging

import pytest

from backend.services import chat_executor_timing


@pytest.mark.parametrize("failed", [False, True])
def test_stage_records_elapsed_time_and_outcome_without_exception_content(
    monkeypatch, caplog, failed
):
    times = iter([10.0, 10.125])
    monkeypatch.setattr(chat_executor_timing.time, "monotonic", lambda: next(times))
    caplog.set_level(logging.INFO, logger=chat_executor_timing.logger.name)
    error = RuntimeError("private command and credential")
    if failed:
        with pytest.raises(RuntimeError) as caught:
            with chat_executor_timing.executor_stage("attachment", "generation-1"):
                raise error
        assert caught.value is error
    else:
        with chat_executor_timing.executor_stage("attachment", "generation-1"):
            pass
    assert len(caplog.records) == 1
    assert f"duration_ms=125 success={not failed}" in caplog.text
    assert "identity=generation-1" in caplog.text
    assert "private" not in caplog.text
