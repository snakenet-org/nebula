<!--
  @ai-purpose: Project detail — environments + the secret key/value grid. The core screen of the app.
  @ai-context: can_edit/can_reveal are derived from project.my_role (owner/admin/editor/viewer — see
    nebular.projects' permission matrix, mirrored client-side only for showing/hiding controls; the
    backend re-checks everything independently). Values are masked (`•••••••`) by default —
    revealValue() is called on demand per cell and the plaintext is kept only in this component's own
    `revealed` map (never persisted, cleared on navigation since the component unmounts). Editing a
    value is an inline per-cell shadcn-vue Popover (editingCell) with an "apply to all environments"
    Checkbox — the one UI affordance for the spec's "same value everywhere" convenience
    (nebular.secrets.set_value_for_all_environments). Deleting a key or an environment goes through
    a shadcn-vue AlertDialog.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, badge, button, input, label,
    checkbox, table, popover, alert-dialog, skeleton)
  @version: 2.0.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-06
-->
<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { PhArrowLeft, PhEye, PhEyeSlash, PhGear, PhPencilSimple, PhPlus, PhTrash, PhX } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Skeleton } from '@/components/ui/skeleton';

const props = defineProps({ projectId: { type: String, required: true } });
const emit = defineEmits(['navigate']);

const project = ref(null);
const environments = ref([]);
const keys = ref([]);
const loading = ref(true);

const canEdit = computed(() => ['owner', 'admin', 'editor'].includes(project.value?.my_role));
const canReveal = computed(() => ['owner', 'admin'].includes(project.value?.my_role));

async function loadAll() {
  loading.value = true;
  try {
    const [p, envs, ks] = await Promise.all([
      api.getProject(props.projectId),
      api.listEnvironments(props.projectId),
      api.listSecrets(props.projectId),
    ]);
    project.value = p;
    environments.value = envs;
    keys.value = ks;
  } catch (e) {
    toast.error(e.message);
  } finally {
    loading.value = false;
  }
}
onMounted(loadAll);

function valueFor(key, environmentId) {
  return key.values.find((v) => v.environment_id === environmentId) || null;
}

// ── New environment ─────────────────────────────────────────────────────
const showEnvForm = ref(false);
const newEnvName = ref('');
const savingEnv = ref(false);
async function addEnvironment() {
  if (!newEnvName.value.trim()) return;
  savingEnv.value = true;
  try {
    const env = await api.createEnvironment(props.projectId, { name: newEnvName.value.trim() });
    environments.value.push(env);
    newEnvName.value = '';
    showEnvForm.value = false;
    await loadAll();
  } catch (e) {
    toast.error(e.message);
  } finally {
    savingEnv.value = false;
  }
}

const confirmDeleteEnv = ref(null);
async function deleteEnvironment() {
  if (!confirmDeleteEnv.value) return;
  try {
    await api.deleteEnvironment(props.projectId, confirmDeleteEnv.value.id);
    confirmDeleteEnv.value = null;
    await loadAll();
    toast.success('Environment deleted.');
  } catch (e) {
    toast.error(e.message);
  }
}

// ── New secret key ───────────────────────────────────────────────────────
const showKeyForm = ref(false);
const newKey = ref({ name: '', description: '' });
const savingKey = ref(false);
async function addKey() {
  if (!newKey.value.name.trim()) return;
  savingKey.value = true;
  try {
    const key = await api.createSecret(props.projectId, {
      name: newKey.value.name.trim(),
      description: newKey.value.description.trim() || null,
    });
    keys.value.push(key);
    newKey.value = { name: '', description: '' };
    showKeyForm.value = false;
  } catch (e) {
    toast.error(e.message);
  } finally {
    savingKey.value = false;
  }
}

const confirmDeleteKey = ref(null);
async function deleteKey() {
  if (!confirmDeleteKey.value) return;
  try {
    await api.deleteSecret(props.projectId, confirmDeleteKey.value.id);
    keys.value = keys.value.filter((k) => k.id !== confirmDeleteKey.value.id);
    confirmDeleteKey.value = null;
    toast.success('Key deleted.');
  } catch (e) {
    toast.error(e.message);
  }
}

