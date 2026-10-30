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
  case when they could be an ordinary word (``MATH``, ``FRAMES``, ``Spider``),
  except plain-word method names such as ``Dropout``. Names with a digit or
  inner capitals (``GSM8K``, ``ImageNet``, ``LLaVA``) ignore case.
- A version continuation ends nothing: ``Qwen3.5``, ``Qwen3-VL``, and
  ``LIBERO-Goal`` never yield ``Qwen3`` or ``LIBERO``. Lowercase modifiers stay
  allowed (``GRPO-based``).
- A hyphenated prefix makes a different name: ``Flow-GRPO``, ``delta-VAE``,
  and ``m-EuroSAT`` never yield ``GRPO``, ``VAE``, or ``EuroSAT``.
- A match followed by a capitalised word or a number (``SWE-Bench Lite``,
  ``RoboTwin 2.0``), or preceded by a capitalised word in the same phrase
  (``Geometry-Change VLA``), is flagged ``variant_suspect`` so the judge decides
  whether it names something else. A bare one- or two-letter abbreviation
  (``SD``, ``CE``, ``AR``) is flagged too, unless the same abstract also names
  the entity in full.
- A plain-word method name capitalised inside a longer capitalised name
  (``World Embedding Benchmark``) belongs to that name and is skipped.
- A plain-word method is dropped from an abstract that also mentions a more
  specific method containing its name: ``Transformer`` goes when ``Looped Transformer``
  or ``Diffusion Transformer`` is present.
- An abbreviation in brackets right after the method's own long form takes the
  long form into the link: ``group-relative policy optimization (GRPO)``.
- Method names written ``Diffusion Transformer (DiT)`` match as the long form
  and as the abbreviation; a full name contributes its abbreviation only
  (``World Action Models (WAMs)`` gives ``WAMs`` and ``WAM``). An abbreviation
  the abstract defines with another expansion (``Inadequate Generalization
  (IG)``) is not linked anywhere in that abstract; ``Diffusion Transformers (DiTs)`` becomes one span.
  Method names also match their plural (``DiTs``, ``LLMs``, ``Transformers``).
  An exact catalog name always beats an abbreviation or plural.
- A version after a family name keeps the match (``LLaVA-1.5`` links
  ``LLaVA``); a name that already carries a version does not (``Qwen3.5`` is
  not ``Qwen3``).
- Frameworks (``llama.cpp``, ``vLLM``) match like single names, without plurals.
- URLs and ``$...$`` math are skipped, and an abbreviation between a name and
  its version, or inside a longer name, is read through
  (``Terminal-Bench (TB) 3.0``, ``autoregressive (AR) models``).
- A benchmark suffix that spells the benchmark's slug is part of the name
  (``ImageNet-1k`` for slug ``imagenet-1k``).
- A one-word name made of a prefix and an acronym also matches hyphenated
  (``BiLSTM`` and ``Bi-LSTMs``).
- Checkpoint suffixes keep a method match (``Qwen2.5-Math``, ``-Instruct``),
  and British spellings match (``quantisation``).
- A model-size suffix keeps a method match: ``REPA-XL/2``, ``Qwen3-8B``, and
  ``ViT-B/16`` link ``REPA``, ``Qwen3``, and ``ViT``.
- A benchmark that only exists as explicit versions (``MMEB-v2``, ``MMEB-v3``)
  links its bare name to the latest version.
- Curated aliases match like names but rank below them; a capitalised
  one-word alias (``Astra``) always goes to the judge, a lowercase technical
  word (``autoregressive``) does not.
- When a benchmark and a method share a name (benchmark ``GQA``, method
  ``Grouped-Query Attention (GQA)``), both become candidates for the judge,
  which keeps at most one per span.
- A list that writes the family once links each member that is a catalog
  name: ``SWE-bench Verified, Multilingual, and Pro``.
