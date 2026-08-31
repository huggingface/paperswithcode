#!/usr/bin/env python3
"""Phase 0–1 robotics benchmarks: fix mis-tagged rows and add tier-1 leaderboards.

Run:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_robotics_benchmarks.py
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.evaluations import DatasetCreateRequest
from backend.models.database import Paper
from backend.services.arxiv_service import ArxivService
from backend.services.dataset_service import DatasetService
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROBOTICS_TASK_SLUG = "robotics"
IMAGE_UNDERSTANDING_TASK_SLUG = "image-understanding"
SUCCESS_RATE_METRIC = "Success Rate"
TARGET_AREA_COVERAGE_METRIC = "Target Area Coverage"
PUSH_T_SLUG = "push-t"

LIBERO_DATASET_ID = 108
CALVIN_ABCD_DATASET_ID = 235

# Mis-tagged real-world task datasets (currently under Image Understanding).
MISLINKED_DATASET_IDS = (237, 238, 239)

NATIVE_PAPER_URL_FIXES = {
    CALVIN_ABCD_DATASET_ID: "2112.03227",
    236: "2405.05941",  # SimplerEnv WidowX
    237: "2506.01844",  # Meta-World authors' collected (SmolVLA eval suite)
    238: "2506.01844",  # SO100 real-world tasks
    239: "2506.01844",  # SO101 real-world tasks
}


@dataclass(frozen=True)
class BenchmarkSpec:
    slug: str
    name: str
    source_arxiv: str
    full_name: str | None = None
    description: str = ""
    short_description: str = ""
    homepage: str | None = None
    introduced_date: date | None = None
    parent_dataset_id: int | None = None
    split_name: str | None = None


BENCHMARKS: list[BenchmarkSpec] = [
    # --- Phase 1A: seed-list benchmark papers ---
    BenchmarkSpec(
        slug="droid",
        name="DROID",
        source_arxiv="2403.12945",
        full_name="DROID: A Large-Scale In-The-Wild Robot Manipulation Dataset",
        short_description="76k+ in-the-wild teleoperated manipulation trajectories.",
        description=(
            "DROID is a large-scale in-the-wild robot manipulation dataset with "
            "76k+ trajectories across diverse scenes, objects, and instructions. "
            "It underpins Open X-Embodiment-style pretraining and downstream "
            "real-robot evaluation."
        ),
        homepage="https://droid-dataset.github.io/",
        introduced_date=date(2024, 3, 19),
    ),
    BenchmarkSpec(
        slug="egodex",
        name="EgoDex",
        source_arxiv="2505.11709",
        full_name="EgoDex Dexterous Manipulation Benchmark",
        short_description="829h egocentric dexterous hand manipulation video.",
        description=(
            "EgoDex provides large-scale egocentric video of dexterous hand "
            "manipulation with 3D hand tracking, plus held-out tasks for "
            "evaluating dexterous policy learning."
        ),
        introduced_date=date(2025, 5, 17),
    ),
    BenchmarkSpec(
        slug="mujoco-playground",
        name="MuJoCo Playground",
        source_arxiv="2502.08844",
        full_name="MuJoCo Playground Simulation Suite",
        short_description="GPU-accelerated loco-manipulation sim benchmark suite.",
        description=(
            "MuJoCo Playground is a GPU simulation suite for locomotion and "
            "manipulation built on MuJoCo MJX, providing standardized tasks "
            "for robot learning research."
        ),
        introduced_date=date(2025, 2, 12),
    ),
    BenchmarkSpec(
        slug="galaxea-open-world",
        name="Galaxea Open-World",
        source_arxiv="2509.00576",
        full_name="Galaxea Open-World Dataset",
        short_description="Real-home tabletop and mobile manipulation eval suite.",
        description=(
            "Galaxea Open-World is a real-home dataset and evaluation suite "
            "covering tabletop and mobile manipulation in open-world home scenes."
        ),
        introduced_date=date(2025, 9, 1),
    ),
    BenchmarkSpec(
        slug="eo-data-1-5m",
        name="EO-Data1.5M",
        source_arxiv="2508.21112",
        full_name="EmbodiedOneVision EO-Data1.5M",
        short_description="Unified embodied pretraining and eval suite for EO-1.",
        description=(
            "EO-Data1.5M is the embodied pretraining and evaluation suite "
            "introduced with EmbodiedOneVision (EO-1) for general robot control."
        ),
        introduced_date=date(2025, 8, 28),
    ),
    BenchmarkSpec(
        slug="egomimic",
        name="EgoMimic",
        source_arxiv="2410.24221",
        full_name="EgoMimic Evaluation Suite",
        short_description="Egocentric human-to-bimanual robot transfer benchmark.",
        description=(
            "EgoMimic scales imitation learning from egocentric human video to "
            "bimanual robot policies, with an evaluation suite for transfer tasks."
        ),
        introduced_date=date(2024, 10, 31),
    ),
    BenchmarkSpec(
        slug="ph2d",
        name="PH2D",
        source_arxiv="2503.13441",
        full_name="PH2D Humanoid Egocentric Dataset",
        short_description="Humanoid egocentric task-oriented manipulation dataset.",
        description=(
            "PH2D (Humanoid Policy ~ Human Policy) introduces a humanoid "
            "egocentric task-oriented dataset for dexterous manipulation research."
        ),
        introduced_date=date(2025, 3, 17),
    ),
    # --- Phase 1B: widely reused eval suites ---
    BenchmarkSpec(
        slug="bridge-data-v2",
        name="Bridge Data V2",
        source_arxiv="2305.11106",
        full_name="Bridge Data V2",
        short_description="Cross-embodiment tabletop manipulation demonstrations.",
        description=(
            "Bridge Data V2 is a widely used real-robot manipulation dataset "
            "of tabletop demonstrations used for cross-embodiment pretraining "
            "and downstream policy evaluation."
        ),
        homepage="https://rail-berkeley.github.io/bridgedata/",
        introduced_date=date(2023, 5, 18),
    ),
    BenchmarkSpec(
        slug="rlbench",
        name="RLBench",
        source_arxiv="1909.12271",
        full_name="RLBench",
        short_description="100+ simulated language-conditioned manipulation tasks.",
        description=(
            "RLBench is a large-scale simulation benchmark with 100+ language-"
            "conditioned manipulation tasks for evaluating robot learning methods."
        ),
        homepage="https://sites.google.com/view/rlbench",
        introduced_date=date(2019, 9, 26),
    ),
    BenchmarkSpec(
        slug="robomimic",
        name="RoboMimic",
        source_arxiv="2108.03298",
        full_name="RoboMimic Benchmark",
        short_description="Offline imitation-learning benchmark with multiple task suites.",
        description=(
            "RoboMimic is a benchmark for learning from offline human "
            "demonstrations, with multiple simulated manipulation suites used "
            "by Diffusion Policy, ACT, and related methods."
        ),
        homepage="https://robomimic.github.io/",
        introduced_date=date(2021, 8, 7),
    ),
    BenchmarkSpec(
        slug="push-t",
        name="Push-T",
        source_arxiv="2303.04137",
        full_name="Push-T",
        short_description="2D contact-rich pushing task from the Diffusion Policy suite.",
        description=(
            "Push-T is a contact-rich 2D pushing benchmark from the Diffusion "
            "Policy evaluation suite, commonly reported with success rate."
        ),
        introduced_date=date(2023, 3, 7),
    ),
    BenchmarkSpec(
        slug="aloha-sim",
        name="ALOHA Sim",
        source_arxiv="2304.13705",
        full_name="ALOHA Sim",
        short_description="Simulated bimanual ALOHA manipulation tasks.",
        description=(
            "Simulated bimanual manipulation tasks from the ALOHA / ACT "
            "evaluation suite, including cube transfer and related tasks."
        ),
        introduced_date=date(2023, 4, 24),
    ),
    BenchmarkSpec(
        slug="language-table",
        name="Language Table",
        source_arxiv="2206.13408",
        full_name="Language Table",
        short_description="Language-conditioned tabletop block manipulation.",
        description=(
            "Language Table is a language-conditioned tabletop manipulation "
            "benchmark where policies follow natural-language instructions."
        ),
        introduced_date=date(2022, 6, 27),
    ),
    BenchmarkSpec(
        slug="simplerenv-google-robot",
        name="SimplerEnv Google Robot",
        source_arxiv="2405.05941",
        full_name="SimplerEnv Google Robot",
        short_description="SimplerEnv visual-matching eval on Google Robot tasks.",
        description=(
            "Google Robot visual-matching evaluation split from SimplerEnv, "
            "used to benchmark real-to-sim transfer for manipulation policies."
        ),
        homepage="https://simpler-env.github.io/",
        introduced_date=date(2024, 5, 9),
    ),
    BenchmarkSpec(
        slug="libero-plus",
        name="LIBERO-Plus",
        source_arxiv="2510.13626",
        full_name="LIBERO-Plus",
        short_description="Robustness benchmark extending LIBERO with perturbations.",
        description=(
            "LIBERO-Plus stress-tests VLA models with controlled perturbations "
            "across layout, camera, robot state, language, lighting, background, "
            "and sensor noise."
        ),
        homepage="https://github.com/sylvestf/LIBERO-plus",
        introduced_date=date(2025, 10, 15),
        parent_dataset_id=LIBERO_DATASET_ID,
    ),
    BenchmarkSpec(
        slug="robotwin",
        name="RoboTwin",
        source_arxiv="2409.02920",
        full_name="RoboTwin",
        short_description="Dual-arm manipulation benchmark with generative digital twins.",
        description=(
            "RoboTwin is a dual-arm manipulation benchmark and data-generation "
            "framework with generative digital twins and standardized sim evaluation."
        ),
        homepage="https://robotwin-platform.github.io/",
        introduced_date=date(2024, 9, 4),
    ),
    BenchmarkSpec(
        slug="franka-kitchen",
        name="Franka Kitchen",
        source_arxiv="2106.09739",
        full_name="Franka Kitchen",
        short_description="Multitask kitchen manipulation benchmark.",
        description=(
            "Franka Kitchen is a multitask simulated kitchen manipulation "
            "benchmark widely used for offline RL and representation learning."
        ),
        introduced_date=date(2021, 6, 17),
    ),
    BenchmarkSpec(
        slug="meta-world-mt10",
        name="Meta-World MT10",
        source_arxiv="1904.03106",
        full_name="Meta-World MT10",
        short_description="Meta-World multitask benchmark with 10 training tasks.",
        description=(
            "Meta-World MT10 is the 10-task multitask split from Meta-World, "
            "commonly used for meta-RL and representation-learning evaluation."
        ),
        homepage="https://meta-world.github.io/",
        introduced_date=date(2019, 4, 5),
    ),
    BenchmarkSpec(
        slug="meta-world-mt50",
        name="Meta-World MT50",
        source_arxiv="1904.03106",
        full_name="Meta-World MT50",
        short_description="Meta-World multitask benchmark with 50 tasks.",
        description=(
            "Meta-World MT50 is the 50-task multitask split from Meta-World "
            "for broader generalization evaluation."
        ),
        homepage="https://meta-world.github.io/",
        introduced_date=date(2019, 4, 5),
    ),
    BenchmarkSpec(
        slug="robocasa",
        name="RoboCasa",
        source_arxiv="2406.09669",
        full_name="RoboCasa",
        short_description="Large-scale everyday kitchen manipulation sim benchmark.",
        description=(
            "RoboCasa is a large-scale simulation benchmark for everyday "
            "kitchen manipulation and long-horizon VLA evaluation."
        ),
        homepage="https://robocasa.ai/",
        introduced_date=date(2024, 6, 13),
    ),
    BenchmarkSpec(
        slug="behavior-1k",
        name="BEHAVIOR-1K",
        source_arxiv="2403.04125",
        full_name="BEHAVIOR-1K",
        short_description="1000 everyday household activity benchmark.",
        description=(
            "BEHAVIOR-1K is a large-scale benchmark of 1000 everyday household "
            "activities for embodied AI and long-horizon manipulation."
        ),
        homepage="https://behavior.stanford.edu/",
        introduced_date=date(2024, 3, 6),
    ),
    BenchmarkSpec(
        slug="maniskill2",
        name="ManiSkill2",
        source_arxiv="2302.04659",
        full_name="ManiSkill2",
        short_description="Unified generalizable manipulation skills benchmark.",
        description=(
            "ManiSkill2 is a unified simulation benchmark for generalizable "
            "manipulation skills with diverse objects and task variations."
        ),
        homepage="https://maniskill.ai/",
        introduced_date=date(2023, 2, 9),
    ),
    # --- Phase 1C: LIBERO splits ---
    BenchmarkSpec(
        slug="libero-spatial",
        name="LIBERO-Spatial",
        source_arxiv="2306.03310",
        full_name="LIBERO-Spatial",
        short_description="LIBERO spatial-relation knowledge transfer suite.",
        description=(
            "LIBERO-Spatial evaluates knowledge transfer for spatial-relation "
            "manipulation tasks in the LIBERO lifelong learning benchmark."
        ),
        homepage="https://libero-project.github.io/",
        introduced_date=date(2023, 6, 5),
        parent_dataset_id=LIBERO_DATASET_ID,
        split_name="Spatial",
    ),
    BenchmarkSpec(
        slug="libero-object",
        name="LIBERO-Object",
        source_arxiv="2306.03310",
        full_name="LIBERO-Object",
        short_description="LIBERO object-centric knowledge transfer suite.",
        description=(
            "LIBERO-Object evaluates object-centric knowledge transfer tasks "
            "in the LIBERO lifelong learning benchmark."
        ),
        homepage="https://libero-project.github.io/",
        introduced_date=date(2023, 6, 5),
        parent_dataset_id=LIBERO_DATASET_ID,
        split_name="Object",
    ),
    BenchmarkSpec(
        slug="libero-goal",
        name="LIBERO-Goal",
        source_arxiv="2306.03310",
        full_name="LIBERO-Goal",
        short_description="LIBERO goal-conditioned knowledge transfer suite.",
        description=(
            "LIBERO-Goal evaluates goal-conditioned knowledge transfer tasks "
            "in the LIBERO lifelong learning benchmark."
        ),
        homepage="https://libero-project.github.io/",
        introduced_date=date(2023, 6, 5),
        parent_dataset_id=LIBERO_DATASET_ID,
        split_name="Goal",
    ),
    BenchmarkSpec(
        slug="libero-long",
        name="LIBERO-Long",
        source_arxiv="2306.03310",
        full_name="LIBERO-Long",
        short_description="LIBERO long-horizon knowledge transfer suite.",
        description=(
            "LIBERO-Long evaluates long-horizon knowledge transfer tasks "
            "in the LIBERO lifelong learning benchmark."
        ),
        homepage="https://libero-project.github.io/",
        introduced_date=date(2023, 6, 5),
        parent_dataset_id=LIBERO_DATASET_ID,
        split_name="Long",
    ),
    BenchmarkSpec(
        slug="libero-90",
        name="LIBERO-90",
        source_arxiv="2306.03310",
        full_name="LIBERO-90",
        short_description="LIBERO 90-task average success benchmark.",
        description=(
            "LIBERO-90 reports average success over 90 tasks and is the "
            "headline number in most VLA papers evaluating on LIBERO."
        ),
        homepage="https://libero-project.github.io/",
        introduced_date=date(2023, 6, 5),
        parent_dataset_id=LIBERO_DATASET_ID,
        split_name="90-task average",
    ),
    # --- Phase 1D: CALVIN splits ---
    BenchmarkSpec(
        slug="calvin-abc-d",
        name="CALVIN ABC→D",
        source_arxiv="2112.03227",
        full_name="CALVIN ABC→D",
        short_description="CALVIN language-conditioned policy learning split ABC→D.",
        description=(
            "CALVIN ABC→D evaluates language-conditioned policy learning when "
            "training on environments A/B/C and testing on held-out environment D."
        ),
        homepage="http://calvin.cs.uni-freiburg.de/",
        introduced_date=date(2021, 12, 6),
        parent_dataset_id=CALVIN_ABCD_DATASET_ID,
        split_name="ABC→D",
    ),
    BenchmarkSpec(
        slug="calvin-long-horizon",
        name="CALVIN Long-Horizon",
        source_arxiv="2112.03227",
        full_name="CALVIN Long-Horizon",
        short_description="CALVIN long-horizon chained manipulation evaluation.",
        description=(
            "CALVIN long-horizon chains evaluate sequential language-conditioned "
            "manipulation tasks over extended horizons."
        ),
        homepage="http://calvin.cs.uni-freiburg.de/",
        introduced_date=date(2021, 12, 6),
        parent_dataset_id=CALVIN_ABCD_DATASET_ID,
        split_name="Long-horizon",
    ),
]


def paper_url_for(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


async def ensure_arxiv_paper(session, arxiv_id: str) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        return existing

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(f"Failed to fetch arXiv metadata for {arxiv_id}")

    paper_id = PaperService(session).add_paper(
        {
            "arxiv_id": metadata.arxiv_id,
            "title": metadata.title,
            "abstract": metadata.abstract,
            "version": metadata.version,
            "date_published": metadata.published.date() if metadata.published else None,
            "primary_category": metadata.primary_category,
            "all_categories": metadata.categories,
            "is_latest_version": True,
        }
    )
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Failed to load newly created paper {paper_id}")
    logger.info("Indexed arXiv paper %s (id=%s)", arxiv_id, paper.id)
    return paper


def get_task_id(session, slug: str) -> int:
    row = session.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"), {"slug": slug}
    ).one()
    return int(row[0])


def get_metric_id(session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).one()
    return int(row[0])


def ensure_metric(
    session,
    name: str,
    direction: str,
    full_name: str,
    scale: str,
    description: str,
) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).first()
    if row:
        return int(row[0])

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:n, :d, :full, :scale, :desc)
            RETURNING id
            """
        ),
        {
            "n": name,
            "d": direction,
            "full": full_name,
            "scale": scale,
            "desc": description,
        },
    ).scalar_one()
    logger.info("Created metric %r (id=%s)", name, metric_id)
    return int(metric_id)


