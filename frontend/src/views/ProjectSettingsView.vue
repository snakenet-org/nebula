<!--
  @ai-purpose: Project settings — rename/description, sharing (Viewer/Editor roles), REST API access
    keys, and the danger-zone delete. Owner+admin only — the backend enforces this independently on
    every call (can_manage_sharing/can_manage_access_keys/can_delete), this view only hides controls.
  @ai-context: A newly created access key's raw token is shown exactly once, right after creation
    (createdToken), in a copyable box with an explicit "you won't see this again" warning — mirrors
    the one-time-reveal convention every sibling app uses for API tokens (Gravity/Singularity's M2M
    tokens, Satellite's deployment tokens). Built from shadcn-vue Card/Table/Select/Badge/
    AlertDialog/Input/Label/Button.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, table, select, badge,
    alert-dialog, input, label, button, skeleton)
  @version: 3.0.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-06
-->
<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { PhArrowLeft, PhArrowsClockwise, PhCheck, PhCopy, PhGithubLogo, PhKey, PhLinkBreak, PhTrash, PhUserPlus } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';

const props = defineProps({ projectId: { type: String, required: true } });
const emit = defineEmits(['navigate']);

const project = ref(null);
const shares = ref([]);
const accessKeys = ref([]);
const loading = ref(true);

const canManage = computed(() => ['owner', 'admin'].includes(project.value?.my_role));

