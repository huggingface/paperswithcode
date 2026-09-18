"""Upload one curation trace bundle to a private Hugging Face bucket.

This runs as a short-lived subprocess of the API worker. Bucket uploads go
through ``hf_xet``, whose Rust runtime keeps its allocator arenas for the
life of the process; running it in-process grew each uvicorn worker by
roughly 60 MB per trace and exhausted the backend memory cap. Exiting after
every upload returns that memory to the host.

The parent passes the bucket token through ``HF_TOKEN`` in this process's
environment, never on the command line.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--directory", required=True, type=Path)
    arguments = parser.parse_args(argv)

    from huggingface_hub import HfApi

    files = sorted(path for path in arguments.directory.iterdir() if path.is_file())
    if not files:
        print("trace bundle directory is empty", file=sys.stderr)
        return 2
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    api.create_bucket(arguments.bucket, private=True, exist_ok=True)
    api.batch_bucket_files(
        arguments.bucket,
        add=[(str(path), f"{arguments.prefix}/{path.name}") for path in files],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
