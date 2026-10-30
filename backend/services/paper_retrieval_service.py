"""Paper search, taxonomy promotion, and related-paper retrieval policies."""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from collections import OrderedDict
from datetime import date, datetime, timezone
from typing import Callable, List, Optional

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.papers import (
    PaperSearchResults,
    PaperSummary,
    RelatedPaperRecommendation,
)
from backend.models.database import (
    Author as DBAuthor,
    Method as DBMethod,
    Paper as DBPaper,
    PaperAuthor,
    PaperMethod,
)
from backend.services.embedding_retrieval_service import (
    ActiveGeneration,
    EmbeddingRetrievalService,
    RankedCandidate,
    reciprocal_rank_fusion,
)
from backend.services.paper_implementation_service import (
    HF_ARTIFACTS_EXIST_SQL,
    family_repository_exists_clause,
    hf_artifacts_exist_clause,
)
from backend.services.query_embedding_client import (
    QueryEmbeddingUnavailable,
    get_query_embedding_client,
)
from backend.utils.exceptions import DatabaseError


search_logger = logging.getLogger("backend.paper_search")
search_logger.setLevel(logging.INFO)
_related_cache: OrderedDict[tuple, tuple[float, list[RelatedPaperRecommendation]]] = (
    OrderedDict()
)
_related_cache_lock = threading.Lock()
_RELATED_CACHE_TTL_SECONDS = 300
# Punctuation inside a word ("V4.1", "Qwen2.5-VL"), split like the title copy
# in papers_search_vector_update().
_INNER_PUNCTUATION = re.compile(r"(?<=[^\W_])[^\w\s]+(?=[^\W_])|_")
# A split variant ORed in would bring back what a "-term" excludes.
_NEGATED_TERM = re.compile(r"(?:^|\s)-\S")


def _related_cache_get(key: tuple) -> list[RelatedPaperRecommendation] | None:
    with _related_cache_lock:
        cached = _related_cache.get(key)
        if not cached or time.monotonic() - cached[0] >= _RELATED_CACHE_TTL_SECONDS:
            _related_cache.pop(key, None)
            return None
        _related_cache.move_to_end(key)
        return cached[1]


def _related_cache_put(key: tuple, value: list[RelatedPaperRecommendation]) -> None:
    with _related_cache_lock:
        _related_cache[key] = (time.monotonic(), value)
        _related_cache.move_to_end(key)
        while len(_related_cache) > 512:
            _related_cache.popitem(last=False)


