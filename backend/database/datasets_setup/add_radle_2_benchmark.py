#!/usr/bin/env python3
"""Add the RadLE 2.0 medical imaging benchmark and leaderboard rows."""

from __future__ import annotations

import json
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

TASK_SLUG = "medical-imaging"
BENCHMARK_NAME = "Radiology's Last Exam 2.0 (RadLE 2.0)"
BENCHMARK_SLUG = "radiology-s-last-exam-2-0-radle-2-0"
REPORT_URL = "https://crashlab.in/radle-technicalreport"
LEADERBOARD_URL = "https://crashlab.in/radle/2/leaderboard"
INTRODUCED_DATE = date(2026, 7, 14)

SOURCE_SPEC = {
    "source_url": REPORT_URL,
    "title": (
        "Radiology's Last Exam (RadLE) 2.0: "
        "Are we ready for Autonomous AI Diagnosis in Radiology?"
    ),
    "abstract": (
        "CRASH Lab's RadLE 2.0 technical report describes an uncertainty-aware "
        "radiology benchmark for autonomous diagnosis. It evaluates whether AI "
        "systems provide correct diagnoses, calibrate confidence, avoid confident "
        "errors, and know when to defer to a human specialist."
    ),
    "authors": [
        "Suvrankar Datta",
        "Divya Buchireddygari",
        "Hakikat Bir Singh Bhatti",
        "CRASH Lab",
    ],
    "date_published": INTRODUCED_DATE,
}

MODEL_SPECS = {
    "claude_fable_5": {
        "query": "Claude Fable 5 and Claude Mythos 5",
        "model_name": "Claude Fable 5",
        "provider": "Anthropic",
        "score": "758",
        "is_open": False,
    },
    "meta_muse_spark_1_1": {
        "source_url": "https://developer.meta.com/ai/resources/blog/build-with-muse-spark/",
        "title": "Build with Muse Spark, now available on Meta Model API",
        "abstract": (
            "Meta's Muse Spark 1.1 model release introduces an agentic, "
            "multimodal reasoning model available through the Meta Model API."
        ),
        "authors": ["Meta"],
        "date_published": date(2026, 7, 9),
        "model_name": "Meta Muse Spark 1.1",
        "provider": "Meta Model API",
        "score": "735",
        "is_open": False,
    },
    "gpt_5_6_sol_pro": {
        "query": "GPT-5.6: Frontier intelligence that scales with your ambition",
        "model_name": "GPT-5.6 Sol Pro",
        "provider": "OpenAI",
        "score": "665",
        "is_open": False,
    },
    "gemini_3_1_pro": {
        "query": "Gemini 3.1 Pro: A smarter model for your most complex tasks",
        "model_name": "Gemini 3.1 Pro",
        "provider": "Google",
        "score": "660",
        "is_open": False,
    },
    "octomed_7b": {
        "arxiv_id": "2511.23269",
        "model_name": "OctoMed 7B",
        "provider": "OctoMed (academic)",
        "score": "541",
        "is_open": True,
        "num_parameters": 7_000_000_000,
    },
    "grok_4_5": {
        "query": "Introducing Grok 4.5",
        "model_name": "Grok 4.5",
        "provider": "xAI",
        "score": "524",
        "is_open": False,
    },
    "nemotron_3_omni": {
        "arxiv_id": "2604.24954",
        "model_name": "Nemotron 3 Omni",
        "provider": "Nvidia",
        "score": "476",
        "is_open": True,
        "num_parameters": 30_000_000_000,
    },
    "qwen_3_7_plus": {
        "query": "Qwen3.7-Plus",
        "model_name": "Qwen 3.7 Plus",
        "provider": "Alibaba",
        "score": "472",
        "is_open": False,
    },
    "glm_5v_turbo": {
        "arxiv_id": "2604.26752",
        "model_name": "GLM-5V Turbo",
        "provider": "Z.AI",
        "score": "409",
        "is_open": False,
    },
    "minimax_m3": {
        "query": "MiniMax M3: Frontier Coding, 1M Context, Native Multimodality",
        "model_name": "MiniMax M3",
        "provider": "MiniMax",
        "score": "350",
        "is_open": True,
    },
    "gemma_4_31b": {
        "arxiv_id": "2607.02770",
        "model_name": "Gemma 4 31B",
        "provider": "Google",
        "score": "336",
        "is_open": True,
        "num_parameters": 31_000_000_000,
    },
    "lingshu_32b": {
        "arxiv_id": "2506.07044",
        "model_name": "Lingshu 32B",
        "provider": "Alibaba DAMO Academy",
        "score": "284",
        "is_open": True,
        "num_parameters": 32_000_000_000,
    },
    "medgemma_1_5_4b": {
        "arxiv_id": "2604.05081",
        "model_name": "MedGemma 1.5 4B",
        "provider": "Google",
        "score": "277",
        "is_open": True,
        "num_parameters": 4_000_000_000,
    },
    "llama_4_maverick": {
        "query": "The Llama 4 herd: The beginning of a new era of natively multimodal AI innovation",
        "model_name": "Llama 4 Maverick",
        "provider": "Meta",
        "score": "263",
        "is_open": True,
        "num_parameters": 400_000_000_000,
    },
    "internvl_3_5_8b": {
        "arxiv_id": "2508.18265",
        "model_name": "InternVL 3.5 8B",
        "provider": "OpenGVLab",
        "score": "241",
        "is_open": True,
        "num_parameters": 8_000_000_000,
    },
    "mistral_lg_3_2512": {
        "query": "Mistral Large 3",
        "model_name": "Mistral Lg 3 2512",
        "provider": "Mistral AI",
        "score": "181",
        "is_open": False,
    },
}