- Benchmark names lose a trailing ``(...)``, `` — ...``, or split word (``test``,
  ``val``, ``dev``), except an
  abbreviation of the name's initials, which also matches
  (``Humanity's Last Exam (HLE)`` gives ``HLE``). When
  several benchmarks share the resulting base name, the unqualified one wins,
  then the group's single parent, then a parent all variants share, then the
  test split, then the split with the most leaderboard evaluations.
"""

from __future__ import annotations

import re
from collections import defaultdict
import dataclasses
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_NAME_TOKENS = 16

# "@" stays inside a token, so metrics such as Pass@1 match only as written.
_TOKEN = re.compile(r"[^\W_](?:[\w.+@]*[\w+])?")
_PLAIN_TOKEN = re.compile(r"[^\W_](?:[\w.+]*[\w+])?")
_SEPARATOR = re.compile(r"[\s\-_/'’]+")
_QUALIFIER = re.compile(r"\s*(?:\([^()]*\)|\s—\s.*)\s*$")
_MATH = re.compile(r"\$\$.+?\$\$|\$[^$]+\$|https?://\S+", re.S)
_PLAIN_WORD = re.compile(r"[A-Za-z][a-z]*")
_VARIANT_WORD = re.compile(r"[A-Z0-9]")
# A trailing bracket of up to three words, one with two capitals: (DiT), (WAMs),
# (KV cache), (Online RL); not (Delayed Generalization) or (cross-encoder).
_ABBREVIATION = re.compile(
    r"\s*\(((?=[^)]*?\b[A-Za-z0-9\-]*[A-Z][A-Za-z0-9\-]*[A-Z])"
    r"[A-Za-z0-9\-]+(?: [A-Za-z0-9\-]+){0,2})\)\s*$"
)
_SIZE_SUFFIX = re.compile(
    r"-(?:(?:XXL|XL|XS)(?:/\d+)?|[SMLBHG]\+?/\d+|\d+(?:\.\d+)?[BMKT]|\d+x\d+[BM]?)(?![\w.])"
)
_VERSIONED = re.compile(r"^(.*?)(?:[\s\-]v(\d+(?:\.\d+)*)|\s(\d+\.\d+))$", re.I)
# "Terminal-Bench (TB) 3.0": an abbreviation between a name and its version.
_INFIX_ABBREVIATION = re.compile(r"(?<=\w)[ \t]+\([A-Za-z0-9\-]{1,10}\)(?=[ \t]+\d)")
# "autoregressive (AR) models": an abbreviation inside a longer name.
_BRACKET_GAP = re.compile(
    r"[ \t]+\((?=[^)]*[A-Z][^)]*[A-Z])[A-Za-z0-9\-]{2,10}\)[ \t]+"
)
_CHECKPOINT_SUFFIX = re.compile(r"-(?:Instruct|Base|Chat|Math|Coder|Thinking)\b")
_VARIANT_SUFFIX = re.compile(
    r"-(?:mini|lite|tiny|small|base|large|hard|easy|full|pro|plus|test|val|dev)\b", re.I
)
_PAREN_ALIAS = re.compile(r"[ \t]*\([ \t]*([^()\n]{1,40}?)[ \t]*\)")

# Lower ranks win when two entities claim the same surface.
NAME, ABBREVIATION, ALIAS, PLURAL = 0, 1, 1.5, 2


@dataclass(frozen=True)
class CatalogEntity:
    entity_type: str  # "method", "dataset", or "framework"
    entity_id: int
    name: str
    slug: str
    parent_id: int | None = None
    full_name: str | None = None
    # Curated alternative names: "Multimodal Large Language Model (MLLM)" for VLM.
    aliases: tuple[str, ...] = ()
    # "always" links every clean match, "judge" asks the judge, "never" skips.
    mode: str = "judge"
    # Leaderboard evaluations; breaks ties between sibling benchmark splits.
    evals: int = 0


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
    rank: int = 0


@dataclass
class MentionIndex:
    surfaces: dict[tuple[str, ...], list[_Surface]]
    max_tokens: int
    unresolved: list[tuple[str, list[CatalogEntity]]]
    # (entity_type, entity_id) -> lowercased tokens of its matchable name
    names: dict[tuple[str, int], tuple[str, ...]]
    # (entity_type, entity_id) -> lowercased tokens of full-name long forms
    long_forms: dict[tuple[str, int], set[tuple[str, ...]]]
    # entities named with ordinary words only (Transformer, Diffusion Policy)
    plain_names: set[tuple[str, int]]


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


_SPLIT_WORD = re.compile(r"\s+(?:test|val|dev|validation)$", re.I)


def benchmark_base_name(name: str) -> str:
    """``RefCOCOg test`` and ``GLUE (test)`` -> ``RefCOCOg`` and ``GLUE``."""
    previous = None
    while previous != name:
        previous, name = name, _SPLIT_WORD.sub("", base_name(name)).strip()
    return name


def _case_sensitive(entity: CatalogEntity, tokens: tuple[str, ...]) -> bool:
    if entity.entity_type == "framework":
        return True  # product names: "Browser Use", not "browser-use agents"
    if len(tokens) > 1:
        return False
    token = tokens[0]
    if re.search(r"\d|[a-z][A-Z]|@", token):
        return False  # GSM8K, ImageNet, LLaVA, DeltaNet, pass@k never spell an ordinary word
    return not (entity.entity_type == "method" and _PLAIN_WORD.fullmatch(token))


_MONTHS = (
    "jan feb mar apr may jun jul aug sep oct nov dec".split(),
    "january february march april may june july august september october "
    "november december".split(),
)


def _initials_abbreviation(name: str) -> str | None:
    """``Humanity's Last Exam (HLE)`` -> ``HLE``; ``LIBERO-Plus (SFT)`` -> None."""
    bracket = re.search(r"\(([A-Z][A-Za-z0-9]{1,9})\)\s*$", name)
    if not bracket:
        return None
    words = re.findall(r"[A-Za-z0-9]+", re.sub(r"'s\b", "", name[: bracket.start()]))
    initials = "".join(w[0] for w in words).upper()
    letters = "".join(ch for ch in bracket.group(1) if ch.isupper() or ch.isdigit())
    return bracket.group(1) if len(letters) >= 2 and letters == initials else None


def _compact_variants(written: str, entity: CatalogEntity) -> list[tuple[str, float]]:
    """Other ways papers write a name, each with its rank.

    ``MATH 500`` -> ``MATH500``; ``AIME 2025`` -> ``AIME 25`` / ``AIME25``;
    ``HMMT Feb 2025`` -> ``HMMT 2025`` / ``HMMT25``. When two sittings share a
    year (HMMT Feb and Nov 2025), the earlier month ranks first.
    """
    variants: list[tuple[str, float]] = []
    numbered = re.fullmatch(r"(.*\S)\s+(\d+(?:\.\d+)+)", written)
    if numbered:  # SQuAD 1.1 -> SQuAD v1.1
        variants.append((f"{numbered.group(1)} v{numbered.group(2)}", ABBREVIATION))
    joined = re.sub(r"(?<=[A-Za-z])[ \-](?=\d)", "", written)
    if joined != written:
        variants.append((joined, ABBREVIATION))
    if entity.entity_type != "dataset":
        return variants
    years = [(written, ABBREVIATION)]
    month = re.search(r" ([A-Za-z]+) (20\d\d)$", written)
    if month:
        word = month.group(1).lower()
        index = next((m.index(word) for m in _MONTHS if word in m), None)
        if index is not None:
            undated = f"{written[: month.start()]} {month.group(2)}"
            years.append((undated, ABBREVIATION + (index + 1) / 100))
            variants.append(years[-1])
    for name, rank in years:
        short_year = re.sub(r"(?<=[A-Za-z][ \-])20(\d\d)$", r"\1", name)
        if short_year != name:
            variants += [
                (short_year, rank),
                (re.sub(r"[ \-](?=\d\d$)", "", short_year), rank),
            ]
    return variants


def _resolve_benchmark_group(
    members: list[CatalogEntity], by_id: dict[int, CatalogEntity]
) -> CatalogEntity:
    plain = [m for m in members if benchmark_base_name(m.name) == m.name]
    if len(plain) == 1:
        return plain[0]
    if plain:
        return _default_split(plain)
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
            normalize_name(benchmark_base_name(child.name))
        ):
            return parent
        return child
    shared = {m.parent_id for m in roots}
    if len(shared) == 1 and (parent_id := shared.pop()) in by_id:
        return by_id[parent_id]
    return _default_split(roots)


