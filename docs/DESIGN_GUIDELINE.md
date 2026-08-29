# Design Guideline — Nebula flavors

The full frontend design guideline (component-source rules, layout system, typography scale,
color-usage framework, button/table/form/dialog/tabs/motion/toast conventions — everything a
token-driven Vue 3 + Tailwind v4 + shadcn-vue frontend needs) lives on **Gravity**, not in this
repo, so it can be shared and kept in sync across snakeNet.org's other frontends too:

- Page title: **"Frontend Design Guideline"**
- Page id: `1d562fcc-e3e0-44f8-950e-27ac1352aef3` (path `/pages/1d562fcc-e3e0-44f8-950e-27ac1352aef3`
  on whichever host the Gravity instance is reachable at)

**You MUST use the `gravity` MCP server to load the full methodology whenever you need it** — call
its `get_page` tool with the id above, or `search_pages` with query `"Frontend Design Guideline"`
if the id ever goes stale. Don't guess at or reconstruct the general guideline from memory or from
this file alone — this file is deliberately incomplete without it. Treat the Gravity page as
canonical; this file intentionally does **not** duplicate it.

This file keeps only the parts that are Nebula Vault's *own* instantiation of that guideline — the
concrete choices this app made for the slots the Gravity page leaves open, plus the escape hatches
and gotchas that only make sense with Nebula's actual file layout in front of you.

## Keeping the two in sync

Before changing anything in this file, ask whether the change is actually Nebula-specific:

- **Nebula-specific** (a concrete value/choice in a slot the Gravity page leaves open to each app —
  a brand color, the font choice, a container width, an escape hatch tied to a specific Nebula file)
  → change only lives here.
- **Not Nebula-specific** (a change to the *methodology* itself — a new general rule, a change to
  an existing rule's reasoning/shape, a new reusable pattern that any snakeNet.org frontend on this
  stack should follow) → **the Gravity page must be updated too**, via the `gravity` MCP server's
  `update_page` (then `publish_page`) — not just noted here. Never let this file silently drift into
  carrying general guidance that Gravity doesn't have; the whole point of hosting it there is that
  every app referencing it sees the same rule. If you're unsure which bucket a change falls into,
  default to updating Gravity — a rule that's technically Nebula-only today but reads as general
  advice belongs there.

## Nebula's concrete choices