METRICS = [
    {
        "name": "RadLE-C",
        "full_name": "RadLE-C Confidence Weighted Index",
        "scale": "0-2000",
        "description": (
            "Primary RadLE 2.0 metric: net confidence-weighted diagnostic utility."
        ),
    },
    {
        "name": "RadLE-R",
        "full_name": "RadLE-R Reliability Index",
        "scale": "0-100",
        "description": ("Reliability of high-confidence autonomous-level diagnoses."),
    },
    {
        "name": "RadLE-A",
        "full_name": "RadLE-A Accuracy Index",
        "scale": "0-100",
        "description": "Raw diagnostic accuracy across RadLE 2.0 cases.",
    },
    {
        "name": "RadLE-S",
        "full_name": "RadLE-S Safety Index",
        "scale": "0-100",
        "description": "Avoidance of confidence-weighted diagnostic errors.",
    },
    {
        "name": "RadLE-H",
        "full_name": "RadLE-H Handover Readiness Index",
        "scale": "0-100",
        "description": (
            "Readiness to handle cases autonomously or defer to a specialist."
        ),
    },
]


def ensure_external_paper(session, spec: dict) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.source == "external", Paper.source_url == spec["source_url"])
        .first()
    )
    if existing:
        return existing

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=spec["source_url"],
            title=spec["title"],
            abstract=spec["abstract"],
            authors=spec["authors"],
            date_published=spec["date_published"],
        )
    )
    return result.paper


def find_paper(session, spec: dict) -> Paper:
    if "arxiv_id" in spec:
        paper = (
            session.query(Paper)
            .filter(Paper.arxiv_id == spec["arxiv_id"], Paper.is_latest_version)
            .first()
        )
        if paper is None:
            raise RuntimeError(f"Missing arXiv paper {spec['arxiv_id']}")
        return paper

    if "source_url" in spec:
        return ensure_external_paper(session, spec)

    paper = (
        session.query(Paper)
        .filter(Paper.title.ilike(f"%{spec['query']}%"))
        .order_by(Paper.id.desc())
        .first()
    )
    if paper is None:
        raise RuntimeError(f"Missing paper matching {spec['query']!r}")
    return paper


