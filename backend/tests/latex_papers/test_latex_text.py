"""Tests for arXiv LaTeX → plain-text conversion used in page titles and meta tags."""

from backend.utils.latex_text import latex_to_plain_text


def test_latex_to_plain_text_inline_math_omega():
    assert latex_to_plain_text(r"VGGT-$\Omega$") == "VGGT-Ω"


def test_latex_to_plain_text_accents():
    assert latex_to_plain_text(
        r"D\'ej\`a View: Looping Transformers for Multi-View 3D Reconstruction"
    ).startswith("Déjà View:")


def test_latex_to_plain_text_display_math():
    assert latex_to_plain_text(r"Model $$x^2$$ score") == "Model x^2 score"
