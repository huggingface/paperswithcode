from backend.services.abstract_mention_service import (
    CatalogEntity,
    base_name,
    build_index,
    find_candidates,
)


def method(entity_id, name):
    return CatalogEntity("method", entity_id, name, name.lower().replace(" ", "-"))


def dataset(entity_id, name, parent_id=None):
    return CatalogEntity("dataset", entity_id, name, f"d{entity_id}", parent_id)


CATALOG = [
    method(1, "Gated DeltaNet"),
    method(2, "Gated DeltaNet-2"),
    method(3, "Pre-training"),
    method(4, "GRPO"),
    method(5, "Dropout"),
    method(6, "Qwen3"),
    method(7, "Attention"),
    dataset(10, "SWE-Bench"),
    dataset(11, "SWE-Bench Verified"),
    dataset(12, "Terminal Bench 2.0"),
    dataset(13, "Terminal-Bench 2.0 — AutoSaddler 40-task test split", parent_id=12),
    dataset(20, "LIBERO"),
    dataset(21, "LIBERO-Goal", parent_id=20),
    dataset(22, "LIBERO-Plus (Zero-Shot Transfer)", parent_id=20),
    dataset(23, "LIBERO-Plus (SFT)", parent_id=22),
    dataset(30, "SNU-FILM (Easy)"),
    dataset(31, "SNU-FILM (Hard)"),
    dataset(40, "WEAR Outdoor Sports Activity Recognition"),
    dataset(41, "WEAR (Inertia-1 Protocol)", parent_id=40),
    dataset(50, "SkillsBench v1.1 (With Skills)"),
    dataset(51, "SkillsBench (Atria 79-task subset)", parent_id=50),
    dataset(52, "SkillsBench (SkillGate, 16-skill slate)", parent_id=50),
    dataset(60, "MATH"),
    dataset(61, "Spider"),
]
INDEX = build_index(CATALOG)


def links(text):
    return [
        (c.surface, c.entity_type, c.entity_id) for c in find_candidates(text, INDEX)
    ]


def test_base_name_strips_trailing_qualifiers():
    assert base_name("LIBERO-Plus (SFT)") == "LIBERO-Plus"
    assert (
        base_name("Terminal-Bench 2.0 — AutoSaddler 40-task test split")
        == "Terminal-Bench 2.0"
    )
    assert base_name("Xiph-4K (Crop) (Video Frame Interpolation)") == "Xiph-4K"


def test_longest_name_wins_and_offsets_point_into_the_abstract():
    text = "MemT employs Gated DeltaNet-2 within each turn."
    [candidate] = find_candidates(text, INDEX)
    assert candidate.entity_id == 2
    assert text[candidate.start : candidate.end] == "Gated DeltaNet-2"
    assert links("on SWE-Bench Verified.") == [("SWE-Bench Verified", "dataset", 11)]


def test_multi_token_names_ignore_case_and_separator_style():
    assert links("continued pre-training and Pre training") == [
        ("pre-training", "method", 3),
        ("Pre training", "method", 3),
    ]
    assert links("Terminal-Bench 2.0 results") == [
        ("Terminal-Bench 2.0", "dataset", 12)
    ]


def test_single_token_benchmarks_need_exact_case_but_plain_method_words_do_not():
    assert links("math skills, a spider robot, MATH and Spider") == [
        ("MATH", "dataset", 60),
        ("Spider", "dataset", 61),
    ]
    assert links("we apply dropout") == [("dropout", "method", 5)]
    assert links("we use grpo") == []


def test_version_continuations_do_not_match_the_shorter_name():
    assert links("Qwen3.5 and Qwen3-VL beat Qwen3.") == [("Qwen3", "method", 6)]
    assert links("LIBERO-Goal and LIBERO-90") == [("LIBERO-Goal", "dataset", 21)]


def test_lowercase_modifiers_and_possessives_still_match():
    assert links("a GRPO-based recipe extends GRPO's objective") == [
        ("GRPO", "method", 4),
        ("GRPO", "method", 4),
    ]


def test_capitalised_follower_marks_variant_suspect():
    [lite, plain] = find_candidates("SWE-Bench Lite and SWE-Bench tasks", INDEX)
    assert lite.variant_suspect and not plain.variant_suspect


def test_math_spans_are_skipped():
    assert links(r"$\mathrm{Attention}(Q,K,V)$ and attention") == [
        ("attention", "method", 7)
    ]


def test_benchmark_base_names_resolve_through_the_catalog_hierarchy():
    # Unqualified row wins over its qualified split.
    assert links("Terminal-Bench 2.0") == [("Terminal-Bench 2.0", "dataset", 12)]
    # The group's single parent wins (SFT points to Zero-Shot).
    assert links("LIBERO-Plus") == [("LIBERO-Plus", "dataset", 22)]
    # A lone split resolves to the parent that names the same benchmark.
    assert links("WEAR") == [("WEAR", "dataset", 40)]
    # Variants sharing one outside parent resolve to it.
    assert links("SkillsBench") == [("SkillsBench", "dataset", 50)]
    # Co-equal variants with no parent stay unlinked and are reported.
    assert links("SNU-FILM") == []
    assert "snu film" in [key for key, _ in INDEX.unresolved]