def fix_phase0(session, robotics_task_id: int, image_task_id: int) -> None:
    for dataset_id in MISLINKED_DATASET_IDS:
        session.execute(
            text(
                "DELETE FROM task_datasets "
                "WHERE task_id = :task_id AND dataset_id = :dataset_id"
            ),
            {"task_id": image_task_id, "dataset_id": dataset_id},
        )
        session.execute(
            text(
                """
                INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
                VALUES (:task_id, :dataset_id, FALSE)
                ON CONFLICT (task_id, dataset_id) DO NOTHING
                """
            ),
            {"task_id": robotics_task_id, "dataset_id": dataset_id},
        )
        logger.info(
            "Re-linked dataset_id=%s from %s to %s",
            dataset_id,
            IMAGE_UNDERSTANDING_TASK_SLUG,
            ROBOTICS_TASK_SLUG,
        )

    for dataset_id, arxiv_id in NATIVE_PAPER_URL_FIXES.items():
        paper = (
            session.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
            .one()
        )
        session.execute(
            text(
                """
                UPDATE datasets
                SET paper_url = :paper_url,
                    introducing_paper_id = :paper_id,
                    introducing_paper_title = :title
                WHERE id = :dataset_id
                """
            ),
            {
                "paper_url": paper_url_for(paper),
                "paper_id": paper.id,
                "title": paper.title,
                "dataset_id": dataset_id,
            },
        )
        logger.info(
            "Fixed paper_url for dataset_id=%s -> %s",
            dataset_id,
            paper_url_for(paper),
        )


