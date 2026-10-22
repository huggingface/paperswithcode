from backend.services.abstract_mention_service import (
    CatalogEntity,
    base_name,
    build_index,
    find_candidates,
)


def method(entity_id, name, full_name=None):
    return CatalogEntity(
        "method", entity_id, name, name.lower().replace(" ", "-"), full_name=full_name
    )


def dataset(entity_id, name, parent_id=None):
    return CatalogEntity("dataset", entity_id, name, f"d{entity_id}", parent_id)


CATALOG = [
    method(1, "Gated DeltaNet"),
    method(2, "Gated DeltaNet-2"),
    method(3, "Pre-training"),
    method(4, "GRPO", "Group Relative Policy Optimization (GRPO)"),
    method(5, "Dropout"),
    method(6, "Qwen3"),
    method(7, "Attention"),
    method(8, "Diffusion Transformer (DiT)"),
    method(9, "Transformer"),
    method(10, "Diffusion"),
    method(11, "REPA"),
    method(12, "Mixture-of-Experts (MoE)"),
    method(13, "Reranker (cross-encoder)"),
    method(14, "Looped Transformer"),
    method(15, "World Action Models", "World Action Models (WAMs)"),
    method(16, "Key-value cache", "Key-value cache (KV cache)"),
    method(17, "LLaVA"),
    method(18, "Grokking", "Grokking (Delayed Generalization)"),
    method(19, "Integrated Gradients", "Integrated Gradients (IG)"),
    method(20, "REPA2", "Representation Alignment (REPA2)"),
    method(21, "Diffusion Policy"),
    method(22, "Policy Optimization"),
    dataset(75, "Humanoid-v2"),
    dataset(76, "OSWorld"),
    dataset(77, "ImageNet V2"),
    CatalogEntity("dataset", 78, "ImageNet (ILSVRC-2012)", "imagenet-1k"),
    dataset(79, "Terminal Bench 3.0"),
    dataset(80, "AIME 2025"),
    dataset(81, "MATH 500"),
    dataset(82, "COCO (val2017)"),
    dataset(83, "AIME24"),
    dataset(84, "AIME 2024"),
    method(23, "Agent Harness"),
    method(25, "Dr. GRPO"),
    dataset(85, "HMMT Feb 2025"),
    dataset(86, "HMMT November 2025"),
    method(24, "Online Reinforcement Learning (Online RL)"),
    CatalogEntity("framework", 100, "llama.cpp", "llama-cpp"),
    CatalogEntity("framework", 101, "Transformers", "transformers"),
    CatalogEntity("framework", 102, "Transformers", "transformers-vision"),
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
    dataset(70, "MMEB-v2"),
    dataset(71, "MMEB-v3"),
    dataset(72, "CIFAR-10"),
    dataset(73, "CIFAR-100"),
    dataset(74, "LIBERO v2"),
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


def test_hyphenated_prefixes_make_a_different_name():
    assert links("Flow-GRPO, delta-VAE and Thrifty-GRPO") == []
    assert links("then GRPO") == [("GRPO", "method", 4)]


def test_capitalised_neighbours_mark_variant_suspect():
    [inside] = find_candidates("We introduce Geometry-Change GRPO here.", INDEX)
    assert inside.variant_suspect
    [start] = find_candidates("Results improve. GRPO helps.", INDEX)
    assert not start.variant_suspect
    listed = find_candidates("On MATH, SWE-Bench, Spider and GRPO", INDEX)
    assert not any(c.variant_suspect for c in listed)
    [versioned] = find_candidates("on SWE-Bench 2.0 tasks", INDEX)
    assert versioned.variant_suspect


def test_bracketed_abbreviations_and_plurals_match_methods():
    text = "Diffusion Transformers (DiTs) scale well. DiT's stream and MoE layers."
    assert links(text) == [
        ("Diffusion Transformers (DiTs)", "method", 8),
        ("DiT", "method", 8),
        ("MoE", "method", 12),
    ]
    assert links("mixture-of-experts. Transformers too") == [
        ("mixture-of-experts", "method", 12),
        ("Transformers", "method", 9),
    ]
    assert links("a Reranker (cross-encoder)") == [("Reranker", "method", 13)]


def test_model_size_suffixes_keep_the_base_name():
    assert links("improving a strong REPA-XL/2 model and Qwen3-8B") == [
        ("REPA", "method", 11),
        ("Qwen3", "method", 6),
    ]
    assert links("REPA-Tuned") == []


def test_plain_words_inside_a_longer_capitalised_name_are_skipped():
    assert links("on the World Attention Benchmark and Attention Maps") == []
    assert links("Attention helps. We add attention.") == [
        ("Attention", "method", 7),
        ("attention", "method", 7),
    ]


def test_generic_entity_yields_to_a_more_specific_one_in_the_same_abstract():
    assert links("Looped Transformers reuse shared Transformer blocks.") == [
        ("Looped Transformers", "method", 14)
    ]
    assert links("Diffusion Transformers (DiTs) with a transformer block") == [
        ("Diffusion Transformers (DiTs)", "method", 8)
    ]
    assert links("A Transformer.") == [("Transformer", "method", 9)]
    assert links("on LIBERO and LIBERO-Plus") == [
        ("LIBERO", "dataset", 20),
        ("LIBERO-Plus", "dataset", 22),
    ]


def test_full_name_abbreviations_and_their_singulars_match():
    assert links("World action models. WAMs differ; a WAM acts.") == [
        ("World action models", "method", 15),
        ("WAMs", "method", 15),
        ("WAM", "method", 15),
    ]
    assert links("The KV cache grows.") == [("KV cache", "method", 16)]
    assert links("delayed generalization") == []


def test_family_names_keep_version_suffixes():
    assert links("LLaVA-1.5-7B and LLaVA-NeXT") == [("LLaVA", "method", 17)]


def test_frameworks_and_urls():
    assert links("served with llama.cpp") == [("llama.cpp", "framework", 100)]
    assert links("Hugging Face Transformers") == []
    assert links("code at https://github.com/x/GRPO-repo and GRPO") == [
        ("GRPO", "method", 4)
    ]


def test_bare_benchmark_name_links_its_latest_explicit_version():
    assert links("results on MMEB and MMEB-v2") == [
        ("MMEB", "dataset", 71),
        ("MMEB-v2", "dataset", 70),
    ]
    assert links("on CIFAR and SWE-Bench") == [("SWE-Bench", "dataset", 10)]
    assert links("on LIBERO") == [("LIBERO", "dataset", 20)]


def test_locally_defined_abbreviations_are_not_linked():
    assert links("Inadequate Generalization (IG) and later IG again") == []
    assert links("attributions via IG are noisy") == [("IG", "method", 19)]


def test_full_name_long_forms_and_bad_suffixes_do_not_match():
    assert links("visual representation alignment") == []
    assert links("Humanoid robots") == []
    assert links("65.4% on OSWorld-G and OSWorld") == [("OSWorld", "dataset", 76)]
    assert links("ImageNet training") == [("ImageNet", "dataset", 78)]
    assert links("ImageNet-1K, ImageNet-1k, ImageNet-21K") == [
        ("ImageNet-1K", "dataset", 78),
        ("ImageNet-1k", "dataset", 78),
    ]
    [policy] = find_candidates("an improved 3D Diffusion Policy learner", INDEX)
    assert policy.variant_suspect


def test_abbreviation_between_name_and_version_is_read_through():
    assert links("on Terminal-Bench (TB) 3.0 and TB") == [
        ("Terminal-Bench (TB) 3.0", "dataset", 79)
    ]


def test_long_form_before_a_bracketed_name_joins_the_link():
    text = "We train with group-relative policy optimization (GRPO). GRPO helps."
    assert links(text) == [
        ("group-relative policy optimization (GRPO)", "method", 4),
        ("GRPO", "method", 4),
    ]
    assert links("Integrated Gradients (IG) attributions") == [
        ("Integrated Gradients (IG)", "method", 19)
    ]
    assert links("a new policy optimization (GRPO) variant") == [
        ("policy optimization", "method", 22),
        ("GRPO", "method", 4),
    ]


def test_compact_names_and_short_years():
    assert links("AIME25, MATH500, AIME 2025 and MATH-500") == [
        ("AIME25", "dataset", 80),
        ("MATH500", "dataset", 81),
        ("AIME 2025", "dataset", 80),
        ("MATH-500", "dataset", 81),
    ]
    # An exact catalog name beats a short-year alias.
    assert links("AIME24") == [("AIME24", "dataset", 83)]
    assert links("on COCO") == [("COCO", "dataset", 82)]


def test_lowercase_modifiers_and_es_plurals():
    assert links("a self-organized multi-agent harness; multi-agent harnesses") == [
        ("agent harness", "method", 23),
        ("agent harnesses", "method", 23),
    ]
    assert links("delta-GRPO") == []


def test_bracketed_name_with_one_capitalised_word():
    assert links("online reinforcement learning (RL) and Online RL") == [
        ("online reinforcement learning", "method", 24),
        ("Online RL", "method", 24),
    ]


def test_title_abbreviation_full_stop_joins_a_name_and_acronyms_stay():
    assert links("three RL algorithms (GRPO, GiGPO, Dr. GRPO)") == [
        ("GRPO", "method", 4),
        ("Dr. GRPO", "method", 25),
    ]
    assert links("We use GRPO. Dr. Smith agrees.") == [("GRPO", "method", 4)]


def test_month_less_year_aliases_prefer_the_earlier_sitting():
    assert links("HMMT25, HMMT 2025 and HMMT November 2025") == [
        ("HMMT25", "dataset", 85),
        ("HMMT 2025", "dataset", 85),
        ("HMMT November 2025", "dataset", 86),
    ]
