<!--
  @ai-purpose: Shared sub-nav for a Project's settings area — a "Back to project" link plus a row of
  buttons switching between the three distinct settings views (General/Access Management/Git-Sync).
  Used identically by ProjectGeneralSettingsView/ProjectAccessManagementView/ProjectGitSyncView so
  the three pages read as one consistent settings area (each reachable directly by URL) rather than
  unrelated pages, and so a user browsing one section can jump straight to another without
  detouring back through the Project page first.
  @ai-context: Settings used to be a single ProjectSettingsView.vue (Details/Sharing/API keys/GitHub
    sync/Danger zone all as Cards on one page) — split apart per product ask into routes under
    `/projects/:id/settings...`: `/settings` (bare, no suffix — General, kept as the default path so
    existing links/bookmarks to plain `/settings` still resolve), `/settings/access`,
    `/settings/git-sync`. See App.vue's `settingsSection` computed for the routing side of this
    split. Sharing and Access keys were briefly two SEPARATE views/routes
    (`/settings/sharing`/`/settings/access-keys`) the same day, then merged back into one
    `/settings/access` per a same-day follow-up ask — both share the exact same owner/admin/editor
    permission tier, so one "Access Management" page reads more naturally than two near-identical
    ones.
  @dependencies: vue, @phosphor-icons/vue, shadcn-vue (button)
  @version: 2.0.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-27
-->
<script setup>
import { PhArrowLeft, PhGearSix, PhGithubLogo, PhUsers } from '@phosphor-icons/vue';
import { Button } from '@/components/ui/button';

defineProps({
  projectId: { type: String, required: true },
  active: { type: String, required: true }, // 'general' | 'access' | 'git-sync'
});
const emit = defineEmits(['navigate']);

const sections = [
  { key: 'general', label: 'General settings', icon: PhGearSix, path: 'settings' },
  { key: 'access', label: 'Access Management', icon: PhUsers, path: 'settings/access' },
  { key: 'git-sync', label: 'Git-Sync', icon: PhGithubLogo, path: 'settings/git-sync' },
];
</script>

<template>
  <div class="mb-6">
    <Button variant="link" class="px-0 mb-4 text-sm" @click="emit('navigate', `/projects/${projectId}`)">
      <PhArrowLeft :size="14" weight="bold" /> Back to project
    </Button>
    <div class="flex flex-wrap gap-2">
      <Button
        v-for="s in sections"
        :key="s.key"
        :variant="active === s.key ? 'default' : 'outline'"
        size="sm"
        @click="emit('navigate', `/projects/${projectId}/${s.path}`)"
      >
        <component :is="s.icon" :size="14" weight="bold" /> {{ s.label }}
      </Button>
    </div>
  </div>
</template>
