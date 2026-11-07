<!--
  @ai-purpose: Home — the logged-in caller's project list + create-project form.
  @ai-context: listProjects() already scopes to what the caller may see (owned + shared, or every
    project for an admin — see nebula.projects.list_projects) so this view does no server round-trip
    for filtering/search, both are client-side over that one response. my_role badge
    (owner/admin/editor/viewer) is rendered straight from the API response. "New project" is a modal
    Dialog (2026-08-12 — previously an inline toggled form under the header button; switched for
    consistency with every other "create" action in the app, which are all modals now).
    **2026-08-27**: added an All/Owned/Shared role-filter Tabs control next to the search Input — both
    together now span the page's full width (was a lone `max-w-sm` search bar). "Owned" is
    `my_role === 'owner'`; "Shared" is everything else (admin/editor/viewer) — i.e. a project the
    caller sees but did not themselves create, which is the plain-language meaning of "shared" from
    the caller's own point of view, admin's system-wide visibility included. Also reworked the project
    grid's visual language: each card gets a small deterministic "nebula hue" derived from its own id
    (`projectHue`, a cheap string hash % the app's 4 brand colors — cyan/magenta/gold/flare, the same
    tokens `style.css`/`components/ui/button` already use) so cards read as visually distinct from one
    another at a glance, subtly, via a blurred corner glow (opacity ~0.14, brightens slightly on
    hover), a hairline top gradient filament, and a tinted initial-letter avatar — no per-project data
    drives the color (there's no "project color" field), it's purely a stable presentational hash so
    the same project always gets the same hue across reloads.
    **2026-11-08**: a SecretKey always needs exactly one (global) Environment, so a Project is useless
    until at least one Environment exists — "New project" is disabled while `listEnvironments()`
    returns an empty list, and the no-projects empty state gains a hint + link to /environments.
    `environments` stays `null` until loaded (and on load failure), so the button is never disabled
    just because that one call failed — the backend doesn't require an Environment to create a Project.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, badge, button, input, label,
    dialog, skeleton, tabs)
  @version: 3.2.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-11-08
-->
<script setup>
import { computed, onMounted, ref } from 'vue';
import { PhFolderPlus, PhLockKey, PhStack, PhMagnifyingGlass, PhX } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import * as api from '../services/api';

const emit = defineEmits(['navigate']);

const projects = ref([]);
const loading = ref(true);
// null = not loaded yet (or failed) — only a confirmed-empty list disables "New project".
const environments = ref(null);
const noEnvironments = computed(() => Array.isArray(environments.value) && environments.value.length === 0);
const createDialogOpen = ref(false);
const creating = ref(false);
const form = ref({ name: '', description: '' });

// ── Filter + search ──────────────────────────────────────────────────────
// Both client-side only — listProjects() already returns the caller's full visible set in one call,
// so there's no reason to round-trip to the API for either.
const roleFilter = ref('all');
const ownedCount = computed(() => projects.value.filter((p) => p.my_role === 'owner').length);
const sharedCount = computed(() => projects.value.length - ownedCount.value);
const roleFiltered = computed(() => {
  if (roleFilter.value === 'owned') return projects.value.filter((p) => p.my_role === 'owner');
  if (roleFilter.value === 'shared') return projects.value.filter((p) => p.my_role !== 'owner');
  return projects.value;
});

const search = ref('');
const filteredProjects = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return roleFiltered.value;
  return roleFiltered.value.filter(
    (p) => p.name.toLowerCase().includes(q) || (p.description || '').toLowerCase().includes(q)
  );
});

const emptyMessage = computed(() => {
  if (search.value.trim()) return `No projects match "${search.value.trim()}".`;
  if (roleFilter.value === 'owned') return "You don't own any projects yet.";
  if (roleFilter.value === 'shared') return 'No projects have been shared with you yet.';
  return 'No projects match the current filter.';
});

