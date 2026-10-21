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
- A hyphenated prefix makes a different name: ``Flow-GRPO``, ``delta-VAE``,
  and ``m-EuroSAT`` never yield ``GRPO``, ``VAE``, or ``EuroSAT``.
- A match followed by a capitalised word or a number (``SWE-Bench Lite``,
  ``RoboTwin 2.0``), or preceded by a capitalised word in the same phrase
  (``Geometry-Change VLA``), is flagged ``variant_suspect`` so the judge decides
  whether it names something else.
- A plain-word method name capitalised inside a longer capitalised name
  (``World Embedding Benchmark``) belongs to that name and is skipped.
- A generic method is dropped from an abstract that also mentions a more
  specific method containing its name: ``Transformer`` goes when ``Looped Transformer``
  or ``Diffusion Transformer`` is present.
- Method names written ``Diffusion Transformer (DiT)`` match as the long form
  and as the abbreviation, and so does the method's full name
  (``World Action Models (WAMs)`` gives ``WAMs`` and ``WAM``); ``Diffusion Transformers (DiTs)`` becomes one span.
  Method names also match their plural (``DiTs``, ``LLMs``, ``Transformers``).
  An exact catalog name always beats an abbreviation or plural.
- A version after a family name keeps the match (``LLaVA-1.5`` links
  ``LLaVA``); a name that already carries a version does not (``Qwen3.5`` is
  not ``Qwen3``).
- Frameworks (``llama.cpp``, ``vLLM``) match like single names, without plurals.
- URLs and ``$...$`` math are skipped.
- A model-size suffix keeps the match: ``REPA-XL/2``, ``Qwen3-8B``, and
  ``ViT-B/16`` link ``REPA``, ``Qwen3``, and ``ViT``.
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
_MATH = re.compile(r"\$\$.+?\$\$|\$[^$]+\$|https?://\S+", re.S)
_PLAIN_WORD = re.compile(r"[A-Za-z][a-z]*")
_VARIANT_WORD = re.compile(r"[A-Z0-9]")
# A trailing bracket whose first word has two capitals: (DiT), (WAMs), (KV cache).
_ABBREVIATION = re.compile(
    r"\s*\(((?=[^\s)]*[A-Z][^\s)]*[A-Z])[A-Za-z0-9\-]+(?: [A-Za-z0-9\-]+){0,2})\)\s*$"
)
_SIZE_SUFFIX = re.compile(
    r"-(?:(?:XXL|XL|XS|[SMLBHG])(?:/\d+)?|\d+(?:\.\d+)?[BMKT]|\d+x\d+[BM]?)(?![\w.])"
)
_PAREN_ALIAS = re.compile(r"[ \t]*\([ \t]*([^()\n]{1,40}?)[ \t]*\)")

# Lower ranks win when two entities claim the same surface.
NAME, ABBREVIATION, PLURAL = 0, 1, 2


@dataclass(frozen=True)
class CatalogEntity:
    entity_type: str  # "method", "dataset", or "framework"
    entity_id: int
    name: str
    slug: str
    parent_id: int | None = None
    full_name: str | None = None


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
    # (entity_type, entity_id) -> lowercased tokens of its matchable name
    names: dict[tuple[str, int], tuple[str, ...]]


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
    # name tokens -> (rank, owning entity, the name as written)
    targets: dict[tuple[str, ...], list[tuple[int, CatalogEntity, str]]] = defaultdict(
        list
    )
    unresolved: list[tuple[str, list[CatalogEntity]]] = []

    def add(written: str, entity: CatalogEntity, rank: int) -> None:
        key = tuple(normalize_name(written).split())
        if key:
            targets[key].append((rank, entity, written))
        if entity.entity_type == "method" and rank != PLURAL and key:
            last = tokenize(written)[-1]
            if last[-1:].isalpha() and last[-1:].lower() != "s":
                add(written + "s", entity, PLURAL)

    def add_named(written: str, entity: CatalogEntity, rank: int) -> None:
        abbreviation = _ABBREVIATION.search(written)
        add(base_name(written), entity, rank)
        if abbreviation:
            short = abbreviation.group(1)
            add(short, entity, ABBREVIATION)
            if re.fullmatch(r"[A-Z][A-Za-z0-9\-]*[A-Z]s", short):
                add(short[:-1], entity, ABBREVIATION)  # WAMs -> WAM

    for entity in entities:
        if entity.entity_type == "method":
            add_named(entity.name, entity, NAME)
            if entity.full_name and entity.full_name != entity.name:
                add_named(entity.full_name, entity, ABBREVIATION)
        elif entity.entity_type == "framework":
            add(entity.name, entity, NAME)

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
        targets[tuple(key_text.split())].append((NAME, target, written))

    surfaces: dict[tuple[str, ...], list[_Surface]] = {}
    for key, owners in targets.items():
        if len(key) > MAX_NAME_TOKENS:
            continue
        chosen = None
        for rank in sorted({rank for rank, _, _ in owners}):
            distinct = {
                (o.entity_type, o.entity_id): (o, w) for r, o, w in owners if r == rank
            }
            if len(distinct) == 1:
                chosen = next(iter(distinct.values()))
                break
            # Two entities share this name; a lower-ranked unique owner may still win.
            unresolved.append((" ".join(key), [o for o, _ in distinct.values()]))
        if chosen is None:
            continue
        owner, written = chosen
        tokens = tuple(tokenize(written))
        surfaces[key] = [_Surface(owner, tokens, _case_sensitive(owner, tokens))]
    names = {
        (o.entity_type, o.entity_id): key
        for key, owners in targets.items()
        for rank, o, _ in owners
        if rank == NAME and key in surfaces
    }
    max_tokens = max((len(k) for k in surfaces), default=0)
    return MentionIndex(
        surfaces=surfaces, max_tokens=max_tokens, unresolved=unresolved, names=names
    )


