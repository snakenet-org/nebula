<!--
  @ai-purpose: Home — the logged-in caller's project list + create-project form.
  @ai-context: listProjects() already scopes to what the caller may see (owned + shared, or every
    project for an admin — see nebula.projects.list_projects) so this view does no client-side
    filtering. my_role badge (owner/admin/editor/viewer) is rendered straight from the API response.
    "New project" is an inline toggled form, not a modal — creating a Project is the lowest-friction
    action in the app and doesn't need an overlay. Built from shadcn-vue Card/Badge/Button/Input/
    Label/Skeleton.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, badge, button, input, label,
    skeleton)
  @version: 2.0.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-06
-->
<script setup>
import { onMounted, ref } from 'vue';
import { PhFolderPlus, PhLockKey } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import * as api from '../services/api';

const emit = defineEmits(['navigate']);

const projects = ref([]);
const loading = ref(true);
const showForm = ref(false);
const creating = ref(false);
const form = ref({ name: '', description: '' });

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
    showForm.value = false;
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
          Credentials, passwords, and environment variables, organized by project.
        </p>
      </div>
      <Button @click="showForm = !showForm">
        <PhFolderPlus :size="18" weight="bold" /> New project
      </Button>
    </div>

    <Card v-if="showForm" class="mb-6">
      <CardContent>
        <form @submit.prevent="createProject" class="grid sm:grid-cols-2 gap-3">
          <div class="space-y-1.5">
            <Label for="new-project-name">Name</Label>
            <Input id="new-project-name" v-model="form.name" placeholder="Project name" required />
          </div>
          <div class="space-y-1.5">
            <Label for="new-project-description">Description</Label>
            <Input id="new-project-description" v-model="form.description" placeholder="Description (optional)" />
          </div>
          <div class="sm:col-span-2 flex gap-2 justify-end">
            <Button type="button" variant="outline" @click="showForm = false">Cancel</Button>
            <Button type="submit" :disabled="creating">Create</Button>
          </div>
        </form>
      </CardContent>
    </Card>

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

    <div v-else class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <Card
        v-for="p in projects"
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
  </div>
</template>
