<!--
  @ai-purpose: Project detail — the secret key list. The core screen of the app.
  @ai-context: Since the 2026-08-06 global-environments redesign, every key links to exactly ONE
    Environment (picked from the global list at creation, reassignable via the row's Environment
    Select) instead of the old grid-of-values-per-environment shape — so this is now a flat table
    (Key | Environment | Value | actions) with an Environment filter above it, not a grid.
    can_edit/can_reveal are derived from project.my_role (owner/admin/editor/viewer — see
    nebular.projects' permission matrix, mirrored client-side only for showing/hiding controls; the
    backend re-checks everything independently). Values are masked (`•••••••`) by default —
    revealValue() is called on demand per key and the plaintext is kept only in this component's own
    `revealed` map (never persisted, cleared on navigation since the component unmounts). Editing a
    value is an inline per-row shadcn-vue Popover. Deleting a key goes through a shadcn-vue
    AlertDialog. "Upload .env" bulk-adds keys from a pasted-in file: lib/envFile.js parses the raw
    text client-side (rejecting the whole file if any non-comment/non-blank line fails to parse),
    then a shadcn-vue Dialog lets the user pick a target Environment + variable type and review the
    parsed key names before POSTing them all at once to /secret/{project_id}/bulk
    (api.bulkCreateSecrets) — always creates brand-new keys, never updates an existing one; the
    backend 409s (naming every conflict) rather than silently overwriting anything.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, badge, button, input, label,
    select, table, popover, alert-dialog, dialog, skeleton)
  @version: 4.1.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-06
-->
<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { PhArrowLeft, PhEye, PhEyeSlash, PhGear, PhPencilSimple, PhPlus, PhTrash, PhUpload } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { parseEnvFile } from '../lib/envFile';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
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
      api.listEnvironments(),
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

// ── Environment filter ──────────────────────────────────────────────────
const filterEnvironmentId = ref('all');
const filteredKeys = computed(() =>
  filterEnvironmentId.value === 'all'
    ? keys.value
    : keys.value.filter((k) => k.environment_id === filterEnvironmentId.value)
);

// ── New secret key ───────────────────────────────────────────────────────
const showKeyForm = ref(false);
const newKey = ref({ name: '', description: '', environment_id: '', variable_type: 'secret' });
const savingKey = ref(false);
async function addKey() {
  if (!newKey.value.name.trim() || !newKey.value.environment_id) return;
  savingKey.value = true;
  try {
    const key = await api.createSecret(props.projectId, {
      name: newKey.value.name.trim(),
      description: newKey.value.description.trim() || null,
      environment_id: newKey.value.environment_id,
      variable_type: newKey.value.variable_type,
    });
    keys.value.push(key);
    newKey.value = { name: '', description: '', environment_id: '', variable_type: 'secret' };
    showKeyForm.value = false;
  } catch (e) {
    toast.error(e.message);
  } finally {
    savingKey.value = false;
  }
}

// ── Upload .env (bulk add) ───────────────────────────────────────────────
// Parsing happens entirely client-side (lib/envFile.js); the parsed items are only sent to the
// bulk-create API once the user reviews and confirms the dialog below. The whole file is rejected
// if a single line can't be parsed — parseEnvFile never returns a partial result.
const envFileInput = ref(null);
const uploadDialogOpen = ref(false);
const uploadItems = ref([]);
const uploadEnvironmentId = ref('');
const uploadVariableType = ref('secret');
const uploadSubmitting = ref(false);

function openEnvFilePicker() {
  envFileInput.value?.click();
}

async function onEnvFileSelected(event) {
  const file = event.target.files?.[0];
  event.target.value = ''; // allow re-selecting the same file to retrigger 'change'
  if (!file) return;

  const text = await file.text();
  const { items, errors } = parseEnvFile(text);

  if (errors.length) {
    const preview = errors.slice(0, 5).map((e) => `line ${e.line}: "${e.content.trim()}"`).join('; ');
    const more = errors.length > 5 ? ` (+${errors.length - 5} more)` : '';
    toast.error(`Could not parse ${errors.length} line(s) — upload cancelled. ${preview}${more}`);
    return;
  }
  if (!items.length) {
    toast.error('No key=value lines found in that file.');
    return;
  }

  uploadItems.value = items;
  uploadEnvironmentId.value = environments.value.length === 1 ? environments.value[0].id : '';
  uploadVariableType.value = 'secret';
  uploadDialogOpen.value = true;
}

