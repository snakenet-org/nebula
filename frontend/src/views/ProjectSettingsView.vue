<!--
  @ai-purpose: Project settings — rename/description, sharing (Viewer/Editor roles), REST API access
    keys, GitHub sync targets, and the danger-zone delete. Owner+admin only — the backend enforces
    this independently on every call (can_manage_sharing/can_manage_access_keys/can_manage_github/
    can_delete), this view only hides controls.
  @ai-context: A newly created access key's raw token is shown exactly once, right after creation
    (createdToken), in a copyable box with an explicit "you won't see this again" warning — mirrors
    the one-time-reveal convention every sibling app uses for API tokens (Gravity/Singularity's M2M
    tokens, Satellite's deployment tokens). Since the 2026-08-06 multi-repo GitHub sync redesign, a
    Project can have MANY simultaneous sync targets (`githubTargets`, a Table, not a single form) —
    each is pushed to automatically by the backend on every secret/variable value change, not just
    when "Sync now" is clicked here; this view only adds/edits/removes/toggles targets and can
    trigger an on-demand sync (either one target or all of them at once). A target's PAT is
    write-only, same one-shot-reveal-never shape as the access-key token: the edit dialog's PAT
    field is always blank, and a blank submit leaves the stored token untouched. Built from
    shadcn-vue Card/Table/Select/Badge/AlertDialog/Dialog/Switch/Tabs/Input/Label/Button. The GitHub
    sync table's enabled/paused control is a Switch (not a Checkbox, unlike the bulk-upload row-select
    Checkboxes on ProjectView.vue) — a deliberate distinction: this toggles a persistent, already-
    live setting on save (`toggleTargetEnabled` calls the API immediately on flip), which reads more
    naturally as an on/off switch than a selection checkbox.
    Since 2026-08-08, the Add/Edit repository Dialog's PAT field is a `patMode` Tabs toggle
    ("Custom token" / "Reference a secret", same Tabs pattern as PasswordGeneratorDialog.vue) instead
    of a single Input. "Reference a secret" is a two-step Project→Secret Select pair
    (`patSourceProjects`/`patSourceKeys`, lazily loaded on first use of that tab — most targets never
    need it) — the Project list is filtered client-side to `my_role` owner/admin only, since
    referencing a secret you can't reveal yourself would let this Project's sync silently consume a
    credential you never had visibility into (the backend independently re-enforces this via
    can_reveal, this filter is purely so the picker never even offers an option the API would 403).
    The Secret list is further filtered to `is_set` keys only (an unset key has nothing to
    reference). Editing an existing reference-mode target shows its current `pat_source_label`
    read-only and leaves both Selects unset — same "blank/omitted = unchanged" convention the custom
    PAT field already had, now symmetric across both modes: picking nothing in either tab always
    means "don't touch the stored PAT config."
  @ai-rules:
    - Every AlertDialog's per-item target (confirmRevokeShare/confirmRevokeKey/confirmDeleteTarget)
      must live in a ref that is ONLY ever set on open and cleared by our own code — never nulled by
      the dialog's own `@update:open` handler. AlertDialogAction auto-closes unconditionally on
      click (reka-ui's DialogClose has no event.preventDefault escape hatch) and can run before this
      component's own @click listener on the same click event; if target-data and open-state shared
      one ref, that race could null the target before the action handler ever read it, silently
      no-opping the whole action with zero API call — this is exactly what happened to
      revokeAccessKey before this file's 2026-08-07 fix (see the code comment above
      confirmRevokeShare's declaration).
    2026-08-08: the three row-level destructive icon buttons (revoke share, revoke access key, remove
    GitHub target) recolored from `ghost` to the existing `destructive` Button variant, same pass as
    ProjectView.vue/EnvironmentsView.vue — see ProjectView.vue's header for the fuller rationale
    (destructive actions should read as a warning color, not look identical to a neutral edit/sync
    action). No behavior change.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, table, select, badge,
    alert-dialog, dialog, switch, tabs, input, label, button, skeleton)
  @version: 4.4.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-08
