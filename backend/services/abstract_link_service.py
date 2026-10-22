"""Decide which literal catalog mentions in an abstract become links, and store them.

Candidates come from ``abstract_mention_service``. Each entity has a mode:
``always`` links every clean match, ``never`` links nothing, and ``judge`` (or
any match flagged ``variant_suspect``) asks the judge model once per paper and
entity. The verdict covers every occurrence of that entity in the abstract.
Where two entities claim the same words, the higher score wins.

Every candidate is stored, linked or not, keyed to the abstract's SHA-256, so a
changed abstract is re-judged and an unchanged one never is: a rescan after a
catalog change reuses earlier verdicts and asks the judge only about new pairs.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Framework,
    Method,
    Paper,
    PaperAbstractMention,
    PaperMethodExclusion,
)
from backend.services.abstract_mention_service import (
    Candidate,
    MentionIndex,
    build_index,
    find_candidates,
    load_catalog_entities,
)

PROMPT_VERSION = "2026-10-22"
JEV_MODEL = "jev-1.14"
JUDGE_THRESHOLD = 0.6
SYSTEMONE_URL = "https://openrouter.ai/api/v1/systemone"
ALWAYS_SCORE = 1.0

POLICY = (
    "Papers with Code hyperlinks literal mentions of catalog entries in paper "
    "abstracts. Decide whether this candidate should be linked; the verdict covers "
    "all of its occurrences.\n"
    "Link when the phrase refers to this exact catalog entry. Established technical "
    "terms count even if the paper is not about them. Vague words (attention, agent, "
    "diffusion, embedding, transformer, hallucination, probing) count only when the "
    "text refers to the technique itself; a vague word used as a plain noun for the "
    "paper's own system is not a link.\n"
    "Do not link another sense of the word, a different or more specific variant or "
    'entity ("SWE-Bench Lite" vs SWE-Bench, "RoboTwin 2.0" vs RoboTwin), or a '
    "catalog entry that is a different thing than the abstract means. For benchmarks, "
    "a default split or version is fine unless the abstract names another one. Size, "
    'checkpoint, and metric-order suffixes still refer to the entry ("Qwen3-8B" is '
    'Qwen3, "BLEU-4" is BLEU).'
)

KIND = {"method": "method", "dataset": "benchmark", "framework": "software framework"}


@dataclass(frozen=True)
class JudgeRequest:
    key: tuple[str, int]
    name: str
    entity_type: str
    description: str
    occurrences: tuple[str, ...]


class Judge(Protocol):
    name: str

    def score(
        self, title: str, abstract: str, requests: list[JudgeRequest]
    ) -> dict[tuple[str, int], float]: ...


class JevJudge:
    """TypeSafe's Jev decision model through OpenRouter: one yes/no per entity."""

    name = JEV_MODEL

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=60)

    def score(self, title, abstract, requests):
        questions = {
            f"q{i}": {
                "type": "noul",
                "instructions": (
                    f"{POLICY}\n\nCandidate {KIND[r.entity_type]}: {r.name}. "
                    f"Catalog description: {r.description or '(none)'}\n"
                    f"Occurrences in the abstract: {'; '.join(r.occurrences)}\n"
                    "Should this candidate be linked?"
                ),
            }
            for i, r in enumerate(requests)
        }
        response = self.client.post(
            SYSTEMONE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": JEV_MODEL,
                "state": f"Title: {title}\n\nAbstract: {abstract}",
                "questions": questions,
            },
        )
        response.raise_for_status()
        answers = response.json()["answers"]
        return {r.key: float(answers[f"q{i}"]["noul"]) for i, r in enumerate(requests)}


def abstract_sha(abstract: str) -> str:
    return hashlib.sha256(abstract.encode()).hexdigest()


def load_index(db: Session) -> MentionIndex:
    return build_index(load_catalog_entities(db))


def entity_descriptions(db: Session, keys: set[tuple[str, int]]) -> dict:
    """Short catalog descriptions shown to the judge."""
    columns = {
        "method": (Method, Method.description),
        "dataset": (
            Dataset,
            func.coalesce(Dataset.short_description, Dataset.description),
        ),
        "framework": (Framework, Framework.description),
    }
    descriptions = {}
    for entity_type, (model, column) in columns.items():
        ids = [entity_id for kind, entity_id in keys if kind == entity_type]
        if ids:
            rows = db.execute(select(model.id, column).where(model.id.in_(ids)))
            descriptions.update({(entity_type, i): (d or "")[:220] for i, d in rows})
    return descriptions


