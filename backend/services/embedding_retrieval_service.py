"""pgvector retrieval policies shared by related papers and hybrid search."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.models.database import Paper, PaperTask
from backend.services.paper_implementation_service import HF_ARTIFACTS_EXIST_SQL
from backend.services.query_embedding_client import (
    QueryEmbeddingClient,
    QueryEmbeddingContract,
    vector_literal,
)


ARXIV_VERSION_NUMBER_SQL = "CAST(SUBSTRING(p.version FROM 2) AS integer)"


@dataclass(frozen=True)
class ActiveGeneration:
    id: int
    model_name: str
    model_revision: str
    dimensions: int
    input_format_version: str
    query_instruction_version: str
    ranking_version: str


@dataclass(frozen=True)
class RankedCandidate:
    paper_id: int
    rank: int
    score: float | None = None


def reciprocal_rank_fusion(
    branches: list[tuple[list[RankedCandidate], float]],
    *,
    rrf_k: int = 60,
) -> list[tuple[int, float, dict[str, int]]]:
    scores: dict[int, float] = {}
    ranks: dict[int, dict[str, int]] = {}
    for branch_index, (candidates, weight) in enumerate(branches):
        name = "lexical" if branch_index == 0 else "semantic"
        for candidate in candidates:
            scores[candidate.paper_id] = scores.get(
                candidate.paper_id, 0.0
            ) + weight / (rrf_k + candidate.rank)
            ranks.setdefault(candidate.paper_id, {})[name] = candidate.rank
    return [
        (paper_id, score, ranks[paper_id])
        for paper_id, score in sorted(
            scores.items(), key=lambda item: (-item[1], item[0])
        )
    ]


class EmbeddingRetrievalService:
    def __init__(self, db: Session):
        self.db = db

    def active_generation(
        self, configured_id: int | None = None
    ) -> ActiveGeneration | None:
        condition = (
            "id=:id AND status IN ('ready','active')"
            if configured_id
            else "status='active'"
        )
        params = {"id": configured_id} if configured_id else {}
        row = (
            self.db.execute(
                text(
                    f"""SELECT id, model_name, model_revision, dimensions,
                            input_format_version, query_instruction_version, ranking_version
                     FROM paper_embedding_generations WHERE {condition}"""
                ),
                params,
            )
            .mappings()
            .one_or_none()
        )
        return ActiveGeneration(**row) if row else None

    def semantic_search(
        self,
        vector: list[float],
        generation: ActiveGeneration,
        *,
        limit: int = 50,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> list[RankedCandidate]:
        rows = self.db.execute(
            text(
                f"""
                SELECT e.paper_id,
                       e.embedding::halfvec({generation.dimensions}) <=>
                         CAST(:vector AS halfvec({generation.dimensions})) AS distance
                FROM paper_embeddings e
                JOIN papers p ON p.id=e.paper_id
                WHERE e.generation_id=:generation_id AND p.is_latest_version
                  AND (:start_date IS NULL OR p.date_published >= :start_date)
                  AND (:end_date IS NULL OR p.date_published <= :end_date)
                  AND (
                    :has_official_implementation = FALSE
                    OR EXISTS (
                        SELECT 1
                        FROM papers family
                        JOIN paper_repositories pr ON pr.paper_id = family.id
                        WHERE pr.is_official = TRUE
                          AND (
                            (p.arxiv_id IS NOT NULL AND family.arxiv_id = p.arxiv_id)
                            OR (p.arxiv_id IS NULL AND family.id = p.id)
                          )
                    )
                  )
                  AND (
                    :has_code = FALSE
                    OR EXISTS (
                        SELECT 1
                        FROM papers family
                        JOIN paper_repositories pr ON pr.paper_id = family.id
                        WHERE (
                            (p.arxiv_id IS NOT NULL AND family.arxiv_id = p.arxiv_id)
                            OR (p.arxiv_id IS NULL AND family.id = p.id)
                        )
                    )
                  )
                  AND (:has_hf_artifacts = FALSE OR {HF_ARTIFACTS_EXIST_SQL})
                ORDER BY e.embedding::halfvec({generation.dimensions}) <=>
                         CAST(:vector AS halfvec({generation.dimensions}))
                LIMIT :limit
                """
            ),
            {
                "vector": vector_literal(vector),
                "generation_id": generation.id,
                "limit": limit,
                "start_date": start_date,
                "end_date": end_date,
                "has_official_implementation": has_official_implementation,
                "has_code": has_code,
                "has_hf_artifacts": has_hf_artifacts,
            },
        ).all()
        return [
            RankedCandidate(int(row.paper_id), rank, 1 - float(row.distance))
            for rank, row in enumerate(rows, 1)
        ]

    def related_dense(
        self,
        source_paper: Paper,
        generation: ActiveGeneration,
        *,
        limit: int = 50,
    ) -> tuple[list[RankedCandidate], bool]:
        source = (
            self.db.execute(
                text(
                    f"""
                SELECT e.embedding::halfvec({generation.dimensions})::text AS embedding,
                       e.paper_id=:paper_id AS current
                FROM paper_embeddings e
                JOIN papers p ON p.id=e.paper_id
                WHERE e.generation_id=:generation_id
                  -- Resolve the source family first so both lookups use
                  -- indexes; an OR across the join scans every embedding.
                  AND e.paper_id IN (
                      SELECT id FROM papers WHERE id=:paper_id
                      UNION ALL
                      SELECT id FROM papers
                      WHERE :arxiv_id IS NOT NULL AND arxiv_id=:arxiv_id
                  )
                ORDER BY (e.paper_id=:paper_id) DESC,
                         {ARXIV_VERSION_NUMBER_SQL} DESC NULLS LAST,
                         p.id DESC
                LIMIT 1
                """
                ),
                {
                    "generation_id": generation.id,
                    "paper_id": source_paper.id,
                    "arxiv_id": source_paper.arxiv_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if not source:
            return [], False
        vector = source["embedding"]
        rows = self.db.execute(
            text(
                f"""
                SELECT e.paper_id,
                       e.embedding::halfvec({generation.dimensions}) <=>
                         CAST(:vector AS halfvec({generation.dimensions})) AS distance
                FROM paper_embeddings e JOIN papers p ON p.id=e.paper_id
                WHERE e.generation_id=:generation_id
                  AND e.paper_id<>:paper_id AND p.is_latest_version
                  AND NOT (:arxiv_id IS NOT NULL AND p.arxiv_id=:arxiv_id)
                ORDER BY e.embedding::halfvec({generation.dimensions}) <=>
                         CAST(:vector AS halfvec({generation.dimensions}))
                LIMIT :limit
                """
            ),
            {
                "generation_id": generation.id,
                "paper_id": source_paper.id,
                "arxiv_id": source_paper.arxiv_id,
                "vector": vector,
                "limit": limit,
            },
        ).all()
        return (
            [
                RankedCandidate(int(row.paper_id), rank, 1 - float(row.distance))
                for rank, row in enumerate(rows, 1)
            ],
            not bool(source["current"]),
        )

    def related_lexical(
        self, source_paper_id: int, *, limit: int = 50, max_terms: int = 12
    ) -> list[RankedCandidate]:
        """Retrieve lexical neighbors using a bounded set of rare source lexemes."""
        rows = self.db.execute(
            text(
                """
                WITH source_terms AS (
                    SELECT stats.lexeme
                    FROM papers source
                    CROSS JOIN LATERAL
                         unnest(tsvector_to_array(source.search_vector)) AS term(lexeme)
                    JOIN paper_lexeme_document_frequencies stats
                      ON stats.lexeme=term.lexeme
                    WHERE source.id=:paper_id
                      AND length(stats.lexeme) >= 3
                      AND stats.document_frequency >= 2
                      AND stats.document_frequency <= greatest(10, stats.corpus_size / 20)
                    ORDER BY stats.document_frequency ASC, stats.lexeme
                    LIMIT :max_terms
                ), lexical_query AS (
                    SELECT to_tsquery(
                        'english', string_agg(quote_literal(lexeme), ' | ')
                    ) AS query
                    FROM source_terms
                )
                SELECT p.id,
                       ts_rank_cd(p.search_vector, lexical_query.query, 32) AS lexical_score
                FROM papers p CROSS JOIN lexical_query
                WHERE p.is_latest_version AND p.id<>:paper_id
                  AND lexical_query.query IS NOT NULL
                  AND p.search_vector @@ lexical_query.query
                ORDER BY lexical_score DESC, p.citation_count DESC, p.id
                LIMIT :limit
                """
            ),
            {"paper_id": source_paper_id, "max_terms": max_terms, "limit": limit},
        ).all()
        return [
            RankedCandidate(int(row.id), rank, float(row.lexical_score))
            for rank, row in enumerate(rows, 1)
        ]

    def task_fallback(self, source_paper_id: int, limit: int) -> list[int]:
        first_task = (
            self.db.query(PaperTask.task_id)
            .filter(PaperTask.paper_id == source_paper_id)
            .order_by(PaperTask.task_id)
            .limit(1)
            .scalar()
        )
        if first_task is None:
            return []
        return [
            paper_id
            for (paper_id,) in (
                self.db.query(Paper.id)
                .join(PaperTask, PaperTask.paper_id == Paper.id)
                .filter(
                    PaperTask.task_id == first_task,
                    Paper.is_latest_version,
                    Paper.id != source_paper_id,
                )
                .order_by(Paper.citation_count.desc(), Paper.id.asc())
                .limit(limit)
                .all()
            )
        ]

    def encode_query(
        self, query: str, generation: ActiveGeneration, client: QueryEmbeddingClient
    ) -> list[float]:
        contract = QueryEmbeddingContract(
            generation_id=generation.id,
            model_name=generation.model_name,
            model_revision=generation.model_revision,
            dimensions=generation.dimensions,
            instruction_version=generation.query_instruction_version,
        )
        return client.encode(query, contract)

    def encode_and_search(
        self,
        query: str,
        generation: ActiveGeneration,
        client: QueryEmbeddingClient,
        limit: int = 50,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> list[RankedCandidate]:
        return self.semantic_search(
            self.encode_query(query, generation, client),
            generation,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            has_official_implementation=has_official_implementation,
            has_code=has_code,
            has_hf_artifacts=has_hf_artifacts,
        )
