# Frontend Design Guideline

This document is the single source of truth for Nebula Vault's visual language. It was produced by
auditing every view, every shared `ui/*` primitive, and every hand-authored component in
`frontend/src`, and by fixing the inconsistencies found along the way (see
[Consistency fixes applied](#consistency-fixes-applied-in-this-pass) at the bottom). Anything new
built for this app should match what's described here; anything that drifts from it should be
brought back in line the same way the fixes below were.

## 1. Foundations

### 1.1 Component source

**Every visual primitive comes from [shadcn-vue](https://www.shadcn-vue.com)** (`src/components/ui/*`,
vendored via its CLI) **or a plain Tailwind utility on top of one.** Do not hand-roll a new
`.btn`/`.card`/`.pill`-style CSS class, and do not reach for a different component library. If
shadcn-vue doesn't ship a registry block that fits (its `sidebar` block cannot even be generated in
this project — see §9), compose the layout from existing primitives (Button/Tooltip/Separator/etc.)
instead of writing bespoke markup from scratch.

Icons are exclusively [Phosphor Icons](https://phosphoricons.com) (`@phosphor-icons/vue`), rendered
with `weight="bold"` everywhere in this app — never a different weight, never a different icon set.
This is also `components.json`'s configured `iconLibrary`, so every shadcn-generated primitive's own
internal icon (Select's chevron, Dialog's ✕, Checkbox's check, Sonner's toast icons) already matches.

### 1.2 Font

**Raleway**, self-hosted via `@fontsource/raleway` (weights 300/400/500/600/700, imported in
`main.js`) — never a CDN font link (no-CDN policy). It is the sole `--font-sans` /
`--font-heading` for the whole app, including the login screen. Body text defaults to weight 300
(`font-weight: 300` on `body` in `style.css`); shadcn's own component classes layer
`font-medium`/`font-semibold`/`font-bold` on top where needed (buttons, labels, headings), which is
exactly why all five weights are loaded, not just 300.

### 1.3 Theme model — single dark palette, driven entirely by CSS variables

There is **one fixed theme** (`<html class="dark">`, hardcoded in `index.html`, no toggle). But the
whole app — every `ui/*` primitive and every view — reads color exclusively through the semantic
CSS variables defined once in `frontend/src/style.css`'s `:root` block and re-exposed as Tailwind
colors in the adjacent `@theme inline` block:

```
--background --foreground
--card --card-foreground
--popover --popover-foreground
--primary --primary-foreground
--secondary --secondary-foreground
--muted --muted-foreground
--accent --accent-foreground
--destructive --success --warning --info      (semantic state colors)
--border --input --ring
--radius (+ derived --radius-sm/md/lg/xl)
```

**This is the flex point for re-theming the app.** To ship an entirely different color theme,
change only the values inside `:root` in `style.css` — never touch a component file. Every `ui/*`
primitive, every Badge/Button variant, every Card/Dialog/Table already resolves color through these
names, so a new palette propagates for free. The one deliberate exception is the trio of brand-only
tokens (`--gold`, `--magenta`, `--flare`, each with a matching `-foreground`) that back the button
gradients and ambient page glow — see §1.4 — swap those alongside the semantic set when re-theming.

**Do not**:
- hardcode a hex color in a view or a `ui/*` component (grep for `#[0-9a-fA-F]{6}` in `src/` before
  committing anything — this repo has done that sweep before and keeps it clean);
- repurpose a *structural* token (e.g. `--secondary`) to carry a bright brand hue — that breaks
  every place that token's foreground-contrast pairing is assumed correct;
- introduce a second way to express a color (inline `style` hex, a Tailwind arbitrary color) when a
  token already exists for the concept you mean.

The two sanctioned exceptions to "always a token" are documented in §11 (charts) and §12 (the login
backdrop) — both are self-contained enough that hardcoded values there don't leak inconsistency
into the rest of the app.

### 1.4 The baseline brand colors

Three named brand hues, each with its own token pair, layered on top of the semantic set:

| Token | Value | Used for |
|---|---|---|
| `--primary` / `--primary-foreground` | Starlight Cyan `#00f0ff` / `#001217` | The dominant interactive color — default buttons, links, focus rings, active nav state |
| `--gold` / `--gold-foreground` | Solar Gold `#ffb703` / `#2b1c00` | Button-gradient stop, ambient page glow, login-scene sun |
| `--magenta` / `--magenta-foreground` | Cosmic Magenta `#ff007f` / `#2b0018` | `--accent`'s structural hover tint, ambient glow, login-scene nebula |
| `--flare` / `--flare-foreground` | `#ff8c00` (a saturated space orange, distinct from `--gold`) | The second gradient stop on every Button variant |

`--accent` (`rgba(255, 0, 127, 0.16)` bg / `#ff9dc9` fg) is the *translucent, structural* form of
Cosmic Magenta — Select/DropdownMenu focus, active sidebar item, ghost-button hover wash.
`--magenta` itself (full strength) is reserved for ambient decoration (ombient page glow, the login
scene) — never for a structural hover/focus state; that's what `--accent` is for.

**State colors are semantic, not brand, and stay that way on purpose:** `--destructive` (`#f43f5e`),
`--success` (`#22c55e`), `--warning` (`#fbbf24`), `--info` (`#38bdf8`) are the universal
red/green/amber/sky-blue set. Never recolor a destructive button, a failure badge, or a warning
banner with a brand hue — mixing brand color into a state signal makes it unreadable as a signal.

### 1.5 Radius scale

**One radius, used everywhere.** All four derived tokens equal the base token — there is no
size-graded scale anymore:

```
--radius:    0.375rem   (6px)
--radius-sm: var(--radius)
--radius-md: var(--radius)
--radius-lg: var(--radius)
--radius-xl: var(--radius)
```

Previously this was a four-step scale (~9.6px on Tooltip up to ~17.6px on Card/Dialog, largest on
the outermost surface, smallest on the smallest element) — deliberately flattened and shrunk to a
single minimal ~6px radius: a smaller, professional/modern look, and so no two surfaces in the app
ever read as "differently rounded" purely because one happens to be a Card and another a Button.
**If you ever touch this token again, change `--radius` alone and keep all four derived tokens
equal to it — do not reintroduce per-size offsets.**

Mapping (unchanged — pick the class for what you're building; they all resolve to the same 6px now,
the choice is only about which existing convention to follow, not about picking a size):

| Element | Tailwind class | Resolves to |
|---|---|---|
| Card, Dialog, AlertDialog panel | `rounded-xl` | `--radius-xl` |
| Button, Input, Textarea, Select trigger, Select content | `rounded-lg` | `--radius-lg` |
| Tabs segmented-control track / trigger | `rounded-lg` / `rounded-md` | `--radius-lg` / `--radius-md` |
| Tooltip content | `rounded-md` | `--radius-md` |

The only exceptions are elements that are deliberately circular or pill-shaped — a different shape
concept entirely, not a "corner radius" in the sense above, so this flattening doesn't touch them:

| Element | Tailwind class | Why it's different |
|---|---|---|
| Badge | `rounded-4xl` | fully pill-shaped (height is only 20px, so any radius ≥10px pills it) |
| Checkbox | `rounded-[4px]` | fixed, deliberately small — it's a checkbox, not a chip |
| Switch / avatar / slider thumb+track | `rounded-full` | circular |

### 1.6 Glass / elevation

Every raised surface (Card, Dialog, AlertDialog, Popover, Select/DropdownMenu content) is
**translucent**, not solid — that's what makes the "dark glass" look:

- `--card: rgba(13, 19, 30, 0.55)`, `--popover: rgba(12, 17, 27, 0.92)` (popover is denser than card
  since it floats over more varied content).
- `backdrop-blur-xl backdrop-saturate-150` on Card; `backdrop-blur-2xl backdrop-saturate-150` on
  Dialog/AlertDialog/Popover/DropdownMenu/Select content (these hand-added edits to the generated
  files are permanent and deliberate — see §9).
- A 1px `ring-foreground/10` (not a `border`) outlines Card/Dialog/AlertDialog/Select-content —
  a hairline that reads as "glass edge," not a hard border.
- Page background carries three fixed radial gradients (cyan/magenta/gold, all very low opacity)
  behind everything, defined once in `style.css`'s `body` rule — this is the ambient "nebula" wash
  every page sits on top of; don't add a second, per-view background.

## 2. Layout

### 2.1 Page container

Every top-level view wraps its content in one of three fixed container widths, centered:

```html
<div class="max-w-6xl mx-auto px-4 py-8 w-full">   <!-- data views: lists, tables, dashboards -->
<div class="max-w-4xl mx-auto px-4 py-8 w-full">   <!-- form-heavy admin pages (System Settings) -->
<div class="max-w-2xl mx-auto px-4 py-8 w-full">   <!-- single-card reading pages (About) -->
```

Pick by content shape, not by page importance: a page whose primary content is a table/grid of
records gets `max-w-6xl` (Dashboard, Projects, Environments, Audit Logs, a Project's key table, a
Project's Settings — all `max-w-6xl`, even Settings, since it holds several data tables). A page
that's a stack of prose/danger-zone cards with no wide tabular data gets `max-w-4xl` (System
Settings). A page that's a single block of reading text gets `max-w-2xl` (About). `px-4 py-8` is
fixed across all three — never adjust page-level padding per view.

The unauthenticated shell (Login, Reentry) doesn't use this container at all — it's a full-bleed
`flex-1 flex items-center justify-center p-4` centering a single narrow Card (`max-w-sm`).

### 2.2 Page header block

Every data page opens with the same header shape:

```html
<div class="flex items-center justify-between mb-6">
  <div>
    <h1 class="text-2xl font-bold [flex items-center gap-2, if the H1 carries a leading icon]">Title</h1>
    <p class="text-muted-foreground text-sm mt-1">One-line description of what this page is.</p>
  </div>
  <Button>Primary action</Button> <!-- only if the page has exactly one primary create action -->
</div>
```

- `text-2xl font-bold` is the **only** H1 treatment in the app — every page (Dashboard, Projects,
  Environments, Audit Logs, System Settings, a Project, Project Settings, Login, Reentry, About)
  uses exactly this.
- The one-line muted subtitle (`text-muted-foreground text-sm mt-1`) directly under the H1 is
  standard; skip it only when the H1 line itself already fully explains the page (never currently
  the case).
- `mb-6` after the header block, always — this is the fixed vertical rhythm between "header" and
  "first content" everywhere in the app.
- A page-level H1 icon (Environments' `PhStack`, Audit Logs' `PhScroll`) sits inline via
  `flex items-center gap-2` on the H1 itself, sized `22px`, `weight="bold"` — only add one when the
  page represents a single concrete icon-able noun (an entity list); don't add one to a page whose
  subject is already named in the title text alone in every other case (Dashboard, Projects, System
  Settings, a Project's own detail page all skip it).

### 2.3 Section heading inside a Card

A card that groups a titled sub-section of a page (e.g. Settings' "Details"/"Sharing"/"API access
keys" cards) uses a plain `h2` reading `font-semibold` at the Card's own inherited `text-sm` size
(`Card`/`CardContent` set `text-sm` at the container level — never re-set it redundantly), `mb-1`
if a description paragraph follows or `mb-3` if a form/table follows directly. Never use `h2` at a
larger explicit size than the surrounding card content — a section heading is a label for what
follows, not a second page title.

### 2.4 Grids and gaps

- Card grids (project cards, dashboard stat tiles, dashboard charts): `grid sm:grid-cols-2
  lg:grid-cols-3 gap-4` (3-up) or `grid sm:grid-cols-2 lg:grid-cols-4 gap-4` (4-up, stat tiles) or
  `grid lg:grid-cols-3 gap-4` (the three dashboard charts). `gap-4` (16px) is the fixed gap for
  every card grid in the app — never `gap-3` or `gap-6` for a card grid.
- Stacking full-width Cards vertically (System Settings' four zones): `space-y-6`. Individual
  cards in Project Settings instead each carry their own trailing `mb-6` — both compile to the same
  24px gap; either authoring style is acceptable, they are not visually different.
- A 2-column responsive field grid inside a form (Project details, the "New key" dialog's top
  fields): `grid sm:grid-cols-2 gap-3`.
- Stacking `Label` + control inside one field: `space-y-1.5`.
- Stacking multiple field groups in a form: `space-y-3` for a simple single-section form (create
  Project/Environment, Edit key), `space-y-4` for a form with more than one distinct section (e.g.
  fields followed by a `Tabs` block, as in the "New key" dialog).

### 2.5 Nav rail — project-scoped sub-items

The right-hand nav rail (`App.vue`) is icon-only by default (`w-16`) and expands to `w-56` on
clicking the logo, showing a text label beside every icon. Every nav entry — collapsed or expanded
— uses the same active-state token: `bg-accent text-accent-foreground` (translucent Cosmic Magenta,
§1.4) on the item matching the current path, plain `variant="ghost"` otherwise.

While inside a Project (`ProjectView` or any of its three settings pages), the rail additionally
shows a project-scoped section between "Projects" and "Environments": a "back to project" entry
(the Project's own name) followed by its three settings sub-items (General settings/Access
Management/Git-Sync), gated to owner/admin/editor. This section only ever appears while a Project
is open — never elsewhere.

**Collapsed mode only**, the three sub-items are wrapped in one shared "zone" container — a single
continuous shape drawn once around the whole cluster, not an individual highlight per icon — so they
read as one distinct, temporary, project-scoped group rather than blending into the permanent icons
above/below them (the "back to project" entry itself stays plain — it's the section's own header,
not a sub-item, and sits outside the zone):

```html
<div class="w-full flex flex-col gap-1 p-1 rounded-lg bg-primary/10 border border-primary/30">
  <!-- the three icon Buttons, each still plain `variant="ghost"`, `bg-accent text-accent-foreground`
       only when active — exactly the same active-state treatment every other nav item uses -->
</div>
```

Subtle fill (`bg-primary/10`) + a subtle, thin `border border-primary/30` — both keyed to `--primary`
(Starlight Cyan, the app's dominant interactive color, §1.4), not `--accent`, so the *cluster itself*
reads in the theme's primary hue while the *active member within it* still pops via the same accent
highlight every other nav item uses, layered on top of the zone's own fill. Two things were tried and
rejected before landing here: outlining each icon individually ("individually colored highlights with
spaces in between them" doesn't read as one group the way a single wrapping border does — a real
group needs one continuous shape, not several similarly-colored ones sitting near each other), and a
heavier `border-2 border-primary/50` on this same wrapping `<div>` (too loud once it actually existed
as one continuous shape — a thin, low-opacity border is enough to read as a boundary once nothing is
competing with it).

Use a plain `border` for this wrapping `<div>` — it has no competing base class, so `border-{color}`
applies cleanly. This is the opposite advice from styling a `Button` directly: `buttonVariants`
(`components/ui/button/index.js`) already claims `border border-transparent` on every variant, so a
same-specificity `border-{color}` utility placed directly on a `Button` races that base class on
stylesheet order rather than reliably overriding it (a known fragile spot in this app) — use
`outline` there instead, never `border`, precisely because it's a wholly separate box-model layer.
Reach for a wrapping element with a real `border` whenever the shape you want spans a whole group,
not a single interactive control.

Expanded mode does **not** get this zone — indentation (`pl-8`) plus the text label already make the
sub-items' grouping obvious there, so adding the same wash would be redundant.

If a future feature needs the same "temporary, contextual cluster of icons" pattern elsewhere in the
rail, reuse this exact recipe (one wrapping `bg-primary/10` + `border border-primary/30` zone,
collapsed-only) rather than inventing a new one.

## 3. Typography scale

| Use | Classes |
|---|---|
| Page title (H1) | `text-2xl font-bold` |
| Card section title (H2) | `font-semibold` (inherits Card's `text-sm`) |
| Sub-section title inside a card (H3, e.g. Danger Zone's "Transfer ownership") | `font-medium text-sm` |
| Body / default UI text | `text-sm` (Card's own default; explicit `text-sm` outside a Card) |
| Muted helper / description text | `text-muted-foreground text-sm` |
| Meta / caption / table timestamps | `text-muted-foreground text-xs` |
| Monospace (keys, tokens, code, values) | `font-mono`, paired with `text-sm` or `text-xs` per context |

Never leave a text node to fall back to the browser's un-sized default — every piece of copy in
this app carries an explicit `text-*` utility (or inherits one from its immediate Card/CardContent
wrapper).

## 4. Color usage by meaning

| Meaning | Token / variant |
|---|---|
| Primary call-to-action (one per form) | Button `variant="default"` (cyan→flare gradient) |
| Secondary action on the same form | Button `variant="outline"` (gradient border) or `variant="secondary"` (soft tri-color wash) |
| Low-emphasis / toolbar action | Button `variant="ghost"` |
| Destructive action (data loss, cannot be undone) | Button/AlertDialogAction `variant="destructive"` — icon-button and confirm-dialog both |
| Serious, irreversible, but **not** data-destroying (transfer ownership, import a vault) | Button/AlertDialogAction `variant="warning"` |
| Plain text link / back-navigation | Button `variant="link"` |
| Role/status pill: owner | Badge `variant="default"` |
| Role/status pill: admin | Badge `variant="accent"` |
| Role/status pill: editor / success state | Badge `variant="success"` |
| Role/status pill: viewer / caution state | Badge `variant="warning"` |
| Neutral count/type pill (e.g. "N keys", environment name) | Badge `variant="outline"` |
| Reference-key marker | Badge `variant="accent"` + `PhLink` |

**The destructive vs. warning line is meaningful — hold it everywhere:** `destructive` (red) is for
anything that deletes or irreversibly discards data (delete project/key/environment, revoke a
share/access key, remove a GitHub target, reset all data, clear audit logs). `warning` (amber) is
for actions that are serious and hard to walk back but don't destroy data (transfer project
ownership away from yourself, import a vault export, export plaintext secrets to a file). Both the
trigger button *and* its confirming `AlertDialogAction` must agree on the tier — never pair an
`outline` trigger with a `destructive` confirm, or vice versa, for the same action.

## 5. Buttons

Defined once in `components/ui/button/index.js` (`cva`-based `buttonVariants`) — never override a
button's color with ad-hoc classes; add a new `variant` there if a genuinely new semantic tier is
needed (this is exactly how `warning` was added alongside the pre-existing `destructive`).

**Sizes** and where each belongs:

| Size | Height | Icon size inside | Where |
|---|---|---|---|
| `default` | `h-8` (32px) | 16px | Ordinary buttons in forms, toolbars, card actions |
| `sm` | `h-7` (28px) | 14px | Compact inline contexts (pagination Prev/Next, GitHub-sync card header actions) |
| `xs` | `h-6` (24px) | — | Rarely used standalone; mainly backs `icon-xs` |
| `icon` | `size-8` (32px) | 16px | **Standalone** icon-only actions not inside a dense table row (Password Generator's copy/regenerate, Settings' one-time-token copy) |
| `icon-sm` | `size-7` (28px) | 14px | Icon-only action next to `sm`-sized controls |
| `icon-xs` | `size-6` (24px) | 13px | **Table-row** action icon buttons — every row-level edit/reveal/copy/sync/delete icon button in every table in the app uses this size, full stop |

**The `icon-xs` rule is load-bearing for consistency**: any icon-only button that lives inside a
`TableCell` — regardless of how many other action buttons share that row or cell — is `size="icon-xs"`
with a `13`px icon. This was previously inconsistent (Project Settings' three tables used `icon-sm`/
14px while the Project and Environments tables used `icon-xs`/13px) and has been unified; see
[Consistency fixes applied](#consistency-fixes-applied-in-this-pass).

Icon-only buttons **always** carry a `title` attribute (used as the native tooltip) unless they're
already wrapped in a shadcn `Tooltip` (only the Project key table's status icons do this, since that
table already stands up a local `TooltipProvider`).

## 6. Tables

Every data table in the app follows the same shape:

```html
<Card class="py-0">                 <!-- Card wraps ONLY the table when the table IS the page's content -->
  <Table>
    <TableHeader>
      <TableRow>
        <TableHead>Column</TableHead>
        <TableHead class="w-20 text-right">Actions</TableHead>   <!-- trailing action column(s) -->
      </TableRow>
    </TableHeader>
    <TableBody>…</TableBody>
  </Table>
</Card>
```

**Every table has a header row. No exceptions.** (Project Settings' Shares/API-keys/GitHub-targets
tables previously had none — fixed, see below.)

**Trailing action-column header label**: if the column holds exactly one action, label it with that
action's own verb (`Delete`, `Revoke`) — matching the icon button's own `title`. If the column holds
more than one distinct action (edit + delete, or sync + edit + remove), label it generically
`Actions`. Give the column a fixed `w-*` and `text-right`.

**Two valid card shapes for a table**, both correct, chosen by page role — do not force one into
the other:
1. **Table-as-the-page's-content** (Environments, a Project's key table, each Audit Logs tab): the
   `Card` wraps *only* the `Table`, `class="py-0"` (kills the Card's own vertical padding so the
   table's own row padding is the only spacing), with the page's `h1`/toolbar living outside the
   card entirely.
2. **Table-inside-a-grouped-settings-section** (Project Settings' Sharing / API keys / GitHub sync
   cards): the `Table` sits directly inside a normally-padded `CardContent`, alongside that card's
   own heading, description, and inline create-form — because the "unit" here is the whole settings
   section, not the table alone.

**Row height / density**: `TableCell` is `p-2` (8px) by default; don't add extra vertical padding
per cell. Use `class="align-top"` on cells in rows that can wrap to multiple lines (the Project key
table's Key cell, which can carry a description line and a reference subtitle) so short cells in the
same row don't visually center against a taller neighbor.

**Empty state inside an existing table's context** ("no rows match your filter/search"): a plain
`Card` (no `py-0`) with `CardContent class="p-10 text-center text-muted-foreground text-sm"` and one
line of copy — nothing else. This is the default empty state for every *filtered-to-nothing* case in
the app (a search with no matches, an environment filter with no keys, an audit tab with no rows).

**Empty state for a genuinely empty top-level list** (the account/vault has zero of this entity at
all — not filtered, just none exist yet): elevate to an icon + heading + one-line subtitle, still
inside a plain `Card`/`CardContent class="p-10 text-center"`:

```html
<PhWhatever :size="32" weight="bold" class="mx-auto mb-3 text-muted-foreground" />
<p class="font-semibold">No projects yet</p>
<p class="text-muted-foreground text-sm mt-1">Create your first project to start storing secrets.</p>
```

Use the same icon already used for that entity's own page-header H1 if it has one (Environments'
`PhStack`). This distinction — plain one-liner for "no results," icon+CTA for "nothing exists yet" —
is deliberate: the former is routine and transient, the latter is the app's actual onboarding
moment and deserves a beat of guidance.

## 7. Forms

- `Label` always precedes its control, wrapped together in `space-y-1.5`.
- Every text `Input` is `h-8` (fixed — the component has no size variant); never fight this with a
  custom height class.
- Placeholder text explains the *expected value* (`"KEY_NAME"`, `"e.g. production"`), not the
  field's optionality — optionality (or its removal) is a deliberate copy decision made per-field,
  not a default habit (see the 2026-08-12 change dropping "(optional)" from the value field's label
  once the field's own placeholder already implied it).
- A field with a trailing inline action (Generate-password, clear-search) uses the same absolutely-
  positioned-button-inside-padding pattern everywhere:
  ```html
  <div class="relative">
    <Input class="pr-8" />  <!-- or pl-7/pr-7 for a LEADING icon + trailing clear, see §8 -->
    <button type="button" class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
      <PhIcon :size="14" weight="bold" />
    </button>
  </div>
  ```
  This is a native `<button>`, not a shadcn `Button` — it's a decoration on the input, not a
  standalone control, so it skips the Button component's own padding/border treatment entirely and
  should never be given one.
- Dialog forms end in a `DialogFooter`/`AlertDialogFooter`, which is itself a shadcn primitive
  (`bg-muted/50`, its own top border, `flex-col-reverse` on mobile flipping to `flex-row
  justify-end` at `sm:` — don't reimplement this). Button order in markup is always **Cancel, then
  the primary/destructive action** — the component's own row-reverse-on-mobile handles putting the
  primary action within thumb reach on small screens; you don't need to reorder anything yourself.

## 8. Search inputs

**One pattern, used everywhere a list is client- or server-side searchable** (Projects, a Project's
key table, every Audit Logs tab):

```html
<div class="relative [max-w-sm, if standing alone above a list]">
  <PhMagnifyingGlass :size="14" weight="bold" class="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
  <Input v-model="query" placeholder="Search …" class="pl-7 pr-7 [w-64, if inline in a toolbar with other h-8 controls]" />
  <button
    v-if="query"
    type="button"
    title="Clear search"
    class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
    @click="query = ''"
  >
    <PhX :size="14" weight="bold" />
  </button>
</div>
```

Fixed values: search icon `14`px at `left-2.5`, input `pl-7 pr-7`, clear icon `14`px at `right-2`.
The **clear (×) button is not optional** — every search box in the app shows one once there's text
to clear, including on a server-backed search (Audit Logs), where clearing should skip any input
debounce and reload immediately rather than waiting out the normal keystroke delay. This was
previously inconsistent (some search boxes used a 16px icon at `left-3`/`pl-9` with no clear button
at all) and has been unified — see [Consistency fixes applied](#consistency-fixes-applied-in-this-pass).

## 9. Dialogs, AlertDialogs, and overlay conventions

- **Dialog** = create/edit a thing, or review data before submitting (New key, Upload .env review,
  Edit environment, GitHub target add/edit). **AlertDialog** = confirm a single already-decided
  action, usually destructive/warning-tier (delete, revoke, reset, transfer, sync-all). Never use a
  plain `Dialog` to ask "are you sure?" — that's what `AlertDialog` is for, and never use
  `AlertDialog` to collect new input.
- Every create/edit action in the app is a **modal**, never an inline toggled form under a header
  button (this was an earlier pattern, fully retired in the 2026-08-12 modals pass — don't
  reintroduce it).
- Default `DialogContent` width is capped at `sm:max-w-sm` — leave it there for a simple
  single/two-field form. Widen explicitly (`sm:max-w-xl`, `sm:max-w-2xl`) only when the form
  genuinely needs it: a two-column grid with several fields plus a `Tabs` block (New key), or an
  embedded review table (Upload .env). Don't widen a dialog "for comfort" — width communicates
  complexity.
- Every `AlertDialog`/`Dialog` whose confirm/save action reads from a specific list-item target
  (not just "the whole page's one thing," like System Settings' vault-wide resets) must hold that
  target in its **own ref, set only on open, never cleared by the dialog's own `@update:open`
  handler** — only by the action's own success/cancel path. `AlertDialogAction` auto-closes on click
  before a sibling `@click` handler is guaranteed to have read the target, so sharing one ref
  between "is it open" and "what is it for" can silently no-op the action. Every per-row delete/
  revoke dialog in this app (`confirmDeleteKey`/`confirmRevokeShare`/`confirmRevokeKey`/
  `confirmDeleteTarget`/…) already follows this split — copy that shape exactly for any new one.
- The generated `ui/{card,dialog,alert-dialog,popover,dropdown-menu,select}/*.vue` files carry
  permanent, deliberate hand-edits (`backdrop-blur-xl`/`backdrop-blur-2xl` + `backdrop-saturate-150`
  added to their root class string) to produce the glass look — if you ever re-run the shadcn-vue
  CLI's `add` command on one of these, **re-apply those edits afterward**, and also strip the CLI's
  own re-injected Google-Fonts `@import` line and duplicated `@layer base` block from `style.css` —
  this has happened three separate times already (documented in the project journal) and is not a
  hypothetical risk.

## 10. Tabs, Switch vs. Checkbox, Tooltips, Skeletons

- **Tabs** are for a mutually-exclusive *mode* choice within one form (Set value / Reference a
  secret; Custom token / Reference a secret; UUID / Secure password) — always
  `<TabsList class="w-full">` with each `TabsTrigger` given `class="flex-1"` so a 2-way choice
  splits the width evenly.
- **Switch** is for a persistent, already-live setting that takes effect immediately on toggle (a
  key's GitHub-sync `sync_enabled`, a GitHub target's `enabled`). **Checkbox** is for a one-time
  selection made before a single batch submit (the Upload .env review table's per-row "include
  this key"). Don't swap these — the moment a toggle POSTs immediately on click is exactly the
  signal to use `Switch`, not `Checkbox`.
- **Tooltip** wraps icon-only controls that need a hint beyond a native `title` only when the
  control sits somewhere `title`'s plain-text hover isn't enough (the collapsed sidebar's icon-only
  nav — `side="left"`, matching the app's right-hand sidebar edge; the Project key table's
  extraction-count status icons, which need a local `TooltipProvider` since that table sits outside
  `App.vue`'s own one). A plain `title` attribute is sufficient everywhere else and is the default —
  don't wrap every icon button in a `Tooltip` "for consistency"; that's simply unnecessary markup.
- **Skeleton** loading states mirror the shape of what's loading: `h-24 rounded-xl` for a stat-tile
  grid, `h-12 rounded-xl` for a table row, `h-8 w-64` + `h-40 rounded-xl` for a detail page's
  header+body. Never show a bare spinner for a page-level load when a shaped Skeleton is possible;
  reserve a spinner (`PhCircleNotch` + `animate-spin`) for a genuinely indeterminate wait with no
  known shape (Reentry's OIDC callback exchange).

## 11. Charts

`DailyLineChart.vue` is a hand-rolled, dependency-free SVG component (no charting library — matches
this app's self-hosted-everything policy) used for the Dashboard's three single-series daily charts.
It takes its stroke `color` as a prop rather than hardcoding one, but the three call sites currently
pass raw hex literals (`#00f0ff`, `#ffb703`, `#f43f5e`) instead of resolving the live CSS variables —
these happen to equal `--primary`, `--gold`, and `--destructive` today. If the palette in §1.4 is
ever re-themed, update `DashboardView.vue`'s three `color` props to match the new values (or thread
`getComputedStyle` resolution through, if a future chart needs to track the token live) — don't
leave a chart silently pointing at a retired palette. Never introduce a chart color that isn't one
of the app's existing semantic/brand tokens, and never use more than one line per chart (this app
deliberately renders three single-series charts instead of one multi-series/dual-axis chart, since
the three metrics have unrelated scales).

## 12. The login screen — the one intentionally swappable "sub-theme"

`LoginView.vue`'s animated backdrop (starfield, nebula wisps, sun, black hole) is **deliberately
isolated** from the rest of the design system: it lives entirely in that single file's `<script
setup>` (a couple of small procedural-generation helpers) and `<style scoped>` block, using
hardcoded hex/rgba values instead of the shared CSS variables — the only place in the app where
that's sanctioned.

This is by design, not an oversight: it means the whole scene can be replaced with a different
theme (different palette, different celestial motif, or something unrelated entirely) by rewriting
only `LoginView.vue`'s `<script>` generative helpers and `<style scoped>` block — nothing else in
the app needs to change, because nothing else references any of those values. When building a
replacement scene, preserve the contract the rest of the app relies on:

- The `Card` containing the actual sign-in form stays a real shadcn `Card`, still themed through
  the shared tokens for its *content* (Input/Label/Button inside it are unmodified primitives) —
  only its outer shell may get a scoped visual override (`.login-card`'s deeper tint/heavier blur/
  glow-shadow treatment is the existing example of how far that override can go: a `!important`
  background plus box-shadow, layered on top of the component's own default classes, never
  replacing them) — form fields and buttons inside it must read and behave exactly as they do on
  every other page.
- Respect `prefers-reduced-motion: reduce` — freeze every animation in the scene (not just slow it
  down) when that media query matches. This is non-negotiable regardless of what the scene depicts.
- Any procedurally-generated visual detail (streamline strokes, star fields, etc.) should be
  deterministic across renders (interpolate from a fixed index, never `Math.random()`) so
  screenshots and visual review stay stable.
- The scene is `aria-hidden="true"` and `pointer-events: none` — it is pure decoration behind a
  real, fully keyboard/screen-reader-accessible form. Keep it that way.

## 13. Permission-driven UI

Every view that varies its controls by the caller's role/permission follows the same shape:
compute one or more boolean `computed()`s straight off `project.my_role` (`canEdit`, `canReveal`,
`canEditValue`, `canManage`, `canDeleteOrTransfer`, …), named after the backend permission function
they mirror (`nebula.projects.can_edit`/`can_reveal`/`can_edit_value`/…), and gate template branches
on those — never inline a role-array check (`['owner','admin'].includes(...)`) more than once for
the same concept in the same file. The **frontend gate is always a convenience, never the actual
boundary** — the backend independently re-checks every one of these on every call, and every view's
header comment says so explicitly. Keep that comment when you add a new gated control: name the
backend function it mirrors so the two stay traceable to each other.

## 14. Motion

Two motion primitives exist in the whole app, and no others:

1. **Page transition** (`App.vue`'s `.page-content`/`.page-entering`): a 220ms opacity+blur fade in,
   130ms fade+blur out on navigate. This is the only page-level transition; don't add a second one
   (slide, scale) for a specific view.
2. **Dialog/Popover/Tooltip open/close**: shadcn's own built-in `data-open`/`data-closed`
   fade+zoom, ~100ms — inherited from the primitives, never overridden per-instance.

Everything else that moves (the login scene, `animate-spin` on a loading glyph, `animate-pulse` on
a `Skeleton`) is either purely decorative (and must honor `prefers-reduced-motion`, per §12) or a
standard Tailwind utility already scoped to exactly the element that's loading/spinning. Don't
introduce a bespoke keyframe animation for anything that one of these three categories already
covers.

## 15. Toasts

All feedback for an async action goes through `vue-sonner`'s `toast.success()` / `toast.error()`,
imported directly from `'vue-sonner'` in whichever view triggers the action — never a custom banner
or inline status text for something that succeeds/fails once and then is done. One root `<Toaster
position="top-center" richColors />`-equivalent lives in `App.vue`; don't mount a second one.
Success and error are the only two toast types actually used in this app — if a third type is ever
needed (e.g. a neutral info toast), it already has themed CSS variables ready in `ui/sonner/
Sonner.vue` (`--info-bg`/`-border`/`-text`), so add it there rather than approximating it with
`toast.success`/`toast.error`.

---

## Consistency fixes applied in this pass

The following real inconsistencies were found while auditing every view against the patterns above
and corrected in the same pass that produced this document:

1. **Project Settings' three tables (Sharing, API access keys, GitHub sync) had no `<TableHeader>`
   at all**, while every other table in the app (Environments, a Project's key table, every Audit
   Logs tab) has one. Added header rows with column labels to all three, matching §6.
2. **Row-action icon buttons were sized inconsistently across views**: Project Settings' three
   tables used `size="icon-sm"` + 14px icons; the Project and Environments tables used
   `size="icon-xs"` + 13px icons for the same kind of control. Unified on `icon-xs`/13px per §5.
3. **The one-time access-token copy button** in Project Settings used the row-action `icon-sm`/14px
   sizing even though it isn't a table-row control — it's a standalone copy action, the same kind
   `PasswordGeneratorDialog` already has. Resized to `icon`/16px to match that existing standalone
   pattern.
4. **The "Transfer ownership" confirmation used `variant="destructive"`**, the same tier as an
   actual delete, even though transferring a project doesn't destroy any data — it's the same
   "serious but not destructive" tier System Settings already established for Import/Export.
   Changed to `variant="warning"` per §4.
5. **Search inputs were inconsistent in two ways** across Projects, a Project's key search, and
   every Audit Logs tab: icon size/padding varied (14px/`pl-7` vs. 16px/`pl-9`), and only the
   Project key search had a clear (×) button. Unified all five search boxes on one pattern (§8),
   including adding the clear button to the four that lacked it, with Audit Logs' clear action
   skipping the search debounce for an immediate reload.
6. **Environments' genuinely-empty state ("no environments exist yet") was a plain one-line
   message**, while Projects' equivalent first-run empty state uses an icon + heading + subtitle.
   Elevated Environments' true-empty state to match, per the two-tier empty-state rule in §6, and
   gave its previously-unlabeled trailing actions column a header (`Actions`, since it holds both
   edit and delete).

All six were verified with a clean `npm run build` after the change.
