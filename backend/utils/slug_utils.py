"""
Utilities for generating URL-friendly slugs.
"""

import re
import unicodedata


def slugify(text: str) -> str:
    """
    Convert text to a URL-friendly slug.

    - Converts to lowercase
    - Replaces spaces and special characters with hyphens
    - Removes consecutive hyphens
    - Strips leading/trailing hyphens

    Examples:
        "Vision Transformer" -> "vision-transformer"
        "GPT-2" -> "gpt-2"
        "Adam Optimizer" -> "adam-optimizer"
        "BERT  (Bidirectional)" -> "bert-bidirectional"

    Args:
        text: The text to slugify

    Returns:
        URL-friendly slug
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    text = text.lower()

    text = re.sub(r"[^a-z0-9]+", "-", text)

    text = re.sub(r"-+", "-", text)

    text = text.strip("-")

    return text
