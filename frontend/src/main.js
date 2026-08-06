// @ai-purpose: SPA bootstrap — mounts the root Vue component.
// @ai-context: Entry point loaded by index.html. Kicks off the backend config fetch (login-screen
//   feature flags + OIDC client id) before mount; the persisted copy from the previous fetch is used
//   until it resolves (see useConfig.js). Single fixed dark-glass theme — no theme/mode setup needed.
//   Toasts go through shadcn-vue's Sonner component (`<Toaster>`, mounted once in App.vue; any view
//   calls `toast.success()`/`toast.error()` from `vue-sonner` directly) — replaces the earlier
//   vue-toastification plugin now that this app builds exclusively from shadcn-vue.
//   2026-08-06: `import 'vue-sonner/style.css'` was missing entirely — vue-sonner ships its actual
//   `[data-sonner-toaster] { position: fixed; ... }` rules (and every other toast style) in that
//   separate stylesheet, not inline in the component; shadcn-vue's generated `ui/sonner/Sonner.vue`
//   only sets a handful of CSS *variables* (`--normal-bg` etc.) on top of it, so without the base
//   sheet the toaster rendered as a plain unstyled, unpositioned block — pushing real page content
//   down by its own height instead of floating over it (confirmed via a real browser: computed
//   `position` was `static`, and `document.documentElement.scrollHeight` grew when a toast fired).
//   Raleway
//   (weights 300/400/500/600/700 — shadcn's own component classes lean on font-medium/-semibold/
//   -bold throughout, which need real font files loaded to render distinctly rather than all
//   falling back to the single previously-loaded 300 weight) is self-hosted via @fontsource/raleway
//   (bundled by Vite) rather than a Google Fonts CDN link, matching this repo's no-CDN policy.
// @dependencies: vue, vue-sonner, @fontsource/raleway
// @version: 2.1.0
// @author: Marc Fiedler <marc@snakenet.org>
// @date: 2026-08-06
import { createApp } from 'vue';
import '@fontsource/raleway/300.css';
import '@fontsource/raleway/400.css';
import '@fontsource/raleway/500.css';
import '@fontsource/raleway/600.css';
import '@fontsource/raleway/700.css';
import 'vue-sonner/style.css';
import App from './App.vue';
import './style.css';
import { useConfig } from './composables/useConfig';

useConfig().fetchConfig();

createApp(App).mount('#app');
