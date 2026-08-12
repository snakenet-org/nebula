<!--
  @ai-purpose: Home — the logged-in caller's project list + create-project form.
  @ai-context: listProjects() already scopes to what the caller may see (owned + shared, or every
    project for an admin — see nebula.projects.list_projects) so this view does no client-side
    filtering. my_role badge (owner/admin/editor/viewer) is rendered straight from the API response.
    "New project" is a modal Dialog (2026-08-12 — previously an inline toggled form under the header
    button; switched for consistency with every other "create" action in the app, which are all
    modals now). Built from shadcn-vue Card/Badge/Button/Input/Label/Dialog/Skeleton.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, badge, button, input, label,
    dialog, skeleton)
  @version: 3.0.1
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-12
-->
<script setup>
import { computed, onMounted, ref } from 'vue';
import { PhFolderPlus, PhLockKey, PhMagnifyingGlass } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import * as api from '../services/api';

const emit = defineEmits(['navigate']);

const projects = ref([]);
const loading = ref(true);
const createDialogOpen = ref(false);
const creating = ref(false);
const form = ref({ name: '', description: '' });

// ── Search ────────────────────────────────────────────────────────────────
// Client-side only — listProjects() already returns the caller's full visible set in one call, so
// there's no reason to round-trip to the API on every keystroke.
const search = ref('');
const filteredProjects = computed(() => {
  const q = search.value.trim().toLowerCase();
  if (!q) return projects.value;
  return projects.value.filter(
    (p) => p.name.toLowerCase().includes(q) || (p.description || '').toLowerCase().includes(q)
  );
});

async function load() {
  loading.value = true;
  try {
    projects.value = await api.listProjects();
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
      <Button @click="createDialogOpen = true">
        <PhFolderPlus :size="18" weight="bold" /> New project
      </Button>
    </div>

    <div v-if="loading" class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <Skeleton v-for="i in 3" :key="i" class="h-32 rounded-xl" />
    </div>

    <Card v-else-if="!projects.length">
      <CardContent class="p-10 text-center">
        <PhLockKey :size="32" weight="bold" class="mx-auto mb-3 text-muted-foreground" />
        <p class="font-semibold">No projects yet</p>
        <p class="text-muted-foreground text-sm mt-1">Create your first project to start storing secrets.</p>
      </CardContent>
    </Card>

    <template v-else>
      <div class="relative mb-4 max-w-sm">
        <PhMagnifyingGlass :size="16" weight="bold" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="search" placeholder="Search projects…" class="pl-9" />
      </div>

      <Card v-if="!filteredProjects.length">
        <CardContent class="p-10 text-center text-muted-foreground text-sm">
          No projects match "{{ search }}".
        </CardContent>
      </Card>

      <div v-else class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <Card
          v-for="p in filteredProjects"
          :key="p.id"
          class="text-left cursor-pointer transition hover:border-primary/40"
          @click="emit('navigate', `/projects/${p.id}`)"
        >
          <CardContent>
            <div class="flex items-start justify-between gap-2 mb-2">
              <h2 class="font-semibold">{{ p.name }}</h2>
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
