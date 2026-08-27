<!--
  @ai-purpose: System Settings — four admin-only, vault-wide danger zones: reset all data, reset
    logs, import vault, export vault. Reached only from App.vue's sidebar (admin-only nav entry).
  @ai-context: Backend is api/v1/system.py (nebula.system_admin/nebula.vault_transfer) — every route
    there independently re-checks `actor.is_admin` (403 otherwise), this view's own `isAdmin` gate is
    purely a UI convenience, same "backend is the real gate, frontend only hides controls" shape as
    ProjectSettingsView.vue's `canManage`.
    Two red zones (Reset all data / Reset logs) reuse the existing `destructive` Button variant +
    `border-destructive/30` Card, same as ProjectSettingsView.vue's own Danger zone card. The two
    orange zones (Import/Export vault) use a new `warning` Button variant (components/ui/button/
    index.js, added this session — same bg/10+hover/20+text shape as Badge's pre-existing `warning`
    variant, just not previously needed on a Button) + `border-warning/30` Card.
    All four are confirmed via a plain boolean-ref AlertDialog (confirmResetData/confirmResetLogs/
    confirmImport) — no per-item target ref needed (unlike ProjectSettingsView's confirmRevokeShare/
    confirmRevokeKey), since every action here targets "the whole vault," not a specific row.
    Import: a hidden native `<input type="file">` (triggered by a Button, not a shadcn Input — v-model
    doesn't work on a file input) picks a `.json` file; its selected name is shown before the actual
    Import button (disabled until a file is chosen) opens the confirm dialog. The file is read
    client-side via File.text() + JSON.parse — a parse failure surfaces as a toast, never sent to the
    backend, which does its own Pydantic-level validation of the shape (VaultExport) regardless.
    Export triggers a Blob/object-URL download (same pattern as ProjectView.vue's downloadEnvFile) of
    exactly the JSON api.exportVault() returns — re-uploading that same file via Import is a
    supported round-trip (POST /system/import accepts the exact VaultExport shape GET /system/export
    returns).
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, button, alert-dialog)
  @version: 1.1.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-13
-->
<script setup>
import { computed, ref } from 'vue';
import {
  PhDatabase,
  PhDownloadSimple,
  PhScroll,
  PhTrash,
  PhUploadSimple,
  PhWarning,
} from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { useAuth } from '../composables/useAuth';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

const emit = defineEmits(['navigate']);

const { state: auth } = useAuth();
const isAdmin = computed(() => !!auth.session?.user?.isAdmin);

function pluralize(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

// ── Reset all data ───────────────────────────────────────────────────────
const resettingData = ref(false);
const confirmResetData = ref(false);
async function resetAllData() {
  resettingData.value = true;
  try {
    const result = await api.resetSystemData();
    confirmResetData.value = false;
    toast.success(
      `Vault reset: ${pluralize(result.projects_deleted, 'project')}, ` +
        `${pluralize(result.environments_deleted, 'environment')}, and ` +
        `${pluralize(result.audit_logs_deleted, 'log entry', 'log entries')} removed.`
    );
    emit('navigate', '/');
  } catch (e) {
    toast.error(e.message);
  } finally {
    resettingData.value = false;
  }
}

// ── Reset logs ────────────────────────────────────────────────────────────
const resettingLogs = ref(false);
const confirmResetLogs = ref(false);
async function resetLogs() {
  resettingLogs.value = true;
  try {
    const result = await api.resetSystemLogs();
    confirmResetLogs.value = false;
    toast.success(`Cleared ${pluralize(result.audit_logs_deleted, 'audit log entry', 'audit log entries')}.`);
  } catch (e) {
    toast.error(e.message);
  } finally {
    resettingLogs.value = false;
  }
}

// ── Export vault ──────────────────────────────────────────────────────────
const exporting = ref(false);
async function exportVault() {
  exporting.value = true;
  try {
    const data = await api.exportVault();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `nebula-vault-export-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast.success(`Exported ${pluralize(data.projects.length, 'project')} and ${pluralize(data.environments.length, 'environment')}.`);
  } catch (e) {
    toast.error(e.message);
  } finally {
    exporting.value = false;
  }
}

// ── Import vault ──────────────────────────────────────────────────────────
const importFileInput = ref(null);
const importFile = ref(null);
const importing = ref(false);
const confirmImport = ref(false);

function pickImportFile() {
  importFileInput.value?.click();
}
function onImportFileSelected(event) {
  importFile.value = event.target.files?.[0] || null;
  event.target.value = ''; // allow re-picking the same file later (e.g. after a failed import)
}
async function runImport() {
  const file = importFile.value;
  if (!file) return;
  importing.value = true;
  try {
    const text = await file.text();
    let parsed;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new Error('That file is not valid JSON.');
    }
    const summary = await api.importVault(parsed);
    confirmImport.value = false;
    importFile.value = null;
    let message =
      `Imported ${pluralize(summary.projects_created, 'project')}, ${pluralize(summary.keys_created, 'key')}. ` +
      `Environments: ${summary.environments_created} created, ${summary.environments_reused} reused.`;
    if (summary.references_skipped) {
      message += ` ${pluralize(summary.references_skipped, 'reference')} could not be resolved.`;
    }
    toast.success(message);
    emit('navigate', '/projects');
  } catch (e) {
    toast.error(e.message);
  } finally {
    importing.value = false;
  }
}
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 py-8 w-full">
    <h1 class="text-2xl font-bold mb-1">System Settings</h1>
    <p class="text-muted-foreground text-sm mb-6 flex items-center gap-1.5">
      <PhWarning :size="14" weight="bold" /> Admin-only. Each of these acts on the entire vault, across every project and every user.
    </p>

    <template v-if="isAdmin">
      <div class="space-y-6">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card class="border-warning/30">
            <CardContent>
              <h2 class="font-semibold mb-1 text-warning flex items-center gap-2">
                <PhUploadSimple :size="18" weight="bold" /> Import vault
              </h2>
              <p class="text-muted-foreground text-sm mb-4">
                Restores a full vault export — environments, projects, keys, secrets, and variables,
                with all their settings — from a JSON file produced by Export vault. Every imported
                project is created brand-new and owned by <strong>you</strong>, regardless of who
                owned it in the original export. Existing projects are never modified or removed.
              </p>
              <input
                ref="importFileInput"
                type="file"
                accept="application/json,.json"
                class="hidden"
                @change="onImportFileSelected"
              />
              <div class="flex items-center gap-2 flex-wrap">
                <Button type="button" variant="outline" :disabled="importing" @click="pickImportFile">
                  Choose file…
                </Button>
                <span v-if="importFile" class="text-sm text-muted-foreground font-mono">{{ importFile.name }}</span>
                <Button
                  type="button"
                  variant="warning"
                  :disabled="!importFile || importing"
                  @click="confirmImport = true"
                >
                  <PhUploadSimple :size="16" weight="bold" /> Import
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card class="border-warning/30">
            <CardContent>
              <h2 class="font-semibold mb-1 text-warning flex items-center gap-2">
                <PhDownloadSimple :size="18" weight="bold" /> Export vault
              </h2>
              <p class="text-muted-foreground text-sm mb-4">
                Downloads a full backup of every environment, project, key, secret, and variable — with
                all their settings — as a JSON file. <strong>The file contains decrypted, plaintext
                secret values</strong> — store and transmit it as carefully as the secrets themselves.
              </p>
              <Button type="button" variant="warning" :disabled="exporting" @click="exportVault">
                <PhDownloadSimple :size="16" weight="bold" /> Export vault
              </Button>
            </CardContent>
          </Card>
        </div>

        <Card class="border-destructive/30">
          <CardContent>
            <h2 class="font-semibold mb-1 text-destructive flex items-center gap-2">
              <PhDatabase :size="18" weight="bold" /> Reset all data
            </h2>
            <p class="text-muted-foreground text-sm mb-4">
              Permanently deletes every project, key, value, share, access key, and GitHub sync
              target across the whole vault, every environment, and clears the audit log. User
              accounts are not affected. This cannot be undone.
            </p>
            <Button variant="destructive" :disabled="resettingData" @click="confirmResetData = true">
              <PhTrash :size="16" weight="bold" /> Reset all data
            </Button>
          </CardContent>
        </Card>

        <Card class="border-destructive/30">
          <CardContent>
            <h2 class="font-semibold mb-1 text-destructive flex items-center gap-2">
              <PhScroll :size="18" weight="bold" /> Reset logs
            </h2>
            <p class="text-muted-foreground text-sm mb-4">
              Permanently clears every audit log entry — activity, API calls, and failed retrievals —
              across every project. Projects, environments, and keys are not affected. This cannot be
              undone.
            </p>
            <Button variant="destructive" :disabled="resettingLogs" @click="confirmResetLogs = true">
              <PhTrash :size="16" weight="bold" /> Clear audit logs
            </Button>
          </CardContent>
        </Card>
      </div>
    </template>

    <Card v-else>
      <CardContent class="text-muted-foreground text-sm">You don't have permission to view this page.</CardContent>
    </Card>

    <AlertDialog :open="confirmResetData" @update:open="(v) => !v && (confirmResetData = false)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Reset all data?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently deletes EVERY project, key, value, share, access key, and GitHub sync
            target belonging to EVERY user, every environment, and the entire audit log. This cannot
            be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" :disabled="resettingData" @click="resetAllData">
            Reset everything
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <AlertDialog :open="confirmResetLogs" @update:open="(v) => !v && (confirmResetLogs = false)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Clear all audit logs?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently deletes every audit log entry across every project. This cannot be
            undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="destructive" :disabled="resettingLogs" @click="resetLogs">
            Clear logs
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <AlertDialog :open="confirmImport" @update:open="(v) => !v && (confirmImport = false)">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Import '{{ importFile?.name }}'?</AlertDialogTitle>
          <AlertDialogDescription>
            Every project in this file will be created as a brand-new project owned by you. Existing
            projects are never modified or removed.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction variant="warning" :disabled="importing" @click="runImport">
            Import
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
