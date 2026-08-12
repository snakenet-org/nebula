<!--
  @ai-purpose: Project detail — the secret key list. The core screen of the app.
  @ai-context: Since the 2026-08-06 global-environments redesign, every key links to exactly ONE
    Environment (picked from the global list at creation, reassignable via the row's Environment
    Select) instead of the old grid-of-values-per-environment shape — so this is now a flat table
    (Key | Environment | Value | actions) with an Environment filter above it, not a grid.
    can_edit/can_reveal/can_edit_value are derived from project.my_role (owner/admin/editor/viewer —
    see nebula.projects' permission matrix, mirrored client-side only for showing/hiding controls;
    the backend re-checks everything independently). Since 2026-08-09 (later same day), a shared
    EDITOR can reveal+copy a value (canReveal) but can no longer set/change one (canEditValue,
    owner/admin only) — canEdit itself is unchanged and still governs rename/delete/environment-
    reassignment/sync-toggle/creating a bare key. The "New key" form's value Tabs (direct-value /
    reference) only render for canEditValue; an EDITOR instead sees just the Type Select, creating a
    valueless key an owner/admin fills in later. The per-row "Set value" popover trigger is gated on
    canEditValue, not canEdit. Values are masked (`•••••••`) by default —
    revealValue() is called on demand per key and the plaintext is kept only in this component's own
    `revealed` map (never persisted, cleared on navigation since the component unmounts). Editing a
    value is an inline per-row shadcn-vue Popover. Deleting a key goes through a shadcn-vue
    AlertDialog. "Upload .env" bulk-adds keys from a pasted-in file: lib/envFile.js parses the raw
    text client-side (rejecting the whole file if any non-comment/non-blank line fails to parse),
    then a shadcn-vue Dialog lets the user pick a target Environment and review the parsed keys
    row-by-row — each row gets its own "import this key" Checkbox (default checked; unchecked rows
    are simply left out of the POST body, no dedicated skip field needed) and its own Type Select
    (secret/environment variable, default secret), not one Type for the whole batch — before
    POSTing the included rows at once to /secret/{project_id}/bulk (api.bulkCreateSecrets) — always
    creates brand-new keys, never updates an existing one; the backend 409s (naming every conflict)
    rather than silently overwriting anything.
    The hidden file `<input>` behind "Upload .env" deliberately carries NO `accept` attribute:
    macOS's native file picker treats an `accept` list of extensions as a hard filter and, for a
    dotfile-only pattern like `.env` (no distinguishing extension after the leading dot), silently
    hides matching files from the listing even while their containing folder stays navigable — the
    user could browse into a folder but never actually select the `.env` file inside it. Dropping
    `accept` entirely restores the native "All Files" option, matching macOS Finder's convention that
    a dotfile shows once "all files" (not an extension filter) is in effect.
    The create-key form now also takes an optional Value (2026-08-07) so a key can be fully set up
    (name/description/environment/type/value) in one submit instead of a create-then-set-value round
    trip — still entirely optional, a blank value creates the key exactly as before. Renaming a key
    is a small Dialog (openRenameDialog/saveRename) separate from the environment-reassignment
    Select and the value-editor Popover. Both the delete-key AlertDialog and this rename Dialog fixed
    a real bug this session: every AlertDialog target ref in this file used to be nulled by the
    dialog's own `@update:open` handler, which raced against AlertDialogAction's built-in
    auto-close (reka-ui's DialogClose calls `rootContext.onOpenChange(false)` unconditionally on
    click, with no way to defer it) — when that internal handler ran before this component's own
    `@click` listener on the same click event, the target was already null by the time the delete
    handler read it, so its guard silently no-opped with zero API call ever sent. Fixed by splitting
    "which target is this dialog for" (confirmDeleteKey, set once on open, never auto-cleared) from
    "is the dialog open" (deleteKeyDialogOpen, freely toggled by reka-ui) — see the code comment by
    confirmDeleteKey's declaration for the full trace. Caught via a real headless-browser repro (not
    code review): a Playwright pass that created a throwaway key and clicked through the confirm
    dialog showed the dialog closing with zero `DELETE /api/v1/secret/...` request ever leaving the
    browser.
    2026-08-08: added a quick copy-to-clipboard button (PhCopy/PhCheck swap, same 1500ms-then-revert
    pattern as ProjectSettingsView's access-token copy button) next to each value in the table.
    Environment variables copy their already-in-hand `key.value` with no API call; a secret copies
    its already-`revealed` plaintext if the row is currently expanded, otherwise fetches it fresh via
    the same `revealSecretValue` call/`canReveal` gate the Eye button uses — deliberately without
    populating `revealed`, so a "quick copy" never forces the plaintext to also render on screen. Also
    recolored the row's Delete-key button from `ghost` to the existing `destructive` Button variant so
    it reads as a warning color like every other destructive action in the app, instead of looking
    identical to a neutral action (rename/edit/copy).
    2026-08-08 (later same day): key search widened (w-40 → w-64) plus a PhX clear button (shown only
    when keySearch is non-empty) inside the input's own right padding, mirroring how the search icon
    already sits in the left padding. Also dropped the `uppercase` Tailwind class from the new-key Name
    input — it only forced the *displayed* text to render as caps (CSS text-transform, not a data
    transform), which made a deliberately-mixed-case key name look like it was being forced to
    all-caps even though nebula.naming.validate_name (the actual backend constraint) has always allowed
    `[A-Za-z0-9_-]+` — letters of either case. No backend change needed; this was a frontend-only
    cosmetic bug.
    2026-08-08 (later same day): added a per-key GitHub sync toggle (new "Sync" table column) backed
    by SecretKey.sync_enabled (nebula.secrets/api/v1/secret.py) — an editor flips a shadcn-vue Switch,
    which PATCHes { sync_enabled } via the existing updateSecret call (toggleSync); a viewer sees a
    read-only "synced"/"paused" Badge instead, same Select-vs-Badge split canEdit already uses for the
    Environment column. Turning sync off only stops FUTURE pushes (nebula.github_sync.sync_to_github
    now skips the key) — it never retroactively removes a value already pushed to a linked repo.
    2026-08-09: the "New key" form's value section is now a `newKeyValueMode` Tabs toggle ("Set
    value" / "Reference a secret", same Tabs pattern as ProjectSettingsView's GitHub sync PAT
    picker) instead of a plain Type Select + Value Input — "Reference a secret" is a two-step
    Project→Secret Select pair (`referenceSourceProjects`/`referenceSourceKeys`, lazily loaded on
    first use), filtered client-side to owner/admin projects OTHER than this one and to non-reference
    keys (no chaining) — the backend independently re-enforces all of this, these filters just keep
    the picker from ever offering an option the API would reject. Submitting sends
    `source_key_id` instead of `variable_type`/`value`; the created key's type/value are then always
    resolved server-side from the source (api/v1/secret.py's `_to_response`), so no `variable_type`
    round-trips back from this form at all in reference mode. A reference key renders an extra
    `accent` "reference" Badge next to its type Badge, plus a small linked subtitle
    ("References <project> / <key> — only changeable there", `key.source_label`/
    `key.source_project_id`) below its description — clicking it navigates to the source Project.
    Its per-row "Set value" popover is hidden entirely (`canEdit && !key.source_key_id`) — the value
    can only ever be changed by editing the source key, in its own Project — while environment
    reassignment, the Sync toggle, and Edit (rename/description) all stay exactly as editable as any
    other key, since those are this row's own local metadata. The delete AlertDialog/toast now read
    differently for a reference key ("Remove this reference?" / "Reference removed.") than a normal
    one, to make explicit that deleting a reference only ever removes this project's link to it, not
    the source key itself. Separately, the "Rename key" Dialog is now "Edit key" and also edits
    `description` (a new Textarea) in the same submit, not just `name` — was previously name-only,
    even though SecretKey.description could already be set at creation.
    2026-08-09 (later same day): each key row's name now leads with a small status icon —
    `PhInfo` (text-info) when `key.extraction_count > 0`, `PhWarning` (text-warning) otherwise.
    `extraction_count` is new on SecretKeyResponse (api/v1/secret.py + nebula.audit.
    EXTRACTION_ACTIONS — a human's "secret.reveal" or an access key's "vault.retrieve", success
    only) — no frontend computation involved, the count ships straight from listSecrets.
    2026-08-09 (still later): both status icons now use a real shadcn Tooltip ("Extracted N times" /
    "This key has never been extracted") instead of the native `title` attribute used at first —
    wrapped in a local `TooltipProvider` around just this table, since this view sits outside
    App.vue's sidebar-only one.
    2026-08-12: the "Edit key" dialog's Name field (`renameValue`) is now a computed get/set wrapping
    a plain `renameValueRaw` ref, stripping any `\r`/`\n` on every write — a bare `<input>` still
    accepts a pasted line break into its value even though it never renders one, and
    nebula.naming.NAME_PATTERN (letters/digits/hyphens/underscores only) already forbids one server-
    side anyway, so this just keeps the field's actual value honest instead of letting a pasted line
    break surface as an opaque 422 on Save. The Description Textarea is deliberately untouched — its
    own multi-line content is intentional, per the 2026-08-09 entry above.
    2026-08-12 (later same day, closes GH #2 and #3): (1) the per-row "Set value" editor is now a
    shared Dialog (valueDialogOpen/editingKey/editingValue), not an inline Popover — same shape as
    the Edit-key Dialog just above (a single modal at the bottom of the template, its target held in
    a ref set on open, not derived from the dialog's own open/close transitions). (2) the Sync
    column header gained its own toggle-all Switch (allSyncEnabled/toggleAllSync) — scoped to
    `filteredKeys`, the rows actually on screen, same "act on what's visible" scope as the Upload
    dialog's own select-all Checkbox; reuses `syncingToggle`'s existing disabled-guard with the
    sentinel string `'all'` instead of a key id, since this can touch more than one row at once. (3)
    the trailing delete column's header cell, previously empty, now reads "Delete". (4) a new
    "Download .env" button next to "Upload .env" — the exact inverse of that flow — calls
    lib/envFile.js's new `formatEnvFile` over every key in the Project (not just the filtered rows,
    unlike the Sync toggle-all — a downloaded template should be complete) and triggers a browser
    download of `<project>.env` via a throwaway Blob/object-URL. It never reads a secret's actual
    plaintext (no revealSecretValue call at all): each line is
    `KEY=${nebula.<project>.<environment>.KEY}`, the exact cross-project reference syntax
    nebula-cli's own `deploy` command already resolves (confirmed against that sibling repo's
    README) — so the file is a stack-file template to fill in externally, not a real secrets export.
    (5) removed a leftover `uppercase` Tailwind class from the Edit-key dialog's Name input — the
    2026-08-08 entry above already dropped the same class from the *new-key* Name input as a
    cosmetic-only fix (nebula.naming's actual charset rule has always allowed mixed case), but missed
    this second occurrence on the rename/edit form; now neither input forces the displayed text to
    caps, so a deliberately mixed-case name reads back exactly as typed everywhere it's edited.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, badge, button, input,
    textarea, label, select, switch, tabs, table, tooltip, checkbox, alert-dialog, dialog, skeleton)
  @version: 7.4.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-12
-->
<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { PhArrowLeft, PhCheck, PhCopy, PhDownload, PhEye, PhEyeSlash, PhGear, PhInfo, PhLink, PhMagnifyingGlass, PhPencilSimple, PhPlus, PhTrash, PhUpload, PhWarning, PhX } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { formatEnvFile, parseEnvFile } from '../lib/envFile';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

const props = defineProps({ projectId: { type: String, required: true } });
const emit = defineEmits(['navigate']);

const project = ref(null);
const environments = ref([]);
const keys = ref([]);
const loading = ref(true);

const canEdit = computed(() => ['owner', 'admin', 'editor'].includes(project.value?.my_role));
const canReveal = computed(() => ['owner', 'admin', 'editor'].includes(project.value?.my_role));
// Distinct from canEdit/canReveal: a shared EDITOR can rename/delete/reassign-environment/toggle-
// sync a key and can now reveal+copy its current value, but can never set/change what a value IS —
// see nebula.projects' can_edit_value (owner/admin only).
const canEditValue = computed(() => ['owner', 'admin'].includes(project.value?.my_role));

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

// ── Environment filter + key-name search ─────────────────────────────────
const filterEnvironmentId = ref('all');
const keySearch = ref('');
const filteredKeys = computed(() => {
  let result = keys.value;
  if (filterEnvironmentId.value !== 'all') {
    result = result.filter((k) => k.environment_id === filterEnvironmentId.value);
  }
  const q = keySearch.value.trim().toLowerCase();
  if (q) {
    result = result.filter((k) => k.name.toLowerCase().includes(q));
  }
  return result;
});

// ── New secret key ───────────────────────────────────────────────────────
const showKeyForm = ref(false);
const emptyNewKey = () => ({ name: '', description: '', environment_id: '', variable_type: 'secret', value: '' });
const newKey = ref(emptyNewKey());
const savingKey = ref(false);

// ── New key: "reference a secret" picker ─────────────────────────────────
// A key's value can come from another key elsewhere in the vault instead of being set directly —
// same custom-vs-reference Tabs shape as ProjectSettingsView's GitHub sync PAT picker. Referencing
// is explicitly cross-project, so the current project is excluded from the picker; the backend
// independently re-enforces both that and the owner/admin (can_reveal) bar on the source project —
// these filters just keep the picker from ever offering an option the API would reject.
const newKeyValueMode = ref('direct'); // 'direct' | 'reference'
const referenceSourceProjects = ref([]);
const loadingReferenceSourceProjects = ref(false);
const referenceSourceKeys = ref([]);
const loadingReferenceSourceKeys = ref(false);
const referenceSourceProjectId = ref('');
const referenceSourceKeyId = ref('');

async function ensureReferenceSourceProjectsLoaded() {
  if (referenceSourceProjects.value.length || loadingReferenceSourceProjects.value) return;
  loadingReferenceSourceProjects.value = true;
  try {
    const all = await api.listProjects();
    referenceSourceProjects.value = all.filter(
      (p) => p.id !== props.projectId && ['owner', 'admin', 'editor'].includes(p.my_role)
    );
  } catch (e) {
    toast.error(e.message);
  } finally {
    loadingReferenceSourceProjects.value = false;
  }
}
async function loadReferenceSourceKeys(projectId) {
  if (!projectId) {
    referenceSourceKeys.value = [];
    return;
  }
  loadingReferenceSourceKeys.value = true;
  try {
    const ks = await api.listSecrets(projectId);
    // No chaining — a key that's itself a reference can't be referenced again (the backend rejects
    // this too; filtering here just keeps the picker from offering an invalid option).
    referenceSourceKeys.value = ks.filter((k) => !k.source_key_id);
  } catch (e) {
    toast.error(e.message);
    referenceSourceKeys.value = [];
  } finally {
    loadingReferenceSourceKeys.value = false;
  }
}
watch(newKeyValueMode, (mode) => {
  if (mode === 'reference') ensureReferenceSourceProjectsLoaded();
});
watch(referenceSourceProjectId, (projectId) => {
  referenceSourceKeyId.value = '';
  loadReferenceSourceKeys(projectId);
});
function resetNewKeyForm() {
  newKey.value = emptyNewKey();
  newKeyValueMode.value = 'direct';
  referenceSourceProjectId.value = '';
  referenceSourceKeyId.value = '';
  referenceSourceKeys.value = [];
}

async function addKey() {
  if (!newKey.value.name.trim() || !newKey.value.environment_id) return;
  if (newKeyValueMode.value === 'reference' && !referenceSourceKeyId.value) {
    toast.error('Pick a project and a secret to reference.');
    return;
  }
  savingKey.value = true;
  try {
    const payload = {
      name: newKey.value.name.trim(),
      description: newKey.value.description.trim() || null,
      environment_id: newKey.value.environment_id,
    };
    if (newKeyValueMode.value === 'reference') {
      payload.source_key_id = referenceSourceKeyId.value;
    } else {
      payload.variable_type = newKey.value.variable_type;
      payload.value = newKey.value.value || null;
    }
    const key = await api.createSecret(props.projectId, payload);
    keys.value.push(key);
    resetNewKeyForm();
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
// Each row: { name, value, variable_type, included } — `included` is the per-row "import this
// key or not" toggle; an unchecked row is simply left out of the payload built in confirmUpload,
// so "skip on import" needs no dedicated backend field.
const uploadItems = ref([]);
const uploadEnvironmentId = ref('');
const uploadSubmitting = ref(false);

const uploadIncludedCount = computed(() => uploadItems.value.filter((i) => i.included).length);
const uploadAllIncluded = computed(
  () => uploadItems.value.length > 0 && uploadIncludedCount.value === uploadItems.value.length
);
function toggleUploadAll(checked) {
  uploadItems.value.forEach((item) => (item.included = checked));
}

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

  uploadItems.value = items.map((item) => ({ ...item, variable_type: 'secret', included: true }));
  uploadEnvironmentId.value = environments.value.length === 1 ? environments.value[0].id : '';
  uploadDialogOpen.value = true;
}

// ── Download .env ────────────────────────────────────────────────────────
// The inverse of Upload .env — exports every key in the Project (not just the filtered/visible
// rows; a downloaded stack-file template should be complete), using formatEnvFile (lib/envFile.js).
// Never touches revealValue/the API — a key's actual value is never read here, only its already-
// loaded name/description/environment_name, so this needs no canReveal/canEditValue gate at all.
function downloadEnvFile() {
  const text = formatEnvFile(project.value.name, keys.value);
  const blob = new Blob([`${text}\n`], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${project.value.name}.env`;
  link.click();
  URL.revokeObjectURL(url);
}

async function confirmUpload() {
  const selected = uploadItems.value.filter((i) => i.included);
  if (!uploadEnvironmentId.value || !selected.length) return;
  uploadSubmitting.value = true;
  try {
    const created = await api.bulkCreateSecrets(props.projectId, {
      environment_id: uploadEnvironmentId.value,
      items: selected.map(({ name, value, variable_type }) => ({ name, value, variable_type })),
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

// ── GitHub sync toggle ───────────────────────────────────────────────────
// Off just means "skip this key on every future push" (nebula.github_sync.sync_to_github) — it
// does NOT remove a value already pushed to a linked repo, same push-only/no-deletion behavior a
// deleted key already has.
// `syncingToggle` holds the id of whichever key's toggle is mid-request — every toggle in the
// table disables while it's set (not just the one clicked), so a user can't queue up multiple
// overlapping sync_enabled writes by clicking several rows in quick succession.
const syncingToggle = ref(null);
async function toggleSync(key, enabled) {
  syncingToggle.value = key.id;
  try {
    const updated = await api.updateSecret(props.projectId, key.id, { sync_enabled: enabled });
    const idx = keys.value.findIndex((k) => k.id === updated.id);
    if (idx !== -1) keys.value[idx] = updated;
  } catch (e) {
    toast.error(e.message);
  } finally {
    syncingToggle.value = null;
  }
}

// The Sync column header's own toggle-all switch — scoped to the currently visible (filtered) rows,
// same "acts on what's on screen" scope as the Upload dialog's own select-all checkbox. `checked` is
// on when every visible row is already synced; clicking it flips only the rows that actually differ,
// reusing `syncingToggle`'s existing "some sync PATCH is in flight" disabled-guard (a sentinel string
// rather than a key id, since this affects more than one row at once).
const allSyncEnabled = computed(
  () => filteredKeys.value.length > 0 && filteredKeys.value.every((k) => k.sync_enabled)
);
async function toggleAllSync(enabled) {
  const targets = filteredKeys.value.filter((k) => k.sync_enabled !== enabled);
  if (!targets.length) return;
  syncingToggle.value = 'all';
  try {
    const updates = await Promise.all(
      targets.map((key) => api.updateSecret(props.projectId, key.id, { sync_enabled: enabled }))
    );
    for (const updated of updates) {
      const idx = keys.value.findIndex((k) => k.id === updated.id);
      if (idx !== -1) keys.value[idx] = updated;
    }
  } catch (e) {
    toast.error(e.message);
  } finally {
    syncingToggle.value = null;
  }
}

// `confirmDeleteKey` holds ONLY the target being confirmed — it is never cleared by the dialog's
// own close machinery (see deleteKeyDialogOpen below), just set on open and read by deleteKey().
// AlertDialogAction closes the dialog itself on click (reka-ui's DialogClose fires
// rootContext.onOpenChange(false) unconditionally, with no event.preventDefault escape hatch — see
// node_modules/reka-ui/src/Dialog/DialogClose.vue), and Vue may run that internal handler BEFORE
// this component's own @click="deleteKey" listener on the same click event. Previously both the
// dialog's open state AND the delete target lived in the same `confirmDeleteKey` ref, nulled by
// `@update:open` — so a click order where the internal close fired first nulled the target before
// deleteKey() ever read it, and its `if (!confirmDeleteKey.value) return` guard silently no-opped
// with zero API call. Splitting the target ref from the open boolean makes the fix independent of
// listener order entirely. Applied to every AlertDialog target in this file/ProjectSettingsView.vue.
const confirmDeleteKey = ref(null);
const deleteKeyDialogOpen = ref(false);
function openDeleteKeyDialog(key) {
  confirmDeleteKey.value = key;
  deleteKeyDialogOpen.value = true;
}
async function deleteKey() {
  const target = confirmDeleteKey.value;
  if (!target) return;
  try {
    await api.deleteSecret(props.projectId, target.id);
    keys.value = keys.value.filter((k) => k.id !== target.id);
    // A reference key's row IS the reference — deleting it only ever removes this project's link
    // to the source key, never the source key itself (a plain row delete can't cascade upward to
    // whatever it points at).
    toast.success(target.source_key_id ? 'Reference removed.' : 'Key deleted.');
  } catch (e) {
    toast.error(e.message);
  } finally {
    deleteKeyDialogOpen.value = false;
  }
}

// ── Edit key (name + description) ────────────────────────────────────────
const renameDialogOpen = ref(false);
const renameTargetKey = ref(null);
// Key names are charset-restricted server-side (nebula.naming.NAME_PATTERN — letters/digits/
// hyphens/underscores only, no whitespace at all), so a line break can never legitimately end up
// in one — but a plain <input> still happily accepts a pasted \n/\r into its value even though it
// never renders one. Stripping on write (not just on submit) keeps the field's on-screen state and
// its actual value in sync no matter how a line break got in — typed (impossible via a single Enter
// press, which submits the form instead) or pasted.
const renameValueRaw = ref('');
const renameValue = computed({
  get: () => renameValueRaw.value,
  set: (v) => {
    renameValueRaw.value = v.replace(/[\r\n]+/g, '');
  },
});
const renameDescription = ref('');
const renamingKey = ref(false);
function openRenameDialog(key) {
  renameTargetKey.value = key;
  renameValue.value = key.name;
  renameDescription.value = key.description || '';
  renameDialogOpen.value = true;
}
async function saveRename() {
  const target = renameTargetKey.value;
  const name = renameValue.value.trim();
  if (!target || !name) return;
  renamingKey.value = true;
  try {
    const updated = await api.updateSecret(props.projectId, target.id, {
      name,
      description: renameDescription.value.trim() || null,
    });
    const idx = keys.value.findIndex((k) => k.id === updated.id);
    if (idx !== -1) keys.value[idx] = updated;
    toast.success('Key updated.');
    renameDialogOpen.value = false;
  } catch (e) {
    toast.error(e.message);
  } finally {
    renamingKey.value = false;
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

// ── Copy value ────────────────────────────────────────────────────────────
// Environment variables are never anonymized, so their value is already in hand. A secret whose
// value hasn't been revealed yet is fetched on demand (same revealSecretValue call the Eye button
// uses, same canReveal gate below) and copied straight to the clipboard without populating
// `revealed` — a "quick copy" shouldn't force the plaintext to also appear on screen.
const copiedIds = reactive({});
async function copyValue(key) {
  try {
    const value =
      key.variable_type === 'environment'
        ? key.value
        : revealed[key.id] !== undefined
          ? revealed[key.id]
          : (await api.revealSecretValue(props.projectId, key.id)).value;
    await navigator.clipboard?.writeText(value);
    copiedIds[key.id] = true;
    setTimeout(() => delete copiedIds[key.id], 1500);
  } catch (e) {
    toast.error(e.message);
  }
}

// ── Set value ─────────────────────────────────────────────────────────────
// A Dialog now, not an inline Popover — same shared-modal shape as the Edit-key dialog below
// (openRenameDialog/renameTargetKey), so `editingKey` holds the whole row (needed to show its name/
// environment in the dialog title) rather than just an id.
const valueDialogOpen = ref(false);
const editingKey = ref(null);
const editingValue = ref('');
const savingValue = ref(false);
function openEditor(key) {
  editingKey.value = key;
  editingValue.value = '';
  valueDialogOpen.value = true;
}
function closeEditor() {
  valueDialogOpen.value = false;
}
async function saveValue() {
  const target = editingKey.value;
  if (!target) return;
  savingValue.value = true;
  try {
    const updated = await api.setSecretValue(props.projectId, target.id, { value: editingValue.value });
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
          <div class="relative">
            <PhMagnifyingGlass :size="14" weight="bold" class="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input v-model="keySearch" placeholder="Search keys…" class="h-8 w-64 pl-7 pr-7" />
            <button
              v-if="keySearch"
              type="button"
              title="Clear search"
              class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              @click="keySearch = ''"
            >
              <PhX :size="14" weight="bold" />
            </button>
          </div>
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
            class="hidden"
            @change="onEnvFileSelected"
          />
          <Button v-if="canEditValue && environments.length" variant="outline" @click="openEnvFilePicker">
            <PhUpload :size="16" weight="bold" /> Upload .env
          </Button>
          <Button v-if="environments.length && keys.length" variant="outline" @click="downloadEnvFile">
            <PhDownload :size="16" weight="bold" /> Download .env
          </Button>
          <Button v-if="canEdit && environments.length" @click="showKeyForm = !showKeyForm">
            <PhPlus :size="16" weight="bold" /> New key
          </Button>
        </div>
      </div>

      <Card v-if="showKeyForm" class="mb-4">
        <CardContent>
          <form @submit.prevent="addKey" class="space-y-4">
            <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              <div class="space-y-1.5">
                <Label for="new-key-name">Name</Label>
                <Input id="new-key-name" v-model="newKey.name" placeholder="KEY_NAME" required />
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
            </div>

            <div v-if="!canEditValue" class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
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
              <p class="sm:col-span-2 text-muted-foreground text-xs self-end">
                You can create the key now; an owner or admin will need to set its value.
              </p>
            </div>

            <Tabs v-else v-model="newKeyValueMode">
              <TabsList class="w-full max-w-md">
                <TabsTrigger value="direct" class="flex-1">Set value</TabsTrigger>
                <TabsTrigger value="reference" class="flex-1">Reference a secret</TabsTrigger>
              </TabsList>

              <TabsContent value="direct" class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-3">
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
                <div class="sm:col-span-2 space-y-1.5">
                  <Label for="new-key-value">Value (optional)</Label>
                  <Input id="new-key-value" v-model="newKey.value" placeholder="Leave blank to set a value later" class="font-mono" />
                </div>
              </TabsContent>

              <TabsContent value="reference" class="space-y-3 pt-3">
                <div class="grid sm:grid-cols-2 gap-3">
                  <div class="space-y-1.5">
                    <Label>Project</Label>
                    <Select v-model="referenceSourceProjectId">
                      <SelectTrigger class="w-full"><SelectValue placeholder="Select a project…" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem v-for="p in referenceSourceProjects" :key="p.id" :value="p.id">{{ p.name }}</SelectItem>
                      </SelectContent>
                    </Select>
                    <p v-if="!loadingReferenceSourceProjects && !referenceSourceProjects.length" class="text-muted-foreground text-xs">
                      You need reveal access on another project to reference one of its secrets.
                    </p>
                  </div>
                  <div class="space-y-1.5">
                    <Label>Secret</Label>
                    <Select v-model="referenceSourceKeyId" :disabled="!referenceSourceProjectId || loadingReferenceSourceKeys">
                      <SelectTrigger class="w-full"><SelectValue placeholder="Select a secret…" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem v-for="k in referenceSourceKeys" :key="k.id" :value="k.id">{{ k.name }}</SelectItem>
                      </SelectContent>
                    </Select>
                    <p
                      v-if="referenceSourceProjectId && !loadingReferenceSourceKeys && !referenceSourceKeys.length"
                      class="text-muted-foreground text-xs"
                    >
                      That project has no keys to reference yet.
                    </p>
                  </div>
                </div>
                <p class="text-muted-foreground text-xs">
                  This key will always mirror the referenced secret's current type and value — it can
                  only be changed in its source project, but it can still be renamed, reassigned to a
                  different environment here, and synced to GitHub like any other key.
                </p>
              </TabsContent>
            </Tabs>

            <div class="flex gap-2 justify-end">
              <Button type="button" variant="outline" @click="showKeyForm = false">Cancel</Button>
              <Button type="submit" :disabled="savingKey || !newKey.environment_id">Create</Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card v-if="!filteredKeys.length">
        <CardContent class="p-10 text-center text-muted-foreground text-sm">
          {{ !keys.length ? 'No keys yet.' : keySearch.trim() ? `No keys match "${keySearch.trim()}".` : 'No keys in this environment.' }}
        </CardContent>
      </Card>

      <Card v-else class="py-0">
        <TooltipProvider :delay-duration="200">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Key</TableHead>
              <TableHead>Environment</TableHead>
              <TableHead>Value</TableHead>
              <TableHead class="w-20">
                <div class="flex items-center gap-1.5">
                  <span>Sync</span>
                  <Switch
                    v-if="canEdit"
                    size="sm"
                    :model-value="allSyncEnabled"
                    :disabled="syncingToggle !== null"
                    title="Toggle sync for every visible key"
                    @update:model-value="toggleAllSync"
                  />
                </div>
              </TableHead>
              <TableHead class="w-16 text-right">Delete</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="key in filteredKeys" :key="key.id">
              <TableCell class="align-top">
                <div class="flex items-center gap-1.5">
                  <Tooltip v-if="key.extraction_count > 0">
                    <TooltipTrigger as="span" class="inline-flex shrink-0">
                      <PhInfo :size="13" weight="bold" class="text-info" />
                    </TooltipTrigger>
                    <TooltipContent>
                      Extracted {{ key.extraction_count }} time{{ key.extraction_count === 1 ? '' : 's' }}
                    </TooltipContent>
                  </Tooltip>
                  <Tooltip v-else>
                    <TooltipTrigger as="span" class="inline-flex shrink-0">
                      <PhWarning :size="13" weight="bold" class="text-warning" />
                    </TooltipTrigger>
                    <TooltipContent>This key has never been extracted</TooltipContent>
                  </Tooltip>
                  <span class="font-mono font-semibold">{{ key.name }}</span>
                  <Badge :variant="key.variable_type === 'secret' ? 'warning' : 'info'" class="text-[0.65rem] px-1.5 py-0">
                    {{ key.variable_type === 'secret' ? 'secret' : 'env var' }}
                  </Badge>
                  <Badge v-if="key.source_key_id" variant="accent" class="text-[0.65rem] px-1.5 py-0">
                    <PhLink :size="10" weight="bold" /> reference
                  </Badge>
                  <Button v-if="canEdit" variant="ghost" size="icon-xs" title="Edit key" @click="openRenameDialog(key)">
                    <PhPencilSimple :size="12" weight="bold" />
                  </Button>
                </div>
                <div v-if="key.description" class="text-muted-foreground text-xs mt-0.5">{{ key.description }}</div>
                <div v-if="key.source_key_id" class="text-muted-foreground text-xs mt-0.5 flex items-center gap-1">
                  <PhLink :size="11" weight="bold" class="shrink-0" />
                  <button
                    v-if="key.source_label && key.source_project_id"
                    type="button"
                    class="underline decoration-dotted hover:text-foreground text-left"
                    @click="emit('navigate', `/projects/${key.source_project_id}`)"
                  >
                    References {{ key.source_label }} — only changeable there
                  </button>
                  <span v-else>References a secret you no longer have access to</span>
                </div>
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

                  <Button
                    v-if="key.is_set && (key.variable_type === 'environment' || canReveal)"
                    variant="ghost"
                    size="icon-xs"
                    :title="copiedIds[key.id] ? 'Copied!' : 'Copy value'"
                    @click="copyValue(key)"
                  >
                    <PhCheck v-if="copiedIds[key.id]" :size="13" weight="bold" />
                    <PhCopy v-else :size="13" weight="bold" />
                  </Button>

                  <Button
                    v-if="canEditValue && !key.source_key_id"
                    variant="ghost"
                    size="icon-xs"
                    title="Set value"
                    @click="openEditor(key)"
                  >
                    <PhPencilSimple :size="13" weight="bold" />
                  </Button>
                </div>
              </TableCell>
              <TableCell class="align-top">
                <Switch
                  v-if="canEdit"
                  :model-value="key.sync_enabled"
                  :disabled="syncingToggle !== null"
                  :title="key.sync_enabled ? 'Synced to GitHub — click to pause' : 'Not synced to GitHub — click to resume'"
                  @update:model-value="(v) => toggleSync(key, v)"
                />
                <Badge v-else :variant="key.sync_enabled ? 'success' : 'outline'" class="text-[0.65rem] px-1.5 py-0">
                  {{ key.sync_enabled ? 'synced' : 'paused' }}
                </Badge>
              </TableCell>
              <TableCell class="align-top text-right">
                <Button v-if="canEdit" variant="destructive" size="icon-xs" title="Delete key" @click="openDeleteKeyDialog(key)">
                  <PhTrash :size="13" weight="bold" />
                </Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
        </TooltipProvider>
      </Card>
    </template>

    <Dialog :open="uploadDialogOpen" @update:open="(v) => !v && (uploadDialogOpen = false)">
      <DialogContent class="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{{ uploadItems.length }} variable{{ uploadItems.length === 1 ? '' : 's' }} found in file</DialogTitle>
          <DialogDescription>
            Choose the target environment, then pick a type and whether to import each key — this
            only ever creates new keys, never overwrites an existing one.
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-3">
          <div class="space-y-1.5">
            <Label for="upload-env">Environment</Label>
            <Select v-model="uploadEnvironmentId">
              <SelectTrigger id="upload-env" class="w-full"><SelectValue placeholder="Choose one" /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="env in environments" :key="env.id" :value="env.id">{{ env.name }}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div class="rounded-md border max-h-80 overflow-y-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead class="w-10">
                    <Checkbox
                      :model-value="uploadAllIncluded"
                      title="Select all"
                      @update:model-value="toggleUploadAll"
                    />
                  </TableHead>
                  <TableHead>Key</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead class="w-44">Type</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-for="item in uploadItems" :key="item.name" :class="{ 'opacity-50': !item.included }">
                  <TableCell>
                    <Checkbox v-model="item.included" :title="item.included ? 'Skip this key' : 'Import this key'" />
                  </TableCell>
                  <TableCell class="font-mono font-semibold">{{ item.name }}</TableCell>
                  <TableCell class="font-mono text-muted-foreground max-w-56 truncate" :title="item.value">
                    {{ item.value || '—' }}
                  </TableCell>
                  <TableCell>
                    <Select v-model="item.variable_type" :disabled="!item.included">
                      <SelectTrigger size="sm" class="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="secret">Secret</SelectItem>
                        <SelectItem value="environment">Environment variable</SelectItem>
                      </SelectContent>
                    </Select>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="uploadDialogOpen = false">Cancel</Button>
          <Button :disabled="uploadSubmitting || !uploadEnvironmentId || !uploadIncludedCount" @click="confirmUpload">
            Add {{ uploadIncludedCount }} variable{{ uploadIncludedCount === 1 ? '' : 's' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <AlertDialog :open="deleteKeyDialogOpen" @update:open="(v) => (deleteKeyDialogOpen = v)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{{ confirmDeleteKey?.source_key_id ? 'Remove this reference?' : 'Delete this key?' }}</AlertDialogTitle>
          <AlertDialogDescription v-if="confirmDeleteKey?.source_key_id">
            This only removes '{{ confirmDeleteKey?.name }}' from this project — the secret it
            references ({{ confirmDeleteKey?.source_label || 'in its source project' }}) is not
            affected and is not deleted.
          </AlertDialogDescription>
          <AlertDialogDescription v-else>
            This permanently removes '{{ confirmDeleteKey?.name }}' and its value. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="deleteKey">{{ confirmDeleteKey?.source_key_id ? 'Remove reference' : 'Delete' }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <Dialog :open="renameDialogOpen" @update:open="(v) => (renameDialogOpen = v)">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit key</DialogTitle>
          <DialogDescription>References to '{{ renameTargetKey?.name }}' by name (e.g. external API lookups) must be updated separately.</DialogDescription>
        </DialogHeader>
        <form @submit.prevent="saveRename" class="space-y-3">
          <div class="space-y-1.5">
            <Label for="rename-key-name">Name</Label>
            <Input id="rename-key-name" v-model="renameValue" required class="font-mono" />
          </div>
          <div class="space-y-1.5">
            <Label for="rename-key-description">Description</Label>
            <Textarea id="rename-key-description" v-model="renameDescription" placeholder="Description (optional)" rows="3" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" @click="renameDialogOpen = false">Cancel</Button>
            <Button type="submit" :disabled="renamingKey || !renameValue.trim()">Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>

    <Dialog :open="valueDialogOpen" @update:open="(v) => (valueDialogOpen = v)">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Set value</DialogTitle>
          <DialogDescription>{{ editingKey?.name }} — {{ editingKey?.environment_name }}</DialogDescription>
        </DialogHeader>
        <form @submit.prevent="saveValue" class="space-y-3">
          <div class="space-y-1.5">
            <Label for="edit-value">Value</Label>
            <Input id="edit-value" v-model="editingValue" placeholder="value" autofocus class="font-mono" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" @click="valueDialogOpen = false">Cancel</Button>
            <Button type="submit" :disabled="savingValue">Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </div>
</template>
