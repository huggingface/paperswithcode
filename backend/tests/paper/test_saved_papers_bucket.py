from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import ClassVar

from backend.services import saved_papers_bucket_service as saved_papers
from backend.services.paper_bucket_service import PaperBucketError


class FakeHfApi:
    objects: ClassVar[dict[str, tuple[bytes, datetime]]] = {}
    create_calls = 0

    def __init__(self, *, token):
        assert token == "user-token"

    def create_bucket(self, bucket_id, *, private, exist_ok):
        assert bucket_id == "alice/pwc-saved-papers"
        assert private is True
        assert exist_ok is True
        self.__class__.create_calls += 1

    def bucket_info(self, _bucket_id):
        return SimpleNamespace(private=True)

    def list_bucket_tree(self, _bucket_id, prefix=None, *, recursive=False):
        assert recursive is False
        for path, (payload, modified) in self.objects.items():
            if prefix and not path.startswith(f"{prefix}/"):
                continue
            yield SimpleNamespace(
                type="file",
                path=path,
                size=len(payload),
                mtime=modified,
                uploaded_at=modified,
            )

    def batch_bucket_files(self, _bucket_id, *, add=None, delete=None):
        now = datetime.now(UTC)
        for payload, path in add or []:
            self.objects[path] = (bytes(payload), now)
        for path in delete or []:
            self.objects.pop(path, None)


def test_bucket_migrates_once_and_becomes_the_bookmark_source(monkeypatch):
    FakeHfApi.objects = {}
    FakeHfApi.create_calls = 0
    monkeypatch.setattr(saved_papers, "HfApi", FakeHfApi)
    store = saved_papers.SavedPapersBucket(token="user-token", username="alice")
    old = datetime.now(UTC) - timedelta(days=2)

    store.initialize(
        lambda: [
            saved_papers.SavedPaperRef(
                paper_id=10,
                saved_at=old,
                title="A useful paper",
                arxiv_id="2601.00010",
            )
        ]
    )

    assert set(FakeHfApi.objects) == {"papers/10.json", "paperswithcode.json"}
    assert b'"paper_id": 10' in FakeHfApi.objects["papers/10.json"][0]
    assert b'"title": "A useful paper"' in FakeHfApi.objects["papers/10.json"][0]

    def unexpected_legacy_load():
        raise AssertionError("legacy bookmarks should only be loaded once")

    store.initialize(unexpected_legacy_load)
    assert "papers/20.json" not in FakeHfApi.objects

    store.add(30, title="New paper", arxiv_id=None, source_url="https://example.com")
    assert [item.paper_id for item in store.list()] == [30, 10]
    store.remove(10)
    assert [item.paper_id for item in store.list()] == [30]


def test_bucket_cache_runtime_error_is_user_safe(monkeypatch):
    class FailingHfApi(FakeHfApi):
        def batch_bucket_files(self, _bucket_id, *, add=None, delete=None):
            raise RuntimeError("Permission denied")

    FailingHfApi.objects = {}
    monkeypatch.setattr(saved_papers, "HfApi", FailingHfApi)
    store = saved_papers.SavedPapersBucket(token="user-token", username="alice")

    try:
        store.initialize(lambda: [])
    except PaperBucketError as error:
        assert str(error) == "Hugging Face could not write the saved-papers Bucket."
    else:
        raise AssertionError("expected a user-safe Bucket error")


def test_bucket_migration_is_not_marked_complete_until_files_are_verified(
    monkeypatch,
):
    class MissingUploadHfApi(FakeHfApi):
        def batch_bucket_files(self, _bucket_id, *, add=None, delete=None):
            filtered = [item for item in add or [] if item[1] == "paperswithcode.json"]
            super().batch_bucket_files(_bucket_id, add=filtered, delete=delete)

    MissingUploadHfApi.objects = {}
    monkeypatch.setattr(saved_papers, "HfApi", MissingUploadHfApi)
    store = saved_papers.SavedPapersBucket(token="user-token", username="alice")

    try:
        store.initialize(
            lambda: [
                saved_papers.SavedPaperRef(
                    paper_id=10,
                    saved_at=datetime.now(UTC),
                    title="Still safe in the database",
                )
            ]
        )
    except PaperBucketError as error:
        assert "could not verify" in str(error)
    else:
        raise AssertionError("expected migration verification to fail")

    assert "paperswithcode.json" not in MissingUploadHfApi.objects
