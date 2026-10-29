from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.models.database import (
    Base,
    Evaluation,
    Metric,
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


def _evaluation(
    evaluation_id: int,
    paper_id: int,
    dataset_id: int,
    model_name: str = "TRGv2",
    mae: float = 3.64,
    best_rank: int | None = None,
) -> Evaluation:
    return Evaluation(
        id=evaluation_id,
        paper_id=paper_id,
        task_id=1,
        dataset_id=dataset_id,
        model_name=model_name,
        metrics={"MAE": mae},
        best_metric="MAE",
        best_rank=best_rank,
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
        Metric,
    )
    Base.metadata.create_all(bind=engine, tables=[m.__table__ for m in models])
    with sessionmaker(bind=engine)() as db:
        db.add_all(
            [
                Paper(id=1, arxiv_id="2407.14136", version="v1", title="Old"),
                Paper(id=2, arxiv_id="2407.14136", version="v2", title="New"),
                Paper(id=3, arxiv_id="2501.00001", version="v1", title="Other"),
                Metric(id=1, name="MAE", direction="lower_is_better"),
            ]
        )
        # Dataset 2 already shows the model from v2, spelled differently.
        db.add_all(
            [
                _evaluation(7, 1, 1, best_rank=1),
                # A second copy on the old version collapses into row 7.
                _evaluation(11, 1, 1, model_name="trgv2", best_rank=1),
                _evaluation(8, 1, 2, best_rank=1),
                _evaluation(9, 2, 2, model_name="TRG v2", best_rank=1),
                _evaluation(10, 3, 2, model_name="Other", mae=4.0, best_rank=3),
            ]
        )
        db.flush()

        PaperVersionRefreshService(
            db, paper_factory=lambda _paper_id: None
        )._copy_curated_links(1, 2)
        db.flush()

        # Leaderboards list every version, so a copy would show the model twice;
        # the board that lost a row is re-ranked.
        rows = db.query(Evaluation.id, Evaluation.paper_id, Evaluation.best_rank)
        assert rows.order_by(Evaluation.id).all() == [
            (7, 2, 1),
            (9, 2, 1),
            (10, 3, 2),
        ]
