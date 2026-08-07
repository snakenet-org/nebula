<!--
  @ai-purpose: Admin-only Audit Logs page — every mutating action taken through Nebula.
  @ai-context: Three tabs, mirroring nebula.audit's three query helpers: "Activity" (logged-in
    humans — project/environment/secret CRUD, sharing, access keys, login/logout, reveal),
    "API calls" (Project access keys hitting ANY api/v1/vault.py route — /secret, /project,
    /status, see nebula.audit.VAULT_ACTIONS — every attempt, success or not), "Failed retrievals"
    (the success=False subset of API calls, across all three vault routes — the same rows the
    Dashboard's "Failed attempts / day" chart counts, shown here as a readable list instead of a
    chart). The page itself is reachable from the sidebar only for an admin (App.vue) and every
    /api/v1/audit/* route 403s a non-admin server-side too — this view does no client-side gating
    beyond simply not rendering for a non-admin caller (the parent already hides the nav entry).
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, table, badge, tabs, skeleton)
  @version: 1.0.1
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-07
-->
<script setup>
import { onMounted, ref } from 'vue';
import { PhScroll } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';

const activity = ref([]);
const apiCalls = ref([]);
const failedRetrievals = ref([]);
const loading = ref(true);

async function load() {
  loading.value = true;
  try {
    [activity.value, apiCalls.value, failedRetrievals.value] = await Promise.all([
      api.listAuditActivity(),
      api.listAuditApiCalls(),
      api.listAuditFailedRetrievals(),
    ]);
  } catch (e) {
    toast.error(e.message);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function formatTime(iso) {
  return new Date(iso + 'Z').toLocaleString();
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 w-full">
    <div class="mb-6">
      <h1 class="text-2xl font-bold flex items-center gap-2"><PhScroll :size="22" weight="bold" /> Audit logs</h1>
      <p class="text-muted-foreground text-sm mt-1">Every action taken through Nebula Vault. Admin only.</p>
    </div>

    <div v-if="loading" class="space-y-3">
      <Skeleton class="h-12 rounded-xl" v-for="i in 5" :key="i" />
    </div>

    <Tabs v-else default-value="activity">
      <TabsList>
        <TabsTrigger value="activity">Activity ({{ activity.length }})</TabsTrigger>
        <TabsTrigger value="api-calls">API calls ({{ apiCalls.length }})</TabsTrigger>
        <TabsTrigger value="failed">Failed retrievals ({{ failedRetrievals.length }})</TabsTrigger>
      </TabsList>

      <TabsContent value="activity" class="pt-4">
        <Card v-if="!activity.length"><CardContent class="p-10 text-center text-muted-foreground text-sm">No activity recorded yet.</CardContent></Card>
        <Card v-else class="py-0">
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
              <TableRow v-for="row in activity" :key="row.id">
                <TableCell class="text-muted-foreground text-xs whitespace-nowrap">{{ formatTime(row.occurred_at) }}</TableCell>
                <TableCell class="font-medium">{{ row.actor_label || 'unknown' }}</TableCell>
                <TableCell><code class="font-mono text-xs">{{ row.action }}</code></TableCell>
                <TableCell class="text-muted-foreground text-sm">{{ row.object_label || '—' }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      </TabsContent>

      <TabsContent value="api-calls" class="pt-4">
        <Card v-if="!apiCalls.length"><CardContent class="p-10 text-center text-muted-foreground text-sm">No API calls recorded yet.</CardContent></Card>
        <Card v-else class="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Access key</TableHead>
                <TableHead>Key@Environment</TableHead>
                <TableHead>Result</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="row in apiCalls" :key="row.id">
                <TableCell class="text-muted-foreground text-xs whitespace-nowrap">{{ formatTime(row.occurred_at) }}</TableCell>
                <TableCell class="font-medium">{{ row.actor_label || 'unknown' }}</TableCell>
                <TableCell class="font-mono text-xs">{{ row.object_label || '—' }}</TableCell>
                <TableCell>
                  <Badge :variant="row.success ? 'success' : 'destructive'">{{ row.success ? 'ok' : 'failed' }}</Badge>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      </TabsContent>

      <TabsContent value="failed" class="pt-4">
        <Card v-if="!failedRetrievals.length"><CardContent class="p-10 text-center text-muted-foreground text-sm">No failed retrievals — good sign.</CardContent></Card>
        <Card v-else class="py-0">
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
              <TableRow v-for="row in failedRetrievals" :key="row.id">
                <TableCell class="text-muted-foreground text-xs whitespace-nowrap">{{ formatTime(row.occurred_at) }}</TableCell>
                <TableCell class="font-medium">{{ row.actor_label || 'unknown' }}</TableCell>
                <TableCell class="font-mono text-xs">{{ row.object_label || '—' }}</TableCell>
                <TableCell class="text-muted-foreground text-sm">{{ row.detail || '—' }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      </TabsContent>
    </Tabs>
  </div>
</template>
