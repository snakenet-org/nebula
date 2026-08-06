<!--
  @ai-purpose: Global Environments management — list/create/edit/delete the shared environment
    taxonomy (e.g. "production", "staging") every Project's secret keys link into.
  @ai-context: Environments are GLOBAL since the 2026-08-06 redesign (nebular.environments), not
    scoped to any one Project — list/create/update are available to any authenticated caller,
    delete is admin-only (the backend 403s a non-admin; this view also just hides the delete
    action for a non-admin, mirroring ProjectSettingsView's own client-side-hide-only convention).
    secret_key_count is shown per row as a delete-safety hint — the backend 409s
    (EnvironmentInUseError) if a still-linked Environment is deleted anyway.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, table, badge, button,
    input, label, textarea, dialog, alert-dialog, skeleton)
  @version: 1.0.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-06
-->
<script setup>
import { computed, onMounted, ref } from 'vue';
import { PhStack, PhPencilSimple, PhPlus, PhTrash } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { useAuth } from '../composables/useAuth';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';

const { state: auth } = useAuth();
const isAdmin = computed(() => !!auth.session?.user?.isAdmin);

const environments = ref([]);
const loading = ref(true);

async function load() {
  loading.value = true;
  try {
    environments.value = await api.listEnvironments();
  } catch (e) {
    toast.error(e.message);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

// ── Create ────────────────────────────────────────────────────────────────
const showForm = ref(false);
const creating = ref(false);
const form = ref({ name: '', description: '' });
async function createEnvironment() {
  if (!form.value.name.trim()) return;
  creating.value = true;
  try {
    const env = await api.createEnvironment({
      name: form.value.name.trim(),
      description: form.value.description.trim() || null,
    });
    environments.value.push(env);
    environments.value.sort((a, b) => a.name.localeCompare(b.name));
    form.value = { name: '', description: '' };
    showForm.value = false;
    toast.success('Environment created.');
  } catch (e) {
    toast.error(e.message);
  } finally {
    creating.value = false;
  }
}

// ── Edit ──────────────────────────────────────────────────────────────────
const editing = ref(null); // Environment being edited
const editForm = ref({ name: '', description: '' });
const savingEdit = ref(false);
function openEdit(env) {
  editing.value = env;
  editForm.value = { name: env.name, description: env.description || '' };
}
async function saveEdit() {
  if (!editing.value) return;
  savingEdit.value = true;
  try {
    const updated = await api.updateEnvironment(editing.value.id, {
      name: editForm.value.name.trim(),
      description: editForm.value.description.trim() || null,
    });
    const idx = environments.value.findIndex((e) => e.id === updated.id);
    if (idx !== -1) environments.value[idx] = updated;
    editing.value = null;
    toast.success('Environment updated.');
  } catch (e) {
    toast.error(e.message);
  } finally {
    savingEdit.value = false;
  }
}

// ── Delete ────────────────────────────────────────────────────────────────
const confirmDelete = ref(null);
async function deleteEnvironment() {
  if (!confirmDelete.value) return;
  try {
    await api.deleteEnvironment(confirmDelete.value.id);
    environments.value = environments.value.filter((e) => e.id !== confirmDelete.value.id);
    confirmDelete.value = null;
    toast.success('Environment deleted.');
  } catch (e) {
    toast.error(e.message);
  }
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 w-full">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold flex items-center gap-2"><PhStack :size="22" weight="bold" /> Environments</h1>
        <p class="text-muted-foreground text-sm mt-1">
          A shared taxonomy of environments (production, staging, …). Every key in every project links
          to exactly one.
        </p>
      </div>
      <Button @click="showForm = !showForm">
        <PhPlus :size="18" weight="bold" /> New environment
      </Button>
    </div>

    <Card v-if="showForm" class="mb-6">
      <CardContent>
        <form @submit.prevent="createEnvironment" class="grid sm:grid-cols-2 gap-3">
          <div class="space-y-1.5">
            <Label for="new-env-name">Name</Label>
            <Input id="new-env-name" v-model="form.name" placeholder="e.g. production" required />
          </div>
          <div class="space-y-1.5">
            <Label for="new-env-description">Description</Label>
            <Input id="new-env-description" v-model="form.description" placeholder="Description (optional)" />
          </div>
          <div class="sm:col-span-2 flex gap-2 justify-end">
            <Button type="button" variant="outline" @click="showForm = false">Cancel</Button>
            <Button type="submit" :disabled="creating">Create</Button>
          </div>
        </form>
      </CardContent>
    </Card>

    <div v-if="loading" class="space-y-3">
      <Skeleton class="h-12 rounded-xl" v-for="i in 3" :key="i" />
    </div>

    <Card v-else-if="!environments.length">
      <CardContent class="p-10 text-center text-muted-foreground text-sm">
        No environments yet — create one to start adding keys to projects.
      </CardContent>
    </Card>

    <Card v-else class="py-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Description</TableHead>
            <TableHead>Keys</TableHead>
            <TableHead class="w-20"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="env in environments" :key="env.id">
            <TableCell class="font-semibold">{{ env.name }}</TableCell>
            <TableCell class="text-muted-foreground">{{ env.description || '—' }}</TableCell>
            <TableCell><Badge variant="outline">{{ env.secret_key_count }}</Badge></TableCell>
            <TableCell class="text-right whitespace-nowrap">
              <Button variant="ghost" size="icon-xs" title="Edit" @click="openEdit(env)">
                <PhPencilSimple :size="13" weight="bold" />
              </Button>
              <Button
                v-if="isAdmin"
                variant="ghost"
                size="icon-xs"
                title="Delete"
                @click="confirmDelete = env"
              >
                <PhTrash :size="13" weight="bold" />
              </Button>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </Card>

    <Dialog :open="!!editing" @update:open="(v) => !v && (editing = null)">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit environment</DialogTitle>
        </DialogHeader>
        <form @submit.prevent="saveEdit" class="space-y-3">
          <div class="space-y-1.5">
            <Label for="edit-env-name">Name</Label>
            <Input id="edit-env-name" v-model="editForm.name" required />
          </div>
          <div class="space-y-1.5">
            <Label for="edit-env-description">Description</Label>
            <Textarea id="edit-env-description" v-model="editForm.description" rows="3" />
          </div>
          <DialogFooter>
            <Button type="submit" :disabled="savingEdit">Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    <AlertDialog :open="!!confirmDelete" @update:open="(v) => !v && (confirmDelete = null)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this environment?</AlertDialogTitle>
          <AlertDialogDescription>
            '{{ confirmDelete?.name }}' will be permanently removed. This only succeeds if no key in any
            project still links to it.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="deleteEnvironment">Delete</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
