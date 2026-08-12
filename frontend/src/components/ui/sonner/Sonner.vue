<script setup>
import {
  PhCheckCircle,
  PhInfo,
  PhCircleNotch,
  PhXCircle,
  PhWarning,
  PhX,
} from '@phosphor-icons/vue';
import { reactiveOmit } from "@vueuse/core";
import { Toaster as Sonner } from "vue-sonner";
import { cn } from "@/lib/utils";

const props = defineProps({
  id: { type: String, required: false },
  invert: { type: Boolean, required: false },
  theme: { type: String, required: false },
  position: { type: String, required: false },
  closeButtonPosition: { type: String, required: false },
  hotkey: { type: Array, required: false },
  // Defaults on (not vue-sonner's own default of off) so every toast.success/warning/error call in
  // the app is colored without every call site having to opt in — see the template's :style block
  // for the actual green/yellow/red mapping (--success-bg/--warning-bg/--error-bg), keyed off this
  // app's own --success/--warning/--destructive theme tokens (style.css), not vue-sonner's built-in
  // light-mode defaults.
  richColors: { type: Boolean, required: false, default: true },
  expand: { type: Boolean, required: false },
  duration: { type: Number, required: false },
  gap: { type: Number, required: false },
  visibleToasts: { type: Number, required: false },
  closeButton: { type: Boolean, required: false },
  toastOptions: { type: Object, required: false },
  class: { type: String, required: false },
  style: { type: Object, required: false },
  offset: { type: [Object, String, Number], required: false },
  mobileOffset: { type: [Object, String, Number], required: false },
  dir: { type: String, required: false },
  swipeDirections: { type: Array, required: false },
  icons: { type: Object, required: false },
  containerAriaLabel: { type: String, required: false },
});
const delegatedProps = reactiveOmit(props, "class", "toastOptions");
</script>

<template>
  <Sonner
    :class="cn('toaster group', props.class)"
    :style="{
      '--normal-bg': 'var(--popover)',
      '--normal-text': 'var(--popover-foreground)',
      '--normal-border': 'var(--border)',
      '--success-bg': 'color-mix(in oklab, var(--success) 20%, var(--popover))',
      '--success-border': 'color-mix(in oklab, var(--success) 45%, transparent)',
      '--success-text': 'var(--success)',
      '--warning-bg': 'color-mix(in oklab, var(--warning) 20%, var(--popover))',
      '--warning-border': 'color-mix(in oklab, var(--warning) 45%, transparent)',
      '--warning-text': 'var(--warning)',
      '--error-bg': 'color-mix(in oklab, var(--destructive) 20%, var(--popover))',
      '--error-border': 'color-mix(in oklab, var(--destructive) 45%, transparent)',
      '--error-text': 'var(--destructive)',
      '--info-bg': 'color-mix(in oklab, var(--info) 20%, var(--popover))',
      '--info-border': 'color-mix(in oklab, var(--info) 45%, transparent)',
      '--info-text': 'var(--info)',
      '--border-radius': 'var(--radius)',
      '--gray2': 'hsl(var(--popover) / 0.9)',
      '--gray3': 'var(--border)',
      '--gray4': 'var(--border)',
      '--gray5': 'var(--border)',
      '--gray12': 'var(--popover-foreground)',
    }"
    :toast-options="
      props.toastOptions ?? {
        classes: {
          toast: 'rounded-2xl',
        },
      }
    "
    v-bind="delegatedProps"
  >
    <template #success-icon>
      <PhCheckCircle class="size-4" />
    </template>
    <template #info-icon>
      <PhInfo class="size-4" />
    </template>
    <template #warning-icon>
      <PhWarning class="size-4" />
    </template>
    <template #error-icon>
      <PhXCircle class="size-4" />
    </template>
    <template #loading-icon>
      <div>
        <PhCircleNotch class="size-4 animate-spin" />
      </div>
    </template>
    <template #close-icon>
      <PhX class="size-4" />
    </template>
  </Sonner>
</template>