// ── Reveal ────────────────────────────────────────────────────────────────
const revealed = reactive({});
function cellKey(keyId, envId) {
  return `${keyId}:${envId}`;
}
async function toggleReveal(key, environmentId) {
  const ck = cellKey(key.id, environmentId);
  if (revealed[ck] !== undefined) {
    delete revealed[ck];
    return;
  }
  try {
    const res = await api.revealSecretValue(props.projectId, key.id, environmentId);
    revealed[ck] = res.value;
  } catch (e) {
    toast.error(e.message);
  }
}

// ── Set value ─────────────────────────────────────────────────────────────
const editingCell = ref(null); // { keyId, environmentId, value, applyToAll }
const savingValue = ref(false);
function isEditing(keyId, environmentId) {
  return editingCell.value?.keyId === keyId && editingCell.value?.environmentId === environmentId;
}
function openEditor(key, environmentId) {
  editingCell.value = { keyId: key.id, environmentId, value: '', applyToAll: false };
}
function closeEditor() {
  editingCell.value = null;
}
async function saveValue() {
  if (!editingCell.value) return;
  savingValue.value = true;
  try {
    const updated = await api.setSecretValue(props.projectId, editingCell.value.keyId, {
      value: editingCell.value.value,
      apply_to_all_environments: editingCell.value.applyToAll,
      environment_id: editingCell.value.applyToAll ? null : editingCell.value.environmentId,
    });
    const idx = keys.value.findIndex((k) => k.id === updated.id);
    if (idx !== -1) keys.value[idx] = updated;
    // Clear any cached reveal for this key so a stale plaintext never lingers on-screen.
    Object.keys(revealed).forEach((ck) => {
      if (ck.startsWith(`${updated.id}:`)) delete revealed[ck];
    });
    closeEditor();
    toast.success('Value saved.');
  } catch (e) {
    toast.error(e.message);
  } finally {
    savingValue.value = false;
  }
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 w-full">
    <Button variant="link" class="px-0 mb-4 text-sm" @click="emit('navigate', '/')">
      <PhArrowLeft :size="14" weight="bold" /> All projects
    </Button>

    <div v-if="loading" class="space-y-4">
      <Skeleton class="h-8 w-64" />
      <Skeleton class="h-40 rounded-xl" />
    </div>

    <template v-else-if="project">
      <div class="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 class="text-2xl font-bold">{{ project.name }}</h1>
          <p v-if="project.description" class="text-muted-foreground text-sm mt-1">{{ project.description }}</p>
        </div>
        <Button
          v-if="['owner', 'admin'].includes(project.my_role)"
          variant="outline"
          @click="emit('navigate', `/projects/${projectId}/settings`)"
        >
          <PhGear :size="16" weight="bold" /> Settings
        </Button>
      </div>

      <!-- Environments -->
      <div class="flex items-center gap-2 mb-4 flex-wrap">
        <Badge v-for="env in environments" :key="env.id" variant="outline" class="gap-1.5 h-6 px-2.5">
          {{ env.name }}
          <button
            v-if="canEdit"
            type="button"
            title="Delete environment"
            class="cursor-pointer flex items-center opacity-70 hover:opacity-100"
            @click="confirmDeleteEnv = env"
          >
            <PhX :size="11" weight="bold" />
          </button>
        </Badge>
        <Button v-if="canEdit && !showEnvForm" variant="ghost" size="icon-sm" title="Add environment" @click="showEnvForm = true">
          <PhPlus :size="14" weight="bold" />
        </Button>
        <form v-if="showEnvForm" class="flex items-center gap-2" @submit.prevent="addEnvironment">
          <Input class="w-40 h-8" v-model="newEnvName" placeholder="e.g. production" autofocus />
          <Button type="submit" size="sm" :disabled="savingEnv">Add</Button>
          <Button type="button" variant="outline" size="sm" @click="showEnvForm = false">Cancel</Button>
        </form>
      </div>

      <Card v-if="!environments.length" class="mb-6">
        <CardContent class="text-muted-foreground text-sm">
          Add an environment (e.g. "production", "staging") before creating keys.
        </CardContent>
      </Card>

      <!-- Secret keys -->
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold">Secrets</h2>
        <Button v-if="canEdit && environments.length" @click="showKeyForm = !showKeyForm">
          <PhPlus :size="16" weight="bold" /> New key
        </Button>
      </div>

      <Card v-if="showKeyForm" class="mb-4">
        <CardContent>
          <form @submit.prevent="addKey" class="grid sm:grid-cols-2 gap-3">
            <div class="space-y-1.5">
              <Label for="new-key-name">Name</Label>
              <Input id="new-key-name" v-model="newKey.name" placeholder="KEY_NAME" required class="uppercase" />
            </div>
            <div class="space-y-1.5">
              <Label for="new-key-description">Description</Label>
              <Input id="new-key-description" v-model="newKey.description" placeholder="Description (optional)" />
            </div>
            <div class="sm:col-span-2 flex gap-2 justify-end">
              <Button type="button" variant="outline" @click="showKeyForm = false">Cancel</Button>
              <Button type="submit" :disabled="savingKey">Create</Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card v-if="!keys.length">
        <CardContent class="p-10 text-center text-muted-foreground text-sm">No keys yet.</CardContent>
      </Card>

      <Card v-else class="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Key</TableHead>
              <TableHead v-for="env in environments" :key="env.id">{{ env.name }}</TableHead>
              <TableHead class="w-10"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="key in keys" :key="key.id">
              <TableCell class="align-top">
                <div class="font-mono font-semibold">{{ key.name }}</div>
                <div v-if="key.description" class="text-muted-foreground text-xs mt-0.5">{{ key.description }}</div>
              </TableCell>
              <TableCell v-for="env in environments" :key="env.id" class="align-top">
                <div class="flex items-center gap-2">
                  <span v-if="!valueFor(key, env.id)?.is_set" class="text-muted-foreground text-xs">—</span>
                  <span v-else-if="revealed[cellKey(key.id, env.id)] !== undefined" class="font-mono">{{ revealed[cellKey(key.id, env.id)] }}</span>
                  <span v-else class="secret-mask">••••••••</span>

                  <Button
                    v-if="canReveal && valueFor(key, env.id)?.is_set"
                    variant="ghost"
                    size="icon-xs"
                    :title="revealed[cellKey(key.id, env.id)] !== undefined ? 'Hide' : 'Reveal'"
                    @click="toggleReveal(key, env.id)"
                  >
                    <PhEyeSlash v-if="revealed[cellKey(key.id, env.id)] !== undefined" :size="13" weight="bold" />
                    <PhEye v-else :size="13" weight="bold" />
                  </Button>

                  <Popover
                    v-if="canEdit"
                    :open="isEditing(key.id, env.id)"
                    @update:open="(v) => !v && closeEditor()"
                  >
                    <PopoverTrigger as-child>
                      <Button variant="ghost" size="icon-xs" title="Set value" @click="openEditor(key, env.id)">
                        <PhPencilSimple :size="13" weight="bold" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent v-if="editingCell" class="w-64" @keyup.enter="saveValue">
                      <div class="space-y-2.5">
                        <Label :for="`value-${key.id}-${env.id}`">Value for {{ env.name }}</Label>
                        <Input :id="`value-${key.id}-${env.id}`" v-model="editingCell.value" placeholder="value" autofocus />
                        <label class="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
                          <Checkbox v-model="editingCell.applyToAll" />
                          apply to all environments
                        </label>
                        <div class="flex gap-2 justify-end">
                          <Button variant="outline" size="sm" @click="closeEditor">Cancel</Button>
                          <Button size="sm" :disabled="savingValue" @click="saveValue">Save</Button>
                        </div>
                      </div>
                    </PopoverContent>
                  </Popover>
                </div>
              </TableCell>
              <TableCell class="align-top text-right">
                <Button v-if="canEdit" variant="ghost" size="icon-xs" title="Delete key" @click="confirmDeleteKey = key">
                  <PhTrash :size="13" weight="bold" />
                </Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </Card>
    </template>

    <AlertDialog :open="!!confirmDeleteKey" @update:open="(v) => !v && (confirmDeleteKey = null)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this key?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes '{{ confirmDeleteKey?.name }}' and every environment's value for it. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="deleteKey">Delete</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <AlertDialog :open="!!confirmDeleteEnv" @update:open="(v) => !v && (confirmDeleteEnv = null)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this environment?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes '{{ confirmDeleteEnv?.name }}' and every key's value for it. This cannot be undone.
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
