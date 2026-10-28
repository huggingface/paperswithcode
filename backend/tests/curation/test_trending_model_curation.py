import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.curation import ApplyMutationRequest, ResolveModelPaperMutation
from backend.models.database import (
    Author,
    Base,
    Evaluation,
    HfArtifact,
    ModelProviderAlias,
    ModelRelease,
    ModelReleaseArtifact,
    Paper,
    PaperAuthor,
    PaperConference,
    PaperCurationBootstrapBundle,
    PaperCurationJob,
    PaperCurationWorkflow,
    PaperDataset,
    PaperHfArtifact,
    PaperMethod,
    PaperMethodEvidence,
    PaperMethodExclusion,
    PaperOrganization,
    PaperProjectPage,
    PaperRelation,
    PaperRepository,
    PaperTask,
    ProjectPage,
    TrendingModelCandidate,
    TrendingModelCurationState,
)
from backend.services.codex_add_evals_service import (
    CodexPaperJob,
    CodexPaperJobService,
    _curator_skill_digest,
)
from backend.services.codex_curation_callback_service import (
    CodexCurationCallbackService,
)
from backend.services.hf_trending_model_curation_service import (
    HFTrendingModelCurationService,
)
from backend.services.hf_trending_model_discovery_service import (
    HFModelCardClient,
    HFModelCardSnapshot,
    HFTrendingDiscoveryClient,
    HFTrendingModel,
    is_obvious_conversion,
    should_requeue_card,
)
from backend.services.trending_model_resolution_service import (
    release_version_conflict,
    TrendingModelResolutionScopeError,
    TrendingModelResolutionService,
)
from backend.utils.source_urls import source_url_identity


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def test_discovery_uses_hf_cli_global_top_fifty_plus_featured_top_hundred():
    calls = []

    def run(command):
        calls.append(command)
        return json.dumps(
            [
                {
                    "id": "Qwen/Qwen3.8-Flash-Next",
                    "author": "Qwen",
                    "tags": ["transformers", "safetensors", "eval-results"],
                    "created_at": "2026-08-25T00:00:00+00:00",
                    "last_modified": "2026-08-26T00:00:00+00:00",
                    "trending_score": 999,
                }
            ]
        )

    models = HFTrendingDiscoveryClient(run=run, hf_cli="hf").list_top_models()

    assert calls == [
        [
            "hf",
            "models",
            "list",
            "--sort",
            "trending_score",
            "--limit",
            "100",
            "--expand",
            "author,tags,createdAt,lastModified,trendingScore",
            "--format",
            "json",
        ]
    ]
    assert models[0].repo_id == "Qwen/Qwen3.8-Flash-Next"
    assert models[0].featured_publisher is True


def test_discovery_keeps_only_featured_publishers_beyond_top_fifty():
    payload = [
        {"id": f"{author}/model-{rank}", "author": author, "trending_score": 100 - rank}
        for rank, author in enumerate(["community"] * 2 + ["Qwen", "community"])
    ]
    models = HFTrendingDiscoveryClient(
        run=lambda _command: json.dumps(payload), hf_cli="hf"
    ).list_top_models(limit=2, featured_limit=4)

    assert [model.repo_id for model in models] == [
        "community/model-0",
        "community/model-1",
        "Qwen/model-2",
    ]


def test_source_url_identity_preserves_distinct_legacy_and_namespaced_sources():
    assert source_url_identity("https://arxiv.org/abs/cs/0301001") == (
        "arxiv:cs/0301001"
    )
    assert source_url_identity("https://arxiv.org/abs/cs/0301002") != (
        source_url_identity("https://arxiv.org/abs/cs/0301001")
    )
    assert source_url_identity("https://huggingface.co/spaces/org/demo-a") != (
        source_url_identity("https://huggingface.co/spaces/org/demo-b")
    )
    assert source_url_identity("https://github.com/org/repo/tree/main/examples") != (
        source_url_identity("https://github.com/org/repo")
    )
    assert source_url_identity("https://example.com/report?id=1") != (
        source_url_identity("https://example.com/report?id=2")
    )
    assert source_url_identity("https://example.com:8443/report") != (
        source_url_identity("https://example.com/report")
    )


def test_discovery_prefers_hf_cli_from_running_virtualenv(tmp_path, monkeypatch):
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    hf = python.with_name("hf")
    hf.touch(mode=0o755)
    monkeypatch.setattr("sys.executable", str(python))
    calls = []

    def run(command):
        calls.append(command)
        return "[]"

    HFTrendingDiscoveryClient(run=run).list_top_models(limit=1)

    assert calls[0][0] == str(hf)


def test_non_featured_original_release_is_not_deterministically_rejected():
    model = HFTrendingModel.from_payload(
        {
            "id": "ornith-ai/Ornith-1.5-35B-A3B",
            "author": "ornith-ai",
            "tags": ["transformers", "safetensors", "eval-results"],
            "trending_score": 425,
        }
    )

    assert model.featured_publisher is False
    assert is_obvious_conversion(model) is False


def test_novel_finetune_is_left_for_model_judgment():
    model = HFTrendingModel.from_payload(
        {
            "id": "z-lab/Qwen3.8-27B-DFlash2",
            "author": "z-lab",
            "tags": [
                "transformers",
                "dflash2",
                "speculative-decoding",
                "base_model:Qwen/Qwen3.8-27B",
                "base_model:finetune:Qwen/Qwen3.8-27B",
            ],
            "trending_score": 145,
        }
    )

    assert is_obvious_conversion(model) is False


def test_quantized_or_format_only_derivative_is_rejected_before_llm():
    model = HFTrendingModel.from_payload(
        {
            "id": "community/Qwen3.8-27B-GGUF",
            "author": "community",
            "tags": [
                "gguf",
                "quantized",
                "base_model:Qwen/Qwen3.8-27B",
                "base_model:quantized:Qwen/Qwen3.8-27B",
            ],
            "trending_score": 500,
        }
    )

    assert is_obvious_conversion(model) is True


def test_card_is_requeued_only_when_its_content_hash_changes():
    assert should_requeue_card(previous_sha=None, current_sha="a") is True
    assert should_requeue_card(previous_sha="a", current_sha="a") is False
    assert should_requeue_card(previous_sha="a", current_sha="b") is True


def test_model_identity_schema_has_stable_unique_keys():
    release_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in ModelRelease.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    alias_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in ModelProviderAlias.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    artifact_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in ModelReleaseArtifact.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("paper_id", "canonical_name") in release_uniques
    assert ("provider", "alias") in alias_uniques
    assert ("model_release_id", "hf_artifact_id") in artifact_uniques
    assert TrendingModelCandidate.__table__.c.repo_id.unique is True


def test_model_card_snapshot_hashes_readme_not_noisy_repo_metadata(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Release\n\n| Benchmark | Score |\n| X | 42 |\n")
    calls = []

    def run(command):
        calls.append(command)
        if command[:3] == ["hf", "models", "info"]:
            return json.dumps({"sha": "repo-revision-1"})
        return str(readme)

    snapshot = HFModelCardClient(run=run, hf_cli="hf").snapshot("org/model")

    assert snapshot.repo_revision == "repo-revision-1"
    assert len(snapshot.readme_sha) == 64
    assert calls[1] == [
        "hf",
        "download",
        "org/model",
        "README.md",
        "--revision",
        "repo-revision-1",
        "--quiet",
    ]


def test_resolution_accepts_exactly_one_canonical_paper_identity():
    common = {
        "decision": "accept",
        "reason": "Official technical report for a newly trained model.",
        "novelty_kind": "new_weights",
        "evidence_urls": ["https://huggingface.co/org/model"],
        "model_release": {
            "canonical_name": "Model",
            "publisher": "org",
            "is_open": True,
            "aliases": ["org/model"],
        },
    }

    external = ResolveModelPaperMutation.model_validate(
        {
            **common,
            "external_paper": {
                "source_url": "https://github.com/org/model/blob/main/report.pdf",
                "title": "Model Technical Report",
                "abstract": "We introduce Model.",
                "date_published": "2026-08-26",
            },
        }
    )
    assert external.external_paper is not None

    follow_up = ResolveModelPaperMutation.model_validate(
        {**common, "existing_paper_id": 2, "predecessor_paper_id": 1}
    )
    assert follow_up.predecessor_paper_id == 1

    with pytest.raises(ValidationError, match="exactly one paper identity"):
        ResolveModelPaperMutation.model_validate(
            {**common, "existing_paper_id": 1, "arxiv_id": "2608.12345"}
        )


def test_resolution_rejection_cannot_smuggle_a_paper_mutation():
    with pytest.raises(ValidationError, match="rejection cannot include"):
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "reject",
                "reason": "Pure GGUF conversion.",
                "novelty_kind": "repackaging",
                "evidence_urls": ["https://huggingface.co/community/model-GGUF"],
                "existing_paper_id": 1,
            }
        )