| Slot | Nebula's choice |
|---|---|
| Component source | [shadcn-vue](https://www.shadcn-vue.com) (`frontend/src/components/ui/*`), CLI-vendored |
| Icon set | [Phosphor Icons](https://phosphoricons.com) (`@phosphor-icons/vue`), always `weight="bold"` — also `components.json`'s `iconLibrary` |
| Font | Raleway, self-hosted via `@fontsource/raleway` (weights 300/400/500/600/700), imported in `main.js` — never a CDN font link |
| Theme | One fixed dark theme (`<html class="dark">`, no toggle), every color read through `frontend/src/style.css`'s `:root` CSS variables |
| Radius | Flat 6px everywhere (`--radius: 0.375rem`, all four derived tokens equal to it — no size-graded scale) |
| Page container widths | `max-w-6xl` (data/table pages), `max-w-4xl` (form-heavy admin, e.g. System Settings), `max-w-2xl` (single-card reading pages, e.g. About) |

### Brand color tokens

| Token | Value | Used for |
|---|---|---|
| `--primary` / `--primary-foreground` | Starlight Cyan `#00f0ff` / `#001217` | Dominant interactive color — default buttons, links, focus rings, active nav state |
| `--gold` / `--gold-foreground` | Solar Gold `#ffb703` / `#2b1c00` | Button-gradient stop, ambient page glow, login-scene sun |
| `--magenta` / `--magenta-foreground` | Cosmic Magenta `#ff007f` / `#2b0018` | `--accent`'s structural hover tint, ambient glow, login-scene nebula |
| `--flare` / `--flare-foreground` | `#ff8c00` | Second gradient stop on every Button variant |

State colors (`--destructive` `#f43f5e`, `--success` `#22c55e`, `--warning` `#fbbf24`, `--info`
`#38bdf8`) are the universal red/green/amber/sky-blue set — never recolored with a brand hue.

## Nebula's concrete button/card/table/chart recipes

The Gravity page's §5.1 (gradient-driven button variants), §16 (identity/accent entity cards), §6
(table row treatment), and §11.1 (token-driven chart recipe) describe the general *shape* of these
patterns. This is Nebula's own instantiation of each — the actual tokens/angles/percentages/file
locations, kept here rather than on Gravity since a different app picks its own values for these
same slots.

**Buttons** (`components/ui/button/index.js`) — three gradient stops (`--primary` Starlight Cyan,
`--gold` Solar Gold, `--flare` `#ff8c00`), always at `135deg`:
- `default`: 2-stop `linear-gradient(135deg, var(--primary), var(--flare))` fill +
  `shadow-[0_0_20px_-6px_var(--primary)]`, brightening to a `--flare`-colored glow on hover.
- `outline`: the double-background-layer gradient BORDER —
  `[background:linear-gradient(var(--background),var(--background))_padding-box,linear-gradient(135deg,var(--gold),var(--primary)_55%,var(--flare))_border-box]`
  — requires the base variant string to already carry `border border-transparent bg-clip-padding`.
- `secondary`: a `color-mix(in oklab, var(--gold) 16%, var(--secondary))` →
  `color-mix(in oklab, var(--flare) 16%, var(--secondary))` wash, brightening to `26%` on hover.
- `ghost`: the identical gold→flare wash as `secondary`, but only ever rendered inside
  `hover:[...]`/`aria-expanded:[...]` selectors — never at rest.
- `destructive`/`warning`/`link` stay flat semantic (`bg-destructive/10`, `bg-warning/10`, plain
  `text-primary` underline) — no gradient, ever. `--magenta` is deliberately NOT a button-gradient
  stop (swapped out for `--flare` on 2026-08-12 — see the journal entry — magenta stays reserved for
  `--accent`/ambient decoration only).

**Project cards** (`HomeView.vue`'s `projectHue`/`NEBULA_HUE_VARS`): the 4-token hash set is
`['--primary', '--magenta', '--gold', '--flare']`, indexed by a cheap string hash of the Project's
own `id` (`hashString(p.id) % 4`) — never the name/description, which can change. Applied as: a
`-top-12 -right-12 h-36 w-36 blur-3xl opacity-[0.14]` corner glow (`group-hover:opacity-25`), a
`h-px` top-edge `linear-gradient(90deg, transparent, <hue>, transparent)` filament at `opacity-50`,
and a `color-mix(in oklab, <hue> 18%, transparent)`-tinted initials avatar. This is the only place
in the app a card's own accent color varies per-instance — every other Card stays neutral.

**Tables**: row hover is `hover:bg-muted/50` (`TableRow.vue`), selected/expanded rows step up to
`data-[state=selected]:bg-muted` / `has-aria-expanded:bg-muted/50` — both plain `--muted` at
different strengths, never a brand/state color. Separators are the default `border-b` using
`--border` (`rgba(255, 255, 255, 0.09)`). No zebra striping anywhere.

**Charts** (`DailyLineChart.vue`): the Dashboard's three single-series SVG charts take `color` as
  a prop but `DashboardView.vue` currently passes raw hex literals (`#00f0ff`, `#ffb703`, `#f43f5e`)
  instead of resolving the live CSS variables — these happen to equal `--primary`/`--gold`/
  `--destructive` today. If the brand tokens above are ever re-themed, update those three `color`
  props to match. The gradient area-fill under the line runs from the passed `color` at
  `stop-opacity="0.28"` to fully transparent; the baseline rule and axis-label text use
  `text-border`/`text-muted-foreground` (never a hardcoded gray) so they still re-theme even though
  the line's own color is a hardcoded literal.

## Nebula-specific escape hatches

- **Login screen** (`LoginView.vue`): the animated starfield/nebula-wisp/sun/black-hole backdrop is
  the one place in the app using hardcoded hex/rgba instead of shared tokens — deliberately isolated
  to that file's `<script setup>` and `<style scoped>` block so the whole scene can be swapped
  without touching anything else. See the Gravity page §12 for the swap contract (reduced-motion,
  deterministic generation, `aria-hidden`, the `.login-card` override) before rewriting it.
- **Permission-driven UI naming**: every gated `computed()` in a Vue view (`canEdit`, `canReveal`,
  `canEditValue`, `canManage`, `canDeleteOrTransfer`, …) is named after the backend permission
  function it mirrors — `nebula.projects.can_edit`/`can_reveal`/`can_edit_value`/etc. Keep new gated
  controls traceable the same way.
- **shadcn-vue CLI regen gotcha**: the generated `ui/{card,dialog,alert-dialog,popover,
  dropdown-menu,select}/*.vue` files carry permanent hand-edits (`backdrop-blur-xl`/
  `backdrop-blur-2xl` + `backdrop-saturate-150`) for the glass look. Re-running `npx shadcn-vue add`
  on one of these wipes the edit and also re-injects a CDN Google-Fonts `@import` + a duplicate
  `@layer base` block into `style.css` — this has happened three separate times already. Re-apply
  the blur edits and strip both injected blocks again if you ever re-run `add`.

## Consistency-fixes changelog (Nebula's own audit)

The Gravity page's audit pass (the one that produced the guideline) found and fixed six real
inconsistencies in Nebula Vault's frontend at the time: missing `<TableHeader>`s on three Project
Settings tables, inconsistent row-action icon-button sizing (`icon-sm`/14px vs. `icon-xs`/13px,
unified on the latter), an oversized standalone token-copy button, a `destructive`-tier confirm on
a non-destructive transfer-ownership action (moved to `warning`), inconsistent search-input
icon/padding/clear-button treatment across five search boxes, and an under-elevated genuinely-empty
Environments state. All six are described in full, with rationale, on the Gravity page's own
"Consistency fixes applied in this pass" section — this file just notes that the fixes happened and
are the current live behavior; don't reintroduce any of the six.
