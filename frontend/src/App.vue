<!--
  @ai-purpose: Root component — app shell, lightweight client router, right-hand collapsible nav rail.
  @ai-context: A tiny history-based router (no vue-router dep, mirrors Satellite's own App.vue
    pattern) maps the path to a view. Unauthenticated users see LoginView. /reentry completes the
    OIDC callback. Page switches run a blur-fade transition (navigate(): blur out 0.13s, swap the
    component, let CSS reveal the new page 0.22s). Single fixed dark-glass theme.
    `/projects/<id>` and `/projects/<id>/settings` are this app's two path-param routes, parsed out
    of `path.value` by regex since there's no vue-router — the matched id is passed down as a
    `project-id` prop; `undefined` (not null) when absent so Vue omits the attribute entirely for
    every other view. On window/tab focus, any authenticated session (local or OIDC) is silently
    refreshed via useAuth.refreshSession() — see that composable for how each kind actually refreshes
    and, for OIDC, its 24h absolute session cap.
    The nav rail is built from shadcn-vue Button/Tooltip/Separator/Avatar primitives (icon-only by
    default, `sidebarExpanded` starts `false` on every load, deliberately not persisted — "always
    collapsed" per product ask) rather than shadcn-vue's own canned "Sidebar" block — that registry
    item fails to generate in this project's plain-JS mode (see style.css's header comment). Sits on
    the RIGHT edge of the viewport (2026-08-06: moved from the left per product ask), and the
    collapse/expand toggle IS the Nebula Vault logo button itself (no separate `PhSidebarSimple`
    footer button anymore) — clicking the logo toggles `sidebarExpanded` rather than navigating (Home
    already covers "go to the project list"). About moved out of the scrollable nav list and into the
    sidebar's own bottom block, directly above Log out — that block's fixed order is now: identity
    row, About, Log out.
    Toasts render via a single root-level Sonner `<Toaster>` (vue-sonner), top-center — any view
    calls `toast.success()`/`toast.error()` imported directly from 'vue-sonner'.
    2026-08-06: the old top `<header>` bar (just the "Generate password" button) is gone — replaced
    by a sticky `<footer>` at the bottom of `<main>`: the Generate-password button bottom-left, the
    running version + "Powered by snakeNet.org" bottom-right (`useConfig().state.version`, forwarded
    from `GET /api/v1/config`'s new `version` field). Removing the header instead of just relocating
    the button reclaims a full row of vertical space for the page content above it.
    2026-08-12: the "Audit logs" nav entry is no longer admin-only (GitHub #4) — every authenticated
    user can now reach it; the page itself (AuditLogsView.vue) and its backing routes scope what a
    non-admin actually sees to their own owned/editor Projects. Dropped the now-unused `isAdmin`
    computed this required nowhere else in this file.
  @dependencies: vue, @phosphor-icons/vue, vue-sonner, shadcn-vue (button, tooltip, separator,
    avatar, sonner)
  @version: 5.2.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-12
-->
<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { PhFolders, PhGauge, PhInfo, PhPassword, PhScroll, PhStack, PhSignOut } from '@phosphor-icons/vue';
import { Toaster } from '@/components/ui/sonner';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { useAuth } from './composables/useAuth';
import { useConfig } from './composables/useConfig';
import * as oidc from './services/oidc';
import * as api from './services/api';
import PasswordGeneratorDialog from './components/PasswordGeneratorDialog.vue';
import LoginView from './views/LoginView.vue';
import ReentryView from './views/ReentryView.vue';
import DashboardView from './views/DashboardView.vue';
import HomeView from './views/HomeView.vue';
import ProjectView from './views/ProjectView.vue';
import ProjectSettingsView from './views/ProjectSettingsView.vue';
import EnvironmentsView from './views/EnvironmentsView.vue';
import AuditLogsView from './views/AuditLogsView.vue';
import AboutView from './views/AboutView.vue';

const showPasswordGenerator = ref(false);

const { state: auth, logout, refreshSession } = useAuth();
const { state: appConfig } = useConfig();

const path = ref(window.location.pathname);
window.addEventListener('popstate', () => (path.value = window.location.pathname));

const reentry = ref(
  window.location.pathname === '/reentry' || oidc.isCallback() || !!oidc.callbackError()
);

const RETURN_PATH_KEY = 'nebula.returnPath';

const transitioning = ref(false);
const sidebarExpanded = ref(false);

async function navigate(to) {
  if (to === window.location.pathname || transitioning.value) return;
  transitioning.value = true;
  await new Promise((r) => setTimeout(r, 160));
  history.pushState({}, '', to);
  path.value = to;
  await nextTick();
  transitioning.value = false;
}

const isAuthed = computed(() => !!auth.session);

watch(isAuthed, (authed, wasAuthed) => {
  if (!authed || wasAuthed) return;
  const returnPath = sessionStorage.getItem(RETURN_PATH_KEY) || null;
  sessionStorage.removeItem(RETURN_PATH_KEY);
  if (returnPath && returnPath !== '/reentry') {
    navigate(returnPath);
  } else if (path.value === '/reentry') {
    navigate('/');
  }
});

const projectMatch = computed(() => path.value.match(/^\/projects\/([^/?]+)(\/settings)?/));
const projectId = computed(() => (projectMatch.value ? decodeURIComponent(projectMatch.value[1]) : null));
const isSettings = computed(() => !!projectMatch.value?.[2]);

const currentView = computed(() => {
  if (projectId.value) return isSettings.value ? ProjectSettingsView : ProjectView;
  if (path.value.startsWith('/projects')) return HomeView;
  if (path.value.startsWith('/environments')) return EnvironmentsView;
  if (path.value.startsWith('/audit-logs')) return AuditLogsView;
  if (path.value.startsWith('/about')) return AboutView;
  return DashboardView;
});

const initials = computed(() => {
  const name = auth.session?.user?.name || '';
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join('') || '?';
});

async function doLogout() {
  // Best-effort audit-log call — nothing server-side to actually invalidate (stateless JWTs), so a
  // failure here must never block the user from logging out.
  try {
    await api.logout();
  } catch {
    // ignore
  }
  logout();
  navigate('/');
}

// ── Focus-triggered token refresh ─────────────────────────────────────────
// Covers both session kinds: a backgrounded/frozen tab's proactive refresh timer may never fire in
// time, so a catch-up refresh on return-to-foreground is the safety net for either (local sessions
// lean on the server's own 15-minute post-expiry grace window here; OIDC sessions on Authentik's
// refresh_token still being valid and the 24h session cap not yet elapsed).
let _refreshingOnFocus = false;
async function _handleVisibilityChange() {
  if (document.visibilityState !== 'visible') return;
  if (!auth.session?.token || _refreshingOnFocus) return;
  _refreshingOnFocus = true;
  await refreshSession();
  _refreshingOnFocus = false;
}
onMounted(() => document.addEventListener('visibilitychange', _handleVisibilityChange));
onUnmounted(() => document.removeEventListener('visibilitychange', _handleVisibilityChange));
</script>

<template>
  <Toaster position="top-center" />

  <div class="relative min-h-screen flex" style="z-index: 1">
    <main class="flex-1 flex flex-col min-w-0">
      <div :class="['page-content', { 'page-entering': transitioning }]">
        <ReentryView v-if="!isAuthed && reentry" @done="reentry = false" />
        <LoginView v-else-if="!isAuthed" @navigate="navigate" />
        <component :is="currentView" v-else :project-id="projectId || undefined" @navigate="navigate" />
      </div>
      <footer
        v-if="isAuthed"
        class="sticky bottom-0 z-30 flex items-center justify-between gap-2 px-4 py-2.5 border-t border-border bg-card/70 backdrop-blur-xl backdrop-saturate-150"
      >
        <Button variant="outline" size="sm" @click="showPasswordGenerator = true">
          <PhPassword :size="16" weight="bold" /> Generate password
        </Button>
        <span class="text-xs text-muted-foreground">
          <template v-if="appConfig.config.version"><span class="text-primary font-medium">v{{ appConfig.config.version }}</span><span class="mx-1.5">|</span></template>Powered by
          <a
            href="https://snakeNet.org/"
            target="_blank"
            rel="noopener noreferrer"
            class="hover:text-foreground underline-offset-2 hover:underline"
          >snakeNet.org</a>
        </span>
      </footer>
    </main>

    <PasswordGeneratorDialog v-model:open="showPasswordGenerator" />

    <TooltipProvider v-if="isAuthed" :delay-duration="200">
      <aside
        class="sticky top-0 self-start h-screen shrink-0 flex flex-col bg-card backdrop-blur-xl backdrop-saturate-150 border-l border-border overflow-hidden transition-[width] duration-200 ease-in-out z-40"
        :class="sidebarExpanded ? 'w-56' : 'w-16'"
      >
        <Tooltip>
          <TooltipTrigger as-child>
            <button
              class="flex items-center gap-2.5 px-4 py-4 border-b border-border cursor-pointer"
              :class="sidebarExpanded ? 'justify-start' : 'justify-center'"
              @click="sidebarExpanded = !sidebarExpanded"
            >
              <img src="/favicon.png" alt="" width="24" height="24" class="rounded-md shrink-0" />
              <span v-if="sidebarExpanded" class="font-bold text-sm truncate">Nebula Vault</span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="left">{{ sidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar' }}</TooltipContent>
        </Tooltip>

        <nav class="flex-1 flex flex-col gap-1 px-2.5 py-3 overflow-x-hidden">
          <Tooltip v-if="!sidebarExpanded">
            <TooltipTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="w-full"
                :class="path === '/' ? 'bg-accent text-accent-foreground' : ''"
                @click="navigate('/')"
              >
                <PhGauge :size="18" weight="bold" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">Dashboard</TooltipContent>
          </Tooltip>
          <Button
            v-else
            variant="ghost"
            class="w-full justify-start gap-2.5"
            :class="path === '/' ? 'bg-accent text-accent-foreground' : ''"
            @click="navigate('/')"
          >
            <PhGauge :size="18" weight="bold" /> Dashboard
          </Button>

          <Tooltip v-if="!sidebarExpanded">
            <TooltipTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="w-full"
                :class="path.startsWith('/projects') ? 'bg-accent text-accent-foreground' : ''"
                @click="navigate('/projects')"
              >
                <PhFolders :size="18" weight="bold" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">Projects</TooltipContent>
          </Tooltip>
          <Button
            v-else
            variant="ghost"
            class="w-full justify-start gap-2.5"
            :class="path.startsWith('/projects') ? 'bg-accent text-accent-foreground' : ''"
            @click="navigate('/projects')"
          >
            <PhFolders :size="18" weight="bold" /> Projects
          </Button>

          <Tooltip v-if="!sidebarExpanded">
            <TooltipTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="w-full"
                :class="path.startsWith('/environments') ? 'bg-accent text-accent-foreground' : ''"
                @click="navigate('/environments')"
              >
                <PhStack :size="18" weight="bold" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">Environments</TooltipContent>
          </Tooltip>
          <Button
            v-else
            variant="ghost"
            class="w-full justify-start gap-2.5"
            :class="path.startsWith('/environments') ? 'bg-accent text-accent-foreground' : ''"
            @click="navigate('/environments')"
          >
            <PhStack :size="18" weight="bold" /> Environments
          </Button>

          <Tooltip v-if="!sidebarExpanded">
            <TooltipTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="w-full"
                :class="path.startsWith('/audit-logs') ? 'bg-accent text-accent-foreground' : ''"
                @click="navigate('/audit-logs')"
              >
                <PhScroll :size="18" weight="bold" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">Audit logs</TooltipContent>
          </Tooltip>
          <Button
            v-else
            variant="ghost"
            class="w-full justify-start gap-2.5"
            :class="path.startsWith('/audit-logs') ? 'bg-accent text-accent-foreground' : ''"
            @click="navigate('/audit-logs')"
          >
            <PhScroll :size="18" weight="bold" /> Audit logs
          </Button>
        </nav>

        <Separator />

        <div class="flex flex-col gap-1 px-2.5 py-3">
          <div class="flex items-center gap-2.5 px-1.5 py-1" :class="sidebarExpanded ? '' : 'justify-center'">
            <Avatar class="size-6">
              <AvatarFallback class="text-[0.65rem]">{{ initials }}</AvatarFallback>
            </Avatar>
            <span v-if="sidebarExpanded" class="text-xs text-muted-foreground truncate">{{ auth.session?.user?.name }}</span>
          </div>

          <Tooltip v-if="!sidebarExpanded">
            <TooltipTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="w-full"
                :class="path.startsWith('/about') ? 'bg-accent text-accent-foreground' : ''"
                @click="navigate('/about')"
              >
                <PhInfo :size="18" weight="bold" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">About</TooltipContent>
          </Tooltip>
          <Button
            v-else
            variant="ghost"
            class="w-full justify-start gap-2.5"
            :class="path.startsWith('/about') ? 'bg-accent text-accent-foreground' : ''"
            @click="navigate('/about')"
          >
            <PhInfo :size="18" weight="bold" /> About
          </Button>

          <Tooltip v-if="!sidebarExpanded">
            <TooltipTrigger as-child>
              <Button variant="ghost" size="icon" class="w-full" @click="doLogout">
                <PhSignOut :size="18" weight="bold" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">Log out</TooltipContent>
          </Tooltip>
          <Button v-else variant="ghost" class="w-full justify-start gap-2.5" @click="doLogout">
            <PhSignOut :size="18" weight="bold" /> Log out
          </Button>
        </div>
      </aside>
    </TooltipProvider>
  </div>
</template>
