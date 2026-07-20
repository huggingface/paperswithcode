# design-sync notes — Papers With Code Design System

Target project: `Papers With Code Design System` (`30645357-87d8-425c-adde-d45217dceb23`), owned by Niels.

## Status (2026-07-20): first full sync UPLOADED
- 47 components live in the project; 20 have authored previews (graded good), 27 on the floor card.
- Conventions header shipped in README. Anchor (`_ds_sync.json`) uploaded — next sync is incremental.
- **Incident during this run:** a concurrent process (a `codex` agent sharing this working tree) ran
  `git commit -a` ("chore: consolidate outstanding workspace changes", `541b384`) then `git checkout main`,
  which swept the untracked `.design-sync/` durable files into that commit and then removed them from disk
  on the branch switch. Recovered via `git show 541b384:<path>`. The durable set is committed inside
  541b384 (tip of `codex/consolidate-worktree`) AND restored on disk (untracked on `main`). If a future
  run finds `.design-sync/` missing, check `git log --all` for the files before re-authoring.

## Architecture (why the config looks the way it does)
- This repo is a **Vite + React app**, not a published component package. The design system is the
  **shadcn/ui primitive library** in `frontend/src/components/ui/` (Radix + Tailwind + CVA).
- There is **no built library `dist/` with `.d.ts`**. So:
  - The bundle entry is a committed barrel `frontend/.ds-ui-barrel.ts` that re-exports every
    `@/components/ui/*` onto `window.Pwc`. Passed via `cfg.entry` + `--entry`.
  - Because there's no `.d.ts` tree, component discovery is driven entirely by
    `cfg.componentSrcMap` (one primary component per `ui/*.tsx` file, ~47). `.d.ts` prop bodies are
    extracted by ts-morph from those src paths (needs `cfg.tsconfig` for the `@/` alias).
- `PKG_DIR` resolves to `frontend/` because `--entry` walks up to the nearest `package.json` with a
  name. All `cfg.*` paths (`cssEntry`, `tsconfig`, `componentSrcMap` values) are **frontend-relative**.

## CSS / tokens
- `cssEntry` = `.ds-tailwind.css` — the compiled Tailwind stylesheet holding the shadcn "slate"
  base tokens (`--background`, `--primary`, `--border`, …) in `:root`/`.dark`. This is what styles
  the primitives. The app's separate hand-rolled `src/styles.css` (v2 cream/academic look, `--ink`/
  `--bg`/`--accent`, Inter/Newsreader fonts) is **NOT** shipped — the DS pane shows the shadcn theme,
  which is the correct token surface for these primitives.
- The barrel imports no CSS, so esbuild emits no `_ds_bundle.css`; the converter copies
  `.ds-tailwind.css` into it. Good.

## Known render warns (triaged legitimate)
- `[TOKENS_MISSING]`: `--radix-*` (navigation-menu viewport h/w, accordion-content-height) and
  `--tw-shadow-color` are **runtime-injected** — expected absent, not a defect.
- `[TOKENS_MISSING]`: `--sidebar-border`, `--sidebar-accent` ARE real shadcn sidebar tokens the app's
  `index.css` never defined. Only affects the Sidebar card's border/accent. TODO: decide whether to
  ship sidebar tokens when authoring the Sidebar preview.

## Root cause of the earlier lost config
- `.gitignore` ignored the **entire** `.design-sync/` dir, so config.json/NOTES/previews were never
  committed and the sync anchor vanished. Fixed: now only machine-state subpaths (`.cache/`,
  `learnings/`, `node_modules`) are ignored; the durable set is committed.

## How the committed sync inputs are (re)generated
- `frontend/.ds-ui-barrel.ts` — re-exports of `ui/*` onto `window.Pwc`; regenerable by hand.
- `frontend/.ds-tailwind.css` — compiled Tailwind. Regenerate with tailwind CLI using
  `frontend/tailwind.sync.config.ts` (widens `content` to include `.design-sync/previews/`).
  Exact command not yet verified — both files are gitignored build artifacts but present on disk.