class PaperRetrievalService:
    """Own paper retrieval policy without expanding the core paper CRUD service."""

    def __init__(
        self,
        db: Session,
        *,
        settings: Settings,
        summary_factory: Callable[[list[DBPaper]], list[PaperSummary]],
        paper_resolver: Callable[[str], DBPaper],
    ) -> None:
        self.db = db
        self.settings = settings
        self._summary_factory = summary_factory
        self._paper_resolver = paper_resolver
        self.applied_mode: str = "keyword"

    def _convert_db_papers_to_summaries(
        self, papers: list[DBPaper]
    ) -> list[PaperSummary]:
        return self._summary_factory(papers)

    def _resolve_db_paper_by_id_or_arxiv(self, identifier: str) -> DBPaper:
        return self._paper_resolver(identifier)

    def search_db_papers(
        self,
        query: str,
        limit: int = 10,
        mode: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> list[DBPaper]:
        """
        Search latest papers using the configured rollout mode.

        ``keyword`` uses weighted PostgreSQL FTS, ``semantic`` uses the active
        pgvector generation, and ``hybrid`` fuses both rankings with RRF.

        Args:
            query: User-entered search query
            limit: Maximum number of results

        Returns:
            List of paper summaries in the selected mode's ranking order
        """
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        try:
            selected_mode = (mode or self.settings.paper_search_mode).lower()
            self.applied_mode = selected_mode
            retrieval_limit = max(20, limit)
            if selected_mode == "keyword":
                results = self._search_papers_fts(
                    cleaned_query,
                    retrieval_limit,
                    start_date=start_date,
                    end_date=end_date,
                    has_official_implementation=has_official_implementation,
                    has_code=has_code,
                    has_hf_artifacts=has_hf_artifacts,
                )
            elif selected_mode == "semantic":
                results = self._search_papers_semantic(
                    cleaned_query,
                    retrieval_limit,
                    start_date=start_date,
                    end_date=end_date,
                    has_official_implementation=has_official_implementation,
                    has_code=has_code,
                    has_hf_artifacts=has_hf_artifacts,
                )
            elif selected_mode == "hybrid":
                results = self._search_papers_hybrid(
                    cleaned_query,
                    retrieval_limit,
                    start_date=start_date,
                    end_date=end_date,
                    has_official_implementation=has_official_implementation,
                    has_code=has_code,
                    has_hf_artifacts=has_hf_artifacts,
                )
            else:
                raise ValueError(f"Unsupported paper search mode: {selected_mode}")

            results = self._promote_canonical_entity_paper(
                cleaned_query,
                results,
                limit,
                start_date=start_date,
                end_date=end_date,
                has_official_implementation=has_official_implementation,
                has_code=has_code,
                has_hf_artifacts=has_hf_artifacts,
            )
            if start_date is not None:
                results = [
                    paper
                    for paper in results
                    if paper.date_published is not None
                    and paper.date_published >= start_date
                ]
            if end_date is not None:
                results = [
                    paper
                    for paper in results
                    if paper.date_published is not None
                    and paper.date_published <= end_date
                ]
            return results[:limit]

        except Exception as e:
            raise DatabaseError(f"Error searching papers: {str(e)}")

    def search_papers(
        self,
        query: str,
        limit: int = 10,
        mode: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> List[PaperSummary]:
        """Return the lightweight compatibility projection for search consumers."""
        papers = self.search_db_papers(
            query,
            limit,
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            has_official_implementation=has_official_implementation,
            has_code=has_code,
            has_hf_artifacts=has_hf_artifacts,
        )
        return self._convert_db_papers_to_summaries(papers)

    def search_papers_page(
        self,
        query: str,
        page: int = 1,
        page_size: int = 10,
        mode: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> PaperSearchResults:
        """Return a stable slice of the relevance ranking with page metadata."""
        end = page * page_size
        ranked = self.search_papers(
            query,
            end + 1,
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            has_official_implementation=has_official_implementation,
            has_code=has_code,
            has_hf_artifacts=has_hf_artifacts,
        )
        start = end - page_size
        return PaperSearchResults(
            next_page=page + 1 if len(ranked) > end else None,
            previous_page=page - 1 if page > 1 else None,
            results=ranked[start:end],
            applied_filters=(
                {"has_official_implementation": "true"}
                if has_official_implementation
                else {}
            ),
        )

    @staticmethod
    def _normalize_arxiv_search_query(query: str) -> Optional[str]:
        """Return a version-free ArXiv identity from an ID or ArXiv URL."""
        candidate = query.strip().lower()
        candidate = re.sub(
            r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/", "", candidate
        )
        candidate = candidate.rstrip("/")
        candidate = re.sub(r"\.pdf$", "", candidate)
        match = re.fullmatch(
            r"((?:\d{4}\.\d{4,5})|(?:[a-z][a-z.\-]+/\d{7}))(?:v\d+)?",
            candidate,
        )
        return match.group(1) if match else None

    @staticmethod
    def _normalize_entity_search_text(value: str | None) -> str:
        """Normalize taxonomy names and navigational queries identically."""
        if not value:
            return ""
        return re.sub(r"[^\w]+", " ", value.casefold()).strip()

    @classmethod
    def _canonical_entity_query(cls, query: str) -> str | None:
        """Return the entity name from a bare or explicit source-paper query.

        Bare entity names such as ``BERT`` are navigational. Longer topical
        queries such as ``BERT pruning`` must remain ordinary hybrid searches.
        A small, entity-agnostic vocabulary also recognizes explicit requests
        for the original/source paper without maintaining query-to-paper rules.
        """
        normalized = cls._normalize_entity_search_text(query)
        if not normalized:
            return None

        tokens = normalized.split()
        origin_words = {
            "canonical",
            "foundational",
            "introduced",
            "introducing",
            "original",
            "paper",
            "seminal",
            "source",
            "that",
            "the",
        }
        if not any(token in origin_words for token in tokens):
            return normalized

        entity_tokens = [token for token in tokens if token not in origin_words]
        return " ".join(entity_tokens) or None

    @staticmethod
    def _edit_distance(left: str, right: str) -> int:
        """Return Levenshtein distance for short normalized entity aliases."""
        if len(left) > len(right):
            left, right = right, left
        previous = list(range(len(left) + 1))
        for right_index, right_character in enumerate(right, 1):
            current = [right_index]
            for left_index, left_character in enumerate(left, 1):
                current.append(
                    min(
                        current[-1] + 1,
                        previous[left_index] + 1,
                        previous[left_index - 1] + (left_character != right_character),
                    )
                )
            previous = current
        return previous[-1]

    @classmethod
    def _entity_alias_match_quality(
        cls, query: str, alias: str | None
    ) -> tuple[int, int] | None:
        """Score exact, spacing, prefix, and bounded-typo alias matches."""
        normalized_alias = cls._normalize_entity_search_text(alias)
        if not normalized_alias:
            return None
        if query == normalized_alias:
            return 0, 0

        compact_query = query.replace(" ", "")
        compact_alias = normalized_alias.replace(" ", "")
        if compact_query == compact_alias:
            return 1, 0

        query_tokens = query.split()
        alias_tokens = normalized_alias.split()
        if len(query_tokens) > 2:
            return None
        if (
            len(compact_query) >= 4
            and len(query_tokens) == len(alias_tokens)
            and len(query_tokens[-1]) >= 3
            and all(
                alias_token.startswith(query_token)
                for query_token, alias_token in zip(
                    query_tokens, alias_tokens, strict=True
                )
            )
        ):
            return 2, len(compact_alias) - len(compact_query)

        longest = max(len(compact_query), len(compact_alias))
        if len(compact_query) < 5 or abs(len(compact_query) - len(compact_alias)) > 3:
            return None
        allowed_distance = 1 if longest <= 5 else 2 if longest <= 12 else 3
        distance = cls._edit_distance(compact_query, compact_alias)
        if distance <= allowed_distance and distance / longest <= 0.22:
            return 3, distance
        return None

    def _resolve_method_entity(self, query: str):
        """Resolve one taxonomy method from an exact, prefix, or typo query."""
        entity_query = self._canonical_entity_query(query)
        if not entity_query:
            return None

        methods = self.db.query(
            DBMethod.id,
            DBMethod.name,
            DBMethod.full_name,
            DBMethod.slug,
            DBMethod.source_paper_id,
        ).all()
        best_by_method = {}
        for method in methods:
            qualities = []
            for alias_quality, alias in enumerate(
                (method.name, method.full_name, method.slug)
            ):
                match = self._entity_alias_match_quality(entity_query, alias)
                if match is not None:
                    qualities.append((*match, alias_quality))
            if qualities:
                best_by_method[method.id] = (min(qualities), method)

        if not best_by_method:
            return None
        best_quality = min(quality for quality, _method in best_by_method.values())
        matches = [
            method
            for quality, method in best_by_method.values()
            if quality == best_quality
        ]
        if len(matches) != 1:
            fingerprint = hashlib.sha256(query.casefold().encode()).hexdigest()[:16]
            search_logger.info(
                "paper_search canonical_entity_ambiguous fingerprint=%s methods=%s",
                fingerprint,
                [method.id for method in matches],
            )
            return None
        match_kind = ("exact", "spacing", "prefix", "typo")[best_quality[0]]
        return matches[0], match_kind

    @staticmethod
    def _paper_in_date_range(
        paper: DBPaper,
        start_date: date | None,
        end_date: date | None,
    ) -> bool:
        if start_date is None and end_date is None:
            return True
        published = paper.date_published
        return (
            published is not None
            and (start_date is None or published >= start_date)
            and (end_date is None or published <= end_date)
        )

    @staticmethod
    def _filter_query_by_date_range(query, start_date, end_date):
        if start_date is not None:
            query = query.filter(DBPaper.date_published >= start_date)
        if end_date is not None:
            query = query.filter(DBPaper.date_published <= end_date)
        return query

    @staticmethod
    def _filter_query_by_official_implementation(query, required: bool):
        if required:
            return query.filter(family_repository_exists_clause(official_only=True))
        return query

    @staticmethod
    def _filter_query_by_search_artifacts(
        query, has_code: bool, has_hf_artifacts: bool
    ):
        if has_code:
            query = query.filter(family_repository_exists_clause())
        if has_hf_artifacts:
            query = query.filter(hf_artifacts_exist_clause())
        return query

    def _paper_has_official_implementation(self, paper: DBPaper) -> bool:
        return (
            self.db.query(DBPaper.id)
            .filter(
                DBPaper.id == paper.id,
                family_repository_exists_clause(official_only=True),
            )
            .first()
            is not None
        )

    def _method_source_paper(
        self,
        method_row,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> tuple[DBPaper | None, str]:
        """Resolve a method's source paper or a citation-ranked fallback."""
        if method_row.source_paper_id is not None:
            source = self.db.get(DBPaper, method_row.source_paper_id)
            if (
                source is not None
                and source.is_latest_version
                and self._paper_in_date_range(source, start_date, end_date)
                and (
                    not has_official_implementation
                    or self._paper_has_official_implementation(source)
                )
                and self._filter_query_by_search_artifacts(
                    self.db.query(DBPaper.id).filter(DBPaper.id == source.id),
                    has_code,
                    has_hf_artifacts,
                ).first()
                is not None
            ):
                return source, "source_paper"
            if source is not None and source.arxiv_id:
                latest_query = self.db.query(DBPaper).filter(
                    DBPaper.arxiv_id == source.arxiv_id,
                    DBPaper.is_latest_version,
                )
                latest = (
                    self._filter_query_by_search_artifacts(
                        self._filter_query_by_official_implementation(
                            self._filter_query_by_date_range(
                                latest_query, start_date, end_date
                            ),
                            has_official_implementation,
                        ),
                        has_code,
                        has_hf_artifacts,
                    )
                    .order_by(DBPaper.version.desc(), DBPaper.id.desc())
                    .first()
                )
                if latest is not None:
                    return latest, "source_paper_latest_version"

        # Citation counts are refreshed from Semantic Scholar. Within the
        # already-resolved method's paper set, they are a useful canonicality
        # prior; oldest publication and stable id resolve missing/equal counts.
        fallback_query = (
            self.db.query(DBPaper)
            .join(PaperMethod, PaperMethod.paper_id == DBPaper.id)
            .filter(
                PaperMethod.method_id == method_row.id,
                DBPaper.is_latest_version,
            )
        )
        fallback = (
            self._filter_query_by_search_artifacts(
                self._filter_query_by_official_implementation(
                    self._filter_query_by_date_range(
                        fallback_query, start_date, end_date
                    ),
                    has_official_implementation,
                ),
                has_code,
                has_hf_artifacts,
            )
            .order_by(
                DBPaper.citation_count.desc().nullslast(),
                DBPaper.date_published.asc().nullslast(),
                DBPaper.id.asc(),
            )
            .first()
        )
        return fallback, "semantic_scholar_citations"

    def _method_paper_candidates(
        self,
        method_id: int,
        limit: int,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> list[DBPaper]:
        """Return popular papers that use a resolved method."""
        query = (
            self.db.query(DBPaper)
            .join(PaperMethod, PaperMethod.paper_id == DBPaper.id)
            .filter(PaperMethod.method_id == method_id, DBPaper.is_latest_version)
        )
        return (
            self._filter_query_by_search_artifacts(
                self._filter_query_by_official_implementation(
                    self._filter_query_by_date_range(query, start_date, end_date),
                    has_official_implementation,
                ),
                has_code,
                has_hf_artifacts,
            )
            .order_by(
                DBPaper.citation_count.desc().nullslast(),
                DBPaper.date_published.asc().nullslast(),
                DBPaper.id.asc(),
            )
            .limit(limit)
            .all()
        )

    def _fuzzy_title_candidates(
        self,
        query: str,
        limit: int,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> list[tuple[DBPaper, float]]:
        """Use trigram KNN to retrieve short incomplete or misspelled titles."""
        normalized = self._normalize_entity_search_text(query)
        tokens = normalized.split()
        if (
            len(normalized.replace(" ", "")) < 4
            or len(tokens) > 2
            or self._normalize_arxiv_search_query(query)
        ):
            return []

        rows = (
            self.db.execute(
                text(f"""
                WITH nearest AS MATERIALIZED (
                    SELECT p.id,
                           p.title,
                           p.citation_count,
                           word_similarity(:query, lower(p.title)) AS similarity
                    FROM papers p
                    WHERE p.is_latest_version
                      AND (:start_date IS NULL OR p.date_published >= CAST(:start_date AS date))
                      AND (:end_date IS NULL OR p.date_published <= CAST(:end_date AS date))
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
                            SELECT 1 FROM papers family
                            JOIN paper_repositories pr ON pr.paper_id = family.id
                            WHERE (
                                (p.arxiv_id IS NOT NULL AND family.arxiv_id = p.arxiv_id)
                                OR (p.arxiv_id IS NULL AND family.id = p.id)
                            )
                        )
                      )
                      AND (:has_hf_artifacts = FALSE OR {HF_ARTIFACTS_EXIST_SQL})
                    ORDER BY CAST(:query AS text) <<-> lower(p.title)
                    LIMIT :candidate_limit
                )
                SELECT id, title, citation_count, similarity
                FROM nearest
                ORDER BY similarity DESC, citation_count DESC NULLS LAST, id
            """),
                {
                    "query": normalized,
                    "candidate_limit": max(100, limit * 4),
                    "start_date": start_date,
                    "end_date": end_date,
                    "has_official_implementation": has_official_implementation,
                    "has_code": has_code,
                    "has_hf_artifacts": has_hf_artifacts,
                },
            )
            .mappings()
            .all()
        )
        if not rows:
            return []
        ranked = []
        for row in rows:
            quality = self._title_query_match_quality(normalized, row["title"])
            if quality is None:
                continue
            match_kind, distance = quality
            compact_length = max(1, len(normalized.replace(" ", "")))
            edit_confidence = 1 - distance / compact_length
            confidence = max(float(row["similarity"]), edit_confidence)
            ranked.append(
                (
                    match_kind,
                    distance,
                    -confidence,
                    -(row["citation_count"] or 0),
                    int(row["id"]),
                    confidence,
                )
            )
        ranked.sort(key=lambda candidate: candidate[:5])
        ranked = ranked[: max(20, limit)]
        papers = (
            self.db.query(DBPaper)
            .filter(
                DBPaper.id.in_(
                    [paper_id for *_ranking, paper_id, _confidence in ranked]
                )
            )
            .all()
        )
        by_id = {int(paper.id): paper for paper in papers}
        return [
            (by_id[paper_id], confidence)
            for *_ranking, paper_id, confidence in ranked
            if paper_id in by_id
        ]

    @classmethod
    def _title_query_match_quality(
        cls, normalized_query: str, title: str
    ) -> tuple[int, int] | None:
        """Compare a short query with equally sized title-token windows."""
        query_tokens = normalized_query.split()
        title_tokens = cls._normalize_entity_search_text(title).split()
        width = len(query_tokens)
        if not width or len(title_tokens) < width:
            return None
        matches = [
            quality
            for start in range(len(title_tokens) - width + 1)
            if (
                quality := cls._entity_alias_match_quality(
                    normalized_query, " ".join(title_tokens[start : start + width])
                )
            )
            is not None
        ]
        return min(matches) if matches else None

    @staticmethod
    def _high_confidence_fuzzy_top(
        candidates: list[tuple[DBPaper, float]],
    ) -> DBPaper | None:
        """Return a safe typo/prefix winner, or abstain when evidence is weak."""
        if not candidates or candidates[0][1] < 0.55:
            return None
        if len(candidates) == 1:
            return candidates[0][0]
        top, top_score = candidates[0]
        second, second_score = candidates[1]
        if top_score - second_score >= 0.08:
            return top
        top_citations = top.citation_count or 0
        second_citations = second.citation_count or 0
        if abs(top_score - second_score) <= 0.02 and top_citations >= max(
            100, second_citations * 3
        ):
            return top
        return None

    @staticmethod
    def _fuse_paper_branches(
        branches: list[tuple[list[DBPaper], float]],
    ) -> list[DBPaper]:
        """RRF multiple paper lists with citation-aware deterministic ties."""
        scores: dict[int, float] = {}
        papers: dict[int, DBPaper] = {}
        for branch, weight in branches:
            for rank, paper in enumerate(branch, 1):
                paper_id = int(paper.id)
                papers[paper_id] = paper
                scores[paper_id] = scores.get(paper_id, 0.0) + weight / (60 + rank)
        return sorted(
            papers.values(),
            key=lambda paper: (
                -scores[int(paper.id)],
                -(paper.citation_count or 0),
                int(paper.id),
            ),
        )

    def _promote_canonical_entity_paper(
        self,
        query: str,
        results: list[DBPaper],
        limit: int,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> list[DBPaper]:
        """Enrich short navigational searches with taxonomy and title signals.

        Exact identities remain deterministic. Confident method resolutions
        add their source and popular linked papers; trigram title neighbors
        repair incomplete terms and bounded typos. All signals are data-driven
        and apply equally to keyword, semantic, and hybrid retrieval.
        """
        if self.db is None or limit <= 0:
            return results[:limit]

        normalized_title = self._normalize_entity_search_text(query)
        normalized_arxiv = self._normalize_arxiv_search_query(query)
        identity = next(
            (
                paper
                for paper in results
                if (normalized_arxiv and paper.arxiv_id == normalized_arxiv)
                or self._normalize_entity_search_text(paper.title) == normalized_title
            ),
            None,
        )
        resolved = self._resolve_method_entity(query)
        method = resolved[0] if resolved else None
        match_kind = resolved[1] if resolved else None
        canonical = None
        evidence = None
        method_candidates = []
        if method is not None:
            canonical, evidence = self._method_source_paper(
                method,
                start_date=start_date,
                end_date=end_date,
                has_official_implementation=has_official_implementation,
                has_code=has_code,
                has_hf_artifacts=has_hf_artifacts,
            )
            method_candidates = self._method_paper_candidates(
                method.id,
                max(20, limit),
                start_date=start_date,
                end_date=end_date,
                has_official_implementation=has_official_implementation,
                has_code=has_code,
                has_hf_artifacts=has_hf_artifacts,
            )

        fuzzy_candidates = self._fuzzy_title_candidates(
            query,
            max(20, limit),
            start_date=start_date,
            end_date=end_date,
            has_official_implementation=has_official_implementation,
            has_code=has_code,
            has_hf_artifacts=has_hf_artifacts,
        )
        fuzzy_papers = [paper for paper, _score in fuzzy_candidates]
        fuzzy_top = (
            None
            if method is not None
            else self._high_confidence_fuzzy_top(fuzzy_candidates)
        )
        fused = self._fuse_paper_branches(
            [
                (results, 1.0),
                (method_candidates, 1.0),
                (fuzzy_papers, 1.25),
            ]
        )
        pinned = []
        navigational_head = [identity, canonical]
        if method is not None:
            navigational_head.extend(method_candidates[:5])
        navigational_head.append(fuzzy_top)
        for paper in navigational_head:
            if paper is not None and all(
                int(existing.id) != int(paper.id) for existing in pinned
            ):
                pinned.append(paper)
        pinned_ids = {int(paper.id) for paper in pinned}
        enriched = pinned + [
            paper for paper in fused if int(paper.id) not in pinned_ids
        ]

        fingerprint = hashlib.sha256(query.casefold().encode()).hexdigest()[:16]
        if method is not None and canonical is not None:
            search_logger.info(
                "paper_search canonical_entity fingerprint=%s method_id=%s "
                "paper_id=%s evidence=%s match=%s",
                fingerprint,
                method.id,
                canonical.id,
                evidence,
                match_kind,
            )
        elif fuzzy_top is not None:
            search_logger.info(
                "paper_search fuzzy_title fingerprint=%s paper_id=%s score=%.3f",
                fingerprint,
                fuzzy_top.id,
                fuzzy_candidates[0][1],
            )
        return enriched[:limit]

    @staticmethod
    def _normalized_title_expression():
        return func.lower(
            func.regexp_replace(func.btrim(DBPaper.title), r"\s+", " ", "g")
        )

    def _search_papers_fts(
        self,
        query: str,
        limit: int,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> List[DBPaper]:
        """Weighted PostgreSQL FTS with deterministic identity overrides."""
        normalized_title = " ".join(query.lower().split())
        normalized_arxiv_id = self._normalize_arxiv_search_query(query)
        ts_query = func.websearch_to_tsquery("english", query)
        split_query = _INNER_PUNCTUATION.sub(" ", query)
        if split_query != query and not _NEGATED_TERM.search(query):
            ts_query = ts_query.op("||")(
                func.websearch_to_tsquery("english", split_query)
            )
        author_ts_query = func.websearch_to_tsquery("simple", query)
        arxiv_match = (
            DBPaper.arxiv_id == normalized_arxiv_id if normalized_arxiv_id else False
        )
        title_match = self._normalized_title_expression() == normalized_title
        lexical_rank = func.ts_rank_cd(DBPaper.search_vector, ts_query, 32)

        # Keep unindexed identity predicates in their own lane so the lexical
        # branch remains eligible for the partial GIN index. A paper can occur
        # in both branches; aggregation retains its best identity tier and FTS
        # rank before the SQL-level limit is applied.
        date_filters = []
        if start_date is not None:
            date_filters.append(DBPaper.date_published >= start_date)
        if end_date is not None:
            date_filters.append(DBPaper.date_published <= end_date)
        if has_official_implementation:
            date_filters.append(family_repository_exists_clause(official_only=True))
        if has_code:
            date_filters.append(family_repository_exists_clause())
        if has_hf_artifacts:
            date_filters.append(hf_artifacts_exist_clause())

        identity_candidates = select(
            DBPaper.id.label("paper_id"),
            DBPaper.citation_count.label("citation_count"),
            DBPaper.date_published.label("date_published"),
            case((arxiv_match, 0), else_=1).label("identity_tier"),
            lexical_rank.label("lexical_rank"),
        ).where(
            DBPaper.is_latest_version,
            or_(arxiv_match, title_match),
            *date_filters,
        )
        lexical_candidates = select(
            DBPaper.id.label("paper_id"),
            DBPaper.citation_count.label("citation_count"),
            DBPaper.date_published.label("date_published"),
            func.cast(2, DBPaper.id.type).label("identity_tier"),
            lexical_rank.label("lexical_rank"),
        ).where(
            DBPaper.is_latest_version,
            DBPaper.search_vector.op("@@")(ts_query),
            *date_filters,
        )
        normalized_author = func.lower(
            func.regexp_replace(func.btrim(DBAuthor.name), r"\s+", " ", "g")
        )
        author_candidates = (
            select(
                PaperAuthor.paper_id.label("paper_id"),
                DBPaper.citation_count.label("citation_count"),
                DBPaper.date_published.label("date_published"),
                case((normalized_author == normalized_title, 1), else_=2).label(
                    "identity_tier"
                ),
                lexical_rank.label("lexical_rank"),
            )
            .join(DBAuthor, DBAuthor.id == PaperAuthor.author_id)
            .join(DBPaper, DBPaper.id == PaperAuthor.paper_id)
            .where(
                DBPaper.is_latest_version,
                func.to_tsvector("simple", DBAuthor.name).op("@@")(author_ts_query),
                *date_filters,
            )
        )
        candidates = identity_candidates.union_all(
            lexical_candidates, author_candidates
        ).subquery()
        ranked_candidates = (
            select(
                candidates.c.paper_id,
                candidates.c.citation_count,
                candidates.c.date_published,
                func.min(candidates.c.identity_tier).label("identity_tier"),
                func.max(candidates.c.lexical_rank).label("lexical_rank"),
            )
            .group_by(
                candidates.c.paper_id,
                candidates.c.citation_count,
                candidates.c.date_published,
            )
            .subquery()
        )
        # Rank narrow candidate rows before fetching full paper records. The
        # citation/date tie-breakers are identical in every lane for a paper.
        ranked_candidates = (
            select(ranked_candidates)
            .order_by(
                ranked_candidates.c.identity_tier.asc(),
                ranked_candidates.c.lexical_rank.desc(),
                ranked_candidates.c.citation_count.desc(),
                ranked_candidates.c.date_published.desc().nullslast(),
                ranked_candidates.c.paper_id.asc(),
            )
            .limit(limit)
            .subquery()
        )

        return (
            self.db.query(DBPaper)
            .join(ranked_candidates, ranked_candidates.c.paper_id == DBPaper.id)
            .order_by(
                ranked_candidates.c.identity_tier.asc(),
                ranked_candidates.c.lexical_rank.desc(),
                DBPaper.citation_count.desc(),
                DBPaper.date_published.desc().nullslast(),
                DBPaper.id.asc(),
            )
            .all()
        )

    def _search_papers_hybrid(
        self,
        query: str,
        limit: int,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> List[DBPaper]:
        """Fuse weighted FTS and pgvector ranks, falling back immediately to FTS."""
        candidate_limit = max(50, limit)
        lexical = self._search_papers_fts(
            query,
            candidate_limit,
            start_date=start_date,
            end_date=end_date,
            has_official_implementation=has_official_implementation,
            has_code=has_code,
            has_hf_artifacts=has_hf_artifacts,
        )
        lexical_candidates = [
            RankedCandidate(int(paper.id), rank)
            for rank, paper in enumerate(lexical, 1)
        ]
        fingerprint = hashlib.sha256(query.casefold().encode()).hexdigest()[:16]
        started = datetime.now(timezone.utc)
        try:
            generation, semantic_candidates = self._semantic_candidates(
                query,
                candidate_limit,
                start_date=start_date,
                end_date=end_date,
                has_official_implementation=has_official_implementation,
                has_code=has_code,
                has_hf_artifacts=has_hf_artifacts,
            )
        except Exception as error:
            self.applied_mode = "keyword"
            fallback_reason = type(error).__name__ + ":" + str(error)[:80]
            search_logger.info(
                "paper_search mode=keyword_fallback fingerprint=%s results=%s fallback=%s",
                fingerprint,
                len(lexical),
                fallback_reason,
            )
            return lexical[:limit]

        fused = reciprocal_rank_fusion(
            [
                (lexical_candidates, self.settings.hybrid_lexical_weight),
                (semantic_candidates, self.settings.hybrid_semantic_weight),
            ],
            rrf_k=self.settings.hybrid_rrf_k,
        )
        # Preserve deterministic exact-title/ArXiv identity overrides.
        normalized_title = " ".join(query.lower().split())
        normalized_arxiv = self._normalize_arxiv_search_query(query)
        identity_ids = {
            int(paper.id)
            for paper in lexical
            if " ".join(paper.title.lower().split()) == normalized_title
            or (normalized_arxiv and paper.arxiv_id == normalized_arxiv)
        }
        fused_positions = {
            paper_id: index for index, (paper_id, _score, _ranks) in enumerate(fused)
        }
        ordered_ids = sorted(
            (paper_id for paper_id, _, _ in fused),
            key=lambda paper_id: (
                paper_id not in identity_ids,
                fused_positions[paper_id],
            ),
        )[:limit]
        papers_query = self.db.query(DBPaper).filter(DBPaper.id.in_(ordered_ids))
        if start_date is not None:
            papers_query = papers_query.filter(DBPaper.date_published >= start_date)
        if end_date is not None:
            papers_query = papers_query.filter(DBPaper.date_published <= end_date)
        papers = papers_query.all()
        by_id = {int(paper.id): paper for paper in papers}
        elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        search_logger.info(
            "paper_search mode=hybrid fingerprint=%s generation=%s results=%s "
            "latency_ms=%.1f component_ranks=%s",
            fingerprint,
            generation.id,
            len(ordered_ids),
            elapsed_ms,
            [
                {"paper_id": paper_id, **ranks}
                for paper_id, _score, ranks in fused[: min(limit, 10)]
            ],
        )
        return [by_id[paper_id] for paper_id in ordered_ids if paper_id in by_id]

    def _semantic_candidates(
        self,
        query: str,
        limit: int,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> tuple[ActiveGeneration, list[RankedCandidate]]:
        if self.settings.query_embedder != "hf_endpoint":
            raise QueryEmbeddingUnavailable("query_embedder_disabled")
        retrieval = EmbeddingRetrievalService(self.db)
        generation = retrieval.active_generation(self.settings.embedding_generation_id)
        if generation is None:
            raise QueryEmbeddingUnavailable("no_active_generation")
        client = get_query_embedding_client(
            self.settings.hf_query_embedding_endpoint_url,
            self.settings.hf_token,
            self.settings.query_embedding_timeout_ms,
            self.settings.query_embedding_max_concurrency,
        )
        return generation, retrieval.encode_and_search(
            query,
            generation,
            client,
            limit,
            start_date=start_date,
            end_date=end_date,
            has_official_implementation=has_official_implementation,
            has_code=has_code,
            has_hf_artifacts=has_hf_artifacts,
        )

    def _search_papers_semantic(
        self,
        query: str,
        limit: int,
        start_date: date | None = None,
        end_date: date | None = None,
        has_official_implementation: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> List[DBPaper]:
        """Dense query-to-paper retrieval with exact-identity and keyword fallback."""
        fingerprint = hashlib.sha256(query.casefold().encode()).hexdigest()[:16]
        started = datetime.now(timezone.utc)
        try:
            generation, candidates = self._semantic_candidates(
                query,
                max(50, limit),
                start_date=start_date,
                end_date=end_date,
                has_official_implementation=has_official_implementation,
                has_code=has_code,
                has_hf_artifacts=has_hf_artifacts,
            )
        except Exception as error:
            self.applied_mode = "keyword"
            search_logger.info(
                "paper_search mode=keyword_fallback fingerprint=%s fallback=%s",
                fingerprint,
                type(error).__name__ + ":" + str(error)[:80],
            )
            return self._search_papers_fts(
                query,
                limit,
                start_date=start_date,
                end_date=end_date,
                has_official_implementation=has_official_implementation,
                has_code=has_code,
                has_hf_artifacts=has_hf_artifacts,
            )

        normalized_title = " ".join(query.lower().split())
        normalized_arxiv = self._normalize_arxiv_search_query(query)
        identity_query = self.db.query(DBPaper).filter(
            DBPaper.is_latest_version,
            or_(
                self._normalized_title_expression() == normalized_title,
                DBPaper.arxiv_id == normalized_arxiv if normalized_arxiv else False,
            ),
        )
        if start_date is not None:
            identity_query = identity_query.filter(DBPaper.date_published >= start_date)
        if end_date is not None:
            identity_query = identity_query.filter(DBPaper.date_published <= end_date)
        if has_official_implementation:
            identity_query = identity_query.filter(
                family_repository_exists_clause(official_only=True)
            )
        identity_query = self._filter_query_by_search_artifacts(
            identity_query, has_code, has_hf_artifacts
        )
        identity_rows = identity_query.order_by(DBPaper.id).all()
        ordered_ids = [int(paper.id) for paper in identity_rows]
        ordered_ids.extend(
            candidate.paper_id
            for candidate in candidates
            if candidate.paper_id not in ordered_ids
        )
        ordered_ids = ordered_ids[:limit]
        papers_query = self.db.query(DBPaper).filter(DBPaper.id.in_(ordered_ids))
        if start_date is not None:
            papers_query = papers_query.filter(DBPaper.date_published >= start_date)
        if end_date is not None:
            papers_query = papers_query.filter(DBPaper.date_published <= end_date)
        if has_official_implementation:
            papers_query = papers_query.filter(
                family_repository_exists_clause(official_only=True)
            )
        papers_query = self._filter_query_by_search_artifacts(
            papers_query, has_code, has_hf_artifacts
        )
        papers = papers_query.all()
        by_id = {int(paper.id): paper for paper in papers}
        elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
        search_logger.info(
            "paper_search mode=semantic fingerprint=%s generation=%s results=%s "
            "latency_ms=%.1f",
            fingerprint,
            generation.id,
            len(ordered_ids),
            elapsed_ms,
        )
        return [by_id[paper_id] for paper_id in ordered_ids if paper_id in by_id]

    def get_related_papers(
        self, paper_identifier: str, limit: int = 4
    ) -> list[RelatedPaperRecommendation]:
        source = self._resolve_db_paper_by_id_or_arxiv(paper_identifier)
        retrieval = EmbeddingRetrievalService(self.db)
        generation = None
        if self.settings.related_papers_mode == "embedding":
            try:
                generation = retrieval.active_generation(
                    self.settings.embedding_generation_id
                )
            except Exception:
                generation = None
        cache_key = (
            self.db.get_bind().url.database,
            int(source.id),
            self.settings.related_papers_mode,
            generation.id if generation else None,
            generation.ranking_version if generation else "task-v1",
            self.settings.related_papers_min_similarity,
            limit,
        )
        cached = _related_cache_get(cache_key)
        if cached is not None:
            return cached
        selected: list[tuple[int, str, float | None, int | None, bool]] = []
        seen = {int(source.id)}
        if self.settings.related_papers_mode == "embedding":
            try:
                if generation:
                    started = datetime.now(timezone.utc)
                    dense, stale = retrieval.related_dense(source, generation, limit=50)
                    ranked = dense
                    provenance = "dense"
                    if generation.ranking_version.startswith("hybrid"):
                        lexical = retrieval.related_lexical(source.id, limit=50)
                        fused = reciprocal_rank_fusion(
                            [(lexical, 1.0), (dense, 1.0)], rrf_k=60
                        )
                        dense_scores = {item.paper_id: item.score for item in dense}
                        ranked = [
                            RankedCandidate(paper_id, rank, dense_scores.get(paper_id))
                            for rank, (paper_id, _score, _ranks) in enumerate(fused, 1)
                        ]
                        provenance = "hybrid"
                    for candidate in ranked:
                        if (
                            self.settings.related_papers_min_similarity is not None
                            and candidate.score is not None
                            and candidate.score
                            < self.settings.related_papers_min_similarity
                        ):
                            continue
                        selected.append(
                            (
                                candidate.paper_id,
                                provenance,
                                candidate.score,
                                generation.id,
                                stale,
                            )
                        )
                        seen.add(candidate.paper_id)
                        if len(selected) == limit:
                            break
                    logger = logging.getLogger("backend.related_papers")
                    logger.info(
                        "related_papers paper_id=%s generation=%s source_vector=%s "
                        "dense_count=%s latency_ms=%.1f",
                        source.id,
                        generation.id,
                        "stale" if stale else "current",
                        len(selected),
                        (datetime.now(timezone.utc) - started).total_seconds() * 1000,
                    )
            except Exception as error:
                logging.getLogger("backend.related_papers").warning(
                    "related_papers fallback paper_id=%s reason=%s",
                    source.id,
                    (type(error).__name__ + ":" + str(error))[:120],
                )
        if len(selected) < limit:
            for paper_id in retrieval.task_fallback(source.id, limit * 2):
                if paper_id in seen:
                    continue
                selected.append((paper_id, "task_fallback", None, None, False))
                seen.add(paper_id)
                if len(selected) == limit:
                    break
        ids = [item[0] for item in selected]
        papers = self.db.query(DBPaper).filter(DBPaper.id.in_(ids)).all() if ids else []
        by_id = {int(paper.id): paper for paper in papers}
        summaries = {
            int(summary.id): summary
            for summary in self._convert_db_papers_to_summaries(papers)
        }
        recommendations = []
        for paper_id, provenance, similarity, generation_id, stale in selected:
            paper = by_id.get(paper_id)
            if paper is None:
                continue
            summary = summaries[int(paper.id)].model_dump()
            recommendations.append(
                RelatedPaperRecommendation(
                    **summary,
                    provenance=provenance,
                    similarity=similarity,
                    generation_id=generation_id,
                    used_stale_source_vector=stale,
                )
            )
        _related_cache_put(cache_key, recommendations)
        return recommendations
