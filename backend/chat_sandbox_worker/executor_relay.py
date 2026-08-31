"""Minimal stdin/stdout relay for the root-only sandbox executor socket."""

from __future__ import annotations

import os
import select
import socket
import sys
from pathlib import Path

from backend.chat_sandbox_worker.executor_daemon import EXECUTOR_SOCKET


def relay(socket_path: Path = EXECUTOR_SOCKET) -> int:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        poller = select.poll()
        poller.register(sys.stdin.buffer, select.POLLIN | select.POLLHUP)
        poller.register(connection, select.POLLIN | select.POLLHUP)
        input_open = True
        while True:
            for descriptor, event in poller.poll():
                if descriptor == sys.stdin.buffer.fileno():
                    if event & select.POLLIN:
                        data = os.read(descriptor, 64 * 1024)
                        if data:
                            connection.sendall(data)
                            continue
                    if input_open:
                        input_open = False
                        poller.unregister(sys.stdin.buffer)
                        connection.shutdown(socket.SHUT_WR)
                elif descriptor == connection.fileno():
                    data = connection.recv(64 * 1024)
                    if not data:
                        return 0
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()


def main() -> int:
    if sys.argv[1:]:
        raise RuntimeError("Executor relay accepts no arguments")
    return relay()


if __name__ == "__main__":
    raise SystemExit(main())
