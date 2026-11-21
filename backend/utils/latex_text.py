"""Convert common LaTeX text-mode markup in arXiv titles to plain Unicode."""

from __future__ import annotations

import re

_LATEX_ACUTE = {
    "a": "á",
    "e": "é",
    "i": "í",
    "o": "ó",
    "u": "ú",
    "y": "ý",
    "A": "Á",
    "E": "É",
    "I": "Í",
    "O": "Ó",
    "U": "Ú",
    "Y": "Ý",
}
_LATEX_GRAVE = {
    "a": "à",
    "e": "è",
    "i": "ì",
    "o": "ò",
    "u": "ù",
    "A": "À",
    "E": "È",
    "I": "Ì",
    "O": "Ò",
    "U": "Ù",
}
_LATEX_CIRCUMFLEX = {
    "a": "â",
    "e": "ê",
    "i": "î",
    "o": "ô",
    "u": "û",
    "A": "Â",
    "E": "Ê",
    "I": "Î",
    "O": "Ô",
    "U": "Û",
}
_LATEX_UMLAUT = {
    "a": "ä",
    "e": "ë",
    "i": "ï",
    "o": "ö",
    "u": "ü",
    "y": "ÿ",
    "A": "Ä",
    "E": "Ë",
    "I": "Ï",
    "O": "Ö",
    "U": "Ü",
    "Y": "Ÿ",
}
_LATEX_ACCENT_BY_COMMAND = {
    "'": _LATEX_ACUTE,
    "`": _LATEX_GRAVE,
    "^": _LATEX_CIRCUMFLEX,
    '"': _LATEX_UMLAUT,
    "~": {"n": "ñ", "N": "Ñ"},
}
_LATEX_STANDALONE_COMMANDS = {
    "ss": "ß",
    "ae": "æ",
    "AE": "Æ",
    "oe": "œ",
    "OE": "Œ",
    "o": "ø",
    "O": "Ø",
    "l": "ł",
    "L": "Ł",
}
_BRACED_TEXT_COMMAND_RE = re.compile(
    r"\\(?:textbf|mathbf|emph|textit|textsl|texttt|color|textcolor)\{([^{}]*)\}"
)
_ACCENT_RE = re.compile(r"\\(['\"`^~])([A-Za-z])")
_CEDILLA_RE = re.compile(r"\\c\{([cCsS])\}")
_STANDALONE_RE = re.compile(
    r"\\("
    + "|".join(re.escape(name) for name in _LATEX_STANDALONE_COMMANDS)
    + r")(?![A-Za-z])"
)
_DISPLAY_MATH_RE = re.compile(r"\$\$([^$]+)\$\$")
_INLINE_MATH_RE = re.compile(r"\$([^$]+)\$")
_LATEX_MATH_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("varphi", "φ"),
    ("varepsilon", "ε"),
    ("vartheta", "ϑ"),
    ("Gamma", "Γ"),
    ("Delta", "Δ"),
    ("Theta", "Θ"),
    ("Lambda", "Λ"),
    ("Sigma", "Σ"),
    ("Omega", "Ω"),
    ("alpha", "α"),
    ("beta", "β"),
    ("gamma", "γ"),
    ("delta", "δ"),
    ("epsilon", "ε"),
    ("zeta", "ζ"),
    ("eta", "η"),
    ("theta", "θ"),
    ("kappa", "κ"),
    ("lambda", "λ"),
    ("mu", "μ"),
    ("nu", "ν"),
    ("xi", "ξ"),
    ("pi", "π"),
    ("rho", "ρ"),
    ("sigma", "σ"),
    ("tau", "τ"),
    ("phi", "φ"),
    ("chi", "χ"),
    ("psi", "ψ"),
    ("omega", "ω"),
)
_MATH_COMMAND_RE = re.compile(r"\\([A-Za-z]+)")


def _math_segment_to_plain(segment: str) -> str:
    plain = segment.strip()
    for name, char in _LATEX_MATH_SYMBOLS:
        plain = plain.replace(f"\\{name}", char)
    plain = _MATH_COMMAND_RE.sub(lambda m: m.group(1), plain)
    return plain.replace("$", "")


def _unwrap_math_delimiters(text: str) -> str:
    plain = _DISPLAY_MATH_RE.sub(lambda m: _math_segment_to_plain(m.group(1)), text)
    plain = _INLINE_MATH_RE.sub(lambda m: _math_segment_to_plain(m.group(1)), plain)
    return plain.replace("$", "")


def latex_to_plain_text(text: str) -> str:
    """Render common arXiv title/abstract LaTeX text commands as plain Unicode."""
    if not text:
        return text

    def replace_accent(match: re.Match[str]) -> str:
        accent, letter = match.group(1), match.group(2)
        return _LATEX_ACCENT_BY_COMMAND.get(accent, {}).get(letter, match.group(0))

    def replace_cedilla(match: re.Match[str]) -> str:
        letter = match.group(1)
        return {"c": "ç", "C": "Ç"}.get(letter, match.group(0))

    def replace_standalone(match: re.Match[str]) -> str:
        return _LATEX_STANDALONE_COMMANDS.get(match.group(1), match.group(0))

    plain = _BRACED_TEXT_COMMAND_RE.sub(r"\1", text)
    plain = _CEDILLA_RE.sub(replace_cedilla, plain)
    plain = _ACCENT_RE.sub(replace_accent, plain)
    plain = _STANDALONE_RE.sub(replace_standalone, plain)
    plain = _unwrap_math_delimiters(plain)
    return plain.replace("~", "\u00a0")