-->
<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { PhArrowLeft, PhArrowsClockwise, PhCheck, PhCopy, PhGithubLogo, PhKey, PhPencilSimple, PhPlus, PhTrash, PhUserPlus } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';

const props = defineProps({ projectId: { type: String, required: true } });
const emit = defineEmits(['navigate']);

const project = ref(null);
const shares = ref([]);
const accessKeys = ref([]);
const githubTargets = ref([]);
const loading = ref(true);

const canManage = computed(() => ['owner', 'admin'].includes(project.value?.my_role));

async function loadAll() {
  loading.value = true;
  try {
    project.value = await api.getProject(props.projectId);
    if (['owner', 'admin'].includes(project.value.my_role)) {
      [shares.value, accessKeys.value, githubTargets.value] = await Promise.all([
        api.listShares(props.projectId),
        api.listAccessKeys(props.projectId),
        api.listGithubTargets(props.projectId),
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
// `confirmRevokeShare` holds ONLY the target — never cleared by the dialog's own close machinery,
// only by openRevokeShareDialog/on success. See ProjectView.vue's confirmDeleteKey comment for why:
// AlertDialogAction auto-closes unconditionally on click (no event.preventDefault escape hatch in
// reka-ui's DialogClose), which can race ahead of this component's own @click handler on the same
// click event — if the target and the open-state shared one ref, the target could already be null
// by the time the handler read it, silently no-opping the whole action.
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
// See confirmRevokeShare's comment above — same target/open-state split, same reason.
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

// ── GitHub sync (many simultaneous targets) ─────────────────────────────────
function summarizeResult(r) {
  if (r.error) return `${r.name}: ${r.error}`;
  let msg = `${r.name}: ${r.secrets_synced} secret(s), ${r.variables_synced} variable(s) across ${r.environments_synced} environment(s)`;
  if (r.failures.length) msg += ` — ${r.failures.length} failure(s)`;
  return msg;
}
function toastResults(results) {
  const failed = results.filter((r) => !r.success);
  if (!results.length) {
    toast.error('No enabled GitHub sync targets to sync.');
  } else if (failed.length) {
    toast.error(`${failed.length}/${results.length} target(s) failed. ${failed.map(summarizeResult).join(' | ')}`);
  } else {
    toast.success(results.map(summarizeResult).join(' | '));
  }
}

const targetDialogOpen = ref(false);
const editingTarget = ref(null); // null = creating a new target
const targetForm = ref({ name: '', repo_url: '', pat: '', pat_source_project_id: null, pat_source_key_id: null });
const patMode = ref('custom'); // 'custom' | 'reference'
const savingTarget = ref(false);

// ── PAT "reference a secret" picker ─────────────────────────────────────────
// Lazily loaded on first use — most targets stick with a custom token and never need this.
const patSourceProjects = ref([]);
const loadingPatSourceProjects = ref(false);
const patSourceKeys = ref([]);
const loadingPatSourceKeys = ref(false);
async function ensurePatSourceProjectsLoaded() {
  if (patSourceProjects.value.length || loadingPatSourceProjects.value) return;
  loadingPatSourceProjects.value = true;
  try {
    const all = await api.listProjects();
    // Only projects the caller can REVEAL (owner/admin) — the backend independently re-enforces
    // this via can_reveal, this filter just keeps the picker from ever offering an option the API
    // would reject.
    patSourceProjects.value = all.filter((p) => ['owner', 'admin'].includes(p.my_role));
  } catch (e) {
    toast.error(e.message);
  } finally {
    loadingPatSourceProjects.value = false;
  }
}
async function loadPatSourceKeys(projectId) {
  if (!projectId) {
    patSourceKeys.value = [];
    return;
  }
  loadingPatSourceKeys.value = true;
  try {
    const keys = await api.listSecrets(projectId);
    patSourceKeys.value = keys.filter((k) => k.is_set);
  } catch (e) {
    toast.error(e.message);
    patSourceKeys.value = [];
  } finally {
    loadingPatSourceKeys.value = false;
  }
}
watch(
  () => targetForm.value.pat_source_project_id,
  (projectId) => {
    targetForm.value.pat_source_key_id = null;
    loadPatSourceKeys(projectId);
  }
);

function resetTargetForm() {
  targetForm.value = { name: '', repo_url: '', pat: '', pat_source_project_id: null, pat_source_key_id: null };
  patSourceKeys.value = [];
}
function openCreateTarget() {
  editingTarget.value = null;
  patMode.value = 'custom';
  resetTargetForm();
  targetDialogOpen.value = true;
  ensurePatSourceProjectsLoaded();
}
function openEditTarget(target) {
  editingTarget.value = target;
  patMode.value = target.pat_source_key_id ? 'reference' : 'custom';
  resetTargetForm();
  targetForm.value.name = target.name;
  targetForm.value.repo_url = target.repo_url;
  targetDialogOpen.value = true;
  ensurePatSourceProjectsLoaded();
}
async function saveTarget() {
  savingTarget.value = true;
  try {
    const payload = {
      name: targetForm.value.name.trim() || null,
      repo_url: targetForm.value.repo_url.trim(),
    };
    if (patMode.value === 'reference') {
      if (targetForm.value.pat_source_key_id) {
        payload.pat_source_key_id = targetForm.value.pat_source_key_id;
      } else if (!editingTarget.value) {
        toast.error('Pick a project and a secret to reference.');
        return;
      }
    } else {
      const pat = targetForm.value.pat.trim();
      if (pat) {
        payload.pat = pat;
      } else if (!editingTarget.value) {
        toast.error('Enter a personal access token.');
        return;
      }
    }
    if (editingTarget.value) {
      const updated = await api.updateGithubTarget(props.projectId, editingTarget.value.id, payload);
      const idx = githubTargets.value.findIndex((t) => t.id === updated.id);
      if (idx !== -1) githubTargets.value[idx] = updated;
      toast.success('GitHub sync target updated.');
    } else {
      const created = await api.createGithubTarget(props.projectId, payload);
      githubTargets.value.push(created);
      toast.success('GitHub sync target added.');
    }
    targetDialogOpen.value = false;
  } catch (e) {
    toast.error(e.message);
  } finally {
    savingTarget.value = false;
  }
}
async function toggleTargetEnabled(target, enabled) {
  try {
    const updated = await api.updateGithubTarget(props.projectId, target.id, { enabled });
    const idx = githubTargets.value.findIndex((t) => t.id === updated.id);
    if (idx !== -1) githubTargets.value[idx] = updated;
  } catch (e) {
    toast.error(e.message);
  }
}
// See confirmRevokeShare's comment above — same target/open-state split, same reason.
const confirmDeleteTarget = ref(null);
const deleteTargetDialogOpen = ref(false);
function openDeleteTargetDialog(target) {
  confirmDeleteTarget.value = target;
  deleteTargetDialogOpen.value = true;
}
async function deleteTarget() {
  const target = confirmDeleteTarget.value;
  if (!target) return;
  try {
    await api.deleteGithubTarget(props.projectId, target.id);
    githubTargets.value = githubTargets.value.filter((t) => t.id !== target.id);
    toast.success('GitHub sync target removed.');
  } catch (e) {
    toast.error(e.message);
  } finally {
    deleteTargetDialogOpen.value = false;
  }
}

async function refreshGithubTargets() {
  githubTargets.value = await api.listGithubTargets(props.projectId);
}

const syncingTargetId = ref(null);
async function syncTargetNow(target) {
  syncingTargetId.value = target.id;
  try {
    const result = await api.syncGithubTarget(props.projectId, target.id);
    toastResults([result]);
  } catch (e) {
    toast.error(e.message);
  } finally {
    syncingTargetId.value = null;
    await refreshGithubTargets();
  }
}

const syncingAll = ref(false);
const confirmSyncAll = ref(false);
async function syncAllNow() {
  confirmSyncAll.value = false;
  syncingAll.value = true;
  try {
    const results = await api.syncGithubAll(props.projectId);
    toastResults(results);
  } catch (e) {
    toast.error(e.message);
  } finally {
    syncingAll.value = false;
    await refreshGithubTargets();
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
                  <Button variant="destructive" size="icon-sm" title="Revoke access" @click="openRevokeShareDialog(share)">
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
                  <Button v-if="!k.revoked" variant="destructive" size="icon-sm" title="Revoke" @click="openRevokeKeyDialog(k)">
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
          <div class="flex items-center justify-between mb-3">
            <h2 class="font-semibold flex items-center gap-2"><PhGithubLogo :size="18" weight="bold" /> GitHub sync</h2>
            <div class="flex gap-2">
              <Button type="button" size="sm" variant="outline" @click="openCreateTarget">
                <PhPlus :size="14" weight="bold" /> Add repository
              </Button>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                :disabled="!githubTargets.some((t) => t.enabled) || syncingAll"
                @click="confirmSyncAll = true"
              >
                <PhArrowsClockwise :size="14" weight="bold" /> Sync all now
              </Button>
            </div>
          </div>
          <p class="text-muted-foreground text-sm mb-4">
            Every enabled repository below is pushed automatically, every time a key's value
            changes — not just when you click "Sync now". Each repository gets every key/value in
            this project as per-Environment secrets and variables (via the
            <code class="font-mono">gh</code> CLI); each Nebula Environment becomes a same-named
            GitHub Environment.
          </p>

          <p v-if="!githubTargets.length" class="text-muted-foreground text-sm">No repositories linked yet.</p>
          <Table v-else>
            <TableBody>
              <TableRow v-for="t in githubTargets" :key="t.id">
                <TableCell>
                  <div class="font-medium">{{ t.name }}</div>
                  <div class="text-muted-foreground text-xs font-mono">{{ t.repo_url }}</div>
                  <div class="text-muted-foreground text-xs mt-0.5 flex items-center gap-1">
                    <PhKey :size="11" weight="bold" />
                    <span v-if="t.pat_source_key_id">{{ t.pat_source_label || 'Referenced secret (no access)' }}</span>
                    <span v-else>Custom token</span>
                  </div>
                </TableCell>
                <TableCell>
                  <div class="flex items-center gap-2">
                    <Switch :model-value="t.enabled" @update:model-value="(v) => toggleTargetEnabled(t, v)" />
                    <span class="text-muted-foreground text-xs">{{ t.enabled ? 'enabled' : 'paused' }}</span>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge v-if="t.last_sync_success === true" variant="success">synced</Badge>
                  <Badge v-else-if="t.last_sync_success === false" variant="destructive">failed</Badge>
                  <Badge v-else variant="outline">never synced</Badge>
                  <div v-if="t.last_synced_at" class="text-muted-foreground text-xs mt-1">
                    {{ new Date(t.last_synced_at).toLocaleString() }}
                  </div>
                </TableCell>
                <TableCell class="text-right whitespace-nowrap">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    title="Sync this repository now"
                    :disabled="syncingTargetId === t.id"
                    @click="syncTargetNow(t)"
                  >
                    <PhArrowsClockwise :size="14" weight="bold" />
                  </Button>
                  <Button variant="ghost" size="icon-sm" title="Edit" @click="openEditTarget(t)">
                    <PhPencilSimple :size="14" weight="bold" />
                  </Button>
                  <Button variant="destructive" size="icon-sm" title="Remove" @click="openDeleteTargetDialog(t)">
                    <PhTrash :size="14" weight="bold" />
                  </Button>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
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

    <AlertDialog :open="confirmSyncAll" @update:open="(v) => !v && (confirmSyncAll = false)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Sync all repositories now?</AlertDialogTitle>
          <AlertDialogDescription>
            Every key with a value set will be written to every ENABLED repository below as a
            per-Environment secret or variable. This overwrites any existing value of the same name
            there.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction @click="syncAllNow">Sync now</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <AlertDialog :open="deleteTargetDialogOpen" @update:open="(v) => (deleteTargetDialogOpen = v)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove this repository?</AlertDialogTitle>
          <AlertDialogDescription>
            '{{ confirmDeleteTarget?.name }}' will no longer receive automatic or manual syncs.
            Nothing already synced to it is affected.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="deleteTarget">Remove</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <Dialog :open="targetDialogOpen" @update:open="(v) => (targetDialogOpen = v)">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ editingTarget ? 'Edit GitHub repository' : 'Add GitHub repository' }}</DialogTitle>
          <DialogDescription>
            {{ editingTarget ? 'Repositories can be added, edited, and removed independently — every enabled one stays in sync.' : 'Every key with a value set will be pushed here on every value change.' }}
          </DialogDescription>
        </DialogHeader>
        <form @submit.prevent="saveTarget" class="space-y-3">
          <div class="space-y-1.5">
            <Label for="target-name">Name (optional)</Label>
            <Input id="target-name" v-model="targetForm.name" placeholder="e.g. production" />
          </div>
          <div class="space-y-1.5">
            <Label for="target-repo-url">Repository URL</Label>
            <Input id="target-repo-url" v-model="targetForm.repo_url" placeholder="https://github.com/owner/repo" required />
          </div>
          <div class="space-y-1.5">
            <Label>Personal access token</Label>
            <Tabs v-model="patMode">
              <TabsList class="w-full">
                <TabsTrigger value="custom" class="flex-1">Custom token</TabsTrigger>
                <TabsTrigger value="reference" class="flex-1">Reference a secret</TabsTrigger>
              </TabsList>

              <TabsContent value="custom" class="space-y-1.5 pt-2">
                <Input
                  id="target-pat"
                  v-model="targetForm.pat"
                  type="password"
                  :placeholder="editingTarget ? 'Leave blank to keep the current token' : 'ghp_…'"
                />
              </TabsContent>

              <TabsContent value="reference" class="space-y-3 pt-2">
                <p v-if="editingTarget?.pat_source_key_id" class="text-muted-foreground text-xs">
                  Currently referencing
                  <span class="font-medium text-foreground">{{ editingTarget.pat_source_label || 'a secret you no longer have access to' }}</span>.
                  Pick a project and secret below to change it, or leave both unset to keep it.
                </p>
                <div class="space-y-1.5">
                  <Label>Project</Label>
                  <Select v-model="targetForm.pat_source_project_id">
                    <SelectTrigger class="w-full"><SelectValue placeholder="Select a project…" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem v-for="p in patSourceProjects" :key="p.id" :value="p.id">{{ p.name }}</SelectItem>
                    </SelectContent>
                  </Select>
                  <p v-if="!loadingPatSourceProjects && !patSourceProjects.length" class="text-muted-foreground text-xs">
                    You need to own or administer a project to reference one of its secrets.
                  </p>
                </div>
                <div class="space-y-1.5">
                  <Label>Secret</Label>
                  <Select
                    v-model="targetForm.pat_source_key_id"
                    :disabled="!targetForm.pat_source_project_id || loadingPatSourceKeys"
                  >
                    <SelectTrigger class="w-full"><SelectValue placeholder="Select a secret…" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem v-for="k in patSourceKeys" :key="k.id" :value="k.id">{{ k.name }}</SelectItem>
                    </SelectContent>
                  </Select>
                  <p
                    v-if="targetForm.pat_source_project_id && !loadingPatSourceKeys && !patSourceKeys.length"
                    class="text-muted-foreground text-xs"
                  >
                    This project has no secrets with a value set yet.
                  </p>
                </div>
                <p class="text-muted-foreground text-xs">
                  The sync always uses this secret's CURRENT value — rotating it anywhere in the vault
                  updates this repository's token too, with nothing to re-save here.
                </p>
              </TabsContent>
            </Tabs>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" @click="targetDialogOpen = false">Cancel</Button>
            <Button type="submit" :disabled="savingTarget">{{ editingTarget ? 'Save' : 'Add repository' }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

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