def _default_split(candidates: list[CatalogEntity]) -> CatalogEntity:
    """Sibling splits with no parent: the test split, else the most evals."""
    return min(
        candidates,
        key=lambda m: (
            not re.search(r"\btest\b", m.name, re.I),
            -m.evals,
            m.entity_id,
        ),
    )


def build_index(entities: Iterable[CatalogEntity]) -> MentionIndex:
    entities = list(entities)
    datasets = {e.entity_id: e for e in entities if e.entity_type == "dataset"}
    # name tokens -> (rank, owning entity, the name as written)
    targets: dict[tuple[str, ...], list[tuple[int, CatalogEntity, str]]] = defaultdict(
        list
    )
    unresolved: list[tuple[str, list[CatalogEntity]]] = []
    long_forms: dict[tuple[str, int], set[tuple[str, ...]]] = defaultdict(set)

    def add(written: str, entity: CatalogEntity, rank: int) -> None:
        key = tuple(normalize_name(written).split())
        if key:
            targets[key].append((rank, entity, written))
        if entity.entity_type == "method" and rank != PLURAL and key:
            last = tokenize(written)[-1]
            if re.search(r"[a-z]{3,}[^s]s$", last) and len(tokenize(written)) > 1:
                add(written[:-1], entity, PLURAL)  # World Action Models -> Model
            elif re.search(r"(?:s|x|z|ch|sh)$", last, re.I):
                add(written + "es", entity, PLURAL)  # harness -> harnesses
            elif last[-1:].isalpha():
                add(written + "s", entity, PLURAL)
        if rank != PLURAL:
            for variant, variant_rank in _compact_variants(written, entity):
                add(variant, entity, variant_rank)
        prefixed = re.fullmatch(r"([A-Z][a-z]+)([A-Z]{2,}[A-Za-z0-9]*)", written)
        if rank != PLURAL and prefixed:
            add(
                f"{prefixed.group(1)}-{prefixed.group(2)}", entity, ABBREVIATION
            )  # Bi-LSTM
        british = re.sub(r"iz(ation|e|ed|ing|er)\b", r"is\1", written)
        if rank != PLURAL and british != written:
            add(british, entity, max(rank, ABBREVIATION))  # quantisation

    def add_named(
        written: str, entity: CatalogEntity, long_form: bool, rank: float = NAME
    ) -> None:
        abbreviation = _ABBREVIATION.search(written)
        if long_form:
            add(base_name(written), entity, rank)
        if abbreviation and written[: abbreviation.start()].strip():
            long_forms[(entity.entity_type, entity.entity_id)].add(
                tuple(normalize_name(written[: abbreviation.start()]).split())
            )
        if abbreviation:
            short = abbreviation.group(1)
            add(short, entity, max(rank, ABBREVIATION))
            if re.fullmatch(r"[A-Z][A-Za-z0-9\-]*[A-Z]s", short):
                add(short[:-1], entity, max(rank, ABBREVIATION))  # WAMs -> WAM

    for entity in entities:
        for alias in entity.aliases:
            add_named(alias, entity, long_form=True, rank=ALIAS)

    for entity in entities:
        if entity.entity_type == "method":
            add_named(entity.name, entity, long_form=True)
            if entity.full_name and entity.full_name != entity.name:
                # Only the abbreviation: full names' long forms are often generic.
                add_named(entity.full_name, entity, long_form=False)
        elif entity.entity_type == "framework":
            add(entity.name, entity, NAME)

    groups: dict[str, list[CatalogEntity]] = defaultdict(list)
    for dataset in datasets.values():
        groups[normalize_name(benchmark_base_name(dataset.name))].append(dataset)
    for key_text, members in groups.items():
        if not key_text:
            continue
        target = _resolve_benchmark_group(members, datasets)
        for member in members:
            if _SPLIT_WORD.search(base_name(member.name)):
                add(base_name(member.name), member, NAME)  # "RefCOCOg val" itself
        written = benchmark_base_name(
            (target if target in members else members[0]).name
        )
        targets[tuple(key_text.split())].append((NAME, target, written))
        for variant, variant_rank in _compact_variants(written, target):
            add(variant, target, variant_rank)
        for member in members:
            abbreviation = _initials_abbreviation(member.name)
            if abbreviation:
                add(abbreviation, target, ABBREVIATION)

    group_names = {
        normalize_name(benchmark_base_name(d.name)) for d in datasets.values()
    }
    latest: dict[tuple[str, ...], tuple[tuple[int, ...], CatalogEntity, str]] = {}
    for dataset in datasets.values():
        versioned = _VERSIONED.match(base_name(dataset.name))
        if not versioned or not versioned.group(1).strip():
            continue
        family = versioned.group(1).strip()
        version = tuple(
            int(n) for n in (versioned.group(2) or versioned.group(3)).split(".")
        )
        key = tuple(normalize_name(family).split())
        if _PLAIN_WORD.fullmatch(family) or any(
            other.split()[: len(key)] == list(key) and not _VERSIONED.match(other)
            for other in group_names
        ):
            continue  # Humanoid-v2; ImageNet V2 next to Imagenet-1k
        if key not in latest or version > latest[key][0]:
            latest[key] = (version, dataset, family)
    for key, (_, dataset, family) in latest.items():
        targets[key].append((ABBREVIATION, dataset, family))

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
                chosen, chosen_rank = next(iter(distinct.values())), rank
                break
            # Two entities share this name; a lower-ranked unique owner may still win.
            unresolved.append((" ".join(key), [o for o, _ in distinct.values()]))
        if chosen is None:
            continue
        owner, written = chosen
        tokens = tuple(tokenize(written))
        surfaces[key] = [
            _Surface(owner, tokens, _case_sensitive(owner, tokens), chosen_rank)
        ]
        # A benchmark named GQA and the method Grouped-Query Attention (GQA): keep
        # one owner per other entity type, and let the judge pick by context.
        for entity_type in sorted(
            {o.entity_type for _, o, _ in owners} - {owner.entity_type}
        ):
            rivals = {
                (o.entity_type, o.entity_id): (r, o, w)
                for r, o, w in owners
                if o.entity_type == entity_type and r != PLURAL
            }
            if len(rivals) == 1:
                r, o, w = next(iter(rivals.values()))
                rival_tokens = tuple(tokenize(w))
                surfaces[key].append(
                    _Surface(o, rival_tokens, _case_sensitive(o, rival_tokens), r)
                )
    names = {
        (o.entity_type, o.entity_id): key
        for key, owners in targets.items()
        for rank, o, _ in owners
        if rank == NAME and key in surfaces
    }
    max_tokens = max((len(k) for k in surfaces), default=0)
    return MentionIndex(
        surfaces=surfaces,
        max_tokens=max_tokens,
        unresolved=unresolved,
        names=names,
        long_forms=dict(long_forms),
        plain_names={
            key
            for key, name in names.items()
            if all(_PLAIN_WORD.fullmatch(t) for t in surfaces[name][0].tokens)
        },
    )


