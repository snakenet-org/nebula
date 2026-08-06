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
    AlertDialog.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, badge, button, input, label,
    select, table, popover, alert-dialog, skeleton)
  @version: 3.0.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-06
-->
<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { PhArrowLeft, PhEye, PhEyeSlash, PhGear, PhPencilSimple, PhPlus, PhTrash } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
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
const newKey = ref({ name: '', description: '', environment_id: '' });
const savingKey = ref(false);
async function addKey() {
  if (!newKey.value.name.trim() || !newKey.value.environment_id) return;
  savingKey.value = true;
  try {
    const key = await api.createSecret(props.projectId, {
      name: newKey.value.name.trim(),
      description: newKey.value.description.trim() || null,
      environment_id: newKey.value.environment_id,
    });
    keys.value.push(key);
    newKey.value = { name: '', description: '', environment_id: '' };
    showKeyForm.value = false;
  } catch (e) {
    toast.error(e.message);
  } finally {
    savingKey.value = false;
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
          <Button v-if="canEdit && environments.length" @click="showKeyForm = !showKeyForm">
            <PhPlus :size="16" weight="bold" /> New key
          </Button>
        </div>
      </div>

      <Card v-if="showKeyForm" class="mb-4">
        <CardContent>
          <form @submit.prevent="addKey" class="grid sm:grid-cols-3 gap-3">
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
            <div class="sm:col-span-3 flex gap-2 justify-end">
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
                <div class="font-mono font-semibold">{{ key.name }}</div>
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
                  <span v-else-if="revealed[key.id] !== undefined" class="font-mono">{{ revealed[key.id] }}</span>
                  <span v-else class="secret-mask">••••••••</span>

                  <Button
                    v-if="canReveal && key.is_set"
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
