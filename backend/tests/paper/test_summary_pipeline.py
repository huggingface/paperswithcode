from __future__ import annotations

from backend.services.paper_summary_pipeline import (
    PROMPT_HASH,
    build_summary_input,
    count_words,
    render_messages,
    summary_input_hash,
    strip_model_meta_postamble,
    summary_word_bounds,
    choose_representative_ids,
    validate_summary,
)


def test_strip_model_meta_postamble() -> None:
    value = " ".join(["result"] * 88) + " (88 words)\n\n*Self-Correction: retry"
    cleaned = strip_model_meta_postamble(value)

    assert cleaned == " ".join(["result"] * 88)
    assert validate_summary(cleaned) == []


def test_summary_input_is_title_abstract_only_and_deterministic():
    assert build_summary_input("  A   Title ", " First\n second ") == (
        "A Title",
        "First second",
    )
    assert summary_input_hash(" A Title", "First second") == summary_input_hash(
        "A   Title ", " First\nsecond "
    )
    assert summary_input_hash("A Title", "First second") != summary_input_hash(
        "A title", "First second"
    )


def test_prompt_has_one_semantic_output_and_stable_hash():
    messages = render_messages("Title", " ".join(["abstract"] * 100))
    assert messages[-1]["content"].endswith("Abstract: " + " ".join(["abstract"] * 100))
    assert "80–120" in messages[-1]["content"]
    assert len(PROMPT_HASH) == 64


def test_summary_validation_bounds_and_boilerplate():
    valid = " ".join(f"term{i}" for i in range(80))
    assert count_words(valid) == 80
    assert validate_summary(valid) == []
    assert validate_summary("short output") == ["too_short"]
    boilerplate = "This paper presents " + " ".join(f"term{i}" for i in range(77))
    assert "boilerplate" in validate_summary(boilerplate)
    assert "citation_like" in validate_summary(valid + " [1]")


def test_summary_validation_scales_lower_bound_for_terse_sources():
    terse_abstract = " ".join(f"source{i}" for i in range(28))
    concise_summary = " ".join(f"summary{i}" for i in range(30))

    assert summary_word_bounds(terse_abstract) == (30, 120)
    assert validate_summary(concise_summary, abstract=terse_abstract) == []
    assert validate_summary(" ".join(["summary"] * 29), abstract=terse_abstract) == [
        "too_short"
    ]
    assert summary_word_bounds(" ".join(["source"] * 100)) == (80, 120)


def test_representative_selection_is_deterministic_and_preserves_forced_ids():
    from datetime import date

    candidates = []
    categories = ["cs.CV", "cs.CL", "cs.RO", "cs.LG", "q-bio.QM", "cs.AI"]
    for paper_id in range(1, 81):
        candidates.append(
            {
                "id": paper_id,
                "source": "external" if paper_id <= 20 else "arxiv",
                "primary_category": categories[paper_id % len(categories)],
                "date_published": date(2014 + paper_id % 12, 1, 1),
                "abstract_chars": 400 + (paper_id % 3) * 700,
            }
        )
    first = choose_representative_ids(
        candidates, forced_ids=[1, 25, 79], size=30, external_target=8
    )
    second = choose_representative_ids(
        list(reversed(candidates)), forced_ids=[79, 1, 25], size=30, external_target=8
    )
    assert first == second
    assert {1, 25, 79}.issubset(first)
    assert sum(paper_id <= 20 for paper_id in first) == 8