def _blank(match: re.Match) -> str:
    return " " * len(match.group())  # keeps character offsets stable


def _masked(abstract: str) -> str:
    return _INFIX_ABBREVIATION.sub(_blank, _MATH.sub(_blank, abstract))


def _continues_as_variant(text_value: str, end: int, surface: _Surface) -> bool:
    rest = text_value[end : end + 2]
    if len(rest) < 2:
        return False
    if surface.entity.entity_type == "method" and _SIZE_SUFFIX.match(text_value, end):
        return False
    if surface.entity.entity_type == "method" and _CHECKPOINT_SUFFIX.match(
        text_value, end
    ):
        return False  # Qwen2.5-Math-7B, Qwen3-8B-Instruct are still Qwen2.5 / Qwen3
    versioned = rest[0] in ".-" and rest[1].isdigit()
    if versioned and _is_unversioned_method(surface):
        return False  # LLaVA-1.5 is still LLaVA
    if rest[0] == "." and rest[1].isdigit():
        return True
    if rest[0] == "-" and (rest[1].isspace() or _VARIANT_SUFFIX.match(text_value, end)):
        return True  # COCO-$20^i$ (masked maths), MMAU-mini
    return rest[0] == "-" and (rest[1].isupper() or rest[1].isdigit())


def _is_unversioned_method(surface: _Surface) -> bool:
    return surface.entity.entity_type == "method" and not any(
        ch.isdigit() for token in surface.tokens for ch in token
    )


