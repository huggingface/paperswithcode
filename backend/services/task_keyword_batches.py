"""Short, replayable database batches for the long-running task matcher."""

from contextlib import closing
import logging
import time

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

logger = logging.getLogger(__name__)


def _run_batch(connect, operation):
    # Reads and ON CONFLICT inserts are safe even if a commit acknowledgement
    # was lost. Never replay the linker's destructive rebuild operation here.
    for attempt in range(3):
        try:
            with closing(connect()) as conn, conn:
                return operation(conn)
        except psycopg2.OperationalError:
            if attempt == 2:
                raise
            logger.warning(
                "Task keyword batch disconnected; reconnecting", exc_info=True
            )
            time.sleep(2**attempt)


def iter_latest_papers(connect, paper_ids=None, batch_size=1000):
    """Release each connection before spending CPU time matching its page."""
    last_id = 0
    while True:

        def read_page(conn):
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                scope = " AND id = ANY(%s)" if paper_ids is not None else ""
                params = (
                    (last_id, paper_ids, batch_size) if scope else (last_id, batch_size)
                )
                cur.execute(
                    "SELECT id, title, abstract FROM papers "
                    f"WHERE is_latest_version AND id > %s{scope} ORDER BY id LIMIT %s",
                    params,
                )
                return cur.fetchall()

        page = _run_batch(connect, read_page)
        if not page:
            return
        yield from page
        last_id = page[-1]["id"]


def insert_task_links(connect, links):
    def insert(conn):
        with conn.cursor() as cur:
            execute_batch(
                cur,
                "INSERT INTO paper_tasks (paper_id, task_id, source) "
                "VALUES (%(paper_id)s, %(task_id)s, 'auto') "
                "ON CONFLICT (paper_id, task_id) DO NOTHING",
                links,
            )

    _run_batch(connect, insert)