async function confirmUpload() {
  if (!uploadEnvironmentId.value || !uploadItems.value.length) return;
  uploadSubmitting.value = true;
  try {
    const created = await api.bulkCreateSecrets(props.projectId, {
      environment_id: uploadEnvironmentId.value,
      variable_type: uploadVariableType.value,
      items: uploadItems.value.map(({ name, value }) => ({ name, value })),
    });
    keys.value.push(...created);
    toast.success(`Added ${created.length} variable${created.length === 1 ? '' : 's'}.`);
    uploadDialogOpen.value = false;
    uploadItems.value = [];
  } catch (e) {
    toast.error(e.message);
  } finally {
    uploadSubmitting.value = false;
  }
}

// ── Reassign environment ─────────────────────────────────────────────────
async function reassignEnvironment(key, environmentId) {
  if (environmentId === key.environment_id) return;
  try {
    const updated = await api.updateSecret(props.projectId, key.id, { environment_id: environmentId });
    const idx = keys.value.findIndex((k) => k.id === updated.id);
    if (idx !== -1) keys.value[idx] = updated;
    toast.success('Environment updated.');
  } catch (e) {
    toast.error(e.message);
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
async function toggleReveal(key) {
  if (revealed[key.id] !== undefined) {
    delete revealed[key.id];
    return;
  }
  try {
    const res = await api.revealSecretValue(props.projectId, key.id);
    revealed[key.id] = res.value;
  } catch (e) {
    toast.error(e.message);
  }
}

// ── Set value ─────────────────────────────────────────────────────────────
const editingKeyId = ref(null);
const editingValue = ref('');
const savingValue = ref(false);
function openEditor(key) {
  editingKeyId.value = key.id;
  editingValue.value = '';
}
function closeEditor() {
  editingKeyId.value = null;
}
async function saveValue() {
  if (!editingKeyId.value) return;
  savingValue.value = true;
  try {
    const updated = await api.setSecretValue(props.projectId, editingKeyId.value, { value: editingValue.value });
    const idx = keys.value.findIndex((k) => k.id === updated.id);
    if (idx !== -1) keys.value[idx] = updated;
    delete revealed[updated.id];
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
    <Button variant="link" class="px-0 mb-4 text-sm" @click="emit('navigate', '/projects')">
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

      <Card v-if="!environments.length" class="mb-6">
        <CardContent class="text-muted-foreground text-sm">
          No environments exist yet — create one on the Environments page before adding keys.
        </CardContent>
      </Card>

      <!-- Secret keys -->
      <div class="flex items-center justify-between mb-3 gap-3 flex-wrap">
        <h2 class="font-semibold">Secrets</h2>
        <div class="flex items-center gap-2">
          <Select v-model="filterEnvironmentId">
            <SelectTrigger size="sm" class="w-40"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All environments</SelectItem>
              <SelectItem v-for="env in environments" :key="env.id" :value="env.id">{{ env.name }}</SelectItem>
            </SelectContent>
          </Select>
          <input
            ref="envFileInput"
            type="file"
            accept=".env,text/plain"
            class="hidden"
            @change="onEnvFileSelected"
          />
          <Button v-if="canEdit && environments.length" variant="outline" @click="openEnvFilePicker">
            <PhUpload :size="16" weight="bold" /> Upload .env
          </Button>
          <Button v-if="canEdit && environments.length" @click="showKeyForm = !showKeyForm">
            <PhPlus :size="16" weight="bold" /> New key
          </Button>
        </div>
      </div>

      <Card v-if="showKeyForm" class="mb-4">
        <CardContent>
          <form @submit.prevent="addKey" class="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div class="space-y-1.5">
              <Label for="new-key-name">Name</Label>
              <Input id="new-key-name" v-model="newKey.name" placeholder="KEY_NAME" required class="uppercase" />
            </div>
            <div class="space-y-1.5">
              <Label for="new-key-description">Description</Label>
              <Input id="new-key-description" v-model="newKey.description" placeholder="Description (optional)" />
            </div>
            <div class="space-y-1.5">
              <Label for="new-key-env">Environment</Label>
              <Select v-model="newKey.environment_id">
                <SelectTrigger id="new-key-env" class="w-full"><SelectValue placeholder="Choose one" /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="env in environments" :key="env.id" :value="env.id">{{ env.name }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="space-y-1.5">
              <Label for="new-key-type">Type</Label>
              <Select v-model="newKey.variable_type">
                <SelectTrigger id="new-key-type" class="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="secret">Secret</SelectItem>
                  <SelectItem value="environment">Environment variable</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="sm:col-span-2 lg:col-span-4 flex gap-2 justify-end">
              <Button type="button" variant="outline" @click="showKeyForm = false">Cancel</Button>
              <Button type="submit" :disabled="savingKey || !newKey.environment_id">Create</Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card v-if="!filteredKeys.length">
        <CardContent class="p-10 text-center text-muted-foreground text-sm">
          {{ keys.length ? 'No keys in this environment.' : 'No keys yet.' }}
        </CardContent>
      </Card>

      <Card v-else class="py-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Key</TableHead>
              <TableHead>Environment</TableHead>
              <TableHead>Value</TableHead>
              <TableHead class="w-10"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="key in filteredKeys" :key="key.id">
              <TableCell class="align-top">
                <div class="flex items-center gap-1.5">
                  <span class="font-mono font-semibold">{{ key.name }}</span>
                  <Badge :variant="key.variable_type === 'secret' ? 'warning' : 'info'" class="text-[0.65rem] px-1.5 py-0">
                    {{ key.variable_type === 'secret' ? 'secret' : 'env var' }}
                  </Badge>
                </div>
                <div v-if="key.description" class="text-muted-foreground text-xs mt-0.5">{{ key.description }}</div>
              </TableCell>
              <TableCell class="align-top">
                <Select
                  v-if="canEdit"
                  :model-value="key.environment_id"
                  @update:model-value="(v) => reassignEnvironment(key, v)"
                >
                  <SelectTrigger size="sm" class="w-32"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem v-for="env in environments" :key="env.id" :value="env.id">{{ env.name }}</SelectItem>
                  </SelectContent>
                </Select>
                <Badge v-else variant="outline">{{ key.environment_name }}</Badge>
              </TableCell>
              <TableCell class="align-top">
                <div class="flex items-center gap-2">
                  <span v-if="!key.is_set" class="text-muted-foreground text-xs">—</span>
                  <!-- Environment variables are never anonymized — the value ships in the list response itself. -->
                  <span v-else-if="key.variable_type === 'environment'" class="font-mono">{{ key.value }}</span>
                  <span v-else-if="revealed[key.id] !== undefined" class="font-mono">{{ revealed[key.id] }}</span>
                  <span v-else class="secret-mask">••••••••</span>

                  <Button
                    v-if="canReveal && key.is_set && key.variable_type === 'secret'"
                    variant="ghost"
                    size="icon-xs"
                    :title="revealed[key.id] !== undefined ? 'Hide' : 'Reveal'"
                    @click="toggleReveal(key)"
                  >
                    <PhEyeSlash v-if="revealed[key.id] !== undefined" :size="13" weight="bold" />
                    <PhEye v-else :size="13" weight="bold" />
                  </Button>

                  <Popover
                    v-if="canEdit"
                    :open="editingKeyId === key.id"
                    @update:open="(v) => !v && closeEditor()"
                  >
                    <PopoverTrigger as-child>
                      <Button variant="ghost" size="icon-xs" title="Set value" @click="openEditor(key)">
                        <PhPencilSimple :size="13" weight="bold" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent v-if="editingKeyId === key.id" class="w-64" @keyup.enter="saveValue">
                      <div class="space-y-2.5">
                        <Label :for="`value-${key.id}`">Value for {{ key.environment_name }}</Label>
                        <Input :id="`value-${key.id}`" v-model="editingValue" placeholder="value" autofocus />
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

    <Dialog :open="uploadDialogOpen" @update:open="(v) => !v && (uploadDialogOpen = false)">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add {{ uploadItems.length }} variable{{ uploadItems.length === 1 ? '' : 's' }} from file</DialogTitle>
          <DialogDescription>
            Review before adding — this creates {{ uploadItems.length === 1 ? 'a new key' : 'new keys' }}
            only; it never overwrites an existing key's value.
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1.5">
              <Label for="upload-env">Environment</Label>
              <Select v-model="uploadEnvironmentId">
                <SelectTrigger id="upload-env" class="w-full"><SelectValue placeholder="Choose one" /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="env in environments" :key="env.id" :value="env.id">{{ env.name }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="space-y-1.5">
              <Label for="upload-type">Type</Label>
              <Select v-model="uploadVariableType">
                <SelectTrigger id="upload-type" class="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="secret">Secret</SelectItem>
                  <SelectItem value="environment">Environment variable</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div class="space-y-1.5">
            <Label>Keys found</Label>
            <div class="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto rounded-md border p-2">
              <Badge v-for="item in uploadItems" :key="item.name" variant="outline" class="font-mono">
                {{ item.name }}
              </Badge>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="uploadDialogOpen = false">Cancel</Button>
          <Button :disabled="uploadSubmitting || !uploadEnvironmentId" @click="confirmUpload">
            Add {{ uploadItems.length }} variable{{ uploadItems.length === 1 ? '' : 's' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <AlertDialog :open="!!confirmDeleteKey" @update:open="(v) => !v && (confirmDeleteKey = null)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this key?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes '{{ confirmDeleteKey?.name }}' and its value. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="deleteKey">Delete</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