def judge_paper(
    db: Session, paper: Paper, index: MentionIndex, judge: Judge
) -> list[PaperAbstractMention]:
    """Build the mention rows for one paper; nothing is written."""
    abstract = paper.abstract or ""
    candidates = find_candidates(abstract, index)
    if not candidates:
        return []
    excluded = set(
        db.scalars(
            select(PaperMethodExclusion.method_id).where(
                PaperMethodExclusion.paper_id == paper.id
            )
        )
    )
    entities = {
        (s.entity.entity_type, s.entity.entity_id): s.entity
        for surfaces in index.surfaces.values()
        for s in surfaces
    }
    by_entity: dict[tuple[str, int], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        key = (candidate.entity_type, candidate.entity_id)
        if not (candidate.entity_type == "method" and candidate.entity_id in excluded):
            by_entity[key].append(candidate)

    scores: dict[tuple[str, int], float] = {}
    needs_judge = []
    for key, found in by_entity.items():
        mode = entities[key].mode
        if mode == "never":
            scores[key] = 0.0
        elif mode == "always" and not any(c.variant_suspect for c in found):
            scores[key] = ALWAYS_SCORE
        else:
            needs_judge.append(key)

    sha = abstract_sha(abstract)
    judged_by: dict[tuple[str, int], str] = {}
    for key, (score, judge_name) in _previous_verdicts(db, paper.id, sha).items():
        if key in needs_judge:
            scores[key], judged_by[key] = score, judge_name
    needs_judge = [key for key in needs_judge if key not in judged_by]
    if needs_judge:
        descriptions = entity_descriptions(db, set(needs_judge))
        requests = [
            JudgeRequest(
                key=key,
                name=entities[key].name,
                entity_type=key[0],
                description=descriptions.get(key, ""),
                occurrences=tuple(
                    c.surface
                    + (
                        " (next to a capitalised word or number)"
                        if c.variant_suspect
                        else ""
                    )
                    for c in by_entity[key]
                ),
            )
            for key in needs_judge
        ]
        scores.update(judge.score(paper.title or "", abstract, requests))
        judged_by.update({key: judge.name for key in needs_judge})

    linked = {key for key, score in scores.items() if score >= JUDGE_THRESHOLD}
    linked -= _losers_of_shared_spans(by_entity, scores, linked)
    return [
        PaperAbstractMention(
            paper_id=paper.id,
            entity_type=c.entity_type,
            entity_id=c.entity_id,
            start_offset=c.start,
            end_offset=c.end,
            surface=c.surface,
            abstract_sha=sha,
            linked=key in linked,
            judge=judged_by.get(key),
            score=scores.get(key),
            prompt_version=PROMPT_VERSION,
        )
        for key, found in by_entity.items()
        for c in found
    ]


def _previous_verdicts(
    db: Session, paper_id: int, sha: str
) -> dict[tuple[str, int], tuple[float, str]]:
    """Judge scores already given for this exact abstract and prompt."""
    rows = db.execute(
        select(
            PaperAbstractMention.entity_type,
            PaperAbstractMention.entity_id,
            PaperAbstractMention.score,
            PaperAbstractMention.judge,
        ).where(
            PaperAbstractMention.paper_id == paper_id,
            PaperAbstractMention.abstract_sha == sha,
            PaperAbstractMention.prompt_version == PROMPT_VERSION,
            PaperAbstractMention.judge.isnot(None),
        )
    )
    return {(t, i): (score, judge) for t, i, score, judge in rows}


def mentions_changed(
    db: Session, paper_id: int, rows: list[PaperAbstractMention]
) -> bool:
    """False when the stored rows already say exactly this."""
    stored = db.execute(
        select(
            PaperAbstractMention.entity_type,
            PaperAbstractMention.entity_id,
            PaperAbstractMention.start_offset,
            PaperAbstractMention.end_offset,
            PaperAbstractMention.linked,
            PaperAbstractMention.abstract_sha,
            PaperAbstractMention.prompt_version,
        ).where(PaperAbstractMention.paper_id == paper_id)
    ).all()
    fresh = {
        (
            r.entity_type,
            r.entity_id,
            r.start_offset,
            r.end_offset,
            r.linked,
            r.abstract_sha,
            r.prompt_version,
        )
        for r in rows
    }
    return {tuple(row) for row in stored} != fresh


def _losers_of_shared_spans(by_entity, scores, linked) -> set[tuple[str, int]]:
    """Benchmark GQA vs method GQA: the lower score loses the shared words."""
    losers = set()
    for a in linked:
        for b in linked:
            if a == b or scores[a] >= scores[b]:
                continue
            if any(
                x.start < y.end and y.start < x.end
                for x in by_entity[a]
                for y in by_entity[b]
            ):
                losers.add(a)
    return losers


def store_paper_mentions(
    db: Session, paper_id: int, rows: list[PaperAbstractMention]
) -> None:
    db.execute(
        delete(PaperAbstractMention).where(PaperAbstractMention.paper_id == paper_id)
    )
    db.add_all(rows)


def stored_abstract_shas(db: Session) -> dict[int, str]:
    """Paper id -> abstract SHA its mentions were judged for, current prompt only."""
    rows = db.execute(
        select(PaperAbstractMention.paper_id, PaperAbstractMention.abstract_sha)
        .where(PaperAbstractMention.prompt_version == PROMPT_VERSION)
        .distinct()
    )
    return {paper_id: sha for paper_id, sha in rows}
