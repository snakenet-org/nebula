<!--
  @ai-purpose: Project access management — who can see/edit this project (Viewer/Editor sharing)
    AND the REST API access keys used against `GET /api/v1/vault/secret`, on one page. One of three
    views split out of the former monolithic ProjectSettingsView.vue (2026-08-27) — the other two
    are ProjectGeneralSettingsView/ProjectGitSyncView. Originally split into two SEPARATE views
    (ProjectSharingView/ProjectAccessKeysView, same day) but merged back together per a same-day
    follow-up product ask — sharing and access keys are both "who/what can access this project"
    concerns and share the exact same permission tier, so a single "Access Management" page reads
    more naturally than two near-identical pages one click apart. `canManage` is owner/admin/editor,
    matching the backend's `can_manage_sharing`/`can_manage_access_keys` gates (both widened to
    include a shared EDITOR per the 2026-08-17 permission-matrix rework — still the same tier for
    both, which is what makes merging them onto one page correct rather than just convenient).
  @ai-context: A newly created access key's raw token is shown exactly once, right after creation
    (createdToken), in a copyable box with an explicit "you won't see this again" warning — mirrors
    the one-time-reveal convention every sibling app uses for API tokens.
  @ai-rules:
    - `confirmRevokeShare`/`confirmRevokeKey` must each live in a ref that is ONLY ever set on open
      and cleared by our own code — never nulled by their dialog's own `@update:open` handler.
      AlertDialogAction auto-closes unconditionally on click (reka-ui's DialogClose has no
      event.preventDefault escape hatch) and can run before this component's own @click listener on
      the same click event; if target-data and open-state shared one ref, that race could null the
      target before the action handler ever read it, silently no-opping the whole action with zero
      API call — this is the same class of bug the former ProjectSettingsView.vue's 2026-08-07 fix
      addressed for revokeAccessKey.
  @ai-context2: 2026-08-29: dropped the page's own `ProjectSettingsNav` sub-nav — "back to
    project"/General settings/Access Management/Git-Sync now live as a project-scoped section of
    App.vue's own nav rail instead (see that file's same-day journal entry).
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, input, select, table,
    badge, button, alert-dialog, skeleton)
  @version: 1.1.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-29
-->
<script setup>
import { computed, onMounted, ref } from 'vue';
import { PhCheck, PhCopy, PhKey, PhTrash, PhUserPlus } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';

const props = defineProps({ projectId: { type: String, required: true } });

const project = ref(null);
const shares = ref([]);
const accessKeys = ref([]);
const loading = ref(true);

const canManage = computed(() => ['owner', 'admin', 'editor'].includes(project.value?.my_role));

async function loadAll() {
  loading.value = true;
  try {
    project.value = await api.getProject(props.projectId);
    if (['owner', 'admin', 'editor'].includes(project.value.my_role)) {
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
// See this file's own header comment for why target/open-state are split across two refs.
const confirmRevokeShare = ref(null);
const revokeShareDialogOpen = ref(false);
function openRevokeShareDialog(share) {
  confirmRevokeShare.value = share;
  revokeShareDialogOpen.value = true;
}
async function revokeShare() {
  const target = confirmRevokeShare.value;
  if (!target) return;
  try {
    await api.revokeShare(props.projectId, target.user_id);
    shares.value = shares.value.filter((s) => s.user_id !== target.user_id);
    toast.success('Access revoked.');
  } catch (e) {
    toast.error(e.message);
  } finally {
    revokeShareDialogOpen.value = false;
  }
}

// ── API access keys ─────────────────────────────────────────────────────
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
// See this file's own header comment for why target/open-state are split across two refs.
const confirmRevokeKey = ref(null);
const revokeKeyDialogOpen = ref(false);
function openRevokeKeyDialog(key) {
  confirmRevokeKey.value = key;
  revokeKeyDialogOpen.value = true;
}
async function revokeAccessKey() {
  const target = confirmRevokeKey.value;
  if (!target) return;
  try {
    await api.revokeAccessKey(props.projectId, target.id);
    const idx = accessKeys.value.findIndex((k) => k.id === target.id);
    if (idx !== -1) accessKeys.value[idx] = { ...accessKeys.value[idx], revoked: true };
    toast.success('Access key revoked.');
  } catch (e) {
    toast.error(e.message);
  } finally {
    revokeKeyDialogOpen.value = false;
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
      <h1 class="text-2xl font-bold mb-6">{{ project.name }} — Access Management</h1>

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
            <TableHeader>
              <TableRow>
                <TableHead>Username</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead class="w-16 text-right">Revoke</TableHead>
              </TableRow>
            </TableHeader>
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
                  <Button variant="destructive" size="icon-xs" title="Revoke access" @click="openRevokeShareDialog(share)">
                    <PhTrash :size="13" weight="bold" />
                  </Button>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <h2 class="font-semibold mb-3">API access keys</h2>
          <p class="text-muted-foreground text-sm mb-4">
            Grants REST access to every secret in this project via
            <code class="font-mono">GET /api/v1/vault/secret?environment=&key=</code>,
            authenticated with this key as a bearer token plus the site-wide
            <code class="font-mono">X-Nebula-Token</code>. Both names must match exactly
            (case-insensitively) and may only contain letters, numbers, hyphens, and underscores.
          </p>

          <Card v-if="createdToken" class="mb-4 bg-primary/10 border-primary/30">
            <CardContent class="p-3">
              <p class="text-sm font-semibold mb-2">Copy this token now — it won't be shown again.</p>
              <div class="flex items-center gap-2">
                <code class="font-mono text-xs flex-1 break-all">{{ createdToken }}</code>
                <Button variant="ghost" size="icon" title="Copy" @click="copyToken">
                  <PhCheck v-if="copied" :size="16" weight="bold" />
                  <PhCopy v-else :size="16" weight="bold" />
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
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Token</TableHead>
                <TableHead>Status</TableHead>
                <TableHead class="w-16 text-right">Revoke</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="k in accessKeys" :key="k.id">
                <TableCell>{{ k.name }}</TableCell>
                <TableCell class="font-mono text-muted-foreground">{{ k.token_prefix }}…</TableCell>
                <TableCell>
                  <Badge :variant="k.revoked ? 'destructive' : 'success'">{{ k.revoked ? 'revoked' : 'active' }}</Badge>
                </TableCell>
                <TableCell class="text-right">
                  <Button v-if="!k.revoked" variant="destructive" size="icon-xs" title="Revoke" @click="openRevokeKeyDialog(k)">
                    <PhTrash :size="13" weight="bold" />
                  </Button>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </template>

    <Card v-else-if="project">
      <CardContent class="text-muted-foreground text-sm">You don't have permission to manage this project.</CardContent>
    </Card>

    <AlertDialog :open="revokeShareDialogOpen" @update:open="(v) => (revokeShareDialogOpen = v)">
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

    <AlertDialog :open="revokeKeyDialogOpen" @update:open="(v) => (revokeKeyDialogOpen = v)">
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
  </div>
</template>
