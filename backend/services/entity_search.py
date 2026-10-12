"""Shared mechanics for navigational benchmark, method, and task search."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import unquote, urlparse

from sqlalchemy import Text, case, cast, func, literal, or_


class EntitySearchKind(StrEnum):
    DATASET = "dataset"
    METHOD = "method"
    TASK = "task"


_ROUTES = {
    EntitySearchKind.DATASET: "benchmark",
    EntitySearchKind.METHOD: "methods",
    EntitySearchKind.TASK: "tasks",
}
_CANONICAL_HOSTS = {"paperswithcode.co", "www.paperswithcode.co"}
_ARROWS = "→←↔⇒⇐⇔⟶⟵"
_SEPARATORS = re.compile(r"[\s\-_()/\\[\]{}:;,\u2010-\u2015]+")
_TOKENS = re.compile(r"[^\W_]+", flags=re.UNICODE)

DETERMINISTIC_CANDIDATE_LIMIT = 500
FUZZY_CANDIDATE_LIMIT = 100
FUZZY_MIN_CONFIDENCE = 0.55
FUZZY_WINNING_MARGIN = 0.08


@dataclass(frozen=True)
class EntitySearchTerms:
    raw: str
    normalized: str
    tokens: tuple[str, ...]
    slug_identity: str | None
    identity_only: bool = False
    invalid: bool = False

    @property
    def usable(self) -> bool:
        return not self.invalid and bool(self.tokens or self.slug_identity)

    @property
    def lexical_query(self) -> str:
        return " ".join(self.tokens)

    @property
    def prefix_tsquery(self) -> str:
        return " & ".join(f"{token}:*" for token in self.tokens)


@dataclass(frozen=True)
class EntitySearchCandidate:
    entity_id: int
    name: str
    tier: int
    relevance: float


def normalize_entity_search_text(value: str | None) -> str:
    """Normalize only reviewed separators and symbols used by entity names."""
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.translate(
        str.maketrans(
            {
                "τ": "tau",
                "Τ": "tau",
                "σ": "sigma",
                "Σ": "sigma",
                "×": "x",
                **{arrow: " to " for arrow in _ARROWS},
            }
        )
    )
    normalized = _SEPARATORS.sub(" ", normalized.casefold())
    return " ".join(normalized.split())


def tokenize_entity_search_text(value: str | None) -> tuple[str, ...]:
    """Return safe ``simple``-configuration lexemes for prefix/FTS queries."""
    return tuple(_TOKENS.findall(normalize_entity_search_text(value)))


def prepare_entity_search(
    value: str | None, kind: EntitySearchKind
) -> EntitySearchTerms:
    """Parse trusted canonical routes, otherwise prepare an ordinary name query."""
    raw = (value or "").strip()
    if not raw:
        return EntitySearchTerms(raw="", normalized="", tokens=(), slug_identity=None)

    parsed = urlparse(raw)
    is_absolute_url = bool(parsed.scheme or parsed.netloc)
    is_route = raw.startswith("/")
    if is_absolute_url or is_route:
        if is_absolute_url:
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname not in _CANONICAL_HOSTS
            ):
                return EntitySearchTerms(
                    raw=raw,
                    normalized="",
                    tokens=(),
                    slug_identity=None,
                    invalid=True,
                )
            path = parsed.path
        else:
            path = parsed.path

        parts = [unquote(part) for part in path.split("/") if part]
        expected_route = _ROUTES[kind]
        if len(parts) != 2 or parts[0].casefold() != expected_route:
            return EntitySearchTerms(
                raw=raw,
                normalized="",
                tokens=(),
                slug_identity=None,
                invalid=True,
            )
        return EntitySearchTerms(
            raw=raw,
            normalized=normalize_entity_search_text(parts[1]),
            tokens=tokenize_entity_search_text(parts[1]),
            slug_identity=parts[1].casefold(),
            identity_only=True,
        )

    normalized = normalize_entity_search_text(raw)
    tokens = tokenize_entity_search_text(raw)
    # Numeric API IDs are intentionally not search identities. A numeric slug
    # can still be reached through its canonical entity route.
    slug_identity = None if raw.isdigit() or not tokens else raw.casefold()
    return EntitySearchTerms(
        raw=raw,
        normalized=normalized,
        tokens=tokens,
        slug_identity=slug_identity,
    )


def deterministic_match(
    terms: EntitySearchTerms,
    *,
    name: str,
    slug: str | None,
    full_name: str | None = None,
) -> tuple[int, float] | None:
    """Pure-Python equivalent of the PostgreSQL deterministic lanes."""
    if not terms.usable:
        return None
    if terms.slug_identity and (slug or "").casefold() == terms.slug_identity:
        return 0, 1.0
    if terms.identity_only:
        return None

    normalized_name = normalize_entity_search_text(name)
    if normalized_name == terms.normalized:
        return 1, 1.0
    if full_name and normalize_entity_search_text(full_name) == terms.normalized:
        return 2, 1.0

    name_tokens = tokenize_entity_search_text(name)
    if terms.tokens and all(
        any(name_token.startswith(query_token) for name_token in name_tokens)
        for query_token in terms.tokens
    ):
        return 3, 1.0
    if terms.tokens and all(token in name_tokens for token in terms.tokens):
        return 4, len(terms.tokens) / max(1, len(name_tokens))
    return None


def postgres_search_expressions(model, terms: EntitySearchTerms, *, full_name=None):
    """Build indexed PostgreSQL predicates and relevance expressions."""
    slug_exact = (
        func.lower(model.slug) == terms.slug_identity
        if terms.slug_identity
        else literal(False)
    )
    if terms.identity_only:
        return (
            slug_exact,
            case((slug_exact, 0), else_=5),
            case((slug_exact, 1.0), else_=0.0),
        )

    normalized_name = func.pwc_entity_search_normalize(model.name)
    exact_name = normalized_name == terms.normalized
    exact_full_name = (
        func.pwc_entity_search_normalize(full_name) == terms.normalized
        if full_name is not None
        else literal(False)
    )

    if terms.tokens:
        prefix_query = func.to_tsquery("simple", terms.prefix_tsquery)
        lexical_query = func.websearch_to_tsquery("simple", terms.lexical_query)
        normalized_vector = func.to_tsvector("simple", normalized_name)
        prefix_match = or_(
            model.search_vector.op("@@")(prefix_query),
            normalized_vector.op("@@")(prefix_query),
        )
        lexical_match = model.search_vector.op("@@")(lexical_query)
        # A single term's cover density only counts its repetitions (and the
        # raw-name vector double-counts hyphenated compounds such as
        # "human-scene"), so treat single-term matches as textual ties that
        # entity trends break, like `deterministic_match`. Multi-term queries
        # rank adjacency on the separator-normalized name.
        if len(terms.tokens) == 1:
            relevance = case((prefix_match, 1.0), else_=0.0)
        else:
            relevance = func.greatest(
                func.coalesce(
                    func.ts_rank_cd(model.search_vector, lexical_query, 32), 0.0
                ),
                func.coalesce(
                    func.ts_rank_cd(
                        func.setweight(normalized_vector, "A"), prefix_query, 32
                    ),
                    0.0,
                ),
            )
    else:
        prefix_match = literal(False)
        lexical_match = literal(False)
        relevance = literal(0.0)

    predicate = or_(
        slug_exact,
        exact_name,
        exact_full_name,
        prefix_match,
        lexical_match,
    )
    tier = case(
        (slug_exact, 0),
        (exact_name, 1),
        (exact_full_name, 2),
        (prefix_match, 3),
        (lexical_match, 4),
        else_=5,
    )
    return predicate, tier, relevance


def postgres_fuzzy_ordering(name_column, normalized_query: str):
    """Return the indexed trigram distance and displayed-name similarity."""
    normalized_name = func.pwc_entity_search_normalize(name_column)
    distance = cast(literal(normalized_query), Text).op("<->")(normalized_name)
    similarity = func.similarity(normalized_query, normalized_name)
    return distance, similarity


def _damerau_levenshtein(left: str, right: str) -> int:
    """Optimal-string-alignment distance for short candidate windows."""
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous_previous: list[int] | None = None
    previous = list(range(len(right) + 1))
    for row_index, left_char in enumerate(left, start=1):
        current = [row_index]
        for column_index, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            value = min(
                current[column_index - 1] + 1,
                previous[column_index] + 1,
                previous[column_index - 1] + cost,
            )
            if (
                previous_previous is not None
                and row_index > 1
                and column_index > 1
                and left_char == right[column_index - 2]
                and left[row_index - 2] == right_char
            ):
                value = min(value, previous_previous[column_index - 2] + 1)
            current.append(value)
        previous_previous, previous = previous, current
    return previous[-1]


def _edit_confidence(query: str, name: str) -> float:
    query_tokens = tokenize_entity_search_text(query)
    name_tokens = tokenize_entity_search_text(name)
    if not query_tokens or not name_tokens:
        return 0.0
    window_size = min(len(query_tokens), len(name_tokens))
    query_compact = "".join(query_tokens)
    best = 0.0
    for start in range(len(name_tokens) - window_size + 1):
        candidate = "".join(name_tokens[start : start + window_size])
        denominator = max(1, len(query_compact), len(candidate))
        confidence = 1 - _damerau_levenshtein(query_compact, candidate) / denominator
        # Prefer an equally good typo repair that explains more of the
        # displayed name, without making a single misspelled long token too
        # weak to recover inside a multi-token name.
        coverage_factor = 0.7 + 0.3 * (window_size / len(name_tokens))
        best = max(best, confidence * coverage_factor)
    return best


def choose_fuzzy_winner(
    query: str,
    rows: list[tuple[int, str, float]],
    *,
    minimum: float = FUZZY_MIN_CONFIDENCE,
    margin: float = FUZZY_WINNING_MARGIN,
) -> EntitySearchCandidate | None:
    """Promote one typo candidate only when confidence and separation are clear."""
    ranked = [
        (
            max(float(similarity or 0.0), _edit_confidence(query, name)),
            int(entity_id),
            name,
        )
        for entity_id, name, similarity in rows
    ]
    ranked.sort(key=lambda row: (-row[0], row[2].casefold(), row[1]))
    if not ranked or ranked[0][0] < minimum:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < margin:
        return None
    confidence, entity_id, name = ranked[0]
    return EntitySearchCandidate(entity_id, name, 5, confidence)


def empty_page(container):
    return container(count=0, next_page=None, previous_page=None, results=[])
