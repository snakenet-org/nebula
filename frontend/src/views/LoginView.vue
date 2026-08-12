<!--
  @ai-purpose: Login screen — local username/password (the optional admin login) + "Sign in with
    snakeNet ID".
  @ai-context: Posts credentials via useAuth.loginLocal, or starts the Authentik PKCE redirect via
    services/oidc.beginLogin. The basic form is shown only when !config.basicLoginDisabled; the OIDC
    button is shown only when OIDC.enabled and its caption comes from OIDC.caption.
    **2026-08-12 redesign**: the backdrop is a full pure-CSS deep-space scene in this app's rebased
    Solar-Gold/Cosmic-Magenta/Starlight-Cyan palette (style.css) — a twinkling starfield, drifting
    nebula-cloud wisps (one per baseline color, plus two extra diffuse fog patches), a glowing sun,
    and a black hole (event horizon + a slowly rotating accretion-disk ring), all nested inside one
    `.cosmos` layer sized larger than the viewport, animated at a 480s crawl so the WHOLE scene drifts
    as one horizontally across the frame (a slow camera pan across a fixed nebula, not each object
    independently wandering) — every individual object's own drift animation is layered on top of
    that at similarly glacial durations (260s–560s) per the "very very slowly" ask.
    **2026-08-12 (later same day) revision**: dropped the single pulsing "nova" burst (its
    `repeating-conic-gradient` spikes read as radiating lines, not a star) in favor of two tiled
    starfield layers (`.stars-far`/`.stars-near`) — small repeating radial-gradient dot patterns
    stamped across the whole scene via `background-repeat`, giving many more, much smaller,
    plain-dot stars instead of the old single sparse hand-positioned set, with zero lines/spikes
    anywhere in the scene now. Added two extra large, heavily-blurred, low-opacity wisp patches
    (`.wisp-fog-a`/`.wisp-fog-b`) for denser overall nebula haze between the three named-color wisps.
    Every drift keyframe (`drift-a`/`drift-b`/`drift-c`, reused across the wisps/starfield/sun/black
    hole) and `.cosmos`'s own pan are now purely horizontal (`translateX`, right-to-left-and-back
    within one cycle) rather than diagonal, per explicit direction, and slowed further still. The
    login Card itself got a stronger dark-glass treatment than the shared `ui/card` default (deeper
    black tint, heavier blur, a soft magenta glow shadow) so it visibly "hovers" above the scene
    rather than blending into it. Honours prefers-reduced-motion (freezes every animation in the
    scene, login functionality is unaffected). Built from shadcn-vue Card/Input/Label/Button.
    **2026-08-12 (later same day) — realistic black hole + more clouds + standout stars**: the old
    black hole (a flat `conic-gradient` ring div) is replaced with an inline SVG built to actually
    resemble a gravitationally-lensed accretion disk (the attached Interstellar/NASA-simulation-style
    reference renders), not just a glowing ring:
      - a wide, flat gradient ellipse (`rx` ≫ `ry`) for the near/far disk seen almost edge-on,
      - a rounder gradient ellipse (`rx` ≈ `ry`) for the lensed halo — the light from the FAR side of
        the disk bent by gravity so it appears as an arc above and below the hole itself, the single
        detail that actually makes a flat ring read as a black hole rather than a plain Saturn-like
        disk,
      - both punched out over the event horizon via one shared `<mask>` (`#bh-mask`) rather than
        z-order tricks,
      - ~23 thin concentric ellipse strokes layered on top (`diskStreamlines`/`haloStreamlines`
        computed properties, procedurally generated — NOT hand-authored one-by-one, and NOT
        `Math.random` — a fixed `i / count` interpolation so the markup is deterministic across
        renders/screenshots) for the fine turbulent-plasma linework visible in the reference images,
        each interpolated from hot near-white through Solar Gold/Flare to a dark red-black at the
        outer edge via a small `mixHex()` helper,
      - a static (non-rotating) linear-gradient "beaming" overlay, screen-blended, brightening one
        side of the disk relative to the other — real accretion disks are asymmetrically bright from
        relativistic Doppler beaming, and it's the other detail that sells the reference photos,
      - a thin bright `photon ring` stroke right at the horizon boundary, and the event horizon
        itself last/on top as a flat, un-blurred black circle — deliberately crisp, no blur filter on
        the hole itself, so the "much greater detail... crisp clear" ask lands on the disk texture,
        not a soft smudge.
      Only the disk+halo+streamlines+beaming group (`.bh-flow`) rotates (reuses the old `disk-spin`
      timing, renamed `bh-spin`); the photon ring and event horizon stay static, since they're the
      hole itself, not the flowing plasma. A separate blurred `::before` pseudo-element supplies the
      soft ambient bloom around the whole thing — kept OUTSIDE the SVG entirely so the disk geometry
      itself never has to fight a blur filter for sharpness. Grew `.black-hole` 16vmin → 20vmin so
      the added texture is actually visible.
      Cloud coverage: three more named wisps (`wisp-cyan-2`/`wisp-gold-2`/`wisp-magenta-2`) at new
      positions/sizes/drift timings, reusing the exact same three baseline theme colors as the
      original three (style.css's Solar Gold/Cosmic Magenta/Starlight Cyan) rather than inventing new
      hues — "more clouds", not a new palette.
      Stars: a new `.bright-stars` layer of 7 explicitly hand-placed, larger (2–3.2px, vs. the
      tiled starfields' 0.4–0.8px dots), individually-glowing stars (`brightStars` array, each own
      top/left/size/glow-color/animation-delay) — a few of them tinted pale gold/cyan to echo the
      theme colors rather than all pure white — layered above `.stars-far`/`.stars-near` so "a few
      selected stars" read as genuinely brighter/bigger, not just more dots in the same tiled pattern.
    **2026-08-12 (later same day) — removed the halo**: the "lensed halo" ellipse
    (`bh-halo-grad`) + its own `haloStreamlines` ring set from the entry directly above turned out
    to read as a separate bright/hazy sphere overlapping the black hole in an actual screenshot,
    not as thin lensed arcs above/below the event horizon — since it's a nearly-circular (`rx`≈`ry`)
    FILLED ellipse rather than a stroke, the mid-radius "hot" gradient stop glowed across its whole
    annulus at once instead of forming a crisp ring, and its size/opacity (0.85) made it compete
    with the flat disk rather than sit subtly behind it. Removed entirely per explicit feedback —
    the flat edge-on disk (`bh-disk-grad` + `diskStreamlines`), the Doppler-beaming overlay, the
    photon ring, and the event horizon are unchanged and were confirmed to already look right.
  @dependencies: vue, vue-sonner, shadcn-vue (card, input, label, button)
  @version: 5.1.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-12
-->
<script setup>
import { computed, ref } from 'vue';
import { toast } from 'vue-sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { useAuth } from '../composables/useAuth';
import { useConfig } from '../composables/useConfig';
import { OIDC } from '../config/oidc';
import { beginLogin } from '../services/oidc';

const { loginLocal } = useAuth();
const { state: config } = useConfig();

const username = ref('');
const password = ref('');
const busy = ref(false);

// ── Black hole rendering ────────────────────────────────────────────────────
// Linear interpolation between two hex colors, used to color each procedurally-generated
// streamline stroke below (hot near-white at the disk's inner edge, cooling toward Solar
// Gold/Flare, then a dark red-black at the outer edge) without hand-listing ~20 colors.
function mixHex(hexA, hexB, t) {
  const a = parseInt(hexA.slice(1), 16);
  const b = parseInt(hexB.slice(1), 16);
  const r = Math.round(((a >> 16) & 255) + ((((b >> 16) & 255) - ((a >> 16) & 255)) * t));
  const g = Math.round(((a >> 8) & 255) + ((((b >> 8) & 255) - ((a >> 8) & 255)) * t));
  const bl = Math.round((a & 255) + (((b & 255) - (a & 255)) * t));
  return `rgb(${r}, ${g}, ${bl})`;
}

// The wide, flat ellipse — the near/far disk seen almost edge-on, crossing straight through the
// hole. Same hot→cool interpolation as the halo above, just a much flatter aspect ratio.
const DISK_STREAMLINE_COUNT = 14;
const diskStreamlines = computed(() =>
  Array.from({ length: DISK_STREAMLINE_COUNT }, (_, i) => {
    const t = i / (DISK_STREAMLINE_COUNT - 1);
    return {
      rx: 82 + t * 112,
      ry: 15 + t * 21,
      opacity: 0.55 - t * 0.38,
      width: 1.7 - t * 1.0,
      color: mixHex('#fff8e6', '#6a1500', t),
    };
  })
);

// A handful of hand-placed, individually-glowing stars — larger and brighter than anything in the
// tiled .stars-far/.stars-near patterns, so a few points genuinely stand out rather than the whole
// field reading as uniform dots. A couple are tinted pale gold/cyan to echo the theme's baseline
// colors instead of all being pure white.
const brightStars = [
  { top: '12%', left: '22%', size: 3, color: '#fff9ec', glow: 'rgba(255, 246, 221, 0.9)', delay: '0s', duration: '6s' },
  { top: '68%', left: '9%', size: 2.4, color: '#e8fbff', glow: 'rgba(0, 240, 255, 0.85)', delay: '1.4s', duration: '7.5s' },
  { top: '28%', left: '80%', size: 3.2, color: '#fff3d6', glow: 'rgba(255, 183, 3, 0.85)', delay: '2.1s', duration: '5.5s' },
  { top: '84%', left: '46%', size: 2.2, color: '#ffe9f4', glow: 'rgba(255, 0, 127, 0.7)', delay: '0.6s', duration: '8s' },
  { top: '6%', left: '58%', size: 2.6, color: '#f2fbff', glow: 'rgba(0, 240, 255, 0.7)', delay: '3.2s', duration: '6.8s' },
  { top: '46%', left: '92%', size: 2, color: '#fff9ec', glow: 'rgba(255, 246, 221, 0.8)', delay: '1.9s', duration: '7s' },
  { top: '58%', left: '32%', size: 2.8, color: '#fff3d6', glow: 'rgba(255, 183, 3, 0.75)', delay: '4s', duration: '6.2s' },
];

async function submit() {
  busy.value = true;
  try {
    await loginLocal(username.value, password.value);
  } catch (e) {
    toast.error(e.message);
  } finally {
    busy.value = false;
  }
}

async function oidcLogin() {
  try {
    const p = window.location.pathname;
    if (p && p !== '/reentry') {
      sessionStorage.setItem('nebula.returnPath', p);
    }
    await beginLogin();
  } catch (e) {
    toast.error(e.message);
  }
}
</script>

<template>
  <div class="flex-1 flex items-center justify-center p-4 login-scene">
    <div class="space" aria-hidden="true">
      <div class="cosmos">
        <div class="stars-far"></div>
        <div class="stars-near"></div>
        <div class="bright-stars">
          <span
            v-for="(s, i) in brightStars"
            :key="i"
            class="bright-star"
            :style="{
              top: s.top,
              left: s.left,
              width: s.size + 'px',
              height: s.size + 'px',
              background: s.color,
              boxShadow: `0 0 ${s.size * 2.4}px ${s.size * 0.8}px ${s.glow}`,
              animationDelay: s.delay,
              animationDuration: s.duration,
            }"
          ></span>
        </div>
        <div class="wisp wisp-cyan"></div>
        <div class="wisp wisp-gold"></div>
        <div class="wisp wisp-magenta"></div>
        <div class="wisp wisp-cyan-2"></div>
        <div class="wisp wisp-gold-2"></div>
        <div class="wisp wisp-magenta-2"></div>
        <div class="wisp wisp-fog-a"></div>
        <div class="wisp wisp-fog-b"></div>
        <div class="sun">
          <div class="sun-corona"></div>
          <div class="sun-core"></div>
        </div>
        <div class="black-hole">
          <svg class="black-hole-svg" viewBox="0 0 400 400" aria-hidden="true">
            <defs>
              <mask id="bh-mask">
                <rect x="0" y="0" width="400" height="400" fill="#fff" />
                <circle cx="200" cy="200" r="76" fill="#000" />
              </mask>
              <!-- The disk gradient puts its brightest ("hot") stop right at the #bh-mask boundary
                   (~30%/70%) rather than at the shape's own geometric center — the center is
                   exactly what the mask hides, so a stop placed there would never actually be
                   visible. -->
              <linearGradient id="bh-disk-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#3a0d00" />
                <stop offset="22%" stop-color="#ff8c00" />
                <stop offset="30%" stop-color="#fff6dd" />
                <stop offset="70%" stop-color="#fff6dd" />
                <stop offset="78%" stop-color="#ff8c00" />
                <stop offset="100%" stop-color="#3a0d00" />
              </linearGradient>
              <linearGradient id="bh-beam-grad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#fff6dd" stop-opacity="0.55" />
                <stop offset="22%" stop-color="#fff6dd" stop-opacity="0" />
                <stop offset="100%" stop-color="#fff6dd" stop-opacity="0" />
              </linearGradient>
            </defs>

            <!-- Rotating plasma: flat edge-on disk + fine turbulence streamlines + the asymmetric
                 "Doppler beaming" bright side. -->
            <g class="bh-flow">
              <ellipse cx="200" cy="200" rx="192" ry="34" fill="url(#bh-disk-grad)" mask="url(#bh-mask)" />
              <ellipse
                v-for="(l, i) in diskStreamlines"
                :key="'disk' + i"
                cx="200"
                cy="200"
                :rx="l.rx"
                :ry="l.ry"
                fill="none"
                :stroke="l.color"
                :stroke-width="l.width"
                :opacity="l.opacity"
                mask="url(#bh-mask)"
              />
              <ellipse cx="200" cy="200" rx="192" ry="140" fill="url(#bh-beam-grad)" mask="url(#bh-mask)" style="mix-blend-mode: screen" opacity="0.4" />
            </g>

            <!-- Static: the hole itself, not the flowing plasma — a thin bright photon ring right
                 at the horizon boundary, then a crisp, un-blurred black event horizon on top. -->
            <circle cx="200" cy="200" r="79" fill="none" stroke="#fff8e8" stroke-width="2.2" opacity="0.85" class="bh-photon-ring" />
            <circle cx="200" cy="200" r="76" fill="#000" />
          </svg>
        </div>
      </div>
    </div>

    <Card class="w-full max-w-sm relative z-10 login-card">
      <CardContent class="px-8">
        <div class="mb-7">
          <h1 class="text-2xl font-bold flex items-center gap-2">
            <img src="/favicon.png" alt="" width="26" height="26" class="rounded-md" /> Nebula Vault
          </h1>
          <p class="text-muted-foreground text-sm mt-1">A self-hosted secrets manager for snakeNet.org</p>
        </div>

        <form v-if="!config.config.basicLoginDisabled" @submit.prevent="submit" class="space-y-3">
          <div class="space-y-1.5">
            <Label for="login-username">Username</Label>
            <Input id="login-username" v-model="username" placeholder="Username" autocomplete="username" />
          </div>
          <div class="space-y-1.5">
            <Label for="login-password">Password</Label>
            <Input
              id="login-password"
              v-model="password"
              type="password"
              placeholder="Password"
              autocomplete="current-password"
            />
          </div>
          <Button class="w-full" :disabled="busy" type="submit">
            {{ busy ? 'Signing in…' : 'Sign in' }}
          </Button>
        </form>

        <template v-if="OIDC.enabled">
          <div v-if="!config.config.basicLoginDisabled" class="flex items-center gap-3 my-5 text-xs text-muted-foreground">
            <span class="flex-1 border-t border-border"></span>
            or
            <span class="flex-1 border-t border-border"></span>
          </div>
          <Button variant="outline" class="w-full" @click="oidcLogin">{{ OIDC.caption }}</Button>
        </template>
      </CardContent>
    </Card>
  </div>