def _resolution_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Author.__table__,
            HfArtifact.__table__,
            PaperHfArtifact.__table__,
            ModelRelease.__table__,
            ModelReleaseArtifact.__table__,
            ModelProviderAlias.__table__,
            TrendingModelCandidate.__table__,
            ProjectPage.__table__,
            PaperAuthor.__table__,
            PaperTask.__table__,
            PaperMethod.__table__,
            PaperMethodEvidence.__table__,
            PaperMethodExclusion.__table__,
            PaperDataset.__table__,
            PaperRepository.__table__,
            PaperProjectPage.__table__,
            PaperConference.__table__,
            PaperOrganization.__table__,
            Evaluation.__table__,
            PaperRelation.__table__,
            PaperCurationBootstrapBundle.__table__,
            PaperCurationJob.__table__,
        ],
    )
    return Session(engine)


def test_resolution_creates_follow_up_relation():
    db = _resolution_session()
    predecessor = Paper(
        title="Earlier Family Release",
        source="external",
        source_url="https://example.com/earlier",
        version="v1",
        is_latest_version=True,
    )
    successor = Paper(
        title="New Family Release",
        source="external",
        source_url="https://example.com/new",
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="org/new-model",
        author="org",
        readme_sha="9" * 64,
        status="resolving",
    )
    db.add_all([predecessor, successor, candidate])
    db.commit()

    TrendingModelResolutionService(db).apply(
        candidate.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "accept",
                "reason": "Official release page establishes a distinct follow-up.",
                "novelty_kind": "new_weights",
                "evidence_urls": [
                    "https://example.com/new",
                    "https://example.com/earlier",
                ],
                "existing_paper_id": successor.id,
                "predecessor_paper_id": predecessor.id,
                "model_release": {
                    "canonical_name": "New Model",
                    "publisher": "org",
                    "is_open": True,
                    "aliases": ["org/new-model"],
                },
            }
        ),
        allowed_paper_ids={predecessor.id, successor.id},
    )

    relation = db.get(PaperRelation, (predecessor.id, successor.id))
    assert relation is not None


def test_resolution_rejects_predecessor_outside_callback_scope():
    db = _resolution_session()
    predecessor = Paper(
        title="Unscoped Earlier Release",
        source="external",
        source_url="https://example.com/earlier",
        version="v1",
        is_latest_version=True,
    )
    successor = Paper(
        title="Scoped New Release",
        source="external",
        source_url="https://example.com/new",
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="org/new-model",
        author="org",
        readme_sha="9" * 64,
        status="resolving",
    )
    db.add_all([predecessor, successor, candidate])
    db.commit()

    mutation = ResolveModelPaperMutation.model_validate(
        {
            "decision": "accept",
            "reason": "Official release page establishes a distinct follow-up.",
            "novelty_kind": "new_weights",
            "evidence_urls": [
                "https://example.com/new",
                "https://example.com/earlier",
            ],
            "existing_paper_id": successor.id,
            "predecessor_paper_id": predecessor.id,
            "model_release": {
                "canonical_name": "New Model",
                "publisher": "org",
                "is_open": True,
                "aliases": ["org/new-model"],
            },
        }
    )
    with pytest.raises(TrendingModelResolutionScopeError, match="outside"):
        TrendingModelResolutionService(db).apply(
            candidate.id,
            mutation,
            allowed_paper_ids={successor.id},
        )


def test_arxiv_evidence_requires_the_canonical_arxiv_host():
    assert TrendingModelResolutionService._canonical_arxiv_evidence(
        "2608.54321", "https://arxiv.org/pdf/2608.54321.pdf"
    )
    assert not TrendingModelResolutionService._canonical_arxiv_evidence(
        "2608.54321", "https://example.com/abs/2608.54321"
    )
    for url in (
        "https://arxiv.org/abs/2608.54321v2",
        "https://arxiv.org/html/2608.54321",
        "https://www.arxiv.org/html/2608.54321v3/",
        "https://arxiv.org/pdf/2608.54321v1.pdf",
    ):
        assert TrendingModelResolutionService._canonical_arxiv_evidence(
            "2608.54321", url
        ), url
    assert TrendingModelResolutionService._canonical_arxiv_evidence(
        "2608.54321v2", "https://arxiv.org/abs/2608.54321"
    )
    for url in (
        "https://arxiv.org/abs/2608.543210",
        "https://arxiv.org/html/2605.25571",
        "https://arxiv.org/list/2608.54321",
    ):
        assert not TrendingModelResolutionService._canonical_arxiv_evidence(
            "2608.54321", url
        ), url


def test_resolution_links_existing_paper_release_and_hf_artifact():
    db = _resolution_session()
    paper = Paper(
        title="Existing Report",
        source="external",
        source_url="https://example.com/report",
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="a" * 64,
        status="resolving",
    )
    db.add_all([paper, candidate])
    db.commit()

    result = TrendingModelResolutionService(db).apply(
        candidate.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "accept",
                "reason": "New weights with first-party benchmark results.",
                "novelty_kind": "new_weights",
                "evidence_urls": [
                    "https://huggingface.co/org/model",
                    "https://example.com/report",
                ],
                "existing_paper_id": paper.id,
                "model_release": {
                    "canonical_name": "Model",
                    "publisher": "org",
                    "is_open": True,
                    "aliases": ["org/model"],
                },
            }
        ),
    )

    assert result["paper_id"] == paper.id
    assert db.query(ModelRelease).one().canonical_name == "Model"
    assert db.query(HfArtifact).one().repo_id == "org/model"
    assert db.query(PaperHfArtifact).one().paper_id == paper.id
    assert db.get(TrendingModelCandidate, candidate.id).status == "resolved"


def test_resolution_rejects_existing_paper_without_canonical_source_evidence():
    db = _resolution_session()
    paper = Paper(
        title="Unrelated Paper",
        source="external",
        source_url="https://example.com/unrelated",
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="f" * 64,
        status="resolving",
    )
    db.add_all([paper, candidate])
    db.commit()

    with pytest.raises(ValueError, match="canonical source evidence"):
        TrendingModelResolutionService(db).apply(
            candidate.id,
            ResolveModelPaperMutation.model_validate(
                {
                    "decision": "accept",
                    "reason": "Attempted unrelated link.",
                    "novelty_kind": "new_release",
                    "evidence_urls": ["https://huggingface.co/org/model"],
                    "existing_paper_id": paper.id,
                    "model_release": {
                        "canonical_name": "Model",
                        "publisher": "org",
                        "is_open": True,
                        "aliases": [],
                    },
                }
            ),
        )


def test_resolution_accepts_pinned_model_card_for_existing_hf_model_paper():
    db = _resolution_session()
    paper = Paper(
        title="Qwen3.8-27B",
        source="external",
        source_url="https://huggingface.co/Qwen/Qwen3.8-27B",
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="Qwen/Qwen3.8-27B",
        author="Qwen",
        readme_sha="a" * 64,
        status="resolving",
    )
    db.add_all([paper, candidate])
    db.commit()

    result = TrendingModelResolutionService(db).apply(
        candidate.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "accept",
                "reason": "First-party pinned model card documents new weights.",
                "novelty_kind": "new_weights",
                "evidence_urls": [
                    "https://huggingface.co/Qwen/Qwen3.8-27B/raw/abc123/README.md"
                ],
                "existing_paper_id": paper.id,
                "model_release": {
                    "canonical_name": "Qwen3.8-27B",
                    "publisher": "Qwen",
                    "is_open": True,
                    "aliases": ["Qwen/Qwen3.8-27B"],
                },
            }
        ),
    )

    assert result["paper_id"] == paper.id
    assert db.get(TrendingModelCandidate, candidate.id).status == "resolved"


