# Papers With Code UI — conventions for building with this library

This is a **shadcn/ui** primitive library (Radix UI + Tailwind CSS + class-variance-authority),
exported on `window.Pwc`. Build ML/research-product UIs — paper cards, benchmark leaderboards,
dataset browsers, task pages — from these real components.

## Setup & wrapping
- **No global provider is required.** Components are styled by the semantic CSS-variable tokens in
  `styles.css` (which `@import`s `_ds_bundle.css`); as long as that stylesheet is loaded, primitives
  render correctly on their own.
- **Theming is token-based, light/dark.** The tokens live on `:root` (light) and `.dark` (dark) as
  HSL triples. To switch a subtree to dark, put `className="dark"` on an ancestor — every token
  cascades. Never hard-code hex colors; use the token classes below so both themes work.
- **The only component that needs a wrapper is `Tooltip`:** wrap it (or the app region using it) in
  `<TooltipProvider>`. Popover/DropdownMenu/Select/Dialog/Menubar manage their own Radix context and
  need no app-level provider.

## Styling idiom — Tailwind utilities backed by semantic tokens
Style layout with Tailwind utility classes; use these **semantic color utilities** (never raw colors)
so the design stays on-brand and theme-correct:

| Surface / role | Utilities |
|---|---|
| Page / base | `bg-background` `text-foreground` |
| Card / panel | `bg-card` `text-card-foreground` `border` `rounded-lg` `shadow-sm` |
| Primary action | `bg-primary` `text-primary-foreground` |
| Secondary / subtle | `bg-secondary` `text-secondary-foreground` `bg-muted` |
| Muted/secondary text | `text-muted-foreground` |
| Hover/active surface | `bg-accent` `text-accent-foreground` |
| Danger | `bg-destructive` `text-destructive-foreground` |
| Borders / inputs | `border-border` `border-input` `ring-ring` |
| Corner radius | `rounded-md` / `rounded-lg` (from `--radius`) |

Prefer **component props over classes** for anything a component already models — e.g.
`<Button variant="outline" size="sm">`, `<Badge variant="secondary">`, `<Toggle variant="outline">`.
Variant sets: Button = `default|secondary|outline|ghost|destructive|link` × `default|sm|lg|icon`;
Badge = `default|secondary|destructive|outline`; Alert/Toggle have their own (see each `.prompt.md`).
Merge extra classes with the exported `cn()` helper. Icons come from **lucide-react**.

## Where the truth lives
- `styles.css` + `_ds_bundle.css` — the token definitions and every component's compiled styles. Read
  these before inventing a class.
- `components/<Name>/<Name>.prompt.md` — per-component usage + prop reference. Read the component's
  own file before composing it.

## Idiomatic snippet
```tsx
import { Card, CardHeader, CardTitle, CardDescription, CardContent, Badge, Button } from "window.Pwc";

<Card className="max-w-md">
  <CardHeader>
    <CardTitle>Attention Is All You Need</CardTitle>
    <CardDescription className="text-muted-foreground">Vaswani et al. — NeurIPS 2017</CardDescription>
  </CardHeader>
  <CardContent className="flex flex-col gap-4">
    <div className="flex gap-2">
      <Badge variant="secondary">Machine Translation</Badge>
      <Badge variant="outline">Transformers</Badge>
    </div>
    <Button size="sm">Get code</Button>
  </CardContent>
</Card>
```