def _has_hyphenated_prefix(text_value: str, start: int) -> bool:
    """``Flow-GRPO``, ``delta-VAE``; a lowercase modifier on a lowercase phrase
    (``multi-agent harness``) is not a different name."""
    if start < 2 or text_value[start - 1] != "-" or not text_value[start - 2].isalnum():
        return False
    # [^\W_] is exactly str.isalnum(), so "α-GRPO" or "é-GRPO" match too.
    prefix = re.search(r"([^\W_]+)-$", text_value[:start]).group(1)
    return not (prefix.isalpha() and prefix.islower() and text_value[start].islower())


def _followed_by_variant_word(text_value: str, end: int) -> bool:
    match = re.match(r"[ \t]+(\S+)", text_value[end:])
    word = match.group(1) if match else ""
    return bool(_VARIANT_WORD.match(word) or re.match(r"v\d", word))  # GDPval v2


def _preceded_by_name_word(text_value: str, start: int) -> bool:
    """True for ``Geometry-Change VLA``; false at a sentence or clause start."""
    match = re.search(r"(\S+)[ \t]+$", text_value[:start])
    word = match.group(1) if match else ""
    name_like = word[:1].isupper() or (word[:1].isdigit() and word.upper() == word)
    if not word or not name_like or not word[-1].isalnum():
        return False
    before = text_value[: match.start()].rstrip()
    return bool(before) and before[-1] not in ".!?:;"