- Excluded from the sync: `sonner.tsx`/`toaster.tsx` (pure toast mount-points, render empty) and the
  `use-toast` hook.

## Authored-preview recipe (calibrated 2026-07-20)
- Import components from the package name: `import { Button, Card } from "paperswithcode"` — the
  story-imports shim redirects it to `window.Pwc`. Subcomponents (CardHeader, SelectItem, TabsList,
  AvatarFallback, MenubarMenu, …) are all exported and importable the same way.
- **Layout glue uses inline styles**, NOT Tailwind utility classes: `.ds-tailwind.css` is a
  pre-compiled stylesheet, so arbitrary utilities (`flex gap-4`) an author adds are NOT in it and
  won't apply. The DS components carry their own compiled classes and render styled; wrapper divs
  must use `style={{display:"flex",gap:12,padding:20}}` etc.
- Token colors in authored markup: `style={{ color: "hsl(var(--muted-foreground))" }}` works.
- **lucide-react icons work** in previews (Checkbox itself imports `Check` from it) — bundled
  normally, safe to use for realistic content.
- Content is on-brand ML/research (papers, benchmarks, datasets, task names), never foo/bar.
- Build a scoped preview: `node .ds-sync/lib/preview-rebuild.mjs --config .design-sync/config.json
  --node-modules frontend/node_modules --out ./ds-bundle --components A,B` then
  `node .ds-sync/package-capture.mjs --out ./ds-bundle --components A,B`.

## Authored previews (20 core components, 2026-07-20)
All graded `good`. The rest of the 47 ship the floor card (authorable on any later re-sync).
- Calibration: Button, Card, Checkbox
- Overlays/wide (orchestrator-authored): Select (closed triggers), Tooltip (`open`, renders in-card),
  Menubar (bar + one open menu), Table (leaderboard). All render inside the card with NO cardMode
  override needed — revisit only if final validate prints `[GRID_OVERFLOW]`.
- Batch A: Input, Textarea, Label, Switch, Badge, Separator, Skeleton
- Batch B: Avatar, Progress, Alert, RadioGroup, Toggle, Tabs
- Gotchas worth keeping: **Avatar** — headless capture has no network, so `AvatarImage` src never
  loads; rely on `AvatarFallback` initials. **Tabs/Menubar/Select/Tooltip** — set a static open/active
  state (`defaultValue` / `open` / `defaultChecked`) so the interesting state renders in a screenshot.
  **BibTeX/JSX braces** — escape `{`/`}` in JSX text as `&#123;`/`&#125;`.

## Known render warns (triaged legitimate — re-sync should NOT treat as new)
- `[TOKENS_MISSING]`: `--radix-*` (navigation-menu viewport, accordion-content-height) and
  `--tw-shadow-color` are runtime-injected — expected absent. `--sidebar-border`/`--sidebar-accent`
  are real shadcn sidebar tokens the app's CSS never defined (only affects the Sidebar floor card).
- `[RENDER_THIN]` on **AspectRatio**: it's an unauthored floor card and AspectRatio with no child
  paints nothing. Non-blocking. Author `.design-sync/previews/AspectRatio.tsx` if it's ever promoted.

## GRID_OVERFLOW overrides (in config `overrides`)
The final validate flagged several authored cards as wider than the product grid cell. Fixed with
presentation-only `cardMode` overrides: `column` for Alert, Input, Separator, Skeleton, Switch, Tabs,
Textarea, Toggle; `single` + `primaryStory:"Default"` for Tooltip (portal content escapes a grid cell).
After the driver build, apply these then targeted-rebuild those 9 (`preview-rebuild.mjs --components …`).

## Re-sync risks
- Committed sync inputs (`.ds-ui-barrel.ts`, `.ds-tailwind.css`) are gitignored — on a fresh clone
  they must be regenerated before a re-sync (barrel by hand; css via tailwind.sync.config.ts).
- All components currently land in a single `general` group (all under `ui/`). Grouping is a TODO.
