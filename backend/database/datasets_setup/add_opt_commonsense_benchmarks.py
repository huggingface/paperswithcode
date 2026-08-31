#!/usr/bin/env python3
"""Add StoryCloze, Winograd, and COPA benchmarks and OPT-175B zero-shot evals."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.evaluations import DatasetCreateRequest
from backend.models.database import Paper
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)

REASONING_TASK_ID = 21
ACCURACY_METRIC_ID = 18
OPT_PAPER_ID = 8907
OPT_SOURCE_URL = "https://arxiv.org/abs/2205.01068"
OPT_NUM_PARAMETERS = 175_000_000_000

BENCHMARKS = [
    {
        "name": "StoryCloze",
        "full_name": "Story Cloze Test",
        "description": (
            "Story Cloze Test evaluates commonsense story understanding by asking models "
            "to choose the correct ending to a four-sentence story. It was introduced "
            "alongside the ROCStories corpus of everyday commonsense narratives."
        ),
        "short_description": (
            "Choose the correct ending to a four-sentence commonsense story."
        ),
        "homepage": "https://huggingface.co/datasets/story_cloze",
        "introduced_date": date(2016, 4, 6),
        "source_kind": "arxiv",
        "source_arxiv_id": "1604.01696",
        "eval_score": "82.1",
        "eval_methodology": (
            "Zero-shot accuracy from metaseq OPT chronicles initial eval table "
            "(GPTZ 175B @ 125k steps); matches paper Appendix A Figure 6."
        ),
    },
    {
        "name": "Winograd",
        "full_name": "Winograd Schema Challenge",
        "description": (
            "The Winograd Schema Challenge tests commonsense reasoning with sentence "
            "pairs that differ in one or two words and contain an ambiguous pronoun "
            "resolved differently in each sentence."
        ),
        "short_description": (
            "Resolve ambiguous pronouns in paired commonsense reasoning sentences."
        ),
        "homepage": "https://cs.nyu.edu/faculty/davise/papers/WinogradSchemas/WS.html",
        "introduced_date": date(2012, 1, 1),
        "source_kind": "external",
        "source_url": "http://www.aaai.org/ocs/index.php/KR/KR12/paper/view/4492",
        "source_title": "The Winograd Schema Challenge",
        "source_abstract": (
            "The Winograd Schema Challenge is an alternative to the Turing Test that "
            "measures a system's ability to perform commonsense reasoning by resolving "
            "pronouns in sentence pairs that require world knowledge to disambiguate."
        ),
        "source_authors": ["Hector J. Levesque", "Ernest Davis", "Leora Morgenstern"],
        "eval_score": "85",
        "eval_methodology": (
            "Zero-shot accuracy read from paper Appendix A Figure 6 (figures/nlp.pdf) "
            "at 175B parameters; GPT-3 prompt replication setup."
        ),
    },
    {
        "name": "COPA",
        "full_name": "Choice of Plausible Alternatives",
        "description": (
            "COPA evaluates open-domain commonsense causal reasoning with 1000 premise "
            "pairs where the model must choose the more plausible alternative."
        ),
        "short_description": (
            "Choose the more plausible causal alternative for a commonsense premise."
        ),
        "homepage": "https://people.ict.usc.edu/~gordon/copa.html",
        "introduced_date": date(2011, 1, 1),
        "source_kind": "external",
        "source_url": "http://www.aaai.org/ocs/index.php/SSS/SSS11/paper/view/2418",
        "source_title": (
            "Choice of Plausible Alternatives: An Evaluation of Commonsense Causal Reasoning"
        ),
        "source_abstract": (
            "COPA provides 1000 questions for assessing progress in open-domain commonsense "
            "causal reasoning. Each item has a premise and two alternatives, and the task "
            "is to select the alternative that more plausibly has a causal relation with "
            "the premise."
        ),
        "source_authors": [
            "Melissa Roemmele",
            "Cosmin Adrian Bejan",
            "Andrew S. Gordon",
        ],
        "eval_score": "87",
        "eval_methodology": (
            "Zero-shot accuracy read from paper Appendix A Figure 6 (figures/nlp.pdf) "
            "at 175B parameters; GPT-3 prompt replication setup."
        ),
    },
]


def ensure_source_paper(session, spec: dict) -> Paper:
    if spec["source_kind"] == "arxiv":
        paper = (
            session.query(Paper)
            .filter(
                Paper.arxiv_id == spec["source_arxiv_id"],
                Paper.is_latest_version.is_(True),
            )
            .first()
        )
        if not paper:
            raise RuntimeError(f"Missing arXiv paper {spec['source_arxiv_id']}")
        return paper

    existing = (
        session.query(Paper)
        .filter(
            Paper.source == "external",
            Paper.source_url == spec["source_url"],
        )
        .first()
    )
    if existing:
        return existing

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=spec["source_url"],
            title=spec["source_title"],
            abstract=spec["source_abstract"],
            authors=spec["source_authors"],
            date_published=spec["introduced_date"],
        )
    )
    return result.paper


def ensure_dataset(session, spec: dict, source_paper: Paper) -> int:
    slug = spec["name"].lower().replace(" ", "-")
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"), {"slug": slug}
    ).first()
    paper_url = (
        f"https://paperswithcode.co/paper/{source_paper.arxiv_id}"
        if source_paper.arxiv_id
        else f"https://paperswithcode.co/paper/{source_paper.id}"
    )
    if row:
        dataset_id = int(row[0])
    else:
        created = DatasetService(session).create_dataset(
            DatasetCreateRequest(
                name=spec["name"],
                full_name=spec["full_name"],
                description=spec["description"],
                short_description=spec["short_description"],
                homepage=spec["homepage"],
                paper_url=paper_url,
                introduced_date=spec["introduced_date"],
                task_ids=[REASONING_TASK_ID],
                languages=["English"],
                modalities=["Text"],
            )
        )
        dataset_id = int(created.id)

    session.execute(
        text(
            """
            UPDATE datasets
            SET introducing_paper_id = :pid,
                introducing_paper_title = :title,
                paper_url = :paper_url,
                introduced_year = COALESCE(introduced_year, :year),
                homepage = COALESCE(homepage, :homepage),
                full_name = COALESCE(full_name, :full_name),
                short_description = COALESCE(short_description, :short_description)
            WHERE id = :did
            """
        ),
        {
            "pid": source_paper.id,
            "title": source_paper.title,
            "paper_url": paper_url,
            "year": spec["introduced_date"].year,
            "homepage": spec["homepage"],
            "full_name": spec["full_name"],
            "short_description": spec["short_description"],
            "did": dataset_id,
        },
    )
    session.execute(
        text(
            "INSERT INTO task_datasets (task_id, dataset_id) "
            "VALUES (:t, :d) ON CONFLICT (task_id, dataset_id) DO NOTHING"
        ),
        {"t": REASONING_TASK_ID, "d": dataset_id},
    )
    session.execute(
        text(
            "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
            "VALUES (:t, :d, :m) ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
        ),
        {"t": REASONING_TASK_ID, "d": dataset_id, "m": ACCURACY_METRIC_ID},
    )
    session.execute(
        text(
            "INSERT INTO paper_tasks (paper_id, task_id, source) "
            "VALUES (:p, :t, 'manual') "
            "ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'"
        ),
        {"p": source_paper.id, "t": REASONING_TASK_ID},
    )
    return dataset_id


def ensure_opt_eval(session, dataset_id: int, score: str, methodology: str) -> str:
    params = {
        "paper_id": OPT_PAPER_ID,
        "task_id": REASONING_TASK_ID,
        "dataset_id": dataset_id,
        "model_name": "OPT-175B",
        "best_metric": "Accuracy",
    }
    existing = session.execute(
        text(
            """
            SELECT id FROM evaluations
            WHERE paper_id = :paper_id AND task_id = :task_id AND dataset_id = :dataset_id
              AND model_name = :model_name
              AND COALESCE(harness, '') = ''
              AND best_metric = :best_metric
            """
        ),
        params,
    ).first()
    if existing:
        return "exists"

    EvaluationService(session).create_evaluation(
        paper_id=OPT_PAPER_ID,
        task_id=REASONING_TASK_ID,
        dataset_id=dataset_id,
        model_name="OPT-175B",
        methodology=methodology,
        metrics={"Accuracy": score},
        best_metric="Accuracy",
        harness=None,
        external_source_url=OPT_SOURCE_URL,
        num_parameters=OPT_NUM_PARAMETERS,
    )
    return "created"


def main() -> None:
    session = db_manager.session_local()
    try:
        for spec in BENCHMARKS:
            source_paper = ensure_source_paper(session, spec)
            dataset_id = ensure_dataset(session, spec, source_paper)
            eval_status = ensure_opt_eval(
                session,
                dataset_id,
                spec["eval_score"],
                spec["eval_methodology"],
            )
            paper_ref = (
                source_paper.arxiv_id if source_paper.arxiv_id else str(source_paper.id)
            )
            print(
                f"{spec['name']}: dataset_id={dataset_id}, "
                f"source=https://paperswithcode.co/paper/{paper_ref}, eval={eval_status}"
            )
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    main()
