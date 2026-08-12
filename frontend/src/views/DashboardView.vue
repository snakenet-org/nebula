<!--
  @ai-purpose: Dashboard — the new home/start page. Stat cards + daily API-request/extraction/
    failure charts.
  @ai-context: Counts/series (nebula.dashboard.summary_counts/extraction_series) are system-wide for
    an admin, but scoped to the caller's own owned+editor Projects for a non-admin (GitHub #4,
    api/v1/dashboard.py resolves the scope server-side via
    nebula.projects.list_editable_project_ids) — see that module's docstring for exactly what each
    stat means once scoped (environment_count in particular becomes "distinct Environments actually
    used by my Projects' keys", not the global Environment count). This view does no scoping itself,
    it only renders whatever the API already returned. Three single-series charts (never one
    dual-axis chart — different metrics, different scales): API requests (EVERY call to ANY
    api/v1/vault.py route — /secret, /project, /status — by a Project access key, success or not,
    renamed from "API extractions" 2026-08-07 to reflect that it's no longer /secret-only), frontend
    extractions (a logged-in human's successful secret.reveal), and failed attempts (the same
    vault.py routes' success=False rows, across all three — this is also exactly what the Audit Logs
    page's "Failed retrievals" tab lists row-by-row). Every authenticated user sees this page;
    project browsing moved to its own /projects route (HomeView.vue, unchanged) now that / is the
    Dashboard.
    2026-08-12 (theme rebase): the three chart line colors were recolored from the old light-blue/
    gold/rose palette to the new baseline brand colors (Starlight Cyan/Solar Gold) and the universal
    destructive red, matching style.css's rebased tokens — cosmetic only, no data/scoping change.
  @dependencies: vue, vue-sonner, @phosphor-icons/vue, shadcn-vue (card, skeleton)
  @version: 1.2.1
  @author: Marc Fiedler <marc@snakenet.org>
  @date: 2026-08-12
-->
<script setup>
import { computed, onMounted, ref } from 'vue';
import { PhFolders, PhKey, PhLockKey, PhStack, PhWarning } from '@phosphor-icons/vue';
import { toast } from 'vue-sonner';
import * as api from '../services/api';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import DailyLineChart from '../components/DailyLineChart.vue';

const loading = ref(true);
const summary = ref(null);
const series = ref(null);

async function load() {
  loading.value = true;
  try {
    [summary.value, series.value] = await Promise.all([api.getDashboardSummary(), api.getDashboardSeries()]);
  } catch (e) {
    toast.error(e.message);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

function toPoints(dict) {
  return Object.entries(dict || {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, value]) => ({ date, value }));
}

const apiPoints = computed(() => toPoints(series.value?.api_requests));
const frontendPoints = computed(() => toPoints(series.value?.frontend_extractions));
const failedPoints = computed(() => toPoints(series.value?.failed_attempts));

const cards = computed(() => [
  { label: 'Environments', value: summary.value?.environment_count ?? 0, icon: PhStack },
  { label: 'Projects', value: summary.value?.project_count ?? 0, icon: PhFolders },
  { label: 'Variables', value: summary.value?.variable_count ?? 0, icon: PhKey },
  { label: 'Secrets', value: summary.value?.secret_count ?? 0, icon: PhLockKey },
]);
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-8 w-full">
    <div class="mb-6">
      <h1 class="text-2xl font-bold">Dashboard</h1>
      <p class="text-muted-foreground text-sm mt-1">An overview of Nebula Vault.</p>
    </div>

    <div v-if="loading" class="space-y-6">
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Skeleton class="h-24 rounded-xl" v-for="i in 4" :key="i" />
      </div>
      <div class="grid lg:grid-cols-3 gap-4">
        <Skeleton class="h-48 rounded-xl" v-for="i in 3" :key="i" />
      </div>
    </div>

    <template v-else>
      <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card v-for="c in cards" :key="c.label">
          <CardContent class="flex items-center gap-3">
            <div class="rounded-lg bg-primary/10 text-primary p-2.5">
              <component :is="c.icon" :size="20" weight="bold" />
            </div>
            <div>
              <div class="text-2xl font-bold leading-none">{{ c.value }}</div>
              <div class="text-muted-foreground text-xs mt-1">{{ c.label }}</div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div class="grid lg:grid-cols-3 gap-4">
        <Card>
          <CardContent>
            <h2 class="font-semibold text-sm mb-3">API requests / day</h2>
            <DailyLineChart :points="apiPoints" color="#00f0ff" />
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <h2 class="font-semibold text-sm mb-3">Secrets extracted via frontend / day</h2>
            <DailyLineChart :points="frontendPoints" color="#ffb703" />
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <h2 class="font-semibold text-sm mb-3 flex items-center gap-1.5">
              <PhWarning :size="14" weight="bold" class="text-destructive" /> Failed attempts / day
            </h2>
            <DailyLineChart :points="failedPoints" color="#f43f5e" />
          </CardContent>
        </Card>
      </div>
    </template>
  </div>
</template>
