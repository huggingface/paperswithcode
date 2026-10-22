"""Loopback client the backend runs through ``Sandbox.exec``.

The sandbox has no network, so the backend cannot reach the compiler API over
a tunnel. Each call runs this module inside the sandbox; it forwards one
request to the compiler on 127.0.0.1 and prints the status and body as JSON.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

_COMPILER = "http://127.0.0.1:7860"


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {"GET", "POST", "DELETE"}:
        return 2
    method, path = sys.argv[1], sys.argv[2]
    if not path.startswith("/"):
        return 2
    request = urllib.request.Request(
        _COMPILER + path,
        data=sys.stdin.buffer.read() if method == "POST" else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    except OSError:
        # The compiler is still starting or has exited; the caller retries.
        status, body = 0, b""
    sys.stdout.write(json.dumps({"status": status, "body": body.decode("utf-8")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
