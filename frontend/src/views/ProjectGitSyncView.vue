<!--
  @ai-purpose: Project GitHub sync target management — add/edit/remove repositories, toggle
    enabled/paused, and trigger on-demand syncs. One of three views split out of the former
    monolithic ProjectSettingsView.vue (2026-08-27, see that day's journal entry) — the other two
    are ProjectGeneralSettingsView/ProjectAccessManagementView. `canManage` is owner/admin/editor,
    matching the backend's `can_manage_github` gate (widened to include a shared EDITOR per the
    2026-08-17 permission-matrix rework).
  @ai-context: Since the 2026-08-06 multi-repo GitHub sync redesign, a Project can have MANY
    simultaneous sync targets (`githubTargets`, a Table, not a single form) — each is pushed to
    automatically by the backend on every secret/variable value change, not just when "Sync now" is
    clicked here; this view only adds/edits/removes/toggles targets and can trigger an on-demand
    sync (either one target or all of them at once). A target's PAT is write-only, same one-shot-
    reveal-never shape as an access-key token: the edit dialog's PAT field is always blank, and a
    blank submit leaves the stored token untouched. Since 2026-08-08, the Add/Edit repository
    Dialog's PAT field is a `patMode` Tabs toggle ("Custom token" / "Reference a secret") — "Reference
    a secret" is a two-step Project→Secret Select pair (`patSourceProjects`/`patSourceKeys`, lazily
    loaded on first use of that tab — most targets never need it), filtered client-side to every
    visible role (matching can_reveal's 2026-08-17 widening to cover a shared VIEWER) and to `is_set`
    keys only — the backend independently re-enforces via can_reveal regardless, this filter just
    keeps the picker from ever offering an option the API would reject. Editing an existing
    reference-mode target shows its current `pat_source_label` read-only and leaves both Selects
    unset — same "blank/omitted = unchanged" convention the custom PAT field already had.
  @ai-rules:
    - `confirmDeleteTarget` must live in a ref that is ONLY ever set on open and cleared by our own
      code — never nulled by the dialog's own `@update:open` handler. See
      ProjectAccessManagementView.vue's own header comment for the full race-condition rationale.
  @ai-context2: 2026-08-29: dropped the page's own `ProjectSettingsNav` sub-nav — "back to
    project"/General settings/Access Management/Git-Sync now live as a project-scoped section of
    App.vue's own nav rail instead (see that file's same-day journal entry).
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, table, select, badge,
    alert-dialog, dialog, switch, tabs, input, label, button, skeleton)
  @version: 1.1.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-29
-->
<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { PhArrowsClockwise, PhGithubLogo, PhKey, PhPencilSimple, PhPlus, PhTrash } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';

const props = defineProps({ projectId: { type: String, required: true } });

const project = ref(null);
const githubTargets = ref([]);
const loading = ref(true);

const canManage = computed(() => ['owner', 'admin', 'editor'].includes(project.value?.my_role));

async function loadAll() {
  loading.value = true;
  try {
    project.value = await api.getProject(props.projectId);
    if (['owner', 'admin', 'editor'].includes(project.value.my_role)) {
      githubTargets.value = await api.listGithubTargets(props.projectId);
    }
  } catch (e) {
    toast.error(e.message);
  } finally {
    loading.value = false;
  }
}
onMounted(loadAll);

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
    // Only projects the caller can REVEAL — since 2026-08-17, can_reveal covers ANY visible role
    // (owner/admin/editor/viewer), so every Project listProjects() returns already qualifies; the
    // backend independently re-enforces this via can_reveal regardless.
    patSourceProjects.value = all.filter((p) => !!p.my_role);
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
// See this file's own header comment for why target/open-state are split across two refs.
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
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 w-full">
    <div v-if="loading" class="space-y-4">
      <Skeleton class="h-8 w-64" />
      <Skeleton class="h-40 rounded-xl" />
    </div>

    <template v-else-if="project && canManage">
      <h1 class="text-2xl font-bold mb-6">{{ project.name }} — Git-Sync</h1>

      <Card>
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
            <TableHeader>
              <TableRow>
                <TableHead>Repository</TableHead>
                <TableHead>Sync</TableHead>
                <TableHead>Status</TableHead>
                <TableHead class="w-24 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
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
                    size="icon-xs"
                    title="Sync this repository now"
                    :disabled="syncingTargetId === t.id"
                    @click="syncTargetNow(t)"
                  >
                    <PhArrowsClockwise :size="13" weight="bold" />
                  </Button>
                  <Button variant="ghost" size="icon-xs" title="Edit" @click="openEditTarget(t)">
                    <PhPencilSimple :size="13" weight="bold" />
                  </Button>
                  <Button variant="destructive" size="icon-xs" title="Remove" @click="openDeleteTargetDialog(t)">
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
  </div>
</template>
