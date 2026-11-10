from types import SimpleNamespace

import pytest

from backend.services.hf_bucket_filesystem import BucketFileSystem


class _Api:
    def __init__(self):
        self.lookups = []

    def bucket_info(self, bucket_id):
        return SimpleNamespace(id=bucket_id)

    def get_bucket_paths_info(self, bucket_id, paths):
        self.lookups.append((bucket_id, list(paths)))
        return [
            SimpleNamespace(
                path=path,
                size=12,
                xet_hash="abc",
                mtime=None,
                uploaded_at=None,
            )
            for path in paths
            if path == "2605/2605.00001.md"
        ]

    def list_bucket_tree(self, *args, **kwargs):
        raise AssertionError("bucket file lookups must not list directories")


@pytest.fixture
def filesystem():
    fs = BucketFileSystem(token="test-token", skip_instance_cache=True)
    fs._api = _Api()
    return fs


def test_info_looks_up_only_the_requested_path(filesystem):
    info = filesystem.info("hf://buckets/org/papers/2605/2605.00001.md")

    assert info["size"] == 12
    assert info["type"] == "file"
    assert filesystem._api.lookups == [("org/papers", ["2605/2605.00001.md"])]
    assert filesystem.dircache == {}


def test_missing_file_is_not_found_without_listing(filesystem):
    assert not filesystem.exists("hf://buckets/org/papers/2605/missing.md")
    with pytest.raises(FileNotFoundError):
        filesystem.info("hf://buckets/org/papers/2605/missing.md")


def test_url_resolves_without_a_directory_check(filesystem):
    url = filesystem.url("hf://buckets/org/papers/_jobs/status/2605 1.json")

    assert url.endswith("/buckets/org/papers/resolve/_jobs/status/2605%201.json")
    assert filesystem._api.lookups == []
