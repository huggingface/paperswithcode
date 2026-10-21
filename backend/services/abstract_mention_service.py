"""Find literal method and benchmark names in paper abstracts.

Candidate generation is deterministic: it only finds where a catalog name
literally occurs. Whether a candidate becomes a link is decided later, by the
entity's ``abstract_linking`` mode and, for ambiguous names, by a judge model.

Matching rules:

- Names and text are split into word tokens; whitespace, hyphens, underscores,
  and slashes all separate tokens, so ``Terminal-Bench 2.0`` matches the row
  named ``Terminal Bench 2.0``.
- The longest name wins (``SWE-Bench Verified`` beats ``SWE-Bench``).
- Multi-token names match case-insensitively. Single-token names match exact
  case, except plain-word method names such as ``Dropout``, so benchmark names
  like ``MATH``, ``FRAMES``, or ``Spider`` never hit ordinary words.
- A version continuation ends nothing: ``Qwen3.5``, ``Qwen3-VL``, and
  ``LIBERO-Goal`` never yield ``Qwen3`` or ``LIBERO``. Lowercase modifiers stay
  allowed (``GRPO-based``).
- A match followed by a capitalised word or a number (``SWE-Bench Lite``) is
  flagged ``variant_suspect`` so the judge decides whether it names a variant.
- Text inside ``$...$`` math is skipped.
- Benchmark names lose a trailing ``(...)`` or `` — ...`` qualifier. When
  several benchmarks share the resulting base name, the unqualified one wins,
  then the group's single parent, then a parent all variants share; otherwise
  the base name is unresolved and not matched.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_NAME_TOKENS = 16

_TOKEN = re.compile(r"[^\W_](?:[\w.+]*[\w+])?")
_SEPARATOR = re.compile(r"[\s\-_/'’]+")
_QUALIFIER = re.compile(r"\s*(?:\([^()]*\)|\s—\s.*)\s*$")
_MATH = re.compile(r"\$\$.+?\$\$|\$[^$]+\$", re.S)
_PLAIN_WORD = re.compile(r"[A-Za-z][a-z]*")
_VARIANT_WORD = re.compile(r"[A-Z0-9]")


@dataclass(frozen=True)
class CatalogEntity:
    entity_type: str  # "method" or "dataset"
    entity_id: int
    name: str
    slug: str
    parent_id: int | None = None


@dataclass(frozen=True)
class Candidate:
    entity_type: str
    entity_id: int
    start: int
    end: int
    surface: str
    variant_suspect: bool


@dataclass(frozen=True)
class _Surface:
    entity: CatalogEntity
    tokens: tuple[str, ...]
    case_sensitive: bool


@dataclass
class MentionIndex:
    surfaces: dict[tuple[str, ...], list[_Surface]]
    max_tokens: int
    unresolved: list[tuple[str, list[CatalogEntity]]]


def normalize_name(name: str) -> str:
    return " ".join(token.lower() for token in tokenize(name))


def tokenize(value: str) -> list[str]:
    return [m.group() for m in _TOKEN.finditer(value)]


def base_name(name: str) -> str:
    """Strip trailing protocol qualifiers: ``LIBERO-Plus (SFT)`` -> ``LIBERO-Plus``."""
    previous = None
    while previous != name:
        previous, name = name, _QUALIFIER.sub("", name).strip()
    return name


def _case_sensitive(entity: CatalogEntity, tokens: tuple[str, ...]) -> bool:
    if len(tokens) > 1:
        return False
    return not (entity.entity_type == "method" and _PLAIN_WORD.fullmatch(tokens[0]))


def _resolve_benchmark_group(
    members: list[CatalogEntity], by_id: dict[int, CatalogEntity]
) -> CatalogEntity | None:
    plain = [m for m in members if base_name(m.name) == m.name]
    if len(plain) == 1:
        return plain[0]
    if len(plain) > 1:
        return None
    ids = {m.entity_id for m in members}
    roots = [m for m in members if m.parent_id not in ids]
    if len(roots) == 1 and len(members) > 1:
        return roots[0]
    if len(members) == 1:
        # A lone qualified split resolves to its parent when the parent names
        # the same benchmark (`WEAR (Inertia-1 Protocol)` -> `WEAR Outdoor ...`).
        child = members[0]
        parent = by_id.get(child.parent_id) if child.parent_id else None
        if parent and normalize_name(parent.name).startswith(
            normalize_name(base_name(child.name))
        ):
            return parent
        return child
    shared = {m.parent_id for m in roots}
    if len(shared) == 1 and (parent_id := shared.pop()) in by_id:
        return by_id[parent_id]
    return None


def build_index(entities: Iterable[CatalogEntity]) -> MentionIndex:
    entities = list(entities)
    datasets = {e.entity_id: e for e in entities if e.entity_type == "dataset"}
    # name tokens -> (owning entity, the name as written)
    targets: dict[tuple[str, ...], list[tuple[CatalogEntity, str]]] = defaultdict(list)
    unresolved: list[tuple[str, list[CatalogEntity]]] = []

    for entity in entities:
        if entity.entity_type == "method":
            key = tuple(normalize_name(entity.name).split())
            if key:
                targets[key].append((entity, entity.name))

    groups: dict[str, list[CatalogEntity]] = defaultdict(list)
    for dataset in datasets.values():
        groups[normalize_name(base_name(dataset.name))].append(dataset)
    for key_text, members in groups.items():
        if not key_text:
            continue
        target = _resolve_benchmark_group(members, datasets)
        if target is None:
            unresolved.append((key_text, members))
            continue
        written = base_name((target if target in members else members[0]).name)
        targets[tuple(key_text.split())].append((target, written))

    surfaces: dict[tuple[str, ...], list[_Surface]] = {}
    for key, owners in targets.items():
        if len(key) > MAX_NAME_TOKENS:
            continue
        distinct = {(o.entity_type, o.entity_id): (o, w) for o, w in owners}
        if len(distinct) > 1:
            unresolved.append((" ".join(key), [o for o, _ in distinct.values()]))
            continue
        owner, written = next(iter(distinct.values()))
        tokens = tuple(tokenize(written))
        surfaces[key] = [_Surface(owner, tokens, _case_sensitive(owner, tokens))]
    max_tokens = max((len(k) for k in surfaces), default=0)
    return MentionIndex(surfaces=surfaces, max_tokens=max_tokens, unresolved=unresolved)


def _masked(abstract: str) -> str:
    return _MATH.sub(lambda m: " " * len(m.group()), abstract)


def _continues_as_variant(text_value: str, end: int) -> bool:
    rest = text_value[end : end + 2]
    if len(rest) < 2:
        return False
    if rest[0] == "." and rest[1].isdigit():
        return True
    return rest[0] == "-" and (rest[1].isupper() or rest[1].isdigit())


def _followed_by_variant_word(text_value: str, end: int) -> bool:
    match = re.match(r"[ \t]+(\S)", text_value[end:])
    return bool(match and _VARIANT_WORD.match(match.group(1)))


def find_candidates(abstract: str, index: MentionIndex) -> list[Candidate]:
    """Return literal catalog mentions in ``abstract`` with character offsets."""
    if not abstract or not index.surfaces:
        return []
    masked = _masked(abstract)
    tokens = list(_TOKEN.finditer(masked))
    words = [t.group() for t in tokens]
    lowered = [w.lower() for w in words]
    candidates: list[Candidate] = []
    i = 0
    while i < len(tokens):
        matched = None
        for n in range(min(index.max_tokens, len(tokens) - i), 0, -1):
            surfaces = index.surfaces.get(tuple(lowered[i : i + n]))
            if not surfaces:
                continue
            if not _contiguous(masked, tokens[i : i + n]):
                continue
            surface = surfaces[0]
            if surface.case_sensitive and tuple(words[i : i + n]) != surface.tokens:
                continue
            matched = (n, surface)
            break
        if matched is None:
            i += 1
            continue
        n, surface = matched
        start, end = tokens[i].start(), tokens[i + n - 1].end()
        if not _continues_as_variant(masked, end):
            candidates.append(
                Candidate(
                    entity_type=surface.entity.entity_type,
                    entity_id=surface.entity.entity_id,
                    start=start,
                    end=end,
                    surface=abstract[start:end],
                    variant_suspect=_followed_by_variant_word(masked, end),
                )
            )
        i += n
    return candidates


def _contiguous(text_value: str, tokens: list[re.Match]) -> bool:
    """Tokens of one name may only be separated by name separators."""
    return all(
        _SEPARATOR.fullmatch(text_value[a.end() : b.start()])
        for a, b in zip(tokens, tokens[1:])
    )


def load_catalog_entities(db: Session) -> list[CatalogEntity]:
    rows = db.execute(
        text(
            """
            SELECT 'method' AS entity_type, id, name, slug, NULL::bigint AS parent_id
            FROM methods WHERE slug IS NOT NULL
            UNION ALL
            SELECT 'dataset', id, name, slug, parent_dataset_id FROM datasets
            """
        )
    ).all()
    return [
        CatalogEntity(row.entity_type, int(row.id), row.name, row.slug, row.parent_id)
        for row in rows
    ]
