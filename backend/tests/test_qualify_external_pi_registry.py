import uuid
from types import SimpleNamespace

import pytest

from backend.scripts.qualify_external_pi_registry import prove_stale_generation_fenced
from backend.services.chat_external_worker_registry import StaleWorkerClaim


class _Repository:
    def __init__(self, *, generation: int = 5, reject: bool = True):
        self.row = SimpleNamespace(
            instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
            release_id="release-a",
            contract_version="external-pi-v1",
            generation=generation,
            state="ready",
        )
        self.reject = reject
        self.claim = None

    def load(self, _db, worker_id):
        assert worker_id == "staging-blue"
        return self.row

    def heartbeat(self, _db, *, claim, **_values):
        self.claim = claim
        if self.reject:
            raise StaleWorkerClaim("fenced")


def test_durable_probe_submits_the_real_stale_generation_claim():
    repository = _Repository()

    assert prove_stale_generation_fenced(
        object(),
        repository,
        worker_id="staging-blue",
        release_id="release-a",
        stale_generation=4,
        current_generation=5,
    )
    assert repository.claim.worker_id == "staging-blue"
    assert repository.claim.instance_id == repository.row.instance_id
    assert repository.claim.generation == 4
    assert repository.claim.release_id == "release-a"
    assert repository.claim.contract_version == "external-pi-v1"


def test_durable_probe_fails_if_repository_accepts_stale_claim():
    with pytest.raises(RuntimeError, match="was accepted"):
        prove_stale_generation_fenced(
            object(),
            _Repository(reject=False),
            worker_id="staging-blue",
            release_id="release-a",
            stale_generation=4,
            current_generation=5,
        )


def test_durable_probe_requires_exact_current_generation():
    with pytest.raises(RuntimeError, match="identity is invalid"):
        prove_stale_generation_fenced(
            object(),
            _Repository(generation=6),
            worker_id="staging-blue",
            release_id="release-a",
            stale_generation=4,
            current_generation=5,
        )
