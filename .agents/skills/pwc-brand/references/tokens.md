# Brand tokens

Source of truth: `frontend/src/styles.css` (website). Python mirror:
`backend/services/brand.py`. oklch values are converted to sRGB hex.

## Colors

| Token | Light | Dark | Role |
| --- | --- | --- | --- |
| `--bg` | `#FAF8F4` | `#11100E` | Page / canvas ("paper") |
| `--bg-elevated` | `#FFFFFF` | `#1A1815` | Cards, tooltips |
| `--bg-subtle` | `#F2EFE8` | `#24211D` | Subtle fills, table stripes |
| `--ink` | `#1A1814` | `#F3EFE7` | Primary text, logo |
| `--ink-soft` | `#5A554C` | `#B9B2A6` | Secondary text, "with Code" |
| `--ink-faint` | `#8E8678` | `#989084` | Labels, eyebrows, ticks, domain |
| `--hairline` | `#E4DFD4` | `#332F29` | Rules, borders, gridlines |
| `--hairline-strong` | `#C8C2B3` | `#514A40` | Stronger borders, axes |
| `--accent` | `#305880` oklch(0.45 0.08 250) | `#79A9DB` oklch(0.72 0.09 250) | The one highlighted element |
| `--accent-soft` | `#D6E7F8` oklch(0.92 0.03 250) | `#192A3C` oklch(0.28 0.04 250) | Non-highlighted data, sparkline area |
| `--accent-text` | `#003C6C` oklch(0.35 0.10 250) | `#97C2F0` oklch(0.80 0.08 250) | Highlighted number / link text |
| `--highlight-bg` / `-text` | `#FFF1D9` / `#733D00` | `#33230F` / `#EEB97B` | Highlighted row callout |
| `--trend-code` | `#33639E` | `#5C8FD6` | Trend chart: GitHub/code series |
| `--trend-hf` | `#AA7D24` | `#B3831F` | Trend chart: Hugging Face series |

Status colors (badges only): positive oklch(0.34 0.10 145) text on
oklch(0.96 0.03 145); negative hue 25; info hue 230/240; warn
oklch(0.55 0.12 30).

## Typography

Google Fonts import (HTML):

```css
@import url('https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,400&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
--serif: 'Newsreader', Georgia, serif;
--sans: 'Inter', -apple-system, sans-serif;
--mono: 'JetBrains Mono', ui-monospace, monospace;
```

Bundled TTFs for Pillow (variable fonts, OFL): `backend/assets/fonts/`
`Newsreader.ttf`, `Newsreader-Italic.ttf`, `Inter.ttf`, `JetBrainsMono.ttf`.
`brand.font(family, size, weight)` sets the weight and optical-size axes.

| Use | Family | Weight | Size (1200 px canvas) | Notes |
| --- | --- | --- | --- | --- |
| Hero title | serif | 500 | 52–56 | -0.02em, sentence case, max 2 lines |
| Page title (site) | serif | 500 | 38 | line-height 1.15 |
| Wordmark "Papers" | serif | 600 | 20 (header) / 26 (card footer) | ink |
| Wordmark "with Code" | serif-italic | 400 | same | ink-soft |
| Subtitle / body | sans | 400 | 23–30 | ink-soft |
| Data labels | sans | 400 (600 highlighted) | 23 | |
| Eyebrow | mono | 500 | 17 | UPPERCASE, 0.12em tracking, ink-faint |
| Numbers / values | mono | 400 (600 highlighted) | 21 | highlighted in accent-text |
| Rank numerals | serif-italic | 400 | 36 | accent |
| Domain | mono | 400 | 18 | ink-faint |

## Logo

- Mark: 32×32 grid — ink square, paper square inset 6, ink square inset 12
  (8×8). Square corners. `assets/pwc-mark.svg`, `assets/pwc-mark-dark.svg`.
- Wordmark: mark, gap ≈ 0.5× font size, "Papers" + space + "with Code".
- Minimum mark size 16 px; keep clear space of one inset (6/32 of the mark)
  around it.

## Shape and layout

- Radius: 4 px (bars, chips), 6 px (buttons), 8 px (cards), 999 px (pills,
  avatars). Logo square.
- Borders are 1 px hairlines. Shadows only for floating UI on the site; none
  in generated images.
- Margins 64–72 px at 1200 px width; header (eyebrow, title, subtitle) →
  hairline → content → hairline → footer (wordmark left, domain right).

## Charts

- Hand-drawn style, no chart-library defaults: no gridline clutter, no
  legends when labels can sit on the data.
- Bars: highlighted bar `--accent`, others `--accent-soft`; values in mono at
  the bar end; label left in sans. Higher-is-better bars start at zero.
  Lower-is-better bars scale as best/value so the best is longest.
- Lines: 2 px stroke in accent (or trend colors), area fill from 26% to 2%
  opacity, dashed `--hairline-strong` guides (3 4), mono 11 px ticks in
  ink-faint.
