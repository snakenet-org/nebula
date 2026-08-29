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

## Nebula-specific escape hatches

- **Charts** (`DailyLineChart.vue`): the Dashboard's three single-series SVG charts take `color` as
  a prop but `DashboardView.vue` currently passes raw hex literals (`#00f0ff`, `#ffb703`, `#f43f5e`)
  instead of resolving the live CSS variables — these happen to equal `--primary`/`--gold`/
  `--destructive` today. If the brand tokens above are ever re-themed, update those three `color`
  props to match.
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
