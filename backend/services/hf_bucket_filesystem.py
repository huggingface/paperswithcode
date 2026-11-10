"""Hugging Face bucket file access that never lists whole directories.

``HfFileSystem`` resolves a bucket file's ``info()`` -- and so ``exists()`` and
the URL of every ``open()`` -- by listing the file's parent directory and
caching the listing on the shared filesystem instance. Paper Markdown, layout,
status and thumbnail buckets hold tens of thousands of objects per directory,
so each lookup took seconds and the cache grew without bound: the full
Markdown backfill reached 5 GB within minutes and backend workers swapped.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from huggingface_hub import HfFileSystem
from huggingface_hub.hf_file_system import HfFileSystemResolvedBucketPath


class BucketFileSystem(HfFileSystem):
    """``HfFileSystem`` whose bucket file lookups touch only the requested path.

    Bucket paths that are not files raise ``FileNotFoundError`` from
    ``info()``; use ``HfFileSystem`` to inspect bucket directories.
    """

    def info(
        self, path: str, refresh: bool = False, revision: str | None = None, **kwargs
    ) -> dict[str, Any]:
        resolved = self.resolve_path(path, revision=revision)
        if (
            not isinstance(resolved, HfFileSystemResolvedBucketPath)
            or not resolved.path
        ):
            return super().info(path, refresh=refresh, revision=revision, **kwargs)
        for entry in self._api.get_bucket_paths_info(
            resolved.bucket_id, [resolved.path]
        ):
            if entry.path == resolved.path:
                return {
                    "name": resolved.unresolve(),
                    "size": entry.size,
                    "type": "file",
                    "xet_hash": entry.xet_hash,
                    "mtime": entry.mtime,
                    "uploaded_at": entry.uploaded_at,
                }
        raise FileNotFoundError(path)

    def url(self, path: str) -> str:
        resolved = self.resolve_path(path)
        if not isinstance(resolved, HfFileSystemResolvedBucketPath):
            return super().url(path)
        return f"{self.endpoint}/buckets/{resolved.bucket_id}/resolve/{quote(resolved.path)}"
