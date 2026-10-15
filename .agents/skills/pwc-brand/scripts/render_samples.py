"""Render the reference brand visuals into a directory for visual comparison.

    uv run python .agents/skills/pwc-brand/scripts/render_samples.py /tmp/pwc-brand

Writes bar-card.png (leaderboard / trend chart for X), list-card.png (ranked
roundup for X), square-card.png (1080x1080 announcement built with frame()),
and og-default.png (fallback share image), all drawn with
backend/services/brand.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

from backend.services.brand import LIGHT, font, frame, wrap_text
from backend.services.default_og_image import _render as render_og
from backend.services.x_insight_cards import Bar, render_bar_card, render_list_card


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "pwc-brand-samples")
    out.mkdir(parents=True, exist_ok=True)
    (out / "bar-card.png").write_bytes(
        render_bar_card(
            "New SOTA on IFEval",
            "Accuracy (higher is better)",
            [
                Bar("LFM2.5-24B-A2B", 96.75, "96.75", True),
                Bar("Rufus-Air", 95.4, "95.4"),
                Bar("Qwen3.5-27B", 95.0, "95"),
                Bar("Agents-A1", 94.82, "94.82"),
            ],
            eyebrow="New state of the art · Instruction Following",
        )
    )
    (out / "list-card.png").write_bytes(
        render_list_card(
            "Top trending papers of the week",
            "Published Oct 5 – Oct 11, 2026",
            [
                "MiMo-V2.6: Scaling Reinforcement Learning Towards Self-Improvement",
                "RealtimeWAM: One-Step Asynchronous World Action Models",
                "LightVAE: Towards Compact and Efficient Video Autoencoders",
            ],
            eyebrow="Top papers · weekly",
        )
    )
    (out / "og-default.png").write_bytes(render_og())
    render_square(out / "square-card.png")
    print(f"wrote {out}/bar-card.png, list-card.png, square-card.png, og-default.png")


def render_square(path: Path) -> None:
    card = frame(
        (1080, 1080),
        eyebrow="New · MCP server",
        title="Papers with Code now has an MCP server",
        subtitle=(
            "Connect Claude, Cursor or Codex to search papers, benchmarks "
            "and leaderboards."
        ),
    )
    draw, px, x = card.draw, card.px, card.margin
    features = [
        ("Search papers", "by topic, title or arXiv id, with code and models"),
        ("Read leaderboards", "state-of-the-art results across benchmarks"),
        ("Browse the taxonomy", "tasks, methods, datasets and trending work"),
    ]
    y = card.top + px(24)
    body_font = font("sans", px(24))
    for number, (head, body) in enumerate(features, start=1):
        draw.text(
            (x, y - px(6)),
            str(number),
            font=font("serif-italic", px(44)),
            fill=LIGHT.accent,
        )
        draw.text((x + px(72), y), head, font=font("sans", px(28), 600), fill=LIGHT.ink)
        for line in wrap_text(draw, body, body_font, 1080 - 2 * x - px(72), 2):
            y += px(36)
            draw.text((x + px(72), y), line, font=body_font, fill=LIGHT.ink_soft)
        y += px(96)
    card.image.save(path)


if __name__ == "__main__":
    main()
