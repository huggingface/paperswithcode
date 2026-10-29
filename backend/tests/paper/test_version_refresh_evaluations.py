from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.models.database import (
    Base,
    Evaluation,
    Paper,
    PaperConference,
    PaperDataset,
    PaperHfArtifact,
    PaperMethod,
    PaperOrganization,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
)
from backend.services.paper_version_refresh_service import PaperVersionRefreshService


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


def _evaluation(evaluation_id: int, paper_id: int, dataset_id: int) -> Evaluation:
    return Evaluation(
        id=evaluation_id,
        paper_id=paper_id,
        task_id=1,
        dataset_id=dataset_id,
        model_name="TRGv2",
        metrics={"MAE": 3.64},
        best_metric="MAE",
    )


def test_version_refresh_moves_evaluations_to_the_new_version(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'refresh.db'}")
    models = (
        Paper,
        PaperTask,
        PaperMethod,
        PaperRepository,
        PaperProjectPage,
        PaperHfArtifact,
        PaperConference,
        PaperOrganization,
        PaperDataset,
        Evaluation,
    )
    Base.metadata.create_all(bind=engine, tables=[m.__table__ for m in models])
    with sessionmaker(bind=engine)() as db:
        db.add_all(
            [
                Paper(id=1, arxiv_id="2407.14136", version="v1", title="Old"),
                Paper(id=2, arxiv_id="2407.14136", version="v2", title="New"),
            ]
        )
        # Row 8 is already on the new version; row 7 is not.
        db.add_all([_evaluation(7, 1, 1), _evaluation(8, 1, 2), _evaluation(9, 2, 2)])
        db.flush()

        PaperVersionRefreshService(
            db, paper_factory=lambda _paper_id: None
        )._copy_curated_links(1, 2)
        db.flush()

        # Leaderboards list every version, so a copy would show the model twice.
        rows = db.query(Evaluation.id, Evaluation.paper_id).order_by(Evaluation.id)
        assert rows.all() == [(7, 2), (9, 2)]
