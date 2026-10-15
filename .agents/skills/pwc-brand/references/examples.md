# Brand examples

## X insight card (Python)

The production cards are `backend/services/x_insight_cards.py`, used by the
`post_x_insight` CRON. A new chart for a post:

```python
from backend.services.x_insight_cards import Bar, render_bar_card

png = render_bar_card(
    "New SOTA on IFEval",                      # serif title, sentence case
    "Accuracy (higher is better)",             # sans subtitle: metric + direction
    [
        Bar("LFM2.5-24B-A2B", 96.75, "96.75", highlight=True),  # the one accent
        Bar("Rufus-Air", 95.4, "95.4"),
        Bar("Qwen3.5-27B", 95.0, "95"),
    ],
    eyebrow="New state of the art · Instruction Following",     # mono, uppercased
)
```

Post text that goes with it (voice):

> LFM2.5-24B-A2B sets a new SOTA on IFEval with 96.75 Accuracy, ahead of
> Rufus-Air at 95.4.

Not: "🚀 Huge news! A groundbreaking model just CRUSHED IFEval! #AI".

## A new Pillow layout (any size)

`frame()` draws the paper, eyebrow, wrapped title, subtitle, rules, and the
footer (wordmark + domain); you only draw the content. This is the square
reference sample (`scripts/render_samples.py`):

```python
from backend.services.brand import LIGHT, font, frame, wrap_text

card = frame(
    (1080, 1080),
    eyebrow="New · MCP server",
    title="Papers with Code now has an MCP server",
    subtitle="Connect Claude, Cursor or Codex to search papers, benchmarks and leaderboards.",
)
draw, px, x = card.draw, card.px, card.margin
y = card.top + px(16)
for number, (head, body) in enumerate(features, start=1):
    draw.text((x, y - px(6)), str(number), font=font("serif-italic", px(44)), fill=LIGHT.accent)
    draw.text((x + px(72), y), head, font=font("sans", px(28), 600), fill=LIGHT.ink)
    for line in wrap_text(draw, body, font("sans", px(24)), 1080 - 2 * x - px(72), 2):
        y += px(36)
        draw.text((x + px(72), y), line, font=font("sans", px(24)), fill=LIGHT.ink_soft)
    y += px(80)
card.image.save("card.png")
```

## Default OG image

`backend/services/default_og_image.py` renders the fallback share image:
centred mark, wordmark, Inter tagline, mono domain on paper — the same
composition as `frontend/public/og-image.png`.

## HTML / SVG chart

```html
<style>
  :root { --bg:#FAF8F4; --ink:#1A1814; --ink-soft:#5A554C; --ink-faint:#8E8678;
          --hairline:#E4DFD4; --accent:#305880; --accent-soft:#D6E7F8; --accent-text:#003C6C; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#11100E; --ink:#F3EFE7; --ink-soft:#B9B2A6; --ink-faint:#989084;
            --hairline:#332F29; --accent:#79A9DB; --accent-soft:#192A3C; --accent-text:#97C2F0; }
  }
  body { background: var(--bg); color: var(--ink); font-family: 'Inter', sans-serif; }
  h1 { font-family: 'Newsreader', serif; font-weight: 500; letter-spacing: -0.02em; }
  .eyebrow, .value { font-family: 'JetBrains Mono', monospace; }
  .eyebrow { text-transform: uppercase; letter-spacing: .12em; color: var(--ink-faint); font-size: 11px; }
  .bar { fill: var(--accent-soft); } .bar.best { fill: var(--accent); }
</style>
```

## Slides

Paper background, one idea per slide, Newsreader 500 title top-left, mono
eyebrow above it, Inter body, wordmark bottom-left at small size, no
template decorations. Charts follow the chart rules in `tokens.md`.