def test_resolution_rejection_is_durable_and_creates_no_catalog_rows():
    db = _resolution_session()
    candidate = TrendingModelCandidate(
        repo_id="community/model-GGUF",
        author="community",
        readme_sha="b" * 64,
        status="resolving",
    )
    db.add(candidate)
    db.commit()

    result = TrendingModelResolutionService(db).apply(
        candidate.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "reject",
                "reason": "Pure quantized conversion.",
                "novelty_kind": "repackaging",
                "evidence_urls": ["https://huggingface.co/community/model-GGUF"],
            }
        ),
    )

    assert result["status"] == "rejected"
    assert db.query(ModelRelease).count() == 0
    assert db.query(Paper).count() == 0


def test_resolution_rejects_obvious_derivative_before_creating_external_paper():
    db = _resolution_session()
    candidate = TrendingModelCandidate(
        repo_id="community/ComfyUI-Model-Latent-Upscaler",
        author="community",
        readme_sha="c" * 64,
        status="resolving",
    )
    db.add(candidate)
    db.commit()

    with pytest.raises(ValueError, match="derivative"):
        TrendingModelResolutionService(db).apply(
            candidate.id,
            ResolveModelPaperMutation.model_validate(
                {
                    "decision": "accept",
                    "reason": "A workflow repository with benchmark screenshots.",
                    "novelty_kind": "new_weights",
                    "evidence_urls": [
                        "https://huggingface.co/community/ComfyUI-Model-Latent-Upscaler"
                    ],
                    "external_paper": {
                        "source_url": "https://huggingface.co/community/ComfyUI-Model-Latent-Upscaler",
                        "title": "ComfyUI Model Latent Upscaler",
                        "abstract": "A derivative upscaling workflow.",
                        "date_published": "2026-08-27",
                    },
                    "model_release": {
                        "canonical_name": "Model Latent Upscaler",
                        "publisher": "community",
                        "is_open": True,
                        "aliases": [],
                    },
                }
            ),
        )

    assert db.query(Paper).count() == 0


def test_arxiv_upgrade_preserves_release_and_retires_external_paper(monkeypatch):
    db = _resolution_session()
    external = Paper(
        title="Model Release",
        source="external",
        source_url="https://org.example/model",
        version="v1",
        is_latest_version=True,
        hf_models=["https://huggingface.co/org/model"],
    )
    artifact = HfArtifact(
        kind="model",
        repo_id="org/model",
        url="https://huggingface.co/org/model",
    )
    db.add_all([external, artifact])
    db.flush()
    release = ModelRelease(
        paper_id=external.id,
        canonical_name="Model",
        publisher="org",
        canonical_source_url=external.source_url,
        aliases=["org/model"],
    )
    db.add(release)
    db.flush()
    db.add_all(
        [
            PaperHfArtifact(paper_id=external.id, hf_artifact_id=artifact.id),
            ModelReleaseArtifact(
                model_release_id=release.id, hf_artifact_id=artifact.id
            ),
        ]
    )
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="9" * 64,
        status="resolving",
        model_release_id=release.id,
    )
    db.add(candidate)
    db.commit()

    async def import_arxiv(_service, arxiv_id, *, commit=True):
        assert commit is False
        paper = Paper(
            title="Model Technical Report",
            source="arxiv",
            arxiv_id=arxiv_id,
            version="v1",
            is_latest_version=True,
        )
        db.add(paper)
        db.flush()
        return paper, True

    monkeypatch.setattr(
        "backend.services.paper_ingestion_service.PaperIngestionService.get_or_import_arxiv_paper",
        import_arxiv,
    )
    result = TrendingModelResolutionService(db).apply(
        candidate.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "accept",
                "reason": "The official release now links its arXiv report.",
                "novelty_kind": "new_weights",
                "evidence_urls": ["https://arxiv.org/abs/2608.12345"],
                "arxiv_id": "2608.12345",
                "model_release": {
                    "canonical_name": "Model",
                    "publisher": "org",
                    "is_open": True,
                    "aliases": ["org/model"],
                },
            }
        ),
    )

    upgraded = db.get(Paper, result["paper_id"])
    assert upgraded.arxiv_id == "2608.12345"
    assert db.get(Paper, external.id).is_latest_version is False
    assert db.get(ModelRelease, release.id).paper_id == upgraded.id
    assert db.get(PaperHfArtifact, (upgraded.id, artifact.id)) is not None
    assert upgraded.hf_models == ["https://huggingface.co/org/model"]
    assert db.query(ProjectPage).filter_by(url=external.source_url).one()


def test_arxiv_import_remains_rollbackable_after_downstream_failure(monkeypatch):
    db = _resolution_session()
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="8" * 64,
        status="resolving",
    )
    db.add(candidate)
    db.commit()

    async def import_arxiv(_service, arxiv_id, *, commit=True):
        assert commit is False
        paper = Paper(
            title="Uncommitted Report",
            source="arxiv",
            arxiv_id=arxiv_id,
            version="v1",
            is_latest_version=True,
        )
        db.add(paper)
        db.flush()
        return paper, True

    monkeypatch.setattr(
        "backend.services.paper_ingestion_service.PaperIngestionService.get_or_import_arxiv_paper",
        import_arxiv,
    )
    monkeypatch.setattr(
        TrendingModelResolutionService,
        "_find_release",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("downstream failure")),
    )
    mutation = ResolveModelPaperMutation.model_validate(
        {
            "decision": "accept",
            "reason": "Official report.",
            "novelty_kind": "new_weights",
            "evidence_urls": ["https://arxiv.org/abs/2608.54321"],
            "arxiv_id": "2608.54321",
            "model_release": {
                "canonical_name": "Model",
                "publisher": "org",
                "is_open": True,
                "aliases": [],
            },
        }
    )
    with pytest.raises(RuntimeError, match="downstream failure"):
        TrendingModelResolutionService(db).apply(candidate.id, mutation)
    db.rollback()

    assert db.query(Paper).count() == 0


def test_release_dedup_uses_normalized_names_and_aliases():
    db = _resolution_session()
    paper = Paper(
        title="Family Report",
        source="external",
        source_url="https://example.com/family",
        version="v1",
        is_latest_version=True,
    )
    db.add(paper)
    db.flush()
    release = ModelRelease(
        paper_id=paper.id,
        canonical_name="Qwen 3.8 Flash Next",
        publisher="Qwen",
        aliases=["qwen/qwen3.8-flash-next"],
    )
    candidate = TrendingModelCandidate(
        repo_id="Qwen/Qwen3.8-Flash-Next",
        author="Qwen",
        readme_sha="7" * 64,
        status="resolving",
    )
    db.add_all([release, candidate])
    db.commit()

    result = TrendingModelResolutionService(db).apply(
        candidate.id,
        ResolveModelPaperMutation.model_validate(
            {
                "decision": "accept",
                "reason": "Same canonical release spelling.",
                "novelty_kind": "new_release",
                "evidence_urls": ["https://example.com/family"],
                "existing_paper_id": paper.id,
                "model_release": {
                    "canonical_name": "Qwen3.8-Flash-Next",
                    "publisher": "Qwen",
                    "is_open": True,
                    "aliases": ["Qwen/Qwen3.8-Flash-Next"],
                },
            }
        ),
    )

    assert result["model_release_id"] == release.id
    assert db.query(ModelRelease).count() == 1


def test_resolution_job_is_candidate_scoped_without_a_paper():
    candidate_id = uuid.uuid4()
    job = CodexPaperJob(
        id=uuid.uuid4(),
        candidate_id=candidate_id,
        paper_id=None,
        paper_route=None,
        paper_title=None,
        requested_by="hf-trending-cron",
        kind="resolve-model-paper",
        status="queued",
        created_at=datetime.now(UTC),
        attempt_count=0,
        trigger="hf-trending-cron",
    )

    assert job.candidate_id == candidate_id
    assert job.paper_id is None
    assert len(_curator_skill_digest("resolve-model-paper")) == 64


