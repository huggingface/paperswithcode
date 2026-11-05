"""Load legacy paperswithcode.com slugs into ``legacy_pwc_slugs``.

Streams the legacy dumps in ``data/legacy_pwc_data/`` with ijson and upserts
one row per slug in bounded batches:

- ``paper``: ``papers-with-abstracts.json`` slug -> arXiv id (rows without one
  are skipped)
- ``method``: ``jul-28-methods.json`` slug -> method name
- ``dataset``: ``jul-28-datasets.json`` slug -> dataset name
- ``sota``: every ``/sota/`` leaderboard link in ``evaluation-tables.json``
  -> the leaderboard's dataset name

Report-only unless --apply. Re-running is safe.

    uv run --env-file backend/keys.env python -m backend.scripts.import_legacy_pwc_slugs --apply
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Iterator
from pathlib import Path

import ijson
from sqlalchemy.dialects.postgresql import insert

from backend.database.connection import db_manager
from backend.models.database import LegacyPwcSlug

logger = logging.getLogger("import_legacy_pwc_slugs")

DEFAULT_DATA_DIR = Path("data/legacy_pwc_data")
LEGACY_PREFIX = "https://paperswithcode.com/"


def _slug(url: str | None, kind: str) -> str | None:
    prefix = f"{LEGACY_PREFIX}{kind}/"
    if not url or not url.startswith(prefix):
        return None
    slug = url[len(prefix) :].strip("/")
    return slug or None


def _items(path: Path) -> Iterator[dict]:
    with path.open("rb") as handle:
        yield from ijson.items(handle, "item")


def paper_rows(data_dir: Path) -> Iterator[tuple[str, str, str]]:
    for paper in _items(data_dir / "papers-with-abstracts.json"):
        slug = _slug(paper.get("paper_url"), "paper")
        arxiv_id = (paper.get("arxiv_id") or "").strip()
        if slug and arxiv_id:
            yield "paper", slug, arxiv_id


def _named_rows(path: Path, kind: str) -> Iterator[tuple[str, str, str]]:
    for entry in _items(path):
        slug = _slug(entry.get("url"), kind)
        name = (entry.get("name") or "").strip()
        if slug and name:
            yield kind, slug, name


def _sota_links(task: dict) -> Iterator[tuple[str, str, str]]:
    for dataset in task.get("datasets") or []:
        name = (dataset.get("dataset") or "").strip()
        for link in dataset.get("dataset_links") or []:
            slug = _slug(link.get("url"), "sota")
            if slug and name:
                yield "sota", slug, name
    for subtask in task.get("subtasks") or []:
        yield from _sota_links(subtask)


def sota_rows(data_dir: Path) -> Iterator[tuple[str, str, str]]:
    for task in _items(data_dir / "evaluation-tables.json"):
        yield from _sota_links(task)


def iter_rows(data_dir: Path, kinds: list[str]) -> Iterator[tuple[str, str, str]]:
    sources = {
        "method": lambda: _named_rows(data_dir / "jul-28-methods.json", "method"),
        "dataset": lambda: _named_rows(data_dir / "jul-28-datasets.json", "dataset"),
        "sota": lambda: sota_rows(data_dir),
        "paper": lambda: paper_rows(data_dir),
    }
    for kind in kinds:
        yield from sources[kind]()


def _flush(batch: dict[tuple[str, str], str]) -> None:
    rows = [
        {"kind": kind, "slug": slug, "target": target}
        for (kind, slug), target in batch.items()
    ]
    statement = insert(LegacyPwcSlug).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["kind", "slug"], set_={"target": statement.excluded.target}
    )
    with db_manager.session_local() as db:
        db.execute(statement)
        db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write rows")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--kind",
        action="append",
        choices=["method", "dataset", "sota", "paper"],
        help="Limit to these kinds (repeatable; default all)",
    )
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    kinds = args.kind or ["method", "dataset", "sota", "paper"]
    counts: dict[str, int] = {kind: 0 for kind in kinds}
    batch: dict[tuple[str, str], str] = {}
    for kind, slug, target in iter_rows(args.data_dir, kinds):
        counts[kind] += 1
        batch[(kind, slug)] = target
        if len(batch) >= args.batch_size:
            if args.apply:
                _flush(batch)
            batch = {}
            logger.info("progress %s", counts)
    if batch and args.apply:
        _flush(batch)
    logger.info("%s %s", "upserted" if args.apply else "would upsert", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
