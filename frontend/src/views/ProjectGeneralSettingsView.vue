<!--
  @ai-purpose: Project general settings — rename/description and the danger-zone transfer/delete.
    One of three views split out of the former monolithic ProjectSettingsView.vue (2026-08-27, see
    that day's journal entry) — the other two are ProjectAccessManagementView/ProjectGitSyncView.
    `canManage` (Details card) is owner/admin/editor, matching the backend's `can_edit` gate on
    `PATCH /project/{id}`; `canDeleteOrTransfer` (Danger zone card) stays owner/admin only, separate
    from `canManage`, since an EDITOR can rename/describe a project but still cannot transfer or
    delete it.
  @ai-context: Transfer ownership and Delete both redirect to /projects on success, since a
    non-admin owner immediately loses can_view on the Project the moment ownership moves away (and a
    deleted project obviously no longer exists to view). `transferUsername` needs no target/open-state
    ref split (unlike the per-row AlertDialogs in ProjectAccessManagementView/ProjectGitSyncView) —
    it's the typed text itself, not an item pulled from a list, so nothing can null it out from under
    the confirm dialog's own close machinery.
  @ai-context2: 2026-08-29: dropped the page's own `ProjectSettingsNav` sub-nav — "back to
    project"/General settings/Access Management/Git-Sync now live as a project-scoped section of
    App.vue's own nav rail instead (see that file's same-day journal entry).
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, input, label, button,
    separator, alert-dialog, skeleton)
  @version: 1.1.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-29
-->
<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { PhArrowsLeftRight } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';

const props = defineProps({ projectId: { type: String, required: true } });
const emit = defineEmits(['navigate']);

const project = ref(null);
const loading = ref(true);

const canManage = computed(() => ['owner', 'admin', 'editor'].includes(project.value?.my_role));
const canDeleteOrTransfer = computed(() => ['owner', 'admin'].includes(project.value?.my_role));

async function loadAll() {
  loading.value = true;
  try {
    project.value = await api.getProject(props.projectId);
  } catch (e) {
    toast.error(e.message);
  } finally {
    loading.value = false;
  }
}
onMounted(loadAll);

// ── Project details ─────────────────────────────────────────────────────
const editName = ref('');
const editDescription = ref('');
const savingDetails = ref(false);
watch(
  project,
  (p) => {
    if (!p) return;
    editName.value = p.name;
    editDescription.value = p.description || '';
  },
  { immediate: true }
);
async function saveDetails() {
  savingDetails.value = true;
  try {
    project.value = await api.updateProject(props.projectId, {
      name: editName.value,
      description: editDescription.value || null,
    });
    toast.success('Project updated.');
  } catch (e) {
    toast.error(e.message);
  } finally {
    savingDetails.value = false;
  }
}

// ── Danger zone ─────────────────────────────────────────────────────────
const confirmDeleteProject = ref(false);
async function deleteProject() {
  try {
    await api.deleteProject(props.projectId);
    confirmDeleteProject.value = false;
    toast.success('Project deleted.');
    emit('navigate', '/projects');
  } catch (e) {
    toast.error(e.message);
  }
}

// Transfer ownership: the backend independently re-checks can_transfer_ownership (owner/admin) and
// 404s on an unknown username / 409s on transferring to the current owner — this view only gates
// the button on a non-empty field.
const transferUsername = ref('');
const transferring = ref(false);
const confirmTransferProject = ref(false);
function openTransferDialog() {
  if (!transferUsername.value.trim()) return;
  confirmTransferProject.value = true;
}
async function transferProject() {
  transferring.value = true;
  try {
    await api.transferProject(props.projectId, { username: transferUsername.value.trim() });
    confirmTransferProject.value = false;
    toast.success(`Ownership transferred to '${transferUsername.value.trim()}'.`);
    emit('navigate', '/projects');
  } catch (e) {
    toast.error(e.message);
  } finally {
    transferring.value = false;
  }
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 w-full">
    <div v-if="loading" class="space-y-4">
      <Skeleton class="h-8 w-64" />
      <Skeleton class="h-40 rounded-xl" />
    </div>

    <template v-else-if="project && canManage">
      <h1 class="text-2xl font-bold mb-6">{{ project.name }} — General settings</h1>

      <Card class="mb-6">
        <CardContent>
          <h2 class="font-semibold mb-3">Details</h2>
          <form @submit.prevent="saveDetails" class="grid sm:grid-cols-2 gap-3">
            <div class="space-y-1.5">
              <Label for="settings-name">Name</Label>
              <Input id="settings-name" v-model="editName" placeholder="Project name" required />
            </div>
            <div class="space-y-1.5">
              <Label for="settings-description">Description</Label>
              <Input id="settings-description" v-model="editDescription" placeholder="Description" />
            </div>
            <div class="sm:col-span-2 flex justify-end">
              <Button type="submit" :disabled="savingDetails">Save</Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card v-if="canDeleteOrTransfer" class="border-destructive/30">
        <CardContent>
          <h2 class="font-semibold mb-2 text-destructive">Danger zone</h2>

          <div class="mb-6">
            <h3 class="font-medium text-sm mb-1">Transfer ownership</h3>
            <p class="text-muted-foreground text-sm mb-3">
              Hand this project to another existing user. They become the owner with full access
              (reveal, sharing, access keys, GitHub sync, delete). If they were previously a shared
              Viewer/Editor, that share is removed since owner status already covers it.
            </p>
            <form @submit.prevent="openTransferDialog" class="flex gap-2">
              <Input class="flex-1 max-w-xs" v-model="transferUsername" placeholder="username" />
              <Button type="submit" variant="outline" :disabled="!transferUsername.trim() || transferring">
                <PhArrowsLeftRight :size="16" weight="bold" /> Transfer
              </Button>
            </form>
          </div>

          <Separator class="mb-6" />

          <h3 class="font-medium text-sm mb-1 text-destructive">Delete this project</h3>
          <p class="text-muted-foreground text-sm mb-4">
            Deleting a project permanently removes every environment, key, value, share, and access key.
          </p>
          <Button variant="destructive" @click="confirmDeleteProject = true">Delete this project</Button>
        </CardContent>
      </Card>
    </template>

    <Card v-else-if="project">
      <CardContent class="text-muted-foreground text-sm">You don't have permission to manage this project.</CardContent>
    </Card>

    <AlertDialog :open="confirmDeleteProject" @update:open="(v) => !v && (confirmDeleteProject = false)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this project?</AlertDialogTitle>
          <AlertDialogDescription>This permanently deletes every environment, key, value, share, and access key. This cannot be undone.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="deleteProject">Delete project</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <AlertDialog :open="confirmTransferProject" @update:open="(v) => !v && (confirmTransferProject = false)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Transfer ownership to '{{ transferUsername.trim() }}'?</AlertDialogTitle>
          <AlertDialogDescription>
            '{{ transferUsername.trim() }}' becomes the owner of '{{ project?.name }}', with full
            access to every secret and setting. This takes effect immediately.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="warning" @click="transferProject">Transfer</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