</template>

<style scoped>
.login-scene {
  position: relative;
  overflow: hidden;
}

.space {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
  background: radial-gradient(140% 90% at 50% 50%, #0a0f16 0%, #05070c 60%, #030406 100%);
}

/* The whole scene lives inside one layer, sized larger than the viewport and panned at a glacial
   480s crawl, purely horizontal (translateX only, `alternate` so it eases back the way it came) —
   this is what makes it read as "the view drifting right-to-left-and-back across the nebula" rather
   than a handful of independently wandering blobs. Every object's own drift animation underneath
   (also horizontal now, see drift-a/b/c) is layered on top of this pan. */
.cosmos {
  position: absolute;
  inset: -20%;
  animation: cosmos-pan 480s linear infinite alternate;
}

@keyframes cosmos-pan {
  0% { transform: translateX(4%) scale(1.05); }
  100% { transform: translateX(-4%) scale(1.05); }
}

/* ── Starfield — two tiled layers (far = smaller/dimmer, near = slightly brighter), each a small
   repeating pattern of plain radial-gradient dots (no lines/spikes) stamped across the whole scene
   via background-repeat, rather than a fixed one-off list of positions — this is what makes "many
   more, much smaller stars" cheap and evenly dense over the full, larger-than-viewport .cosmos
   layer instead of the old single sparse set. Each layer also gets its own glacial horizontal
   drift for a subtle parallax between the two depths. ─── */
.stars-far {
  position: absolute;
  inset: 0;
  background-image:
    radial-gradient(0.5px 0.5px at 14px 22px, rgba(255, 255, 255, 0.7), transparent),
    radial-gradient(0.5px 0.5px at 58px 78px, rgba(255, 255, 255, 0.5), transparent),
    radial-gradient(0.6px 0.6px at 102px 36px, rgba(255, 255, 255, 0.8), transparent),
    radial-gradient(0.4px 0.4px at 136px 116px, rgba(255, 255, 255, 0.45), transparent),
    radial-gradient(0.5px 0.5px at 164px 60px, rgba(255, 255, 255, 0.6), transparent),
    radial-gradient(0.4px 0.4px at 24px 144px, rgba(255, 255, 255, 0.5), transparent),
    radial-gradient(0.5px 0.5px at 180px 14px, rgba(255, 255, 255, 0.55), transparent);
  background-size: 190px 190px;
  background-repeat: repeat;
  opacity: 0.6;
  animation: twinkle 11s ease-in-out infinite, drift-a 560s ease-in-out infinite;
}
.stars-near {
  position: absolute;
  inset: 0;
  background-image:
    radial-gradient(0.7px 0.7px at 10px 26px, #fff, transparent),
    radial-gradient(0.6px 0.6px at 42px 66px, rgba(255, 255, 255, 0.85), transparent),
    radial-gradient(0.8px 0.8px at 74px 14px, #fff, transparent),
    radial-gradient(0.6px 0.6px at 98px 90px, rgba(255, 255, 255, 0.8), transparent),
    radial-gradient(0.7px 0.7px at 112px 42px, #fff, transparent),
    radial-gradient(0.6px 0.6px at 18px 102px, rgba(255, 255, 255, 0.75), transparent),
    radial-gradient(0.7px 0.7px at 62px 120px, #fff, transparent),
    radial-gradient(0.5px 0.5px at 126px 10px, rgba(255, 255, 255, 0.7), transparent);
  background-size: 132px 132px;
  background-repeat: repeat;
  animation: twinkle 8s ease-in-out infinite reverse, drift-c 480s ease-in-out infinite;
}

@keyframes twinkle {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

/* ── A few standout stars — hand-placed (brightStars, script above), individually larger
   (2–3.2px vs. the tiled starfields' 0.4–0.8px dots) and individually glowing via their own
   box-shadow, so a handful of points genuinely read as brighter/bigger rather than the whole
   field looking like uniform dots. Each gets its own animation-delay/-duration (set inline) for a
   staggered, non-uniform twinkle. ─── */
.bright-stars {
  position: absolute;
  inset: 0;
  animation: drift-b 400s ease-in-out infinite;
}
.bright-star {
  position: absolute;
  border-radius: 50%;
  animation-name: star-glow;
  animation-timing-function: ease-in-out;
  animation-iteration-count: infinite;
}
@keyframes star-glow {
  0%, 100% { opacity: 0.6; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1.15); }
}

/* ── Nebula-cloud wisps — two per baseline theme color (six named wisps total), plus two extra
   diffuse fog patches for overall haze, all drifting independently, horizontally, and VERY
   slowly ─── */
.wisp {
  position: absolute;
  border-radius: 50%;
  filter: blur(46px);
  mix-blend-mode: screen;
  opacity: 0.55;
}
.wisp-cyan {
  left: 10%;
  top: 18%;
  width: 52vmin;
  height: 46vmin;
  background: radial-gradient(circle, rgba(0, 240, 255, 0.5) 0%, transparent 70%);
  animation: drift-a 260s ease-in-out infinite;
}
.wisp-gold {
  right: 6%;
  bottom: 8%;
  width: 56vmin;
  height: 50vmin;
  background: radial-gradient(circle, rgba(255, 183, 3, 0.42) 0%, transparent 70%);
  animation: drift-b 340s ease-in-out infinite;
}
.wisp-magenta {
  right: 20%;
  top: 4%;
  width: 38vmin;
  height: 34vmin;
  background: radial-gradient(circle, rgba(255, 0, 127, 0.4) 0%, transparent 70%);
  animation: drift-c 300s ease-in-out infinite;
}
.wisp-cyan-2 {
  left: 42%;
  bottom: 30%;
  width: 34vmin;
  height: 30vmin;
  background: radial-gradient(circle, rgba(0, 240, 255, 0.36) 0%, transparent 70%);
  animation: drift-b 320s ease-in-out infinite reverse;
}
.wisp-gold-2 {
  left: 4%;
  top: 46%;
  width: 40vmin;
  height: 34vmin;
  background: radial-gradient(circle, rgba(255, 183, 3, 0.34) 0%, transparent 70%);
  animation: drift-c 380s ease-in-out infinite reverse;
}
.wisp-magenta-2 {
  right: 42%;
  bottom: 4%;
  width: 30vmin;
  height: 26vmin;
  background: radial-gradient(circle, rgba(255, 0, 127, 0.32) 0%, transparent 70%);
  animation: drift-a 300s ease-in-out infinite;
}
.wisp-fog-a {
  left: 30%;
  bottom: 22%;
  width: 60vmin;
  height: 50vmin;
  filter: blur(60px);
  opacity: 0.32;
  background: radial-gradient(circle, rgba(0, 240, 255, 0.3) 0%, rgba(255, 0, 127, 0.22) 55%, transparent 75%);
  animation: drift-b 400s ease-in-out infinite reverse;
}
.wisp-fog-b {
  right: 34%;
  top: 30%;
  width: 46vmin;
  height: 40vmin;
  filter: blur(56px);
  opacity: 0.3;
  background: radial-gradient(circle, rgba(255, 183, 3, 0.26) 0%, transparent 72%);
  animation: drift-a 360s ease-in-out infinite reverse;
}

/* Purely horizontal — right to left and back within one cycle — per the "drift very very slowly
   from right to left and back" ask; every user of these (wisps, sun, black hole, starfield) is
   slowed to a 260s-560s range on top of .cosmos's own 480s master pan. */
@keyframes drift-a {
  0%, 100% { transform: translateX(5vmin); }
  50% { transform: translateX(-5vmin); }
}
@keyframes drift-b {
  0%, 100% { transform: translateX(-6vmin); }
  50% { transform: translateX(6vmin); }
}
@keyframes drift-c {
  0%, 100% { transform: translateX(4vmin); }
  50% { transform: translateX(-4vmin); }
}

/* ── Sun — a warm Solar Gold sphere with a soft breathing corona ─── */
.sun {
  position: absolute;
  left: 8%;
  bottom: 14%;
  width: 12vmin;
  height: 12vmin;
  animation: drift-b 380s ease-in-out infinite;
}
.sun-core {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: radial-gradient(circle at 38% 32%, #fff6dd 0%, #ffd469 22%, #ffb703 55%, #b56a00 100%);
  box-shadow: 0 0 6vmin -0.5vmin rgba(255, 183, 3, 0.65);
  animation: sun-pulse 14s ease-in-out infinite;
}
.sun-corona {
  position: absolute;
  inset: -60%;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 183, 3, 0.28) 0%, transparent 68%);
  filter: blur(6px);
  animation: sun-pulse 14s ease-in-out infinite reverse;
}
@keyframes sun-pulse {
  0%, 100% { transform: scale(1); opacity: 0.9; }
  50% { transform: scale(1.08); opacity: 1; }
}

/* ── Black hole — an inline SVG built to actually resemble a gravitationally-lensed accretion
   disk (see the header comment for the full shape breakdown: a flat edge-on disk + a rounder
   lensed halo, both punched out over one shared event horizon, textured with procedurally-
   generated streamline strokes). A separate blurred ::before pseudo-element supplies the ambient
   bloom around it — kept OUTSIDE the SVG so the disk geometry itself stays crisp/un-blurred. ─── */
.black-hole {
  position: absolute;
  left: 60%;
  top: 64%;
  width: 20vmin;
  height: 20vmin;
  animation: drift-a 420s ease-in-out infinite reverse;
}
.black-hole::before {
  content: '';
  position: absolute;
  inset: -55%;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 183, 3, 0.28) 0%, rgba(255, 140, 0, 0.16) 40%, transparent 72%);
  filter: blur(18px);
  mix-blend-mode: screen;
  z-index: 0;
}
.black-hole-svg {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: block;
  overflow: visible;
}
/* Only the plasma (disk + halo + streamlines + beaming overlay) rotates — the photon ring and
   event horizon below stay static, since they represent the hole itself, not the flowing matter
   around it. transform-origin is in SVG user-space units (the 400×400 viewBox), not %, since %
   transform-origin on an SVG <g> needs its bounding box computed and isn't reliably centered
   cross-browser otherwise. */
.bh-flow {
  transform-origin: 200px 200px;
  animation: bh-spin 480s linear infinite;
}
@keyframes bh-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
.bh-photon-ring {
  filter: drop-shadow(0 0 3px rgba(255, 248, 232, 0.8));
}

@media (prefers-reduced-motion: reduce) {
  .cosmos,
  .stars-far,
  .stars-near,
  .bright-stars,
  .bright-star,
  .wisp,
  .sun,
  .sun-core,
  .sun-corona,
  .black-hole,
  .bh-flow {
    animation: none;
  }
}

/* ── Login card — a pronounced dark-glass panel hovering above the scene ─── */
.login-card {
  background: rgba(5, 8, 14, 0.42) !important;
  backdrop-filter: blur(28px) saturate(160%);
  -webkit-backdrop-filter: blur(28px) saturate(160%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.03),
    0 25px 70px -20px rgba(255, 0, 127, 0.35),
    0 10px 40px -15px rgba(0, 240, 255, 0.2);
}
</style>