def test_enqueue_resolution_creates_scoped_high_priority_job(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationBootstrapBundle.__table__,
            PaperCurationJob.__table__,
        ],
    )
    db = Session(engine)
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="c" * 64,
        status="discovered",
    )
    db.add(candidate)
    db.commit()
    monkeypatch.setattr(
        "backend.services.codex_add_evals_service._git_revision", lambda: "HEAD"
    )

    job = CodexPaperJobService().enqueue_resolution(
        db,
        candidate=candidate,
        requested_by="hf-trending-cron",
        settings=get_settings(),
        dispatch=False,
    )

    assert job.kind == "resolve-model-paper"
    assert job.candidate_id == candidate.id
    assert job.paper_id is None
    assert job.trigger == "hf-trending-cron"
    assert job.priority < 100
    assert db.get(TrendingModelCandidate, candidate.id).status == "queued"


def test_resolution_context_exposes_exact_and_same_publisher_paper_candidates():
    db = _resolution_session()
    paper = Paper(
        title="Existing Model Report",
        source="external",
        source_url="https://example.com/report",
        version="v1",
        is_latest_version=True,
    )
    artifact = HfArtifact(
        kind="model",
        repo_id="org/model",
        url="https://huggingface.co/org/model",
    )
    sibling_paper = Paper(
        title="Existing Family Release",
        source="external",
        source_url="https://example.com/family",
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="d" * 64,
        readme_revision="e" * 40,
        featured_publisher=True,
        status="resolving",
    )
    db.add_all([paper, sibling_paper, artifact, candidate])
    db.flush()
    db.add(
        ModelRelease(
            paper_id=sibling_paper.id,
            canonical_name="Model 35B",
            publisher="org",
            canonical_source_url="https://example.com/family",
            aliases=["org/model-35b"],
            is_open=True,
        )
    )
    db.add(PaperHfArtifact(paper_id=paper.id, hf_artifact_id=artifact.id))
    db.commit()

    class Jobs:
        @staticmethod
        def serialize(_row, _settings):
            return SimpleNamespace(
                model_dump=lambda **_kwargs: {"kind": "resolve-model-paper"}
            )

    context = CodexCurationCallbackService(db, job_service=Jobs()).context(
        SimpleNamespace(kind="resolve-model-paper", candidate_id=candidate.id),
        get_settings(),
    )

    assert context["candidate"]["repo_id"] == "org/model"
    assert context["candidate"]["readme_sha"] == "d" * 64
    assert context["paper_candidates"] == [
        {
            "id": paper.id,
            "title": "Existing Model Report",
            "arxiv_id": None,
            "source_url": "https://example.com/report",
        },
        {
            "id": sibling_paper.id,
            "title": "Existing Family Release",
            "arxiv_id": None,
            "source_url": "https://example.com/family",
        },
    ]
    assert "paper" not in context


def test_scheduled_resolution_gets_one_validation_correction_attempt(monkeypatch):
    db = _resolution_session()
    paper = Paper(
        title="Scoped Release",
        source="external",
        source_url="https://example.com/release",
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="d" * 64,
        status="resolving",
    )
    db.add_all([paper, candidate])
    db.flush()
    job = PaperCurationJob(
        id=uuid.uuid4(),
        kind="resolve-model-paper",
        candidate_id=candidate.id,
        requested_by="hf-trending-cron",
        trigger="hf-trending-cron",
        policy_version="hf-trending-v1",
        priority=25,
        status="running",
    )
    db.add(job)
    db.commit()
    service = CodexCurationCallbackService(db)
    monkeypatch.setattr(
        service, "_allowed_resolution_paper_ids", lambda _candidate: {paper.id}
    )
    body = ApplyMutationRequest.model_validate(
        {
            "resolve_model_paper": {
                "decision": "accept",
                "reason": "Official release.",
                "novelty_kind": "new_weights",
                "evidence_urls": ["https://example.com/not-the-release"],
                "existing_paper_id": paper.id,
                "model_release": {
                    "canonical_name": "Model",
                    "publisher": "org",
                    "is_open": True,
                    "aliases": ["org/model"],
                },
            }
        }
    )

    with pytest.raises(ValueError, match="canonical source evidence"):
        service._apply_authorized(job, body)
    db.refresh(job)
    assert job.submitted_at is None
    assert job.validation_summary["retryable"] is True

    with pytest.raises(ValueError, match="canonical source evidence"):
        service._apply_authorized(job, body)
    db.refresh(job)
    assert job.submitted_at is not None
    assert job.validation_summary["retryable"] is False

    with pytest.raises(RuntimeError, match="may no longer apply mutations"):
        service._apply_authorized(job, body)


def test_remote_proposal_schema_accepts_typed_model_resolution():
    schema = json.loads(Path("jobs/schemas/curation_proposal.schema.json").read_text())
    proposal = {
        "evaluations": [],
        "evaluation_removals": [],
        "benchmark_gaps": [],
        "validation_evidence": [],
        "resolve_model_paper": {
            "decision": "reject",
            "reason": "Pure conversion",
            "novelty_kind": "repackaging",
            "evidence_urls": ["https://huggingface.co/org/model-GGUF"],
        },
    }

    assert list(Draft202012Validator(schema).iter_errors(proposal)) == []


def test_callback_policy_allows_only_resolution_payload_for_resolution_job():
    mutation = ResolveModelPaperMutation.model_validate(
        {
            "decision": "reject",
            "reason": "Pure conversion",
            "novelty_kind": "repackaging",
            "evidence_urls": ["https://huggingface.co/org/model-GGUF"],
        }
    )
    body = ApplyMutationRequest(resolve_model_paper=mutation)
    row = SimpleNamespace(
        kind="resolve-model-paper",
        status="running",
        submitted_at=None,
        applied_at=None,
    )

    service = CodexCurationCallbackService(SimpleNamespace())
    service._validate_mutation(row, body)

    with pytest.raises(ValueError, match="only model resolution"):
        service._validate_mutation(
            row,
            ApplyMutationRequest(
                resolve_model_paper=mutation,
                enrich={"urls_extracted": True},
            ),
        )


def test_callback_policy_rejects_cron_created_release_pages():
    body = ApplyMutationRequest.model_validate(
        {
            "resolve_model_paper": {
                "decision": "accept",
                "reason": "New weights announced in an official release blog.",
                "novelty_kind": "new_weights",
                "evidence_urls": ["https://example.com/blog/model-release"],
                "external_paper": {
                    "source_url": "https://example.com/blog/model-release",
                    "title": "Model Release",
                    "abstract": "The publisher announces newly trained weights.",
                    "date_published": "2026-08-31",
                },
                "model_release": {
                    "canonical_name": "Model",
                    "publisher": "org",
                    "is_open": True,
                    "aliases": ["org/model"],
                },
            }
        }
    )
    row = SimpleNamespace(
        kind="resolve-model-paper",
        trigger="hf-trending-cron",
        status="running",
        submitted_at=None,
        applied_at=None,
    )

    with pytest.raises(ValueError, match="cannot create external papers"):
        CodexCurationCallbackService(SimpleNamespace())._validate_mutation(row, body)


def test_callback_applies_resolution_and_records_job_result():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationBootstrapBundle.__table__,
            PaperCurationJob.__table__,
        ],
    )
    db = Session(engine)
    candidate = TrendingModelCandidate(
        repo_id="community/model-GGUF",
        author="community",
        readme_sha="1" * 64,
        status="resolving",
    )
    db.add(candidate)
    db.flush()
    row = PaperCurationJob(
        id=uuid.uuid4(),
        kind="resolve-model-paper",
        candidate_id=candidate.id,
        requested_by="hf-trending-cron",
        trigger="hf-trending-cron",
        policy_version="hf-trending-v1",
        priority=25,
        status="running",
    )
    db.add(row)
    db.commit()

    result = CodexCurationCallbackService(db)._apply_authorized(
        row,
        ApplyMutationRequest(
            resolve_model_paper={
                "decision": "reject",
                "reason": "Pure conversion",
                "novelty_kind": "repackaging",
                "evidence_urls": ["https://huggingface.co/community/model-GGUF"],
            }
        ),
    )

    assert result["status"] == "rejected"
    assert db.get(TrendingModelCandidate, candidate.id).status == "rejected"
    refreshed = db.get(PaperCurationJob, row.id)
    assert refreshed.applied_at is not None
    assert refreshed.mutation_result["status"] == "rejected"


