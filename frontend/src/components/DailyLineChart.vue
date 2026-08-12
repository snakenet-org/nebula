<!--
  @ai-purpose: A single-series daily line chart (Dashboard's three extraction/failure charts).
  @ai-context: Dependency-free hand-rolled SVG (same self-hosted-everything policy as every other
    frontend piece here — no chart library added just for three small line charts). One series only,
    so per the dataviz skill's own guidance a legend box is unnecessary (the card title already names
    the series) — color still comes from a passed-in token, never hardcoded per-chart. Ships the
    skill-mandated hover layer: a mousemove handler over an invisible overlay finds the nearest data
    point, draws a vertical crosshair + highlighted dot, and shows a small tooltip with the exact
    date/value — this is what makes it "read" as more than a static sparkline.
  @dependencies: vue
  @version: 1.0.1
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-12
-->
<script setup>
import { computed, ref } from 'vue';

const props = defineProps({
  points: { type: Array, required: true }, // [{ date: 'YYYY-MM-DD', value: Number }]
  color: { type: String, default: '#00f0ff' },
});

const WIDTH = 480;
const HEIGHT = 140;
const PAD_X = 8;
const PAD_TOP = 12;
const PAD_BOTTOM = 22;

const maxValue = computed(() => Math.max(1, ...props.points.map((p) => p.value)));

function xFor(i) {
  if (props.points.length <= 1) return WIDTH / 2;
  return PAD_X + (i / (props.points.length - 1)) * (WIDTH - PAD_X * 2);
}
function yFor(value) {
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;
  return PAD_TOP + plotHeight - (value / maxValue.value) * plotHeight;
}

const linePath = computed(() =>
  props.points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xFor(i)} ${yFor(p.value)}`).join(' ')
);
const areaPath = computed(() => {
  if (!props.points.length) return '';
  const last = props.points.length - 1;
  return `${linePath.value} L ${xFor(last)} ${HEIGHT - PAD_BOTTOM} L ${xFor(0)} ${HEIGHT - PAD_BOTTOM} Z`;
});

const hoverIndex = ref(null);
const svgEl = ref(null);
function onMove(evt) {
  if (!props.points.length || !svgEl.value) return;
  const rect = svgEl.value.getBoundingClientRect();
  const relX = ((evt.clientX - rect.left) / rect.width) * WIDTH;
  let nearest = 0;
  let nearestDist = Infinity;
  props.points.forEach((_, i) => {
    const d = Math.abs(xFor(i) - relX);
    if (d < nearestDist) {
      nearestDist = d;
      nearest = i;
    }
  });
  hoverIndex.value = nearest;
}
function onLeave() {
  hoverIndex.value = null;
}

function formatDate(iso) {
  const d = new Date(iso + 'T00:00:00Z');
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

const totalValue = computed(() => props.points.reduce((sum, p) => sum + p.value, 0));
</script>

<template>
  <div class="space-y-1">
    <svg
      ref="svgEl"
      :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
      class="w-full h-auto"
      @mousemove="onMove"
      @mouseleave="onLeave"
    >
      <defs>
        <linearGradient :id="`grad-${color.replace('#', '')}`" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" :stop-color="color" stop-opacity="0.28" />
          <stop offset="100%" :stop-color="color" stop-opacity="0" />
        </linearGradient>
      </defs>

      <line
        :x1="PAD_X"
        :y1="HEIGHT - PAD_BOTTOM"
        :x2="WIDTH - PAD_X"
        :y2="HEIGHT - PAD_BOTTOM"
        stroke="currentColor"
        class="text-border"
        stroke-width="1"
      />

      <path :d="areaPath" :fill="`url(#grad-${color.replace('#', '')})`" stroke="none" />
      <path :d="linePath" fill="none" :stroke="color" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />

      <template v-if="hoverIndex !== null">
        <line
          :x1="xFor(hoverIndex)"
          :y1="PAD_TOP"
          :x2="xFor(hoverIndex)"
          :y2="HEIGHT - PAD_BOTTOM"
          stroke="currentColor"
          class="text-muted-foreground"
          stroke-width="1"
          stroke-dasharray="2 2"
        />
        <circle :cx="xFor(hoverIndex)" :cy="yFor(points[hoverIndex].value)" r="4" :fill="color" stroke="var(--card)" stroke-width="2" />
      </template>

      <text
        v-if="points.length"
        :x="PAD_X"
        :y="HEIGHT - 6"
        class="fill-muted-foreground"
        font-size="10"
      >
        {{ formatDate(points[0].date) }}
      </text>
      <text
        v-if="points.length"
        :x="WIDTH - PAD_X"
        :y="HEIGHT - 6"
        text-anchor="end"
        class="fill-muted-foreground"
        font-size="10"
      >
        {{ formatDate(points[points.length - 1].date) }}
      </text>
    </svg>

    <div class="flex items-center justify-between text-xs text-muted-foreground h-4">
      <span v-if="hoverIndex !== null">{{ formatDate(points[hoverIndex].date) }}: <span class="text-foreground font-medium">{{ points[hoverIndex].value }}</span></span>
      <span v-else>Total: <span class="text-foreground font-medium">{{ totalValue }}</span></span>
    </div>
  </div>
</template>