async function load() {
  loading.value = true;
  try {
    const [projectList, envList] = await Promise.all([
      api.listProjects(),
      api.listEnvironments().catch(() => null),
    ]);
    projects.value = projectList;
    environments.value = envList;
  } catch (e) {
    toast.error(e.message);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

async function createProject() {
  if (!form.value.name.trim()) return;
  creating.value = true;
  try {
    const project = await api.createProject({
      name: form.value.name.trim(),
      description: form.value.description.trim() || null,
    });
    projects.value.push(project);
    form.value = { name: '', description: '' };
    createDialogOpen.value = false;
    toast.success('Project created.');
    emit('navigate', `/projects/${project.id}`);
  } catch (e) {
    toast.error(e.message);
  } finally {
    creating.value = false;
  }
}

const roleVariant = {
  owner: 'default',
  admin: 'accent',
  editor: 'success',
  viewer: 'warning',
};

// ── Per-project nebula hue ───────────────────────────────────────────────
// A cheap, stable hash of the project's own id, purely presentational — picks one of the app's 4
// brand tokens so cards read as visually distinct at a glance without inventing a real "color" field.
const NEBULA_HUE_VARS = ['--primary', '--magenta', '--gold', '--flare'];
function hashString(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}
function projectHue(p) {
  return `var(${NEBULA_HUE_VARS[hashString(p.id) % NEBULA_HUE_VARS.length]})`;
}
function initials(name) {
  return (name || '').trim().slice(0, 1).toUpperCase() || '?';
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 w-full">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold">Projects</h1>
        <p class="text-muted-foreground text-sm mt-1">
          Credentials, passwords, and variables, organized by project.
        </p>
      </div>
      <span :title="noEnvironments ? 'Create an environment first' : undefined">
        <Button :disabled="noEnvironments" @click="createDialogOpen = true">
          <PhFolderPlus :size="18" weight="bold" /> New project
        </Button>
      </span>
    </div>

    <div v-if="loading" class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <Skeleton v-for="i in 3" :key="i" class="h-32 rounded-xl" />
    </div>

    <Card v-else-if="!projects.length">
      <CardContent class="p-10 text-center">
        <PhLockKey :size="32" weight="bold" class="mx-auto mb-3 text-muted-foreground" />
        <p class="font-semibold">No projects yet</p>
        <p class="text-muted-foreground text-sm mt-1">Create your first project to start storing secrets.</p>
        <template v-if="noEnvironments">
          <p class="text-muted-foreground text-sm mt-3">
            Every key belongs to an environment, so you'll need to create your first environment
            (e.g. <span class="font-mono">production</span>) before you can create a project.
          </p>
          <Button variant="outline" class="mt-4" @click="emit('navigate', '/environments')">
            <PhStack :size="16" weight="bold" /> Create first environment
          </Button>
        </template>
      </CardContent>
    </Card>

    <template v-else>
      <div class="flex items-center gap-3 mb-4 w-full">
        <Tabs :model-value="roleFilter" @update:model-value="(v) => (roleFilter = v)" class="shrink-0">
          <TabsList>
            <TabsTrigger value="all">All <span class="text-muted-foreground">{{ projects.length }}</span></TabsTrigger>
            <TabsTrigger value="owned">Owned <span class="text-muted-foreground">{{ ownedCount }}</span></TabsTrigger>
            <TabsTrigger value="shared">Shared <span class="text-muted-foreground">{{ sharedCount }}</span></TabsTrigger>
          </TabsList>
        </Tabs>
        <div class="relative flex-1 min-w-0">
          <PhMagnifyingGlass :size="14" weight="bold" class="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input v-model="search" placeholder="Search projects…" class="pl-7 pr-7" />
          <button
            v-if="search"
            type="button"
            title="Clear search"
            class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            @click="search = ''"
          >
            <PhX :size="14" weight="bold" />
          </button>
        </div>
      </div>

      <Card v-if="!filteredProjects.length">
        <CardContent class="p-10 text-center text-muted-foreground text-sm">
          {{ emptyMessage }}
        </CardContent>
      </Card>

      <div v-else class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <Card
          v-for="p in filteredProjects"
          :key="p.id"
          class="group relative text-left cursor-pointer transition hover:-translate-y-0.5 hover:border-foreground/20"
          @click="emit('navigate', `/projects/${p.id}`)"
        >
          <div
            class="pointer-events-none absolute -top-12 -right-12 h-36 w-36 rounded-full opacity-[0.14] blur-3xl transition-opacity duration-300 group-hover:opacity-25"
            :style="{ background: projectHue(p) }"
          />
          <div
            class="pointer-events-none absolute inset-x-0 top-0 h-px opacity-50"
            :style="{ background: `linear-gradient(90deg, transparent, ${projectHue(p)}, transparent)` }"
          />
          <CardContent class="relative">
            <div class="flex items-start gap-3 mb-2">
              <div
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold"
                :style="{ background: `color-mix(in oklab, ${projectHue(p)} 18%, transparent)`, color: projectHue(p) }"
              >
                {{ initials(p.name) }}
              </div>
              <div class="min-w-0 flex-1 pt-1">
                <h2 class="font-semibold truncate">{{ p.name }}</h2>
              </div>
              <Badge :variant="roleVariant[p.my_role] || 'default'">{{ p.my_role }}</Badge>
            </div>
            <p v-if="p.description" class="text-muted-foreground text-sm mb-3 line-clamp-2">{{ p.description }}</p>
            <div class="text-muted-foreground text-xs flex gap-3">
              <span>{{ p.environment_count }} environment{{ p.environment_count === 1 ? '' : 's' }}</span>
              <span>{{ p.secret_key_count }} key{{ p.secret_key_count === 1 ? '' : 's' }}</span>
            </div>
            <div class="text-muted-foreground text-xs mt-2">by {{ p.owner_name }}</div>
          </CardContent>
        </Card>
      </div>
    </template>

    <Dialog :open="createDialogOpen" @update:open="(v) => (createDialogOpen = v)">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
        </DialogHeader>
        <form @submit.prevent="createProject" class="space-y-3">
          <div class="space-y-1.5">
            <Label for="new-project-name">Name</Label>
            <Input id="new-project-name" v-model="form.name" placeholder="Project name" required />
          </div>
          <div class="space-y-1.5">
            <Label for="new-project-description">Description</Label>
            <Input id="new-project-description" v-model="form.description" placeholder="Description (optional)" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" @click="createDialogOpen = false">Cancel</Button>
            <Button type="submit" :disabled="creating">Create</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </div>
</template>
