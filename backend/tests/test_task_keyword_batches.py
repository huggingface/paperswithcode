from unittest.mock import MagicMock, Mock

import psycopg2
import pytest

from backend.services import task_keyword_batches as batches


def connection():
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = conn.cursor.return_value
    return conn


def test_paging_releases_connection_before_yield_and_keeps_scope():
    first, last = connection(), connection()
    first.cursor.return_value.fetchall.return_value = [{"id": 7}, {"id": 12}]
    last.cursor.return_value.fetchall.return_value = []
    connect = Mock(side_effect=[first, last])

    papers = batches.iter_latest_papers(connect, [7, 12], batch_size=2)
    assert next(papers) == {"id": 7}
    first.close.assert_called_once()
    assert list(papers) == [{"id": 12}]
    assert first.cursor.return_value.execute.call_args.args[1] == (0, [7, 12], 2)
    assert last.cursor.return_value.execute.call_args.args[1] == (12, [7, 12], 2)
    last.close.assert_called_once()


def test_unknown_commit_outcome_replays_idempotent_insert(monkeypatch):
    first, second = connection(), connection()
    first.__exit__.side_effect = psycopg2.OperationalError(
        "lost commit acknowledgement"
    )
    connect = Mock(side_effect=[first, second])
    execute = Mock()
    monkeypatch.setattr(batches, "execute_batch", execute)
    monkeypatch.setattr(batches.time, "sleep", lambda _: None)
    links = [{"paper_id": 7, "task_id": 3}]

    batches.insert_task_links(connect, links)

    assert execute.call_count == 2
    assert all(
        "ON CONFLICT (paper_id, task_id) DO NOTHING" in call.args[1]
        for call in execute.call_args_list
    )
    assert all(call.args[2] == links for call in execute.call_args_list)
    first.close.assert_called_once()
    second.close.assert_called_once()


def test_disconnect_retries_are_bounded(monkeypatch):
    connect = Mock(side_effect=psycopg2.OperationalError("database unavailable"))
    monkeypatch.setattr(batches.time, "sleep", lambda _: None)
    with pytest.raises(psycopg2.OperationalError):
        list(batches.iter_latest_papers(connect))
    assert connect.call_count == 3


def test_integrity_error_is_not_retried(monkeypatch):
    conn = connection()
    connect = Mock(return_value=conn)
    monkeypatch.setattr(
        batches, "execute_batch", Mock(side_effect=psycopg2.IntegrityError)
    )
    with pytest.raises(psycopg2.IntegrityError):
        batches.insert_task_links(connect, [{"paper_id": 7, "task_id": 3}])
    connect.assert_called_once()
    conn.close.assert_called_once()