@pytest.mark.parametrize(
    ("paper_source", "thumbnail_url", "expected_thumbnail_status"),
    [
        ("external", None, "queued"),
        ("arxiv", None, "queued"),
        ("external", "https://example.com/thumbnail.jpg", None),
    ],
)
def test_callback_atomically_queues_thumbnail_for_external_resolution(
    monkeypatch, paper_source, thumbnail_url, expected_thumbnail_status
):
    db = _resolution_session()
    paper = Paper(
        title="Official Model Release",
        source=paper_source,
        source_url="https://example.com/model-release",
        arxiv_id="2608.12345" if paper_source == "arxiv" else None,
        thumbnail_url=thumbnail_url,
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="org/model",
        author="org",
        readme_sha="1" * 64,
        status="resolving",
    )
    db.add_all([paper, candidate])
    db.flush()
    row = PaperCurationJob(
        id=uuid.uuid4(),
        kind="resolve-model-paper",
        candidate_id=candidate.id,
        requested_by="hf-trending-cron",
        trigger="hf-trending-cron",
        policy_version="hf-trending-v1",
        priority=25,
        status="running",
    )
    db.add(row)
    db.commit()
    service = CodexCurationCallbackService(db)
    monkeypatch.setattr(
        service, "_allowed_resolution_paper_ids", lambda _candidate: {paper.id}
    )

    result = service._apply_authorized(
        row,
        ApplyMutationRequest(
            resolve_model_paper={
                "decision": "accept",
                "reason": "Official release with newly trained weights.",
                "novelty_kind": "new_weights",
                "evidence_urls": [paper.source_url],
                "existing_paper_id": paper.id,
                "model_release": {
                    "canonical_name": "Model",
                    "publisher": "org",
                    "is_open": True,
                    "aliases": ["org/model"],
                },
            }
        ),
    )

    assert result["paper_id"] == paper.id
    db.refresh(row)
    assert row.mutation_result["paper_id"] == paper.id
    assert row.thumbnail_status == expected_thumbnail_status
    assert (row.thumbnail_requested_at is not None) == (
        expected_thumbnail_status == "queued"
    )


def test_hourly_reconcile_queues_new_release_rejects_conversion_and_skips_unchanged(
    monkeypatch,
):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationBootstrapBundle.__table__,
            PaperCurationJob.__table__,
        ],
    )
    db = Session(engine)
    models = [
        HFTrendingModel.from_payload(
            {
                "id": "ornith-ai/Ornith-1.5-35B-A3B",
                "author": "ornith-ai",
                "tags": ["transformers", "eval-results"],
                "trending_score": 425,
            }
        ),
        HFTrendingModel.from_payload(
            {
                "id": "community/Ornith-1.5-35B-A3B-GGUF",
                "author": "community",
                "tags": [
                    "gguf",
                    "base_model:quantized:ornith-ai/Ornith-1.5-35B-A3B",
                ],
                "trending_score": 400,
            }
        ),
    ]

    class Discovery:
        @staticmethod
        def list_top_models():
            return models

    class Cards:
        calls = 0

        @classmethod
        def snapshot(cls, repo_id):
            cls.calls += 1
            assert repo_id == "ornith-ai/Ornith-1.5-35B-A3B"
            return HFModelCardSnapshot(
                repo_revision="a" * 40,
                readme_sha="b" * 64,
                markdown="# Ornith",
            )

    monkeypatch.setattr(
        "backend.services.codex_add_evals_service._git_revision", lambda: "HEAD"
    )
    service = HFTrendingModelCurationService(
        db,
        get_settings(),
        discovery=Discovery(),
        cards=Cards(),
    )

    first = service.reconcile(dispatch=False)
    second = service.reconcile(dispatch=False)

    assert first == {
        "discovered": 2,
        "queued": 1,
        "rejected_conversions": 1,
        "unchanged": 0,
        "errors": [],
        "queued_candidate_ids": [str(db.query(PaperCurationJob).one().candidate_id)],
    }
    assert second["queued"] == 0
    assert second["unchanged"] == 1
    assert db.query(PaperCurationJob).count() == 1
    assert (
        db.query(TrendingModelCandidate)
        .filter_by(repo_id="community/Ornith-1.5-35B-A3B-GGUF")
        .one()
        .status
        == "rejected"
    )


def test_hourly_reconcile_retries_substantive_rejection_after_family_paper_exists():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationBootstrapBundle.__table__,
            PaperCurationJob.__table__,
        ],
    )
    db = Session(engine)
    paper = Paper(
        title="Ornith 1.5",
        source="external",
        source_url="https://example.com/ornith-1.5",
        version="v1",
        is_latest_version=True,
    )
    candidate = TrendingModelCandidate(
        repo_id="ornith-ai/Ornith-1.5-9B",
        author="ornith-ai",
        readme_revision="a" * 40,
        readme_sha="b" * 64,
        status="rejected",
        rejection_reason="Substantive sibling, but no canonical paper found yet.",
    )
    db.add_all([paper, candidate])
    db.flush()
    queued_at = datetime(2026, 8, 26, 15, tzinfo=UTC)
    rejected_at = queued_at + timedelta(minutes=5)
    resolution_job = PaperCurationJob(
        id=uuid.uuid4(),
        kind="resolve-model-paper",
        candidate_id=candidate.id,
        requested_by="hf-trending-cron",
        trigger="hf-trending-cron",
        policy_version="hf-trending-v1",
        priority=25,
        status="failed",
        created_at=queued_at,
        submitted_at=rejected_at,
        proposal={
            "resolve_model_paper": {
                "decision": "reject",
                "novelty_kind": "uncertain",
                "reason": "No family paper existed when inspected.",
                "evidence_urls": ["https://huggingface.co/ornith-ai/Ornith-1.5-9B"],
            }
        },
    )
    db.add_all(
        [
            resolution_job,
            ModelRelease(
                paper_id=paper.id,
                canonical_name="Different-Family-7B",
                publisher="ornith-ai",
                canonical_source_url="https://example.com/different",
                aliases=["ornith-ai/Different-Family-7B"],
                is_open=True,
                created_at=rejected_at + timedelta(minutes=1),
            ),
            ModelRelease(
                paper_id=paper.id,
                canonical_name="Ornith-1.5-70B-A7B",
                publisher="ornith-ai",
                canonical_source_url="https://example.com/ornith-1.5",
                aliases=["ornith-ai/Ornith-1.5-70B-A7B"],
                is_open=True,
                created_at=queued_at + timedelta(minutes=1),
            ),
        ]
    )
    db.commit()

    convergence = HFTrendingModelCurationService(db, get_settings())
    assert not convergence._rejected_candidate_can_converge(candidate, resolution_job)

    db.add(
        ModelRelease(
            paper_id=paper.id,
            canonical_name="Ornith-1.5-35B-A3B",
            publisher="ornith-ai",
            canonical_source_url="https://example.com/ornith-1.5",
            aliases=["ornith-ai/Ornith-1.5-35B-A3B"],
            is_open=True,
            created_at=rejected_at + timedelta(minutes=2),
        )
    )
    db.commit()

    class Discovery:
        @staticmethod
        def list_top_models():
            return []

    class Cards:
        @staticmethod
        def snapshot(_repo_id):
            return HFModelCardSnapshot(
                repo_revision="a" * 40,
                readme_sha="b" * 64,
                markdown="# Ornith 1.5 9B",
            )

    queued = []

    class Jobs:
        @staticmethod
        def enqueue_resolution(_db, *, candidate, **_kwargs):
            candidate.status = "queued"
            queued.append(candidate.repo_id)

        @staticmethod
        def dispatch_next(*_args, **_kwargs):
            return None

    result = HFTrendingModelCurationService(
        db,
        get_settings(),
        discovery=Discovery(),
        cards=Cards(),
        jobs=Jobs(),
    ).reconcile(dispatch=False)

    assert result["queued"] == 1
    assert result["discovered"] == 0
    assert queued == ["ornith-ai/Ornith-1.5-9B"]


