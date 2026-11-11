"""Strict, reviewable launch manifest for featured Hugging Face organizations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeaturedOrganization:
    hf_slug: str
    slug: str
    display_order: int
    name_override: str | None = None
    hf_aliases: tuple[str, ...] = ()
    logo_url_override: str | None = None


FEATURED_ORGANIZATIONS: tuple[FeaturedOrganization, ...] = (
    FeaturedOrganization(
        "microsoft", "microsoft", 1, hf_aliases=("MicrosoftResearch",)
    ),
    FeaturedOrganization("google", "google", 2, hf_aliases=("GoogleDeepMind",)),
    FeaturedOrganization("nvidia", "nvidia", 3),
    FeaturedOrganization("Anthropic", "anthropic", 4),
    FeaturedOrganization("deepseek-ai", "deepseek-ai", 5),
    FeaturedOrganization(
        "facebook",
        "facebook",
        6,
        "Meta",
        (
            "meta-llama",
            "AI-at-Meta",
            "facebook-research",
            "metaresearch",
            "MetaSuperintelligenceLab",
        ),
        logo_url_override=(
            "https://cdn-avatars.huggingface.co/v1/production/uploads/"
            "64c115d1f661ace7c4022432/EbzfQisFJBEcKWDWLyV5O.png"
        ),
    ),
    FeaturedOrganization("Qwen", "qwen", 7),
    FeaturedOrganization("black-forest-labs", "black-forest-labs", 8),
    FeaturedOrganization("stabilityai", "stabilityai", 9),
    FeaturedOrganization("moonshotai", "moonshotai", 10),
    FeaturedOrganization("zai-org", "zai-org", 11),
    FeaturedOrganization("ByteDance", "bytedance", 12),
    FeaturedOrganization("ByteDance-Seed", "bytedance-seed", 13),
    FeaturedOrganization("mistralai", "mistralai", 14, "Mistral AI"),
    FeaturedOrganization("allenai", "allenai", 15),
    FeaturedOrganization("xai-org", "xai-org", 16),
    FeaturedOrganization("openai", "openai", 17),
    FeaturedOrganization("apple", "apple", 18),
    FeaturedOrganization("tencent", "tencent", 19),
    FeaturedOrganization("MiniMaxAI", "minimaxai", 20),
    FeaturedOrganization("baidu", "baidu", 21),
    FeaturedOrganization("sensenova", "sensenova", 22),
    FeaturedOrganization("Ultralytics", "ultralytics", 23),
    FeaturedOrganization("openbmb", "openbmb", 24),
)


def normalize_hf_handle(value: str) -> str:
    return value.strip().lower()


BY_HF_SLUG = {
    normalize_hf_handle(hf_slug): item
    for item in FEATURED_ORGANIZATIONS
    for hf_slug in (item.hf_slug, *item.hf_aliases)
}
BY_PWC_SLUG = {item.slug: item for item in FEATURED_ORGANIZATIONS}

if len(BY_HF_SLUG) != sum(1 + len(item.hf_aliases) for item in FEATURED_ORGANIZATIONS):
    raise RuntimeError("Featured organization HF handles must be unique")
if len(BY_PWC_SLUG) != len(FEATURED_ORGANIZATIONS):
    raise RuntimeError("Featured organization PwC slugs must be unique")
if sorted(item.display_order for item in FEATURED_ORGANIZATIONS) != list(
    range(1, len(FEATURED_ORGANIZATIONS) + 1)
):
    raise RuntimeError("Featured organization display_order must be contiguous")


def featured_for_hf_handle(value: str | None) -> FeaturedOrganization | None:
    if not value:
        return None
    return BY_HF_SLUG.get(normalize_hf_handle(value))