def wire_task_dataset(session, task_id: int, dataset_id: int) -> None:
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


def wire_metric(session, task_id: int, dataset_id: int, metric_id: int) -> None:
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


def tag_source_paper(session, paper_id: int, task_id: int) -> None:
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


def ensure_dataset(
    session,
    task_id: int,
    spec: BenchmarkSpec,
    source_paper: Paper,
) -> tuple[int, bool]:
    row = session.execute(
        text("SELECT id, name FROM datasets WHERE slug = :slug"),
        {"slug": spec.slug},
    ).first()
    created = False

    if row:
        dataset_id = int(row[0])
    else:
        created = DatasetService(session).create_dataset(
            DatasetCreateRequest(
                name=spec.name,
                full_name=spec.full_name or spec.name,
                description=spec.description,
                short_description=spec.short_description,
                homepage=spec.homepage,
                paper_url=paper_url_for(source_paper),
                introduced_date=spec.introduced_date,
                task_ids=[task_id],
                modalities=["Images", "Videos", "Robotics"],
            )
        )
        dataset_id = int(created.id)
        logger.info("Created dataset %r (id=%s)", spec.name, dataset_id)

    session.execute(
        text(
            """
            UPDATE datasets
            SET slug = :slug,
                name = :name,
                full_name = COALESCE(:full_name, full_name),
                description = COALESCE(:description, description),
                short_description = COALESCE(:short_description, short_description),
                homepage = COALESCE(:homepage, homepage),
                paper_url = :paper_url,
                introducing_paper_id = :paper_id,
                introducing_paper_title = :title,
                introduced_year = COALESCE(introduced_year, :year),
                parent_dataset_id = COALESCE(:parent_id, parent_dataset_id),
                split_name = COALESCE(:split_name, split_name)
            WHERE id = :dataset_id
            """
        ),
        {
            "slug": spec.slug,
            "name": spec.name,
            "full_name": spec.full_name,
            "description": spec.description or None,
            "short_description": spec.short_description or None,
            "homepage": spec.homepage,
            "paper_url": paper_url_for(source_paper),
            "paper_id": source_paper.id,
            "title": source_paper.title,
            "year": spec.introduced_date.year if spec.introduced_date else None,
            "parent_id": spec.parent_dataset_id,
            "split_name": spec.split_name,
            "dataset_id": dataset_id,
        },
    )
    return dataset_id, created