def test_rollout_freezes_canary_until_full_workflow_succeeds(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            TrendingModelCandidate.__table__,
            TrendingModelCurationState.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationBootstrapBundle.__table__,
            PaperCurationJob.__table__,
        ],
    )
    db = Session(engine)
    models = [
        HFTrendingModel.from_payload(
            {
                "id": f"org/model-{index}",
                "author": "org",
                "tags": ["transformers"],
                "trending_score": 100 - index,
            }
        )
        for index in range(2)
    ]

    class Discovery:
        @staticmethod
        def list_top_models():
            return models

    class Cards:
        @staticmethod
        def snapshot(repo_id):
            return HFModelCardSnapshot(
                repo_revision=("a" if repo_id.endswith("0") else "b") * 40,
                readme_sha=("c" if repo_id.endswith("0") else "d") * 64,
                markdown="# Model",
            )

    monkeypatch.setattr(
        "backend.services.codex_add_evals_service._git_revision", lambda: "HEAD"
    )
    service = HFTrendingModelCurationService(
        db,
        get_settings(),
        discovery=Discovery(),
        cards=Cards(),
        rollout=True,
    )

    dry = service.reconcile(dispatch=False, max_queued=1)
    canary = service.reconcile(dispatch=False, max_queued=1)
    paused = service.reconcile(dispatch=False, max_queued=1)

    assert dry["rollout_phase"] == "discovery_dry_run_completed"
    assert db.get(TrendingModelCurationState, 1).discovery_dry_run_completed is True
    assert canary["rollout_phase"] == "canary_started"
    assert len(canary["queued_candidate_ids"]) == 1
    assert paused["rollout_phase"] == "canary_in_progress"
    assert paused["queued"] == 0
    assert db.query(PaperCurationJob).count() == 1

    canary_candidate = db.get(
        TrendingModelCandidate,
        uuid.UUID(canary["queued_candidate_ids"][0]),
    )
    canary_candidate.status = "failed"
    db.query(PaperCurationJob).filter(
        PaperCurationJob.candidate_id == canary_candidate.id
    ).one().status = "failed"
    db.commit()

    retry = service.reconcile(dispatch=False, max_queued=1)

    assert retry["rollout_phase"] == "canary_in_progress"
    assert retry["retried_canary"] == 1
    assert db.query(PaperCurationJob).count() == 2
    assert canary_candidate.status == "queued"
    assert db.query(TrendingModelCandidate).count() == 1


def test_resolved_candidate_enqueues_workflow_and_missing_thumbnail(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            HfArtifact.__table__,
            PaperHfArtifact.__table__,
            ModelRelease.__table__,
            ModelReleaseArtifact.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
            PaperCurationBootstrapBundle.__table__,
            PaperCurationJob.__table__,
        ],
    )
    db = Session(engine)
    paper = Paper(
        title="Existing Family Report",
        source="external",
        source_url="https://example.com/family",
        version="v1",
        is_latest_version=True,
    )
    db.add(paper)
    db.flush()
    release = ModelRelease(
        paper_id=paper.id,
        canonical_name="Family Flash 0731",
        publisher="org",
        aliases=[],
    )
    db.add(release)
    db.flush()
    candidate = TrendingModelCandidate(
        repo_id="org/family-flash-0731",
        author="org",
        readme_sha="2" * 64,
        readme_revision="3" * 40,
        status="resolved",
        model_release_id=release.id,
    )
    db.add(candidate)
    db.commit()
    monkeypatch.setattr(
        "backend.services.codex_add_evals_service._git_revision", lambda: "HEAD"
    )

    created = CodexPaperJobService().enqueue_resolved_candidate_workflow(
        db, candidate, get_settings(), dispatch=False
    )

    assert created is True
    workflow = db.query(PaperCurationWorkflow).one()
    assert workflow.source_candidate_id == candidate.id
    assert workflow.source_revision == "3" * 40
    job = db.query(PaperCurationJob).one()
    assert job.kind == "enrich-paper"
    assert job.trigger == "hf-trending-cron"
    assert job.priority == 25
    assert job.thumbnail_status == "queued"
    assert job.thumbnail_requested_at is not None


def test_resolution_scope_excludes_publisher_only_sibling():
    db = _resolution_session()
    exact = Paper(
        title="Exact model report",
        source="external",
        source_url="https://example.com/exact",
        version="v1",
        is_latest_version=True,
    )
    sibling = Paper(
        title="Older publisher report",
        source="external",
        source_url="https://example.com/sibling",
        version="v1",
        is_latest_version=True,
    )
    artifact = HfArtifact(
        kind="model",
        repo_id="org/GLM-5.3-Flash",
        url="https://huggingface.co/org/GLM-5.3-Flash",
    )
    candidate = TrendingModelCandidate(
        repo_id="org/GLM-5.3-Flash",
        author="org",
        status="resolving",
    )
    db.add_all([exact, sibling, artifact, candidate])
    db.flush()
    db.add_all(
        [
            PaperHfArtifact(paper_id=exact.id, hf_artifact_id=artifact.id),
            ModelRelease(
                paper_id=sibling.id,
                canonical_name="GLM-5",
                publisher="org",
                aliases=["org/GLM-5"],
            ),
        ]
    )
    db.commit()

    service = CodexCurationCallbackService(db)

    assert service._allowed_resolution_paper_ids(candidate) == {exact.id}
    service.job_service = SimpleNamespace(
        serialize=lambda *_args: SimpleNamespace(model_dump=lambda **_kwargs: {})
    )
    context = service.context(
        SimpleNamespace(kind="resolve-model-paper", candidate_id=candidate.id),
        get_settings(),
    )
    assert [paper["id"] for paper in context["paper_candidates"]] == [exact.id]


@pytest.mark.parametrize("trigger", ["hf-trending-cron", "hf-daily-cron"])
def test_trending_eval_ownership_rejects_sibling_model_name(trigger):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            ModelProviderAlias.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
        ],
    )
    db = Session(engine)
    paper = Paper(
        title="GLM-5.3-Flash",
        source="external",
        source_url="https://example.com/glm-5.3-flash",
        version="v1",
        is_latest_version=True,
    )
    db.add(paper)
    db.flush()
    release = ModelRelease(
        paper_id=paper.id,
        canonical_name="GLM-5.3-Flash",
        publisher="zai-org",
        aliases=["zai-org/GLM-5.3-Flash"],
    )
    db.add(release)
    db.flush()
    db.add(
        ModelProviderAlias(
            model_release_id=release.id,
            provider="artificial-analysis",
            alias="glm-flash-aa",
        )
    )
    candidate = TrendingModelCandidate(
        repo_id="zai-org/GLM-5.3-Flash",
        author="zai-org",
        status="resolved",
        model_release_id=release.id,
    )
    db.add(candidate)
    db.flush()
    workflow = PaperCurationWorkflow(
        id=uuid.uuid4(),
        paper_id=paper.id,
        source_candidate_id=candidate.id,
        cohort_date=datetime.now(UTC).date(),
        cohort_order=0,
        policy_version="hf-trending-v1",
        status="running",
    )
    db.add(workflow)
    db.commit()
    row = SimpleNamespace(
        paper_id=paper.id,
        parent_workflow_id=workflow.id,
        trigger=trigger,
    )
    service = CodexCurationCallbackService(db)

    with pytest.raises(
        ValueError, match="does not belong to the resolved model release"
    ):
        service._validate_trending_model_ownership(
            row,
            ApplyMutationRequest(
                evaluations=[
                    {
                        "paper_id": paper.id,
                        "task_id": 1,
                        "dataset_id": 1,
                        "model_name": "GLM-5.3",
                        "metrics": {"Score": 0.8},
                        "best_metric": "Score",
                        "source_url": "https://example.com/source",
                    }
                ]
            ),
        )

    service._validate_trending_model_ownership(
        row,
        ApplyMutationRequest(
            evaluations=[
                {
                    "paper_id": paper.id,
                    "task_id": 1,
                    "dataset_id": 1,
                    "model_name": "GLM-5.3-Flash (Thinking)",
                    "metrics": {"Score": 0.8},
                    "best_metric": "Score",
                    "source_url": "https://example.com/source",
                }
            ]
        ),
    )
    service._validate_trending_model_ownership(
        row,
        ApplyMutationRequest(
            evaluations=[
                {
                    "paper_id": paper.id,
                    "task_id": 1,
                    "dataset_id": 1,
                    "model_name": "glm-flash-aa",
                    "metrics": {"Score": 0.8},
                    "best_metric": "Score",
                    "source_url": "https://artificialanalysis.ai/models/glm-flash-aa",
                }
            ]
        ),
    )


