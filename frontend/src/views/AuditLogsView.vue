<!--
  @ai-purpose: Audit Logs page — every mutating action taken through Nebula.
  @ai-context: Three tabs, mirroring nebula.audit's three query helpers: "Activity" (logged-in
    humans — project/environment/secret CRUD, sharing, access keys, login/logout, reveal),
    "API calls" (Project access keys hitting ANY api/v1/vault.py route — /secret, /project,
    /status, see nebula.audit.VAULT_ACTIONS — every attempt, success or not), "Failed retrievals"
    (the success=False subset of API calls, across all three vault routes — the same rows the
    Dashboard's "Failed attempts / day" chart counts, shown here as a readable list instead of a
    chart). 2026-08-12 (GitHub #4): reachable from the sidebar for ANY authenticated user, not just
    an admin — api/v1/audit.py itself decides how much each caller sees: an admin gets every row
    app-wide, a non-admin only the rows belonging to a Project they own or are an EDITOR share on
    (nebula.projects.list_editable_project_ids) — this view does no client-side filtering of its
    own, it just renders whatever the (already correctly scoped) API response contains.
    2026-08-12 (later same day): each tab now has its OWN search box + pagination — the log can run
    to thousands of rows, so a bare unfiltered list no longer scales. `search` is free-text, OR'd
    server-side across actor (user)/action/key (object_label)/project — see
    nebula.audit._search_condition, debounced 300ms here before firing a new request (and resetting
    back to page 1, since a new search invalidates the old page's meaning). Pages are capped at
    PAGE_SIZE=300 (nebula.audit.MAX_PAGE_SIZE) — Prev/Next only render once a tab actually has more
    than one page. Each tab keeps independent { items, total, page, search, loading } state
    (`tabs` below) and reloads only itself on search/page change, not its siblings. The "API calls"
    tab also gained a Project column (`row.project_label`, captured at write time in
    nebula.audit/api/v1/vault.py — see models.tables.AuditLogEntry.project_label) alongside the
    existing Access key column (`row.actor_label`, already the key's own name) — together they
    answer "which access key, from which Project" without parsing the Key@Environment string.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, table, badge, tabs, skeleton, input, button)
  @version: 3.0.0
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-12
-->
<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { PhCaretLeft, PhCaretRight, PhMagnifyingGlass, PhScroll } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { useAuth } from '../composables/useAuth';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

const { state: auth } = useAuth();
const isAdmin = computed(() => !!auth.session?.user?.isAdmin);

// The Audit Logs page's hard per-page cap — matches nebula.audit.MAX_PAGE_SIZE, enforced again
// server-side regardless of what's requested here.
const PAGE_SIZE = 300;
const SEARCH_DEBOUNCE_MS = 300;

const TAB_DEFS = [
  { key: 'activity', label: 'Activity', loader: api.listAuditActivity, empty: 'No activity recorded yet.' },
  { key: 'api-calls', label: 'API calls', loader: api.listAuditApiCalls, empty: 'No API calls recorded yet.' },
  {
    key: 'failed',
    label: 'Failed retrievals',
    loader: api.listAuditFailedRetrievals,
    empty: 'No failed retrievals — good sign.',
  },
];

function makeTabState() {
  return reactive({ items: [], total: 0, page: 1, search: '', loading: true });
}
const tabs = reactive(Object.fromEntries(TAB_DEFS.map((t) => [t.key, makeTabState()])));
const initialLoading = ref(true);
const debounceTimers = {};

async function loadTab(key) {
  const def = TAB_DEFS.find((t) => t.key === key);
  const state = tabs[key];
  state.loading = true;
  try {
    const res = await def.loader({ search: state.search, page: state.page, pageSize: PAGE_SIZE });
    state.items = res.items;
    state.total = res.total;
  } catch (e) {
    toast.error(e.message);
  } finally {
    state.loading = false;
  }
}

function totalPages(state) {
  return Math.max(1, Math.ceil(state.total / PAGE_SIZE));
}

function goToPage(key, page) {
  const state = tabs[key];
  const next = Math.min(Math.max(page, 1), totalPages(state));
  if (next === state.page) return;
  state.page = next;
  loadTab(key);
}

function onSearchInput(key) {
  clearTimeout(debounceTimers[key]);
  debounceTimers[key] = setTimeout(() => {
    tabs[key].page = 1;
    loadTab(key);
  }, SEARCH_DEBOUNCE_MS);
}

onBeforeUnmount(() => {
  Object.values(debounceTimers).forEach(clearTimeout);
});

onMounted(async () => {
  try {
    await Promise.all(TAB_DEFS.map((t) => loadTab(t.key)));
  } finally {
    initialLoading.value = false;
  }
});

function formatTime(iso) {
  return new Date(iso + 'Z').toLocaleString();
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 w-full">
    <div class="mb-6">
      <h1 class="text-2xl font-bold flex items-center gap-2"><PhScroll :size="22" weight="bold" /> Audit logs</h1>
      <p class="text-muted-foreground text-sm mt-1">
        {{ isAdmin ? 'Every action taken through Nebula Vault.' : 'Actions on projects you own or edit.' }}
      </p>
    </div>

    <div v-if="initialLoading" class="space-y-3">
      <Skeleton class="h-12 rounded-xl" v-for="i in 5" :key="i" />
    </div>

    <Tabs v-else default-value="activity">
      <TabsList>
        <TabsTrigger v-for="t in TAB_DEFS" :key="t.key" :value="t.key">
          {{ t.label }} ({{ tabs[t.key].total }})
        </TabsTrigger>
      </TabsList>

      <TabsContent value="activity" class="pt-4 space-y-3">
        <div class="relative max-w-sm">
          <PhMagnifyingGlass :size="16" weight="bold" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            v-model="tabs.activity.search"
            @input="onSearchInput('activity')"
            placeholder="Search by user, action, or key…"
            class="pl-9"
          />
        </div>
        <Card v-if="!tabs.activity.items.length"><CardContent class="p-10 text-center text-muted-foreground text-sm">{{ tabs.activity.search ? `No activity matches "${tabs.activity.search}".` : 'No activity recorded yet.' }}</CardContent></Card>
        <Card v-else class="py-0" :class="{ 'opacity-60': tabs.activity.loading }">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>User</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Object</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="row in tabs.activity.items" :key="row.id">
                <TableCell class="text-muted-foreground text-xs whitespace-nowrap">{{ formatTime(row.occurred_at) }}</TableCell>
                <TableCell class="font-medium">{{ row.actor_label || 'unknown' }}</TableCell>
                <TableCell><code class="font-mono text-xs">{{ row.action }}</code></TableCell>
                <TableCell class="text-muted-foreground text-sm">{{ row.object_label || '—' }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
        <div v-if="tabs.activity.total > PAGE_SIZE" class="flex items-center justify-between text-sm text-muted-foreground">
          <span>Page {{ tabs.activity.page }} of {{ totalPages(tabs.activity) }} ({{ tabs.activity.total }} total)</span>
          <div class="flex gap-2">
            <Button variant="outline" size="sm" :disabled="tabs.activity.page <= 1" @click="goToPage('activity', tabs.activity.page - 1)">
              <PhCaretLeft :size="14" weight="bold" /> Prev
            </Button>
            <Button variant="outline" size="sm" :disabled="tabs.activity.page >= totalPages(tabs.activity)" @click="goToPage('activity', tabs.activity.page + 1)">
              Next <PhCaretRight :size="14" weight="bold" />
            </Button>
          </div>
        </div>
      </TabsContent>

      <TabsContent value="api-calls" class="pt-4 space-y-3">
        <div class="relative max-w-sm">
          <PhMagnifyingGlass :size="16" weight="bold" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            v-model="tabs['api-calls'].search"
            @input="onSearchInput('api-calls')"
            placeholder="Search by access key, action, key, or project…"
            class="pl-9"
          />
        </div>
        <Card v-if="!tabs['api-calls'].items.length"><CardContent class="p-10 text-center text-muted-foreground text-sm">{{ tabs['api-calls'].search ? `No API calls match "${tabs['api-calls'].search}".` : 'No API calls recorded yet.' }}</CardContent></Card>
        <Card v-else class="py-0" :class="{ 'opacity-60': tabs['api-calls'].loading }">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Access key</TableHead>
                <TableHead>Project</TableHead>
                <TableHead>Key@Environment</TableHead>
                <TableHead>Result</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="row in tabs['api-calls'].items" :key="row.id">
                <TableCell class="text-muted-foreground text-xs whitespace-nowrap">{{ formatTime(row.occurred_at) }}</TableCell>
                <TableCell class="font-medium">{{ row.actor_label || 'unknown' }}</TableCell>
                <TableCell class="text-muted-foreground text-sm">{{ row.project_label || '—' }}</TableCell>
                <TableCell class="font-mono text-xs">{{ row.object_label || '—' }}</TableCell>
                <TableCell>
                  <Badge :variant="row.success ? 'success' : 'destructive'">{{ row.success ? 'ok' : 'failed' }}</Badge>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
        <div v-if="tabs['api-calls'].total > PAGE_SIZE" class="flex items-center justify-between text-sm text-muted-foreground">
          <span>Page {{ tabs['api-calls'].page }} of {{ totalPages(tabs['api-calls']) }} ({{ tabs['api-calls'].total }} total)</span>
          <div class="flex gap-2">
            <Button variant="outline" size="sm" :disabled="tabs['api-calls'].page <= 1" @click="goToPage('api-calls', tabs['api-calls'].page - 1)">
              <PhCaretLeft :size="14" weight="bold" /> Prev
            </Button>
            <Button variant="outline" size="sm" :disabled="tabs['api-calls'].page >= totalPages(tabs['api-calls'])" @click="goToPage('api-calls', tabs['api-calls'].page + 1)">
              Next <PhCaretRight :size="14" weight="bold" />
            </Button>
          </div>
        </div>
      </TabsContent>

      <TabsContent value="failed" class="pt-4 space-y-3">
        <div class="relative max-w-sm">
          <PhMagnifyingGlass :size="16" weight="bold" class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            v-model="tabs.failed.search"
            @input="onSearchInput('failed')"
            placeholder="Search by access key, action, or key…"
            class="pl-9"
          />
        </div>
        <Card v-if="!tabs.failed.items.length"><CardContent class="p-10 text-center text-muted-foreground text-sm">{{ tabs.failed.search ? `No failed retrievals match "${tabs.failed.search}".` : 'No failed retrievals — good sign.' }}</CardContent></Card>
        <Card v-else class="py-0" :class="{ 'opacity-60': tabs.failed.loading }">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Access key</TableHead>
                <TableHead>Key@Environment</TableHead>
                <TableHead>Reason</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="row in tabs.failed.items" :key="row.id">
                <TableCell class="text-muted-foreground text-xs whitespace-nowrap">{{ formatTime(row.occurred_at) }}</TableCell>
                <TableCell class="font-medium">{{ row.actor_label || 'unknown' }}</TableCell>
                <TableCell class="font-mono text-xs">{{ row.object_label || '—' }}</TableCell>
                <TableCell class="text-muted-foreground text-sm">{{ row.detail || '—' }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
        <div v-if="tabs.failed.total > PAGE_SIZE" class="flex items-center justify-between text-sm text-muted-foreground">
          <span>Page {{ tabs.failed.page }} of {{ totalPages(tabs.failed) }} ({{ tabs.failed.total }} total)</span>
          <div class="flex gap-2">
            <Button variant="outline" size="sm" :disabled="tabs.failed.page <= 1" @click="goToPage('failed', tabs.failed.page - 1)">
              <PhCaretLeft :size="14" weight="bold" /> Prev
            </Button>
            <Button variant="outline" size="sm" :disabled="tabs.failed.page >= totalPages(tabs.failed)" @click="goToPage('failed', tabs.failed.page + 1)">
              Next <PhCaretRight :size="14" weight="bold" />
            </Button>
          </div>
        </div>
      </TabsContent>
    </Tabs>
  </div>
</template>
