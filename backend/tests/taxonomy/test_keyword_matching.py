from backend.utils.keyword_matching import (
    apply_task_supersession_rules,
    create_keyword_patterns,
    find_matching_items_simple,
)


TASKS = [
    {"id": 1, "slug": "image-editing", "keywords": "image editing"},
    {"id": 2, "slug": "video-editing", "keywords": "video editing"},
    {
        "id": 3,
        "slug": "image-generation",
        "keywords": "image generation, text-to-image, image synthesis",
    },
    {
        "id": 4,
        "slug": "video-generation",
        "keywords": "video generation, text-to-video, image-to-video",
    },
    {
        "id": 5,
        "slug": "image-understanding",
        "keywords": "image understanding, visual reasoning, VQA",
    },
    {
        "id": 6,
        "slug": "video-understanding",
        "keywords": "video understanding, video reasoning, video question answering, video-language model",
    },
    {"id": 7, "slug": "healthcare", "keywords": "healthcare, diagnosis"},
    {
        "id": 8,
        "slug": "reinforcement-learning",
        "keywords": "reinforcement learning, GRPO, PPO",
    },
    {
        "id": 9,
        "slug": "classic-reinforcement-learning",
        "keywords": "PPO, multi-agent RL, Atari",
    },
]


def match(title: str, abstract: str) -> set[int]:
    case_sensitive, case_insensitive = create_keyword_patterns(TASKS)
    text = f"{title} {abstract}"
    matched = find_matching_items_simple(text, case_sensitive, case_insensitive)
    return apply_task_supersession_rules(
        matched,
        {task["slug"]: task["id"] for task in TASKS},
        text,
        title,
        {
            task["slug"]: [
                keyword.strip()
                for keyword in task["keywords"].split(",")
                if keyword.strip()
            ]
            for task in TASKS
        },
    )


def test_video_editing_title_drops_related_work_image_editing() -> None:
    assert match(
        "A New Method for Video Editing",
        "Unlike image editing, video editing requires temporal consistency.",
    ) == {2}


def test_joint_image_and_video_editing_title_keeps_both() -> None:
    assert match(
        "Unified Image and Video Editing",
        "We support image editing and video editing.",
    ) == {1, 2}


def test_text_to_image_title_drops_abstract_video_generation() -> None:
    assert match(
        "Efficient Text-to-Image Synthesis",
        "The same backbone has previously been used for video generation.",
    ) == {3}


def test_video_generation_title_drops_abstract_image_generation() -> None:
    assert match(
        "Fast Video Generation",
        "The architecture originates in image generation.",
    ) == {4}


def test_video_understanding_title_drops_generic_visual_reasoning() -> None:
    assert match(
        "Visual Reasoning for Video Understanding",
        "We evaluate VQA and video understanding.",
    ) == {6}


def test_image_understanding_title_drops_abstract_video_understanding() -> None:
    assert match(
        "Improving Image Understanding",
        "We compare with prior video understanding systems.",
    ) == {5}


def test_neutral_title_keeps_explicit_joint_task_from_abstract() -> None:
    assert match(
        "A Unified Multimodal Foundation Model",
        "We study image generation and video generation.",
    ) == {3, 4}


def test_two_modality_words_without_task_signal_do_not_keep_both() -> None:
    assert (
        match(
            "Image Foundation Models with Video Diffusion Priors",
            "We discuss image generation and video generation.",
        )
        == set()
    )


def test_neutral_title_drops_disconnected_modality_mentions() -> None:
    assert (
        match(
            "A Unified Multimodal Foundation Model",
            "Image generation is well studied. We compare against video generation systems.",
        )
        == set()
    )


def test_generic_joint_phrase_does_not_create_an_image_video_overlap() -> None:
    assert match(
        "Fast Generative Models",
        "Diffusion models are widely used for image and video generation.",
    ) == {4}


def test_background_achievement_claim_does_not_keep_both() -> None:
    assert (
        match(
            "Fast Generative Models",
            "Recent models have demonstrated progress in image and video generation. "
            "We evaluate text-to-image synthesis.",
        )
        == set()
    )


def test_background_model_claim_with_modifiers_does_not_keep_both() -> None:
    assert match(
        "An Image Benchmark",
        "Multimodal models for conventional tasks have demonstrated strong "
        "performance on image and video understanding benchmarks. We introduce "
        "a benchmark for image understanding.",
    ) == {5}


def test_non_medical_diagnosis_does_not_match_healthcare() -> None:
    assert (
        match(
            "D-Bot: Database Diagnosis System using Large Language Models",
            "We diagnose failures in database systems and recommend repairs.",
        )
        == set()
    )


def test_non_medical_diagnosis_overrides_ambiguous_biomedical_word() -> None:
    assert (
        match(
            "A Genetic Algorithm for Failure Diagnosis",
            "We identify failure modes in industrial systems.",
        )
        == set()
    )


def test_plant_disease_diagnosis_does_not_match_healthcare() -> None:
    assert (
        match(
            "A Benchmark for Rice Leaf Disease Diagnosis",
            "We screen crop images and identify plant diseases.",
        )
        == set()
    )


def test_general_reasoning_survey_does_not_match_from_medical_example() -> None:
    assert (
        match(
            "A Survey of Reasoning with Foundation Models",
            "Applications include negotiation and medical diagnosis.",
        )
        == set()
    )


def test_explicit_healthcare_keyword_keeps_diagnosis_match() -> None:
    assert match(
        "Reliable Diagnosis in Healthcare",
        "We improve decision support workflows.",
    ) == {7}


def test_abstract_healthcare_keyword_overrides_generic_diagnosis_title() -> None:
    assert match(
        "Language Models for Diagnosis",
        "We study diagnosis in healthcare.",
    ) == {7}


def test_disease_diagnosis_keeps_healthcare_match() -> None:
    assert match(
        "Deep Learning for Breast Cancer Diagnosis",
        "We detect malignant lesions in screening mammograms.",
    ) == {7}


def test_whole_slide_diagnosis_keeps_healthcare_match() -> None:
    assert match(
        "Attention-Stabilized Learning for Whole-Slide Imaging",
        "We improve whole slide image diagnosis across public WSI datasets.",
    ) == {7}


def test_llm_rl_paper_drops_classic_reinforcement_learning() -> None:
    assert match(
        "Stable PPO for Large Language Model Reasoning",
        "We apply reinforcement learning with PPO to LLM math reasoning.",
    ) == {8}


def test_classic_rl_paper_drops_llm_reinforcement_learning() -> None:
    assert match(
        "Sample-Efficient PPO on Atari",
        "We study reinforcement learning with PPO on Atari games.",
    ) == {9}