def find_candidates(abstract: str, index: MentionIndex) -> list[Candidate]:
    """Return literal catalog mentions in ``abstract`` with character offsets."""
    if not abstract or not index.surfaces:
        return []
    masked = _masked(abstract)
    tokens = _text_tokens(masked, index)
    words = [t.group() for t in tokens]
    lowered = [w.lower() for w in words]
    candidates: list[Candidate] = []
    redefined: set[tuple[str, int]] = set()
    i = 0
    while i < len(tokens):
        matched = _longest_match(index, masked, tokens, words, lowered, i)
        if matched is None:
            i += 1
            continue
        n, fitting = matched
        furthest = tokens[i + n - 1].end()
        for surface in fitting:
            start, end = tokens[i].start(), tokens[i + n - 1].end()
            end = _absorb_parenthesised_alias(index, abstract, masked, end, surface)
            end = _absorb_slug_suffix(masked, start, end, surface)
            inside_name = _followed_by_variant_word(
                masked, end
            ) or _preceded_by_name_word(masked, start)
            if _defined_in_brackets(masked, start, end):
                expanded = _expand_long_form(
                    index, masked, tokens[:i], start, end, surface
                )
                if expanded:
                    start, end = expanded
                    candidates = [c for c in candidates if c.end <= start]
                elif surface.rank == ABBREVIATION and not _shares_long_form(
                    index, tokens[:i], surface
                ):
                    redefined.add(
                        (surface.entity.entity_type, surface.entity.entity_id)
                    )
            part_of_other_name = (
                _continues_as_variant(masked, end, surface)
                or _has_hyphenated_prefix(masked, start)
                or (
                    _next_to_name_word(masked, start, end)
                    and _is_capitalised_plain_word(surface, abstract[start:end])
                )
            )
            if part_of_other_name:
                continue
            furthest = max(furthest, end)
            candidates.append(
                Candidate(
                    entity_type=surface.entity.entity_type,
                    entity_id=surface.entity.entity_id,
                    start=start,
                    end=end,
                    surface=abstract[start:end],
                    variant_suspect=inside_name
                    or len(fitting) > 1
                    or (surface.rank == ABBREVIATION and end - start <= 2)
                    or (
                        surface.rank == ALIAS
                        and len(surface.tokens) == 1
                        and surface.tokens[0][:1].isupper()
                    ),
                )
            )
        end = furthest
        i += n
        while i < len(tokens) and tokens[i].start() < end:
            i += 1
    candidates = [
        c for c in candidates if (c.entity_type, c.entity_id) not in redefined
    ]
    candidates = _add_coordinated_siblings(candidates, index, abstract, masked)
    candidates = _trust_short_forms_backed_by_full_names(candidates)
    return _drop_subsumed(candidates, index)


def _is_short_form(candidate: Candidate) -> bool:
    return len(candidate.surface) <= 2 and candidate.surface.isupper()