def test_trending_eval_ownership_accepts_point_release_card_scores():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            ModelRelease.__table__,
            ModelProviderAlias.__table__,
            TrendingModelCandidate.__table__,
            PaperCurationWorkflow.__table__,
        ],
    )
    db = Session(engine)
    paper = Paper(
        title="DeepSeek-V4.1",
        source="arxiv",
        arxiv_id="2609.00001",
        version="v1",
        is_latest_version=True,
    )
    db.add(paper)
    db.flush()
    release = ModelRelease(
        paper_id=paper.id,
        canonical_name="DeepSeek-V4.1-Flash-1017",
        publisher="deepseek-ai",
        aliases=[],
    )
    db.add(release)
    db.flush()
    candidate = TrendingModelCandidate(
        repo_id="deepseek-ai/DeepSeek-V4.1-Flash-1017",
        author="deepseek-ai",
        status="resolved",
        model_release_id=release.id,
    )
    db.add(candidate)
    db.flush()
    workflow = PaperCurationWorkflow(
        id=uuid.uuid4(),
        paper_id=paper.id,
        source_candidate_id=candidate.id,
        cohort_date=datetime.now(UTC).date(),
        cohort_order=0,
        policy_version="hf-trending-v1",
        status="running",
    )
    db.add(workflow)
    db.commit()
    row = SimpleNamespace(
        paper_id=paper.id, parent_workflow_id=workflow.id, trigger="hf-trending-cron"
    )
    service = CodexCurationCallbackService(db)

    def proposal(model_name):
        return ApplyMutationRequest(
            evaluations=[
                {
                    "paper_id": paper.id,
                    "task_id": 1,
                    "dataset_id": 1,
                    "model_name": model_name,
                    "metrics": {"Accuracy": 41.2},
                    "best_metric": "Accuracy",
                    "source_url": "https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017",
                }
            ]
        )

    # Card-only scores for the triggering point release belong to it.
    service._validate_trending_model_ownership(
        row, proposal("DeepSeek-V4.1-Flash-1017")
    )
    # The paper's earlier release cannot be relabeled onto this release's lane.
    with pytest.raises(
        ValueError, match="does not belong to the resolved model release"
    ):
        service._validate_trending_model_ownership(row, proposal("DeepSeek-V4.1-Flash"))