def paper_url(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def ensure_metrics(session) -> dict[str, int]:
    metric_ids: dict[str, int] = {}
    for metric in METRICS:
        session.execute(
            text(
                """
                INSERT INTO metrics (name, full_name, direction, scale, description)
                VALUES (:name, :full_name, 'higher_is_better', :scale, :description)
                ON CONFLICT (name) DO UPDATE
                SET full_name = EXCLUDED.full_name,
                    direction = EXCLUDED.direction,
                    scale = EXCLUDED.scale,
                    description = EXCLUDED.description
                """
            ),
            metric,
        )
        metric_ids[metric["name"]] = int(
            session.execute(
                text("SELECT id FROM metrics WHERE name = :name"),
                {"name": metric["name"]},
            ).scalar_one()
        )
    return metric_ids


def ensure_dataset(session, task_id: int, source_paper: Paper) -> int:
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": BENCHMARK_SLUG},
    ).first()
    source_url = paper_url(source_paper)
    if row:
        dataset_id = int(row[0])
    else:
        created = DatasetService(session).create_dataset(
            DatasetCreateRequest(
                name=BENCHMARK_NAME,
                full_name=(
                    "Radiology's Last Exam 2.0: A Benchmark for Autonomous "
                    "Diagnosis by AI Agents in Radiology"
                ),
                description=(
                    "RadLE 2.0 is an uncertainty-aware radiology diagnosis "
                    "benchmark from CRASH Lab. Models diagnose single-image "
                    "radiology cases with confidence scores or explicit "
                    "deferrals, and are evaluated on confidence-weighted "
                    "utility, reliability, accuracy, safety, and handover "
                    "readiness."
                ),
                short_description=(
                    "Uncertainty-aware autonomous radiology diagnosis benchmark."
                ),
                homepage=LEADERBOARD_URL,
                paper_url=source_url,
                introduced_date=INTRODUCED_DATE,
                task_ids=[task_id],
                modalities=["Images", "Text"],
                languages=["English"],
            )
        )
        dataset_id = int(created.id)

    session.execute(
        text(
            """
            UPDATE datasets
            SET name = :name,
                full_name = :full_name,
                description = :description,
                short_description = :short_description,
                homepage = :homepage,
                paper_url = :paper_url,
                introducing_paper_id = :paper_id,
                introducing_paper_title = :paper_title,
                introduced_date = :introduced_date,
                introduced_year = :introduced_year,
                modalities = CAST(:modalities AS jsonb),
                languages = CAST(:languages AS jsonb)
            WHERE id = :dataset_id
            """
        ),
        {
            "name": BENCHMARK_NAME,
            "full_name": (
                "Radiology's Last Exam 2.0: A Benchmark for Autonomous "
                "Diagnosis by AI Agents in Radiology"
            ),
            "description": (
                "RadLE 2.0 is an uncertainty-aware radiology diagnosis benchmark "
                "from CRASH Lab. Models diagnose single-image radiology cases "
                "with confidence scores or explicit deferrals, and are evaluated "
                "on confidence-weighted utility, reliability, accuracy, safety, "
                "and handover readiness."
            ),
            "short_description": (
                "Uncertainty-aware autonomous radiology diagnosis benchmark."
            ),
            "homepage": LEADERBOARD_URL,
            "paper_url": source_url,
            "paper_id": source_paper.id,
            "paper_title": source_paper.title,
            "introduced_date": INTRODUCED_DATE,
            "introduced_year": INTRODUCED_DATE.year,
            "modalities": '["Images", "Text"]',
            "languages": '["English"]',
            "dataset_id": dataset_id,
        },
    )
    return dataset_id