def _trust_short_forms_backed_by_full_names(
    candidates: list[Candidate],
) -> list[Candidate]:
    """A bare ``AR`` means the autoregressive model when the same abstract also
    says ``autoregressive``; without that evidence it stays with the judge."""
    backed = {
        (c.entity_type, c.entity_id)
        for c in candidates
        if not _is_short_form(c) and not c.variant_suspect
    }
    return [
        dataclasses.replace(c, variant_suspect=False)
        if _is_short_form(c) and (c.entity_type, c.entity_id) in backed
        else c
        for c in candidates
    ]


_LIST_ITEM = re.compile(
    r"(?:,[ \t]*(?:and[ \t]+|or[ \t]+)?|[ \t]+(?:and|or)[ \t]+)"
    r"([A-Z0-9][\w.+\-]*(?:[ \t][A-Z][\w.+\-]*)?)"
)


def _add_coordinated_siblings(candidates, index, abstract, masked):
    """``SWE-bench Verified, Multilingual, and Pro``: the family is written once."""
    added = []
    for candidate in candidates:
        family = index.names.get((candidate.entity_type, candidate.entity_id), ())[:-1]
        if not family:
            continue
        end = candidate.end
        while item := _LIST_ITEM.match(masked, end):
            key = family + tuple(t.lower() for t in tokenize(item.group(1)))
            sibling = next(
                (
                    s.entity
                    for s in index.surfaces.get(key, ())
                    if s.entity.entity_type == candidate.entity_type
                ),
                None,
            )
            if sibling is None:
                break
            start, end = item.start(1), item.end(1)
            added.append(
                Candidate(
                    entity_type=sibling.entity_type,
                    entity_id=sibling.entity_id,
                    start=start,
                    end=end,
                    surface=abstract[start:end],
                    variant_suspect=False,
                )
            )
    return sorted(candidates + added, key=lambda c: c.start)


def _expand_long_form(index, masked, before, start, end, surface):
    """``group-relative policy optimization (GRPO)``: span the long form too."""
    key = (surface.entity.entity_type, surface.entity.entity_id)
    for long_form in index.long_forms.get(key, ()):
        n = len(long_form)
        if len(before) < n or not _contiguous(masked, before[-n:]):
            continue
        words = [t.group().lower() for t in before[-n:]]
        plural = words[-1].endswith("s") and words[-1][:-1] == long_form[-1]
        if tuple(words) == long_form or (words[:-1] == list(long_form[:-1]) and plural):
            close = masked.index(")", end) + 1
            return before[-n].start(), close
    return None


def _shares_long_form(index: MentionIndex, before: list[re.Match], surface) -> bool:
    """``preference optimization (DPO)`` shortens DPO's own long form."""
    words = {t.group().lower() for t in before[-4:]}
    key = (surface.entity.entity_type, surface.entity.entity_id)
    return any(words & set(form) for form in index.long_forms.get(key, ()))


def _defined_in_brackets(text_value: str, start: int, end: int) -> bool:
    """``Inadequate Generalization (IG)``: the abstract defines its own ``IG``."""
    return text_value[:start].rstrip(" \t").endswith("(") and text_value[end:].lstrip(
        " \t"
    ).startswith(")")


def _drop_subsumed(candidates: list[Candidate], index: MentionIndex) -> list[Candidate]:
    present = {
        (c.entity_type, c.entity_id) for c in candidates if c.entity_type == "method"
    }
    names = {key: index.names.get(key, ()) for key in present}

    def subsumed(key: tuple[str, int]) -> bool:
        name = names[key]
        if not name or key not in index.plain_names:
            return False  # acronyms such as GRPO keep their link next to Dr. GRPO
        return any(
            other != key and len(longer) > len(name) and _contains(longer, name)
            for other, longer in names.items()
        )

    dropped = {key for key in present if subsumed(key)}
    return [c for c in candidates if (c.entity_type, c.entity_id) not in dropped]


def _contains(longer: tuple[str, ...], part: tuple[str, ...]) -> bool:
    return any(
        longer[i : i + len(part)] == part for i in range(len(longer) - len(part) + 1)
    )


def _next_to_name_word(masked: str, start: int, end: int) -> bool:
    """``World Embedding Benchmark``; a version number (``Jev 1.13``) is not a word."""
    following = re.match(r"[ \t]+([A-Z])", masked[end:])
    return bool(following) or _preceded_by_name_word(masked, start)


def _is_capitalised_plain_word(surface: _Surface, written: str) -> bool:
    return (
        surface.entity.entity_type == "method"
        and len(surface.tokens) == 1
        and not surface.case_sensitive
        and written[:1].isupper()
    )


