<!--
  @ai-purpose: Global Environments management — list/create/edit/delete the shared environment
    taxonomy (e.g. "production", "staging") every Project's secret keys link into.
  @ai-context: Environments are GLOBAL since the 2026-08-06 redesign (nebula.environments), not
    scoped to any one Project — list/create/update are available to any authenticated caller,
    delete is admin-only (the backend 403s a non-admin; this view also just hides the delete
    action for a non-admin, mirroring ProjectSettingsView's own client-side-hide-only convention).
    secret_key_count is shown per row as a delete-safety hint — the backend 409s
    (EnvironmentInUseError) if a still-linked Environment is deleted anyway; since 2026-08-12
    (GitHub #6) that 409's detail names exactly which Project(s) are still using it
    (nebula.environments.list_projects_using), surfaced verbatim via the existing
    `toast.error(e.message)` catch — no new frontend plumbing needed, api.js already forwards the
    backend's `detail` string as the thrown Error's message.
    2026-08-08: the row's Delete button recolored from `ghost` to the existing `destructive` Button
    variant — see ProjectView.vue's header for the fuller rationale.
    2026-08-12 (GitHub #6): name/description on both the create form and the edit dialog now strip
    any pasted `\r`/`\n` on write (computed get/set wrapping a raw ref, same pattern
    ProjectView.vue's Edit-key Name field already established) — name's charset was already
    line-break-free server-side (nebula.naming), but description had none, and the edit dialog's
    Description field used to be a multi-line Textarea where Enter genuinely inserted a real
    newline, not just a pasted one. That Textarea is now a plain single-line Input, matching what
    the create form's Description field already was, so line breaks are structurally impossible to
    type, not just stripped after the fact. The backend (nebula.models.environment) also now strips
    `\r`/`\n` from `description` independently, so an API caller bypassing this UI can't reintroduce
    one either.
    2026-08-12 (later same day, GitHub #7): the table's Description cell is now truncated to 250
    characters with a trailing "…" (`truncate()` below) — the full text is still available via the
    cell's `title` attribute on hover, and editing a long description is unaffected (openEdit loads
    the untruncated `env.description` into the edit dialog).
    2026-08-12 (later same day, modals): "New environment" is now a modal Dialog (createDialogOpen)
    instead of an inline toggled Card next to the header button — same shape as the pre-existing Edit
    dialog just below it in this file, so create/edit are now visually consistent instead of one being
    inline and the other a modal.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, table, badge, button,
    input, label, dialog, alert-dialog, skeleton)
  @version: 2.2.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-12
-->
<script setup>
import { computed, onMounted, ref } from 'vue';
import { PhCircleNotch, PhStack, PhPencilSimple, PhPlus, PhTrash } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { stripLineBreaks, truncate } from '../lib/utils';
import { useAuth } from '../composables/useAuth';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
// Name/description are wrapped in computed get/set pairs that strip any pasted \r/\n on every
// write (see lib/utils.stripLineBreaks) — name's charset was already line-break-free server-side
// (nebula.naming), but description had no such restriction until GitHub #6.
const createDialogOpen = ref(false);
const creating = ref(false);
const form = ref({ name: '', description: '' });
const formName = computed({
  get: () => form.value.name,
  set: (v) => { form.value.name = stripLineBreaks(v); },
});
const formDescription = computed({
  get: () => form.value.description,
  set: (v) => { form.value.description = stripLineBreaks(v); },
});
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
    createDialogOpen.value = false;
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
const editFormName = computed({
  get: () => editForm.value.name,
  set: (v) => { editForm.value.name = stripLineBreaks(v); },
});
const editFormDescription = computed({
  get: () => editForm.value.description,
  set: (v) => { editForm.value.description = stripLineBreaks(v); },
});
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
// Target and open-state live in separate refs (same split as ProjectView.vue's confirmDeleteKey):
// AlertDialogAction auto-closes on click, so a combined ref could be nulled before the handler
// reads it. `deletingIds` drives the row's Delete-button spinner while the request is in flight.
const confirmDelete = ref(null);
const deleteDialogOpen = ref(false);
const deletingIds = ref(new Set());
function openDeleteDialog(env) {
  confirmDelete.value = env;
  deleteDialogOpen.value = true;
}
async function deleteEnvironment() {
  const target = confirmDelete.value;
  if (!target || deletingIds.value.has(target.id)) return;
  deletingIds.value.add(target.id);
  deleteDialogOpen.value = false;
  try {
    await api.deleteEnvironment(target.id);
    environments.value = environments.value.filter((e) => e.id !== target.id);
    toast.success('Environment deleted.');
  } catch (e) {
    toast.error(e.message);
  } finally {
    deletingIds.value.delete(target.id);
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
      <Button @click="createDialogOpen = true">
        <PhPlus :size="18" weight="bold" /> New environment
      </Button>
    </div>

    <div v-if="loading" class="space-y-3">
      <Skeleton class="h-12 rounded-xl" v-for="i in 3" :key="i" />
    </div>

    <Card v-else-if="!environments.length">
      <CardContent class="p-10 text-center">
        <PhStack :size="32" weight="bold" class="mx-auto mb-3 text-muted-foreground" />
        <p class="font-semibold">No environments yet</p>
        <p class="text-muted-foreground text-sm mt-1">Create one to start adding keys to projects.</p>
      </CardContent>
    </Card>

    <Card v-else class="py-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Description</TableHead>
            <TableHead>Keys</TableHead>
            <TableHead class="w-20 text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="env in environments" :key="env.id">
            <TableCell class="font-semibold">{{ env.name }}</TableCell>
            <TableCell class="text-muted-foreground" :title="env.description || ''">
              {{ truncate(env.description, 250) || '—' }}
            </TableCell>
            <TableCell><Badge variant="outline">{{ env.secret_key_count }}</Badge></TableCell>
            <TableCell class="text-right whitespace-nowrap">
              <Button variant="ghost" size="icon-xs" title="Edit" @click="openEdit(env)">
                <PhPencilSimple :size="13" weight="bold" />
              </Button>
              <Button
                v-if="isAdmin"
                variant="destructive"
                size="icon-xs"
                title="Delete"
                :disabled="deletingIds.has(env.id)"
                @click="openDeleteDialog(env)"
              >
                <PhCircleNotch v-if="deletingIds.has(env.id)" :size="13" weight="bold" class="animate-spin" />
                <PhTrash v-else :size="13" weight="bold" />
              </Button>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </Card>

    <Dialog :open="createDialogOpen" @update:open="(v) => (createDialogOpen = v)">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New environment</DialogTitle>
        </DialogHeader>
        <form @submit.prevent="createEnvironment" class="space-y-3">
          <div class="space-y-1.5">
            <Label for="new-env-name">Name</Label>
            <Input id="new-env-name" v-model="formName" placeholder="e.g. production" required />
          </div>
          <div class="space-y-1.5">
            <Label for="new-env-description">Description</Label>
            <Input id="new-env-description" v-model="formDescription" placeholder="Description (optional)" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" @click="createDialogOpen = false">Cancel</Button>
            <Button type="submit" :disabled="creating">Create</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    <Dialog :open="!!editing" @update:open="(v) => !v && (editing = null)">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit environment</DialogTitle>
        </DialogHeader>
        <form @submit.prevent="saveEdit" class="space-y-3">
          <div class="space-y-1.5">
            <Label for="edit-env-name">Name</Label>
            <Input id="edit-env-name" v-model="editFormName" required />
          </div>
          <div class="space-y-1.5">
            <Label for="edit-env-description">Description</Label>
            <Input id="edit-env-description" v-model="editFormDescription" placeholder="Description (optional)" />
          </div>
          <DialogFooter>
            <Button type="submit" :disabled="savingEdit">Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    <AlertDialog :open="deleteDialogOpen" @update:open="(v) => (deleteDialogOpen = v)">
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
