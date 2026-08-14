import { cva } from "class-variance-authority";

export { default as Button } from "./Button.vue";

// Gradient assignment is deliberately tied to a variant's FUNCTION, not decorative: `default` is the
// one-per-form primary call-to-action, so it gets the boldest two-stop gradient (Starlight Cyan →
// Flare, the two most saturated baseline colors). `secondary`/`outline` are lower-emphasis
// actions and get a softer three-stop wash (Solar Gold → Cyan → Flare) as a translucent tint/
// gradient-bordered outline instead of a solid fill, so they read as secondary next to a `default`
// button on the same form. `ghost` picks up the same wash only on hover/focus, matching its own
// "invisible until interacted with" role. `destructive`/`link` stay solid, universal red/primary —
// see style.css's header comment on why state colors don't get brand gradients.
// 2026-08-12: swapped the third gradient stop from --magenta to --flare (a saturated space
// yellow-orange) across every variant below — product ask was for buttons to read cyan/orange, not
// cyan/magenta. --magenta itself is untouched everywhere else in the app (style.css's --accent,
// LoginView's ambient scene).
const OUTLINE_GRADIENT_BG =
  "[background:linear-gradient(var(--background),var(--background))_padding-box,linear-gradient(135deg,var(--gold),var(--primary)_55%,var(--flare))_border-box]";
const GHOST_HOVER_WASH =
  "hover:[background:linear-gradient(135deg,color-mix(in_oklab,var(--gold)_18%,transparent),color-mix(in_oklab,var(--flare)_18%,transparent))]";

export const buttonVariants = cva(
  "focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive dark:aria-invalid:border-destructive/50 rounded-lg border border-transparent bg-clip-padding text-sm font-medium focus-visible:ring-3 aria-invalid:ring-3 active:not-aria-[haspopup]:translate-y-px [&_svg:not([class*=size-])]:size-4 group/button inline-flex shrink-0 items-center justify-center whitespace-nowrap transition-all outline-none select-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "text-primary-foreground bg-[linear-gradient(135deg,var(--primary),var(--flare))] shadow-[0_0_20px_-6px_var(--primary)] hover:brightness-110 hover:shadow-[0_0_24px_-4px_var(--flare)]",
        outline: `${OUTLINE_GRADIENT_BG} text-foreground hover:brightness-125 aria-expanded:brightness-125`,
        secondary: `border-transparent text-secondary-foreground [background:linear-gradient(135deg,color-mix(in_oklab,var(--gold)_16%,var(--secondary)),color-mix(in_oklab,var(--flare)_16%,var(--secondary)))] hover:[background:linear-gradient(135deg,color-mix(in_oklab,var(--gold)_26%,var(--secondary)),color-mix(in_oklab,var(--flare)_26%,var(--secondary)))] aria-expanded:brightness-110`,
        ghost: `${GHOST_HOVER_WASH} hover:text-foreground aria-expanded:text-foreground aria-expanded:[background:linear-gradient(135deg,color-mix(in_oklab,var(--gold)_18%,transparent),color-mix(in_oklab,var(--flare)_18%,transparent))]`,
        destructive:
          "bg-destructive/10 hover:bg-destructive/20 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 dark:bg-destructive/20 text-destructive focus-visible:border-destructive/40 dark:hover:bg-destructive/30",
        // Same shape as `destructive`, --warning instead of --destructive — added 2026-08-13 for
        // System Settings' "orange" danger zones (import/export vault), a real but less catastrophic
        // action than a delete. Mirrors badge/index.js's own pre-existing "warning" variant, which
        // uses this exact bg/10 + hover/20 + text shape already.
        warning:
          "bg-warning/10 hover:bg-warning/20 focus-visible:ring-warning/20 dark:focus-visible:ring-warning/40 dark:bg-warning/20 text-warning focus-visible:border-warning/40 dark:hover:bg-warning/30",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default:
          "h-8 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        xs: "h-6 gap-1 rounded-[min(var(--radius-md),10px)] px-2 text-xs in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*=size-])]:size-3",
        sm: "h-7 gap-1 rounded-[min(var(--radius-md),12px)] px-2.5 text-[0.8rem] in-data-[slot=button-group]:rounded-lg has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*=size-])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2",
        icon: "size-8",
        "icon-xs":
          "size-6 rounded-[min(var(--radius-md),10px)] in-data-[slot=button-group]:rounded-lg [&_svg:not([class*=size-])]:size-3",
        "icon-sm":
          "size-7 rounded-[min(var(--radius-md),12px)] in-data-[slot=button-group]:rounded-lg",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);