async def main() -> None:
    session = db_manager.session_local()
    report: list[str] = []
    try:
        robotics_task_id = get_task_id(session, ROBOTICS_TASK_SLUG)
        image_task_id = get_task_id(session, IMAGE_UNDERSTANDING_TASK_SLUG)
        success_rate_id = ensure_metric(
            session,
            SUCCESS_RATE_METRIC,
            "higher_is_better",
            "Success Rate",
            "0-100",
            "Fraction of episodes or tasks completed successfully.",
        )
        coverage_id = ensure_metric(
            session,
            TARGET_AREA_COVERAGE_METRIC,
            "higher_is_better",
            "Target Area Coverage",
            "0-1",
            (
                "Maximum target-area coverage (IoU) achieved during a Push-T "
                "episode; primary sim metric in Diffusion Policy."
            ),
        )

        fix_phase0(session, robotics_task_id, image_task_id)
        for row in session.execute(
            text(
                """
                SELECT td.dataset_id
                FROM task_datasets td
                JOIN tasks t ON t.id = td.task_id AND t.slug = :slug
                LEFT JOIN task_dataset_metrics tdm
                  ON tdm.task_id = td.task_id
                 AND tdm.dataset_id = td.dataset_id
                 AND tdm.metric_id = :metric_id
                WHERE tdm.metric_id IS NULL
                """
            ),
            {"slug": ROBOTICS_TASK_SLUG, "metric_id": success_rate_id},
        ):
            wire_metric(session, robotics_task_id, int(row[0]), success_rate_id)
        report.append("Phase 0: fixed mis-tagged datasets and native paper URLs")

        source_arxiv_ids = sorted({spec.source_arxiv for spec in BENCHMARKS})
        papers: dict[str, Paper] = {}
        for arxiv_id in source_arxiv_ids:
            papers[arxiv_id] = await ensure_arxiv_paper(session, arxiv_id)

        created_count = 0
        for spec in BENCHMARKS:
            source_paper = papers[spec.source_arxiv]
            dataset_id, created = ensure_dataset(
                session, robotics_task_id, spec, source_paper
            )
            if created:
                created_count += 1
            wire_task_dataset(session, robotics_task_id, dataset_id)
            wire_metric(session, robotics_task_id, dataset_id, success_rate_id)
            if spec.slug == PUSH_T_SLUG:
                wire_metric(session, robotics_task_id, dataset_id, coverage_id)
            tag_source_paper(session, source_paper.id, robotics_task_id)
            report.append(
                f"{spec.slug}: dataset_id={dataset_id} "
                f"source={paper_url_for(source_paper)}"
            )

        session.commit()
        logger.info("Robotics benchmarks ready (%s new datasets)", created_count)
        for line in report:
            logger.info("  %s", line)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