def ensure_task_links(
    session, task_id: int, dataset_id: int, metric_ids: dict[str, int]
) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, FALSE)
            ON CONFLICT (task_id, dataset_id) DO NOTHING
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )
    for metric_id in metric_ids.values():
        session.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:task_id, :dataset_id, :metric_id)
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id},
        )


def ensure_paper_task(session, paper_id: int, task_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )


def ensure_eval(
    session, task_id: int, dataset_id: int, paper: Paper, spec: dict
) -> str:
    existing = session.execute(
        text(
            """
            SELECT id
            FROM evaluations
            WHERE paper_id = :paper_id
              AND task_id = :task_id
              AND dataset_id = :dataset_id
              AND model_name = :model_name
              AND COALESCE(harness, '') = ''
              AND best_metric = 'RadLE-C'
            """
        ),
        {
            "paper_id": paper.id,
            "task_id": task_id,
            "dataset_id": dataset_id,
            "model_name": spec["model_name"],
        },
    ).first()
    if existing:
        session.execute(
            text(
                """
                UPDATE evaluations
                SET metrics = CAST(:metrics AS jsonb),
                    methodology = :methodology,
                    uses_additional_data = FALSE,
                    is_open = :is_open,
                    evaluated_on = :evaluated_on,
                    source_url = :source_url,
                    external_source_url = :source_url,
                    external = TRUE,
                    num_parameters = :num_parameters,
                    updated_at = NOW()
                WHERE id = :id
                """
            ),
            {
                "metrics": json.dumps({"RadLE-C": spec["score"]}),
                "methodology": methodology(spec),
                "is_open": spec["is_open"],
                "evaluated_on": INTRODUCED_DATE,
                "source_url": LEADERBOARD_URL,
                "num_parameters": spec.get("num_parameters"),
                "id": existing[0],
            },
        )
        return "updated"

    EvaluationService(session).create_evaluation(
        paper_id=paper.id,
        task_id=task_id,
        dataset_id=dataset_id,
        model_name=spec["model_name"],
        methodology=methodology(spec),
        metrics={"RadLE-C": spec["score"]},
        uses_additional_data=False,
        is_open=spec["is_open"],
        best_metric="RadLE-C",
        evaluated_on=INTRODUCED_DATE,
        external_source_url=LEADERBOARD_URL,
        num_parameters=spec.get("num_parameters"),
    )
    return "created"


def methodology(spec: dict) -> str:
    return (
        "RadLE 2.0 leaderboard result reported by CRASH Lab. The score is "
        f"the RadLE-C Confidence Weighted Index for {spec['model_name']} "
        f"({spec['provider']}) on the July 2026 leaderboard."
    )


def main() -> None:
    session = db_manager.session_local()
    try:
        task = session.execute(
            text("SELECT id, name, slug FROM tasks WHERE slug = :slug"),
            {"slug": TASK_SLUG},
        ).first()
        if task is None:
            raise RuntimeError(f"Missing task slug {TASK_SLUG}")

        metric_ids = ensure_metrics(session)
        source_paper = ensure_external_paper(session, SOURCE_SPEC)
        ensure_paper_task(session, source_paper.id, task.id)
        dataset_id = ensure_dataset(session, task.id, source_paper)
        ensure_task_links(session, task.id, dataset_id, metric_ids)
        session.commit()

        print(f"Benchmark: dataset_id={dataset_id}, source={paper_url(source_paper)}")
        print("Metrics:", ", ".join(metric_ids))

        for spec in MODEL_SPECS.values():
            paper = find_paper(session, spec)
            ensure_paper_task(session, paper.id, task.id)
            status = ensure_eval(session, task.id, dataset_id, paper, spec)
            session.commit()
            print(
                f"{spec['model_name']}: eval={status}, "
                f"paper={paper_url(paper)}, score={spec['score']}"
            )

        EvaluationService(session).recalculate_ranks(
            task.id,
            dataset_id,
            metric_name="RadLE-C",
        )
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    main()