def test_triggered_add_evals_treats_pinned_card_as_first_party_release_evidence():
    runner = Path("jobs/run_paper_curation.py").read_text(encoding="utf-8")
    skill = Path(".agents/skills/remote-paper-curation/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "prioritize its paper-native model lanes" not in runner
    assert "first-party results for it even when the paper does not report" in runner
    assert "first-party evidence for the triggering release" in skill
    assert "never mark them `not_paper_native`" in skill


def test_trending_eval_requires_coverage_for_every_authoritative_source():
    row = SimpleNamespace(
        trigger="hf-trending-cron",
        url_candidates={
            "source_documents": [
                {"kind": "model_card", "url": "https://example.com/card"},
                {"kind": "paper_source", "url": "https://example.com/blog"},
            ]
        },
    )

    with pytest.raises(ValueError, match="every authoritative source"):
        CodexCurationCallbackService._validate_trending_source_coverage(
            row,
            ApplyMutationRequest(
                source_coverage=[
                    {
                        "url": "https://example.com/card",
                        "status": "inspected",
                        "benchmark_outcomes": [],
                    }
                ]
            ),
        )

    CodexCurationCallbackService._validate_trending_source_coverage(
        row,
        ApplyMutationRequest(
            source_coverage=[
                {
                    "url": "https://example.com/card",
                    "status": "inspected",
                    "benchmark_outcomes": [],
                },
                {
                    "url": "https://example.com/blog",
                    "status": "inspected",
                    "benchmark_outcomes": [
                        {
                            "benchmark": "MMLU-Pro",
                            "disposition": "already_present",
                            "detail": "Exact configured leaderboard already has this lane.",
                        }
                    ],
                },
            ]
        ),
    )


def test_trending_source_coverage_accepts_equivalent_repository_urls():
    row = SimpleNamespace(
        trigger="hf-trending-cron",
        url_candidates={
            "source_documents": [
                {
                    "kind": "github_readme",
                    "url": "https://github.com/Example/Model",
                },
                {
                    "kind": "model_card",
                    "url": "https://huggingface.co/Org/Model/raw/abc123/README.md",
                },
            ]
        },
    )

    CodexCurationCallbackService._validate_trending_source_coverage(
        row,
        ApplyMutationRequest(
            source_coverage=[
                {
                    "url": "https://raw.githubusercontent.com/Example/Model/main/README.md",
                    "status": "inspected",
                    "benchmark_outcomes": [],
                },
                {
                    "url": "https://huggingface.co/Org/Model",
                    "status": "inspected",
                    "benchmark_outcomes": [],
                },
            ]
        ),
    )


def test_hf_runner_survives_relocated_virtualenv(tmp_path, monkeypatch):
    from backend.services.hf_trending_model_discovery_service import _run
    import sys

    python = tmp_path / "bin" / "python"
    python.parent.mkdir()
    python.symlink_to(sys.executable)
    hf = python.with_name("hf")
    hf.write_text("#!/deleted-build-directory/bin/python\nprint('[]')\n")
    hf.chmod(0o755)
    monkeypatch.setattr(sys, "executable", str(python))
    assert _run([str(hf), "models", "list"]).strip() == "[]"


def test_scheduled_resolution_retry_reuses_active_candidate_job():
    from backend.services.hf_daily_curation_service import HFDailyCurationService

    db = _resolution_session()
    candidate = TrendingModelCandidate(
        repo_id="org/retry", author="org", status="queued"
    )
    db.add(candidate)
    db.flush()
    failed = PaperCurationJob(
        id=uuid.uuid4(),
        kind="resolve-model-paper",
        candidate_id=candidate.id,
        requested_by="cron",
        trigger="hf-trending-cron",
        status="failed",
    )
    active = PaperCurationJob(
        id=uuid.uuid4(),
        kind="resolve-model-paper",
        candidate_id=candidate.id,
        requested_by="cron",
        trigger="hf-trending-cron",
        status="queued",
        priority=25,
    )
    db.add_all([failed, active])
    db.commit()
    jobs = SimpleNamespace(
        dispatch_next=lambda *_args: None,
        serialize=lambda row, _settings: SimpleNamespace(
            model_dump=lambda **_kwargs: {"id": str(row.id)}
        ),
    )
    result = HFDailyCurationService(
        db, get_settings(), job_service=jobs
    ).retry_scheduled_job(failed.id)
    assert result["id"] == str(active.id)
    assert db.query(PaperCurationJob).count() == 2
    assert active.retry_of_id is None
    assert active.priority == 25


@pytest.mark.parametrize("has_orphan_retry", [False, True])
@pytest.mark.parametrize("direct_retry", [False, True])
def test_scheduled_retry_rejects_superseded_workflow_before_writes(
    has_orphan_retry, direct_retry
):
    from backend.services.hf_daily_curation_service import HFDailyCurationService

    db = _resolution_session()
    PaperCurationWorkflow.__table__.create(db.get_bind())
    db.execute(text("DROP INDEX uq_active_scheduled_paper_curation_stage"))
    db.execute(
        text(
            "CREATE UNIQUE INDEX uq_active_scheduled_paper_curation_stage ON paper_curation_jobs(paper_id, kind, policy_version) WHERE trigger <> 'admin' AND status IN ('queued', 'dispatching', 'running')"
        )
    )
    db.execute(text("DROP INDEX uq_active_paper_curation_workflow"))
    db.execute(
        text(
            "CREATE UNIQUE INDEX uq_active_paper_curation_workflow ON paper_curation_workflows(paper_id) WHERE status IN ('queued', 'running', 'deferred')"
        )
    )
    paper = Paper(
        title="Retry report",
        source="external",
        source_url="https://example.com/retry",
        version="v1",
        is_latest_version=True,
    )
    db.add(paper)
    db.flush()
    old = PaperCurationWorkflow(
        id=uuid.uuid4(),
        paper_id=paper.id,
        cohort_date=datetime.now(UTC).date(),
        policy_version="hf-trending-v1",
        status="partial",
    )
    current = PaperCurationWorkflow(
        id=uuid.uuid4(),
        paper_id=paper.id,
        cohort_date=datetime.now(UTC).date(),
        policy_version="hf-trending-v1",
        status="queued",
    )
    db.add_all([old, current])
    db.flush()
    failed = PaperCurationJob(
        id=uuid.uuid4(),
        kind="add-evals",
        paper_id=paper.id,
        parent_workflow_id=old.id,
        requested_by="cron",
        trigger="hf-trending-cron",
        status="failed",
    )
    db.add(failed)
    db.flush()
    if has_orphan_retry:
        db.add(
            PaperCurationJob(
                id=uuid.uuid4(),
                kind="add-evals",
                paper_id=paper.id,
                parent_workflow_id=old.id,
                requested_by="cron",
                trigger="hf-trending-cron",
                status="queued",
                retry_of_id=failed.id,
            )
        )
    db.commit()
    count = db.query(PaperCurationJob).count()
    if direct_retry:
        # Even if ownership changes after the operator precheck, the DB invariant
        # fails before enqueue's commit can leave behind an orphan job.
        with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
            CodexPaperJobService().retry(db, failed, get_settings(), priority=50)
        db.rollback()
    else:
        service = HFDailyCurationService(
            db, get_settings(), job_service=SimpleNamespace()
        )
        with pytest.raises(ValueError, match=f"active workflow {current.id}"):
            service.retry_scheduled_job(failed.id)
    assert db.query(PaperCurationJob).count() == count
    assert db.get(PaperCurationWorkflow, old.id).status == "partial"
    assert not db.dirty


@pytest.mark.parametrize(
    ("names", "title", "abstract", "conflict"),
    [
        # 2026-10-25: Nanbeige4.3-33B was resolved to the 4.2-3B report.
        (
            ["Nanbeige/Nanbeige4.3-33B", "Nanbeige4.3"],
            "Nanbeige4.2-3B: Unlocking Agentic Capabilities in a Compact Model",
            "",
            True,
        ),
        (
            ["Nanbeige/Nanbeige4.2-3B-FP8"],
            "Nanbeige4.2-3B: Unlocking Agentic Capabilities in a Compact Model",
            "",
            False,
        ),
        (["Kimi K3.1 Pro"], "Kimi K3: Open Frontier Intelligence", "", True),
        (["Qwen/Qwen3.8-27B"], "Qwen3.8 Technical Report", "", False),
        (["Qwen/Qwen3.8-27B"], "Qwen3 Technical Report", "", True),
        (["MiniMaxAI/MiniMax-M3.1-Flash"], "MiniMax-M3: Scaling", "", True),
        (["deepseek-ai/DeepSeek-V4.1-Flash"], "DeepSeek-V4: Towards", "", True),
        (["google/gemma-4-31b-it"], "Gemma 4 Technical Report", "", False),
        # Parameter counts are not versions; unnamed families are not checked.
        (["openai/gpt-oss-120b"], "gpt-oss-120b & gpt-oss-20b Model Card", "", False),
        (["org/Model-2"], "Attention Is All You Need", "", False),
        # A report whose abstract covers the point release is accepted.
        (
            ["meta-llama/Llama-3.1-8B"],
            "The Llama 3 Herd of Models",
            "We present Llama 3.1, a herd of language models.",
            False,
        ),
        (["meta-llama/Llama-3.1-8B"], "The Llama 3 Herd of Models", "", True),
        # A coarse family alias does not cancel the release's own version.
        (
            ["Nanbeige/Nanbeige4.3-33B", "Nanbeige4"],
            "Nanbeige4-3B Technical Report",
            "",
            True,
        ),
    ],
)
def test_release_version_conflict(names, title, abstract, conflict):
    assert bool(release_version_conflict(names, title, abstract)) is conflict


def test_resolution_refuses_another_versions_arxiv_report(monkeypatch):
    db = _resolution_session()
    candidate = TrendingModelCandidate(
        repo_id="Nanbeige/Nanbeige4.3-33B",
        author="Nanbeige",
        readme_sha="7" * 64,
        status="resolving",
    )
    db.add(candidate)
    db.commit()

    async def import_arxiv(_service, arxiv_id, *, commit=True):
        paper = Paper(
            title="Nanbeige4.2-3B: Unlocking Agentic Capabilities in a Compact Model",
            source="arxiv",
            arxiv_id=arxiv_id,
            version="v1",
            is_latest_version=True,
        )
        db.add(paper)
        db.flush()
        return paper, True

    monkeypatch.setattr(
        "backend.services.paper_ingestion_service.PaperIngestionService.get_or_import_arxiv_paper",
        import_arxiv,
    )
    mutation = ResolveModelPaperMutation.model_validate(
        {
            "decision": "accept",
            "reason": "The closest canonical Nanbeige paper is the 4.2-3B report.",
            "novelty_kind": "new_release",
            "evidence_urls": ["https://arxiv.org/abs/2607.22083"],
            "arxiv_id": "2607.22083",
            "model_release": {
                "canonical_name": "Nanbeige4.3-33B",
                "publisher": "Nanbeige",
                "is_open": True,
                "aliases": ["Nanbeige4.3"],
            },
        }
    )
    with pytest.raises(ValueError, match="not this release's nanbeige 4.3"):
        TrendingModelResolutionService(db).apply(candidate.id, mutation, commit=False)
    db.rollback()
    assert db.query(ModelRelease).count() == 0
    assert db.query(Paper).filter_by(arxiv_id="2607.22083").count() == 0


def test_external_upgrade_moves_method_evidence_and_skips_same_name_authors():
    db = _resolution_session()
    external = Paper(
        title="Model Release",
        source="external",
        source_url="https://org.example/model",
        version="v1",
        is_latest_version=True,
    )
    arxiv = Paper(
        title="Model Technical Report",
        source="arxiv",
        arxiv_id="2607.22083",
        version="v1",
        is_latest_version=True,
    )
    alice_external, alice_arxiv, bob = (
        Author(name="Alice Chen"),
        Author(name="alice chen"),
        Author(name="Bob Li"),
    )
    db.add_all([external, arxiv, alice_external, alice_arxiv, bob])
    db.flush()
    db.add_all(
        [
            PaperAuthor(
                paper_id=external.id, author_id=alice_external.id, author_order=0
            ),
            PaperAuthor(paper_id=external.id, author_id=bob.id, author_order=1),
            PaperAuthor(paper_id=arxiv.id, author_id=alice_arxiv.id, author_order=0),
            PaperMethod(paper_id=external.id, method_id=7),
            PaperMethodEvidence(
                paper_id=external.id, method_id=7, evidence_type="curation"
            ),
        ]
    )
    db.commit()

    TrendingModelResolutionService(db)._upgrade_external_paper(external, arxiv)
    db.commit()

    # The method link and its evidence move together; the old link is gone.
    assert db.get(PaperMethod, (arxiv.id, 7)) is not None
    assert db.get(PaperMethodEvidence, (arxiv.id, 7, "curation")) is not None
    assert db.query(PaperMethod).filter_by(paper_id=external.id).count() == 0
    # "Alice Chen" is already listed under another author record; Bob moves.
    authors = {
        row.author_id
        for row in db.query(PaperAuthor).filter_by(paper_id=arxiv.id).all()
    }
    assert authors == {alice_arxiv.id, bob.id}
    assert db.get(Paper, external.id).is_latest_version is False
