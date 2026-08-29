<!--
  @ai-purpose: Root component — app shell, lightweight client router, right-hand collapsible nav rail.
  @ai-context: A tiny history-based router (no vue-router dep, mirrors Satellite's own App.vue
    pattern) maps the path to a view. Unauthenticated users see LoginView. /reentry completes the
    OIDC callback. Page switches run a blur-fade transition (navigate(): blur out 0.13s, swap the
    component, let CSS reveal the new page 0.22s). Single fixed dark-glass theme.
    `/projects/<id>` and `/projects/<id>/settings[/access|/git-sync]` are this app's path-param
    routes, parsed out of `path.value` by one regex since there's no vue-router — the matched id is
    passed down as a `project-id` prop; `undefined` (not null) when absent so Vue omits the attribute
    entirely for every other view. On window/tab focus, any authenticated session (local or OIDC) is silently
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
    sidebar's own bottom block, directly above Log out — that block's fixed order is now:
    Generate password, identity row, About, Log out (see the second 2026-08-12 entry below for why
    Generate password sits there and not in the nav list above).
    Toasts render via a single root-level Sonner `<Toaster>` (vue-sonner), top-center — any view
    calls `toast.success()`/`toast.error()` imported directly from 'vue-sonner'.
    2026-08-06: the old top `<header>` bar (just the "Generate password" button) is gone — replaced
    by a sticky `<footer>` at the bottom of `<main>`, now just the running version + "Powered by
    snakeNet.org" (`useConfig().state.version`, forwarded from `GET /api/v1/config`'s new `version`
    field) — see the 2026-08-12 entry below for where the Generate-password button itself ended up.
    2026-08-12: the "Audit logs" nav entry is no longer admin-only (GitHub #4) — every authenticated
    user can now reach it; the page itself (AuditLogsView.vue) and its backing routes scope what a
    non-admin actually sees to their own owned/editor Projects. Dropped the now-unused `isAdmin`
    computed this required nowhere else in this file.
    2026-08-12 (same day, follow-up): moved the Generate-password button out of the footer entirely
    and into the top of the right-hand nav rail (above a `Separator`, ahead of Dashboard/Projects/
    Environments/Audit logs) — same icon-only-collapsed/icon+text-expanded + Tooltip pattern as every
    other nav entry, but `variant="default"` instead of `ghost` so its cyan→flare brand gradient
    (button/index.js, see style.css's same-day color-rebase note) makes it visually pop against the
    plain nav links below it, per product ask ("make the button colored so it stands out"). The
    footer's `justify-between` became `justify-end` now that it only has the version/Powered-by span
    left in it.
    2026-08-12 (same day, second follow-up): moved the Generate-password button again — out of the
    top of the nav list and down into the bottom block, directly above the identity row (so it now
    reads Generate password / avatar+name / About / Log out) — per product ask. Same
    icon-only-collapsed/icon+text-expanded + Tooltip + `variant="default"` markup, unchanged, just
    relocated; the nav list's leading `Separator` that used to sit between it and Dashboard moved
    with it (removed, since the bottom block already has its own separating `Separator` above it).
    2026-08-13: added a "System Settings" nav entry (route `/system-settings` → new
    SystemSettingsView.vue) at the bottom of the scrollable nav list, below Audit logs — the
    `isAdmin` computed dropped in the 2026-08-12 Audit-logs-opened-up entry above is back, this time
    actually admin-only (`v-if="isAdmin"` around the whole entry, both collapsed/expanded variants),
    since System Settings' four danger zones (reset all data, reset logs, import/export vault — see
    that view's own header) are the one page in this app that stays admin-only end to end.
    2026-08-27: the former single ProjectSettingsView.vue (Details/Sharing/API keys/GitHub sync/
    Danger zone all on one page) is split into three distinct routes/views —
    ProjectGeneralSettingsView (`/settings`, kept bare so old links still resolve),
    ProjectAccessManagementView (`/settings/access` — Sharing + API access keys together; briefly
    two separate views/routes the same day, merged back into one per a same-day follow-up ask, since
    both share the exact same owner/admin/editor permission tier), ProjectGitSyncView
    (`/settings/git-sync`) — per product ask. `settingsSection` (parsed from the same `projectMatch`
    regex, with an extra optional capture group for the sub-path segment) picks the right one;
    `undefined`/no match falls through to plain ProjectView.
    2026-08-29: the three settings pages' own `ProjectSettingsNav` sub-nav (a "back to project" link
    + a row of buttons jumping between the three sections, and ProjectView's own three header
    buttons before that) are both gone — replaced by a project-scoped section of THIS nav rail
    itself, per product ask ("buttons at the top right" → "an extended sidebar with sub-items").
    Shown only while `projectId` is set (i.e. on ProjectView or any of its three settings pages,
    never on the Projects list or anywhere else) — a "back to project" entry (the project's own
    name, highlighted when `settingsSection` is null) followed by three indented sub-items (General
    settings/Access Management/Git-Sync), gated on the SAME owner/admin/editor tier the old header
    buttons used. Since App.vue previously had no reason to know anything about a Project beyond its
    bare id (parsed out of the URL), it now does its own lightweight `api.getProject(projectId)`
    fetch (`sidebarProject`, re-fetched on every `projectId` change, cleared to `null` when leaving a
    project) purely to read `name`/`my_role` for this section — a deliberate, small duplication of
    the fetch every one of the four project-scoped views already does on its own, matching this
    app's existing no-shared-store convention rather than introducing one just for this. The
    component file `components/ProjectSettingsNav.vue` was deleted as dead code — nothing else
    referenced it.
    2026-08-29 (later same day): while the nav rail is COLLAPSED, the three settings sub-items are
    now wrapped in one shared "zone" `<div>` (`bg-primary/10`, `border border-primary/30`,
    `rounded-lg`, `p-1`) instead of each icon carrying its own individual highlight — per product
    follow-up ("one large zone behind and around the sub-menu items with a strong visible border,"
    not "individually colored highlights with spaces in between them"). A first pass tried exactly
    that individually-outlined shape (`outline` per icon, since the shared Button base already claims
    `border border-transparent` and a plain `border-*` override on a `Button` is a known fragile spot
    in this app) — replaced here because a wrapping `<div>` has no such conflicting base class, so a
    real `border` reads as the "strong visible border" the ask wanted, drawn once around the whole
    cluster rather than once per icon with gaps showing through. A follow-up ask then dialed the
    border back down from `border-2 border-primary/50` to a thinner, lower-opacity `border
    border-primary/30` — same shape, just subtler. The active sub-item still pops via the same
    `bg-accent text-accent-foreground` every other nav item uses, now layered on top of the zone's
    own translucent fill. Expanded mode is unchanged — indentation + a text label already make
    the grouping obvious there. See the Frontend Design Guideline's nav-rail section.
  @dependencies: vue, @phosphor-icons/vue, vue-sonner, shadcn-vue (button, tooltip, separator,
    avatar, sonner)
  @version: 6.1.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-29
-->
<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { PhFolderOpen, PhFolders, PhGauge, PhGearSix, PhGithubLogo, PhInfo, PhPassword, PhScroll, PhStack, PhSignOut, PhUsers } from '@phosphor-icons/vue';
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
import ProjectGeneralSettingsView from './views/ProjectGeneralSettingsView.vue';
import ProjectAccessManagementView from './views/ProjectAccessManagementView.vue';
import ProjectGitSyncView from './views/ProjectGitSyncView.vue';
import EnvironmentsView from './views/EnvironmentsView.vue';
import AuditLogsView from './views/AuditLogsView.vue';
import SystemSettingsView from './views/SystemSettingsView.vue';
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
const isAdmin = computed(() => !!auth.session?.user?.isAdmin);

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

// `/projects/:id/settings` (bare, no suffix) is General settings — kept as the default settings
// path so pre-existing links/bookmarks to plain `/settings` still resolve; the other two settings
// views live at `/settings/access` (Sharing + API access keys, merged into one) and
// `/settings/git-sync`. The project-scoped nav-rail section further down (sidebarProject/
// canManageSidebarProject) is what links between all three now — see the 2026-08-29 journal entry.
const projectMatch = computed(() => path.value.match(/^\/projects\/([^/?]+)(\/settings(?:\/([a-z-]+))?)?/));
const projectId = computed(() => (projectMatch.value ? decodeURIComponent(projectMatch.value[1]) : null));
const settingsSection = computed(() => {
  if (!projectMatch.value?.[2]) return null;
  return projectMatch.value[3] || 'general';
});

// Feeds the project-scoped nav-rail section below (name + role for the "back to project"/settings
// sub-items) — a small dedicated fetch, not shared with the views themselves, matching this app's
// existing no-shared-store convention (see the 2026-08-29 journal entry above).
const sidebarProject = ref(null);
watch(
  projectId,
  async (id) => {
    sidebarProject.value = null;
    if (!id) return;
    try {
      sidebarProject.value = await api.getProject(id);
    } catch {
      sidebarProject.value = null;
    }
  },
  { immediate: true }
);
const canManageSidebarProject = computed(() => ['owner', 'admin', 'editor'].includes(sidebarProject.value?.my_role));

const currentView = computed(() => {
  if (projectId.value) {
    switch (settingsSection.value) {
      case 'general':
        return ProjectGeneralSettingsView;
      case 'access':
        return ProjectAccessManagementView;
      case 'git-sync':
        return ProjectGitSyncView;
      default:
        return ProjectView;
    }
  }
  if (path.value.startsWith('/projects')) return HomeView;
  if (path.value.startsWith('/environments')) return EnvironmentsView;
  if (path.value.startsWith('/audit-logs')) return AuditLogsView;
  if (path.value.startsWith('/system-settings')) return SystemSettingsView;
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
        class="sticky bottom-0 z-30 flex items-center justify-end gap-2 px-4 py-2.5 border-t border-border bg-card/70 backdrop-blur-xl backdrop-saturate-150"
      >
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

          <!-- Project-scoped section: only rendered while inside a Project (ProjectView or one of
               its three settings pages) — a "back to project" entry, then General settings/Access
               Management/Git-Sync as indented sub-items, gated the same owner/admin/editor tier the
               old header buttons used. See the 2026-08-29 journal entry above. -->
          <template v-if="projectId">
            <Separator class="my-1" />

            <Tooltip v-if="!sidebarExpanded">
              <TooltipTrigger as-child>
                <Button
                  variant="ghost"
                  size="icon"
                  class="w-full"
                  :class="!settingsSection ? 'bg-accent text-accent-foreground' : ''"
                  @click="navigate(`/projects/${projectId}`)"
                >
                  <PhFolderOpen :size="18" weight="bold" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="left">{{ sidebarProject?.name || 'Back to project' }}</TooltipContent>
            </Tooltip>
            <Button
              v-else
              variant="ghost"
              class="w-full justify-start gap-2.5"
              :class="!settingsSection ? 'bg-accent text-accent-foreground' : ''"
              @click="navigate(`/projects/${projectId}`)"
            >
              <PhFolderOpen :size="18" weight="bold" /> <span class="truncate">{{ sidebarProject?.name || 'Back to project' }}</span>
            </Button>

            <template v-if="canManageSidebarProject">
              <!-- Collapsed: one bordered "zone" wraps all three sub-items, rather than each icon
                   carrying its own individual highlight — a single continuous shape reads as one
                   group at a glance; individually-outlined icons with gaps between them didn't. See
                   the Frontend Design Guideline's nav-rail section. -->
              <div v-if="!sidebarExpanded" class="w-full flex flex-col gap-1 p-1 rounded-lg bg-primary/10 border border-primary/30">
                <Tooltip>
                  <TooltipTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon"
                      class="w-full"
                      :class="settingsSection === 'general' ? 'bg-accent text-accent-foreground' : ''"
                      @click="navigate(`/projects/${projectId}/settings`)"
                    >
                      <PhGearSix :size="16" weight="bold" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="left">General settings</TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon"
                      class="w-full"
                      :class="settingsSection === 'access' ? 'bg-accent text-accent-foreground' : ''"
                      @click="navigate(`/projects/${projectId}/settings/access`)"
                    >
                      <PhUsers :size="16" weight="bold" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="left">Access Management</TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon"
                      class="w-full"
                      :class="settingsSection === 'git-sync' ? 'bg-accent text-accent-foreground' : ''"
                      @click="navigate(`/projects/${projectId}/settings/git-sync`)"
                    >
                      <PhGithubLogo :size="16" weight="bold" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="left">Git-Sync</TooltipContent>
                </Tooltip>
              </div>

              <template v-else>
                <Button
                  variant="ghost"
                  size="sm"
                  class="w-full justify-start gap-2.5 pl-8"
                  :class="settingsSection === 'general' ? 'bg-accent text-accent-foreground' : ''"
                  @click="navigate(`/projects/${projectId}/settings`)"
                >
                  <PhGearSix :size="16" weight="bold" /> General settings
                </Button>

                <Button
                  variant="ghost"
                  size="sm"
                  class="w-full justify-start gap-2.5 pl-8"
                  :class="settingsSection === 'access' ? 'bg-accent text-accent-foreground' : ''"
                  @click="navigate(`/projects/${projectId}/settings/access`)"
                >
                  <PhUsers :size="16" weight="bold" /> Access Management
                </Button>

                <Button
                  variant="ghost"
                  size="sm"
                  class="w-full justify-start gap-2.5 pl-8"
                  :class="settingsSection === 'git-sync' ? 'bg-accent text-accent-foreground' : ''"
                  @click="navigate(`/projects/${projectId}/settings/git-sync`)"
                >
                  <PhGithubLogo :size="16" weight="bold" /> Git-Sync
                </Button>
              </template>
            </template>

            <Separator class="my-1" />
          </template>

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

          <template v-if="isAdmin">
            <Tooltip v-if="!sidebarExpanded">
              <TooltipTrigger as-child>
                <Button
                  variant="ghost"
                  size="icon"
                  class="w-full"
                  :class="path.startsWith('/system-settings') ? 'bg-accent text-accent-foreground' : ''"
                  @click="navigate('/system-settings')"
                >
                  <PhGearSix :size="18" weight="bold" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="left">System Settings</TooltipContent>
            </Tooltip>
            <Button
              v-else
              variant="ghost"
              class="w-full justify-start gap-2.5"
              :class="path.startsWith('/system-settings') ? 'bg-accent text-accent-foreground' : ''"
              @click="navigate('/system-settings')"
            >
              <PhGearSix :size="18" weight="bold" /> System Settings
            </Button>
          </template>
        </nav>

        <Separator />

        <div class="flex flex-col gap-1 px-2.5 py-3">
          <Tooltip v-if="!sidebarExpanded">
            <TooltipTrigger as-child>
              <Button variant="default" size="icon" class="w-full" @click="showPasswordGenerator = true">
                <PhPassword :size="18" weight="bold" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="left">Generate password</TooltipContent>
          </Tooltip>
          <Button
            v-else
            variant="default"
            class="w-full justify-start gap-2.5"
            @click="showPasswordGenerator = true"
          >
            <PhPassword :size="18" weight="bold" /> Generate password
          </Button>

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