async function loadAll() {
  loading.value = true;
  try {
    project.value = await api.getProject(props.projectId);
    if (['owner', 'admin'].includes(project.value.my_role)) {
      [shares.value, accessKeys.value] = await Promise.all([
        api.listShares(props.projectId),
        api.listAccessKeys(props.projectId),
      ]);
    }
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

// ── Sharing ───────────────────────────────────────────────────────────────
const shareForm = ref({ username: '', role: 'viewer' });
const sharing = ref(false);
async function addShare() {
  if (!shareForm.value.username.trim()) return;
  sharing.value = true;
  try {
    const share = await api.createShare(props.projectId, {
      username: shareForm.value.username.trim(),
      role: shareForm.value.role,
    });
    shares.value.push(share);
    shareForm.value = { username: '', role: 'viewer' };
  } catch (e) {
    toast.error(e.message);
  } finally {
    sharing.value = false;
  }
}
async function changeRole(share, role) {
  try {
    const updated = await api.updateShare(props.projectId, share.user_id, { role });
    const idx = shares.value.findIndex((s) => s.user_id === share.user_id);
    if (idx !== -1) shares.value[idx] = updated;
  } catch (e) {
    toast.error(e.message);
  }
}
const confirmRevokeShare = ref(null);
async function revokeShare() {
  if (!confirmRevokeShare.value) return;
  try {
    await api.revokeShare(props.projectId, confirmRevokeShare.value.user_id);
    shares.value = shares.value.filter((s) => s.user_id !== confirmRevokeShare.value.user_id);
    confirmRevokeShare.value = null;
    toast.success('Access revoked.');
  } catch (e) {
    toast.error(e.message);
  }
}

// ── Access keys ───────────────────────────────────────────────────────────
const newKeyName = ref('');
const creatingKey = ref(false);
const createdToken = ref(null);
const copied = ref(false);
async function createAccessKey() {
  if (!newKeyName.value.trim()) return;
  creatingKey.value = true;
  try {
    const created = await api.createAccessKey(props.projectId, { name: newKeyName.value.trim() });
    accessKeys.value.unshift(created);
    createdToken.value = created.token;
    newKeyName.value = '';
  } catch (e) {
    toast.error(e.message);
  } finally {
    creatingKey.value = false;
  }
}
function copyToken() {
  navigator.clipboard?.writeText(createdToken.value);
  copied.value = true;
  setTimeout(() => (copied.value = false), 1500);
}
const confirmRevokeKey = ref(null);
async function revokeAccessKey() {
  if (!confirmRevokeKey.value) return;
  try {
    await api.revokeAccessKey(props.projectId, confirmRevokeKey.value.id);
    const idx = accessKeys.value.findIndex((k) => k.id === confirmRevokeKey.value.id);
    if (idx !== -1) accessKeys.value[idx] = { ...accessKeys.value[idx], revoked: true };
    confirmRevokeKey.value = null;
    toast.success('Access key revoked.');
  } catch (e) {
    toast.error(e.message);
  }
}

// ── GitHub sync ───────────────────────────────────────────────────────────
const githubForm = ref({ repo_url: '', pat: '' });
const savingGithub = ref(false);
watch(
  project,
  (p) => {
    if (!p) return;
    githubForm.value = { repo_url: p.github_repo_url || '', pat: '' };
  },
  { immediate: true }
);
async function saveGithubConfig() {
  savingGithub.value = true;
  try {
    project.value = await api.updateProjectGithub(props.projectId, {
      repo_url: githubForm.value.repo_url.trim() || null,
      pat: githubForm.value.pat.trim() || null,
    });
    githubForm.value.pat = '';
    toast.success('GitHub configuration saved.');
  } catch (e) {
    toast.error(e.message);
  } finally {
    savingGithub.value = false;
  }
}

const syncing = ref(false);
const confirmSync = ref(false);
async function syncNow() {
  confirmSync.value = false;
  syncing.value = true;
  try {
    const result = await api.syncProjectGithub(props.projectId);
    if (result.failures.length) {
      toast.error(
        `Synced ${result.secrets_synced} secret(s), ${result.variables_synced} variable(s) — ${result.failures.length} failure(s). See server logs.`
      );
    } else {
      toast.success(
        `Synced ${result.secrets_synced} secret(s) and ${result.variables_synced} variable(s) across ${result.environments_synced} environment(s).`
      );
    }
  } catch (e) {
    toast.error(e.message);
  } finally {
    syncing.value = false;
  }
}

const confirmDisconnectGithub = ref(false);
async function disconnectGithub() {
  try {
    project.value = await api.disconnectProjectGithub(props.projectId).then(() => api.getProject(props.projectId));
    githubForm.value = { repo_url: '', pat: '' };
    confirmDisconnectGithub.value = false;
    toast.success('GitHub disconnected.');
  } catch (e) {
    toast.error(e.message);
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
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 w-full">
    <Button variant="link" class="px-0 mb-4 text-sm" @click="emit('navigate', `/projects/${projectId}`)">
      <PhArrowLeft :size="14" weight="bold" /> Back to project
    </Button>

    <div v-if="loading" class="space-y-4">
      <Skeleton class="h-8 w-64" />
      <Skeleton class="h-40 rounded-xl" />
    </div>

    <template v-else-if="project && canManage">
      <h1 class="text-2xl font-bold mb-6">{{ project.name }} — Settings</h1>

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

      <Card class="mb-6">
        <CardContent>
          <h2 class="font-semibold mb-3">Sharing</h2>
          <form @submit.prevent="addShare" class="flex gap-2 mb-4">
            <Input class="flex-1" v-model="shareForm.username" placeholder="username" />
            <Select v-model="shareForm.role">
              <SelectTrigger class="w-32"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="viewer">Viewer</SelectItem>
                <SelectItem value="editor">Editor</SelectItem>
              </SelectContent>
            </Select>
            <Button type="submit" :disabled="sharing">
              <PhUserPlus :size="16" weight="bold" /> Share
            </Button>
          </form>

          <p v-if="!shares.length" class="text-muted-foreground text-sm">Not shared with anyone yet.</p>
          <Table v-else>
            <TableBody>
              <TableRow v-for="share in shares" :key="share.user_id">
                <TableCell>{{ share.username }}</TableCell>
                <TableCell class="text-muted-foreground">{{ share.email }}</TableCell>
                <TableCell>
                  <Select :model-value="share.role" @update:model-value="(role) => changeRole(share, role)">
                    <SelectTrigger size="sm" class="w-28"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="viewer">Viewer</SelectItem>
                      <SelectItem value="editor">Editor</SelectItem>
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell class="text-right">
                  <Button variant="ghost" size="icon-sm" title="Revoke access" @click="confirmRevokeShare = share">
                    <PhTrash :size="14" weight="bold" />
                  </Button>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card class="mb-6">
        <CardContent>
          <h2 class="font-semibold mb-3">API access keys</h2>
          <p class="text-muted-foreground text-sm mb-4">
            Grants REST access to every secret in this project via
            <code class="font-mono">GET /api/v1/vault/secret</code>, authenticated with this key as a
            bearer token plus the site-wide <code class="font-mono">X-Nebula-Token</code>.
          </p>

          <Card v-if="createdToken" class="mb-4 bg-primary/10 border-primary/30">
            <CardContent class="p-3">
              <p class="text-sm font-semibold mb-2">Copy this token now — it won't be shown again.</p>
              <div class="flex items-center gap-2">
                <code class="font-mono text-xs flex-1 break-all">{{ createdToken }}</code>
                <Button variant="ghost" size="icon-sm" @click="copyToken">
                  <PhCheck v-if="copied" :size="14" weight="bold" />
                  <PhCopy v-else :size="14" weight="bold" />
                </Button>
              </div>
            </CardContent>
          </Card>

          <form @submit.prevent="createAccessKey" class="flex gap-2 mb-4">
            <Input class="flex-1" v-model="newKeyName" placeholder="key name, e.g. 'deploy-bot'" />
            <Button type="submit" :disabled="creatingKey">
              <PhKey :size="16" weight="bold" /> Generate
            </Button>
          </form>

          <p v-if="!accessKeys.length" class="text-muted-foreground text-sm">No access keys yet.</p>
          <Table v-else>
            <TableBody>
              <TableRow v-for="k in accessKeys" :key="k.id">
                <TableCell>{{ k.name }}</TableCell>
                <TableCell class="font-mono text-muted-foreground">{{ k.token_prefix }}…</TableCell>
                <TableCell>
                  <Badge :variant="k.revoked ? 'destructive' : 'success'">{{ k.revoked ? 'revoked' : 'active' }}</Badge>
                </TableCell>
                <TableCell class="text-right">
                  <Button v-if="!k.revoked" variant="ghost" size="icon-sm" title="Revoke" @click="confirmRevokeKey = k">
                    <PhTrash :size="14" weight="bold" />
                  </Button>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card class="mb-6">
        <CardContent>
          <h2 class="font-semibold mb-3 flex items-center gap-2"><PhGithubLogo :size="18" weight="bold" /> GitHub sync</h2>
          <p class="text-muted-foreground text-sm mb-4">
            Push every key/value in this project into a GitHub repository as per-Environment secrets
            and variables (via the <code class="font-mono">gh</code> CLI) — each Nebula Environment
            becomes a same-named GitHub Environment.
            <Badge :variant="project.github_connected ? 'success' : 'outline'" class="ml-1">
              {{ project.github_connected ? 'connected' : 'not connected' }}
            </Badge>
          </p>

          <form @submit.prevent="saveGithubConfig" class="grid sm:grid-cols-2 gap-3 mb-4">
            <div class="space-y-1.5">
              <Label for="gh-repo-url">Repository URL</Label>
              <Input id="gh-repo-url" v-model="githubForm.repo_url" placeholder="https://github.com/owner/repo" />
            </div>
            <div class="space-y-1.5">
              <Label for="gh-pat">Personal access token</Label>
              <Input
                id="gh-pat"
                v-model="githubForm.pat"
                type="password"
                :placeholder="project.github_connected ? 'Leave blank to keep the current token' : 'ghp_…'"
              />
            </div>
            <div class="sm:col-span-2 flex gap-2 justify-end">
              <Button
                v-if="project.github_connected"
                type="button"
                variant="outline"
                @click="confirmDisconnectGithub = true"
              >
                <PhLinkBreak :size="16" weight="bold" /> Disconnect
              </Button>
              <Button type="submit" :disabled="savingGithub">Save</Button>
              <Button
                type="button"
                variant="secondary"
                :disabled="!project.github_connected || syncing"
                @click="confirmSync = true"
              >
                <PhArrowsClockwise :size="16" weight="bold" /> Sync now
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card class="border-destructive/30">
        <CardContent>
          <h2 class="font-semibold mb-2 text-destructive">Danger zone</h2>
          <p class="text-muted-foreground text-sm mb-4">
            Deleting a project permanently removes every environment, key, value, share, and access key.
          </p>
          <Button variant="destructive" @click="confirmDeleteProject = true">Delete this project</Button>
        </CardContent>
      </Card>
    </template>

    <Card v-else>
      <CardContent class="text-muted-foreground text-sm">You don't have permission to manage this project.</CardContent>
    </Card>

    <AlertDialog :open="!!confirmRevokeShare" @update:open="(v) => !v && (confirmRevokeShare = null)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Revoke access?</AlertDialogTitle>
          <AlertDialogDescription>'{{ confirmRevokeShare?.username }}' will no longer be able to see this project.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="revokeShare">Revoke</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <AlertDialog :open="!!confirmRevokeKey" @update:open="(v) => !v && (confirmRevokeKey = null)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Revoke this access key?</AlertDialogTitle>
          <AlertDialogDescription>Any integration using '{{ confirmRevokeKey?.name }}' will immediately lose API access.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="revokeAccessKey">Revoke</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <AlertDialog :open="confirmSync" @update:open="(v) => !v && (confirmSync = false)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Sync to GitHub?</AlertDialogTitle>
          <AlertDialogDescription>
            Every key with a value set will be written to '{{ project?.github_repo_url }}' as a
            per-Environment secret or variable. This overwrites any existing value of the same name
            there.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction @click="syncNow">Sync now</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <AlertDialog :open="confirmDisconnectGithub" @update:open="(v) => !v && (confirmDisconnectGithub = false)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Disconnect GitHub?</AlertDialogTitle>
          <AlertDialogDescription>Removes the stored repository URL and access token. Nothing already synced to GitHub is affected.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="disconnectGithub">Disconnect</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

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
  </div>
</template>