def _text_tokens(masked: str, index: MentionIndex) -> list[re.Match]:
    """Keep ``pass@1`` whole when the catalog names it; otherwise ``BLEU@4`` is
    read as ``BLEU`` and ``4``."""
    tokens = []
    for token in _TOKEN.finditer(masked):
        if "@" in token.group() and (token.group().lower(),) not in index.surfaces:
            tokens.extend(_PLAIN_TOKEN.finditer(masked, token.start(), token.end()))
        else:
            tokens.append(token)
    return tokens


def _longest_match(index, masked, tokens, words, lowered, i):
    for n in range(min(index.max_tokens + 1, len(tokens) - i), 0, -1):
        # "autoregressive (AR) models": skip a bracketed abbreviation inside the window.
        kept = [
            k
            for k in range(i, i + n)
            if k in (i, i + n - 1) or not _in_bracket_gap(masked, tokens[k])
        ]
        surfaces = index.surfaces.get(tuple(lowered[k] for k in kept))
        if not surfaces or not _contiguous(masked, [tokens[k] for k in kept]):
            continue
        fitting = [
            surface
            for surface in surfaces
            if not surface.case_sensitive
            or tuple(words[k] for k in kept) == surface.tokens
        ]
        if fitting:
            return n, fitting
    return None


def _in_bracket_gap(masked: str, token: re.Match) -> bool:
    """True for ``AR`` in ``autoregressive (AR) models``."""
    before = masked.rfind(" ", 0, token.start())
    after = masked.find(" ", token.end())
    return (
        before >= 0
        and after >= 0
        and bool(_BRACKET_GAP.fullmatch(masked[before : after + 1]))
    )


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
    if (
        matched
        and matched[0] == len(inner)
        and surface.entity in (other.entity for other in matched[1])
    ):
        return paren.end()
    return end


def _absorb_slug_suffix(masked: str, start: int, end: int, surface: _Surface) -> int:
    """``ImageNet-1k`` is the benchmark whose slug is ``imagenet-1k``."""
    suffix = re.match(r"-[A-Za-z0-9]+", masked[end:])
    if surface.entity.entity_type != "dataset" or not suffix:
        return end
    longer = end + suffix.end()
    slug = re.sub(r"[^a-z0-9]+", "-", masked[start:longer].lower()).strip("-")
    return longer if slug == surface.entity.slug else end


def _contiguous(text_value: str, tokens: list[re.Match]) -> bool:
    """Tokens of one name may only be separated by name separators, or by the
    full stop of a short title-case abbreviation (``Dr. GRPO``)."""
    return all(
        _SEPARATOR.fullmatch(text_value[a.end() : b.start()])
        or (
            re.fullmatch(r"\.[ \t]+", text_value[a.end() : b.start()])
            and re.fullmatch(r"[A-Z][a-z]{0,2}", a.group())
        )
        or _BRACKET_GAP.fullmatch(text_value[a.end() : b.start()])
        for a, b in zip(tokens, tokens[1:])
    )


def load_catalog_entities(db: Session) -> list[CatalogEntity]:
    rows = db.execute(
        text(
            """
            SELECT 'method' AS entity_type, id, name, slug, NULL::bigint AS parent_id,
                   full_name, aliases, abstract_linking, 0 AS evals
            FROM methods WHERE slug IS NOT NULL
            UNION ALL
            SELECT 'dataset', id, name, slug, parent_dataset_id, NULL, aliases,
                   abstract_linking,
                   (SELECT count(*) FROM evaluations WHERE dataset_id = datasets.id)
            FROM datasets WHERE slug IS NOT NULL
            UNION ALL
            SELECT 'framework', id, name, slug, NULL, NULL, aliases, abstract_linking, 0
            FROM frameworks WHERE slug IS NOT NULL
            """
        )
    ).all()
    return [
        CatalogEntity(
            entity_type=row.entity_type,
            entity_id=int(row.id),
            name=row.name,
            slug=row.slug,
            parent_id=row.parent_id,
            full_name=row.full_name,
            aliases=tuple(row.aliases or ()),
            mode=row.abstract_linking,
            evals=int(row.evals),
        )
        for row in rows
    ]
