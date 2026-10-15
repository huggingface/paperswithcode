---
name: pwc-brand
description: Papers with Code brand guidelines (colors, fonts, logo, layout, chart style, voice) taken from the paperswithcode.co website, plus the Pillow helpers that apply them. Use this whenever you create or restyle any Papers with Code visual or branded copy — X/social post images and charts, OG/share images, announcement cards, slides, report or dashboard graphics, diagrams, emails, or HTML pages meant to look like the site — even if the request only says "make an image/chart for the X post" or "make it look like our website". Not for paper thumbnails, which show the paper's own artwork (use create-thumbnail).
---

# Papers with Code brand

The website's look is a calm **academic paper**: warm off-white paper,
near-black ink, a serif for titles, a clean sans for text, mono for labels
and numbers, hairline rules instead of shadows, and one muted **blue** accent
used sparingly to point at the thing that matters. Every generated visual
should look like a page of the site.

Exact token values, type scale, and chart specs: `references/tokens.md`.
Worked examples (X card, OG image, HTML/SVG chart, slide): `references/examples.md`.

## How to apply it

- **Server-rendered images (Python/Pillow):** never hard-code colors or font
  paths. Import from `backend/services/brand.py`:
  - `frame(size, title=, subtitle=, eyebrow=, title_size=)` — paper canvas
    with the standard header and footer for any size; draw content between
    `frame.top` and `frame.bottom`, scale your own sizes with `frame.px(n)`
    (sizes are on the 1200×675 reference scale; the frame scales by area).
  - `font(family, size, weight)` with families `serif`, `serif-italic`,
    `sans`, `mono` (bundled variable fonts in `backend/assets/fonts/`).
  - `wrap_text`, `fit_text`, `draw_tracked` (letter-spaced mono labels),
    `draw_mark`, `draw_wordmark`, `LIGHT`/`DARK` palettes.
  - Ready-made 1200×675 cards: `render_bar_card` and `render_list_card` in
    `backend/services/x_insight_cards.py`. Reuse them before writing new ones.
- **Pillow limitation:** skip negative title tracking (-0.02em); drawing
  per character breaks kerning. Tracking is only for mono eyebrows.
- **HTML/SVG/slides:** use the CSS custom properties and Google Fonts import
  from `references/tokens.md`; support dark mode with the `DARK` values.
- **Check your output:** `uv run python .agents/skills/pwc-brand/scripts/render_samples.py <out_dir>`
  renders the references: `bar-card.png` (leaderboard / trend chart, X),
  `list-card.png` (ranked roundup, X), `square-card.png` (1080×1080
  announcement built with `frame()`), `og-default.png` (share image).
  Compare against them and view every image you produce before publishing.

## Rules

**Color**
- Paper `#FAF8F4` background, ink `#1A1814` for primary text; secondary text
  ink-soft `#5A554C`, labels ink-faint `#8E8678`; hairlines `#E4DFD4`.
- One accent: blue `#305880` (`--accent`), with accent-soft `#D6E7F8` for
  non-highlighted data and accent-text `#003C6C` for the highlighted number.
  Use it for the single most important element or series (the new SOTA bar,
  a link, or one consistent series such as list/rank numerals) — not for
  decoration, backgrounds, or headlines.
- Never use orange/red (#DC562F) or saturated brand colors; the site has none.
  Warm highlight (`#FFF1D9` / `#733D00`) only for a "highlighted row" callout.
- Charts: highlighted series in accent, everything else accent-soft or
  hairline-strong `#C8C2B3`. Two-series trend charts use `#33639E` (code) and
  `#AA7D24` (Hugging Face), as on /trends.

**Typography**
- Titles: **Newsreader** (serif), weight 500, tight (-0.02em), sentence case.
- Body and subtitles: **Inter** 400 (600 for emphasis inside data rows).
- Eyebrows, labels, axis ticks, numbers, the domain: **JetBrains Mono**,
  eyebrows UPPERCASE with 0.1–0.12em tracking in ink-faint.
- At most these three families; no other fonts, no all-caps titles.

**Logo**
- The mark is three nested squares (ink / paper / ink, square corners):
  `assets/pwc-mark.svg` (`pwc-mark-dark.svg` on dark). Never round it,
  recolor it, or add effects.
- The wordmark is **"Papers"** in Newsreader 600 ink followed by
  **"with Code"** in Newsreader italic 400 ink-soft (`draw_wordmark`). In
  plain text write "Papers with Code" (lowercase "with"), never "PwC" or
  "PapersWithCode".

**Layout**
- Generous margins (≥ 64 px on 1200 px canvases), left-aligned text,
  hairline rules to separate header, content, and footer.
- Radius 4 px for bars/chips, 8 px for cards; square logo. No drop shadows,
  gradients, glows, or stock imagery.
- Footer on social cards: wordmark left, `paperswithcode.co` in mono
  ink-faint right.
- Sizes: X 1200×675, OG 1200×630, square 1080×1080. Type and margins scale
  with canvas area from the 1200×675 reference (`frame.px`, ×1.2 on square);
  use leftover height for more space between items, not bigger text.

**Voice (captions, post text, slide copy)**
- Direct, specific, and technical, like a research briefing: lead with the
  most interesting fact and give exact numbers with their metric.
- No hype ("groundbreaking", "game-changer", "revolutionary"), no emojis or
  hashtags, no questions to the reader. Name models and benchmarks exactly
  as written on the site.

## Before you publish

1. Background is paper (or the dark palette throughout), never white or
   gray.
2. Only Newsreader / Inter / JetBrains Mono are used.
3. The accent marks exactly one thing per visual.
4. The mark and wordmark are unmodified.
5. Numbers in text and image match the data, and the image was viewed.