def _masked(abstract: str) -> str:
    return _MATH.sub(lambda m: " " * len(m.group()), abstract)


def _continues_as_variant(text_value: str, end: int, surface: _Surface) -> bool:
    rest = text_value[end : end + 2]
    if len(rest) < 2:
        return False
    if _SIZE_SUFFIX.match(text_value, end):
        return False
    versioned = rest[0] in ".-" and rest[1].isdigit()
    if versioned and _is_unversioned_method(surface):
        return False  # LLaVA-1.5 is still LLaVA
    if rest[0] == "." and rest[1].isdigit():
        return True
    return rest[0] == "-" and (rest[1].isupper() or rest[1].isdigit())


def _is_unversioned_method(surface: _Surface) -> bool:
    return surface.entity.entity_type == "method" and not any(
        ch.isdigit() for token in surface.tokens for ch in token
    )


def _has_hyphenated_prefix(text_value: str, start: int) -> bool:
    return (
        start >= 2 and text_value[start - 1] == "-" and text_value[start - 2].isalnum()
    )


def _followed_by_variant_word(text_value: str, end: int) -> bool:
    match = re.match(r"[ \t]+(\S)", text_value[end:])
    return bool(match and _VARIANT_WORD.match(match.group(1)))


def _preceded_by_name_word(text_value: str, start: int) -> bool:
    """True for ``Geometry-Change VLA``; false at a sentence or clause start."""
    match = re.search(r"(\S+)[ \t]+$", text_value[:start])
    word = match.group(1) if match else ""
    if not word or not word[0].isupper() or not word[-1].isalnum():
        return False
    before = text_value[: match.start()].rstrip()
    return bool(before) and before[-1] not in ".!?:;"


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
        matched = _longest_match(index, masked, tokens, words, lowered, i)
        if matched is None:
            i += 1
            continue
        n, surface = matched
        start, end = tokens[i].start(), tokens[i + n - 1].end()
        end = _absorb_parenthesised_alias(index, abstract, masked, end, surface)
        inside_name = _followed_by_variant_word(masked, end) or _preceded_by_name_word(
            masked, start
        )
        part_of_other_name = (
            _continues_as_variant(masked, end, surface)
            or _has_hyphenated_prefix(masked, start)
            or (
                inside_name and _is_capitalised_plain_word(surface, abstract[start:end])
            )
        )
        if not part_of_other_name:
            candidates.append(
                Candidate(
                    entity_type=surface.entity.entity_type,
                    entity_id=surface.entity.entity_id,
                    start=start,
                    end=end,
                    surface=abstract[start:end],
                    variant_suspect=inside_name,
                )
            )
        i += n
        while i < len(tokens) and tokens[i].start() < end:
            i += 1
    return _drop_subsumed(candidates, index)


def _drop_subsumed(candidates: list[Candidate], index: MentionIndex) -> list[Candidate]:
    present = {
        (c.entity_type, c.entity_id) for c in candidates if c.entity_type == "method"
    }
    names = {key: index.names.get(key, ()) for key in present}

    def subsumed(key: tuple[str, int]) -> bool:
        name = names[key]
        return bool(name) and any(
            other != key and len(longer) > len(name) and _contains(longer, name)
            for other, longer in names.items()
        )

    dropped = {key for key in present if subsumed(key)}
    return [c for c in candidates if (c.entity_type, c.entity_id) not in dropped]


def _contains(longer: tuple[str, ...], part: tuple[str, ...]) -> bool:
    return any(
        longer[i : i + len(part)] == part for i in range(len(longer) - len(part) + 1)
    )


def _is_capitalised_plain_word(surface: _Surface, written: str) -> bool:
    return (
        surface.entity.entity_type == "method"
        and len(surface.tokens) == 1
        and not surface.case_sensitive
        and written[:1].isupper()
    )


def _longest_match(index, masked, tokens, words, lowered, i):
    for n in range(min(index.max_tokens, len(tokens) - i), 0, -1):
        surfaces = index.surfaces.get(tuple(lowered[i : i + n]))
        if not surfaces or not _contiguous(masked, tokens[i : i + n]):
            continue
        surface = surfaces[0]
        if surface.case_sensitive and tuple(words[i : i + n]) != surface.tokens:
            continue
        return n, surface
    return None


def _absorb_parenthesised_alias(
    index: MentionIndex, abstract: str, masked: str, end: int, surface: _Surface
) -> int:
    """Extend ``Diffusion Transformers`` over a following ``(DiTs)``."""
    paren = _PAREN_ALIAS.match(masked, end)
    if not paren:
        return end
    inner = list(_TOKEN.finditer(paren.group(1)))
    words = [t.group() for t in inner]
    matched = _longest_match(
        index, paren.group(1), inner, words, [w.lower() for w in words], 0
    )
    if matched and matched[0] == len(inner) and matched[1].entity == surface.entity:
        return paren.end()
    return end


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
            SELECT 'method' AS entity_type, id, name, slug,
                   NULL::bigint AS parent_id, full_name
            FROM methods WHERE slug IS NOT NULL
            UNION ALL
            SELECT 'dataset', id, name, slug, parent_dataset_id, NULL FROM datasets
            UNION ALL
            SELECT 'framework', id, name, slug, NULL, NULL FROM frameworks
            """
        )
    ).all()
    return [
        CatalogEntity(
            row.entity_type,
            int(row.id),
            row.name,
            row.slug,
            row.parent_id,
            row.full_name,
        )
        for row in rows
    ]
