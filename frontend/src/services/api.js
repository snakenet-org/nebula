// @ai-purpose: Authenticated client for the protected Nebula API.
// @ai-context: Every protected route requires BOTH gates: Authorization: Bearer <jwt> and
//   X-Nebula-Token: <shared secret>. Both come from the session stored by useAuth. On 401 a single
//   silent token-refresh is attempted — useAuth.refreshSession() dispatches to the right mechanism
//   for either session kind (local: POST /api/v1/auth/refresh; OIDC: Authentik's refresh_token
//   grant) — and if that succeeds the original request is retried transparently. Only when the
//   refresh itself also fails is the caller logged out. A module-level lock (_refreshPromise)
//   prevents concurrent refresh races when multiple in-flight requests all 401 at the same time.
//   Mirrors Satellite's services/api.js request/parseResponse shape, with thin per-route helpers
//   for projects/environments/secrets/access keys.
//   2026-08-12 (later same day): listAuditActivity/listAuditApiCalls/listAuditFailedRetrievals now
//   take an optional { search, page, pageSize } and build a query string (auditQuery) — the Audit
//   Logs page pages server-side now (300 rows/page max, nebula.audit.MAX_PAGE_SIZE) instead of
//   pulling the whole log in one response.
//   2026-08-12 (later same day): new logSecretCopy — audit-log-only, fired after a successful
//   clipboard copy in ProjectView.vue; createSecret/setSecretValue's payloads may now also carry an
//   optional rotation_frequency/rotation_unit (nebula.rotation), unchanged shape here since both
//   already just forward whatever payload object they're given.
// @version: 2.6.0
// @author: Marc Fiedler <marc@snakenet.org>
// @date: 2026-08-12
import { useAuth } from '../composables/useAuth';

let _refreshPromise = null;

function authHeaders() {
  const { state } = useAuth();
  const session = state.session;
  if (!session) throw new Error('Not authenticated.');
  const headers = { 'Content-Type': 'application/json' };
  if (session.token) headers['Authorization'] = `Bearer ${session.token}`;
  if (session.nebulaToken) headers['X-Nebula-Token'] = session.nebulaToken;
  return headers;
}

async function parseResponse(response) {
  let data = null;
  try {
    data = await response.json();
  } catch {
    // empty/non-JSON body
  }
  if (!response.ok) {
    const detail = data?.detail;
    let msg = typeof detail === 'string' ? detail : `Request failed (HTTP ${response.status}).`;
    if (Array.isArray(detail) && detail.length) msg = detail.map((d) => d.msg || JSON.stringify(d)).join(', ');
    throw new Error(msg);
  }
  return data;
}

async function request(method, path, body, { authExpiryOn401 = true } = {}) {
  const fetchArgs = {
    method,
    headers: authHeaders(),
    body: body === undefined ? undefined : JSON.stringify(body),
  };

  let response;
  try {
    response = await fetch(path, fetchArgs);
  } catch {
    throw new Error('Could not reach the Nebula API.');
  }

  if (response.status === 401 && authExpiryOn401) {
    const auth = useAuth();
    if (!_refreshPromise) {
      _refreshPromise = auth.refreshSession().finally(() => { _refreshPromise = null; });
    }
    const refreshed = await _refreshPromise;
    if (refreshed) {
      try {
        response = await fetch(path, { ...fetchArgs, headers: authHeaders() });
      } catch {
        throw new Error('Could not reach the Nebula API.');
      }
      if (response.status !== 401) {
        return parseResponse(response);
      }
    }
    auth.logout();
    throw new Error('Your session has expired. Please log in again.');
  }

  return parseResponse(response);
}

// ── Projects ──────────────────────────────────────────────────────────────
export const listProjects = () => request('GET', '/api/v1/project/');
export const getProject = (id) => request('GET', `/api/v1/project/${id}`);
export const createProject = (payload) => request('POST', '/api/v1/project/', payload);
export const updateProject = (id, payload) => request('PATCH', `/api/v1/project/${id}`, payload);
export const deleteProject = (id) => request('DELETE', `/api/v1/project/${id}`);
export const transferProject = (id, payload) => request('POST', `/api/v1/project/${id}/transfer`, payload);

// ── GitHub sync (a Project may have many simultaneous sync targets) ────────
export const listGithubTargets = (id) => request('GET', `/api/v1/project/${id}/github/targets`);
export const createGithubTarget = (id, payload) =>
  request('POST', `/api/v1/project/${id}/github/targets`, payload);
export const updateGithubTarget = (id, targetId, payload) =>
  request('PATCH', `/api/v1/project/${id}/github/targets/${targetId}`, payload);
export const deleteGithubTarget = (id, targetId) =>
  request('DELETE', `/api/v1/project/${id}/github/targets/${targetId}`);
export const syncGithubTarget = (id, targetId) =>
  request('POST', `/api/v1/project/${id}/github/targets/${targetId}/sync`);
export const syncGithubAll = (id) => request('POST', `/api/v1/project/${id}/github/sync`);

// ── Sharing ───────────────────────────────────────────────────────────────
export const listShares = (projectId) => request('GET', `/api/v1/project/${projectId}/shares`);
export const createShare = (projectId, payload) =>
  request('POST', `/api/v1/project/${projectId}/shares`, payload);
export const updateShare = (projectId, userId, payload) =>
  request('PATCH', `/api/v1/project/${projectId}/shares/${userId}`, payload);
export const revokeShare = (projectId, userId) =>
  request('DELETE', `/api/v1/project/${projectId}/shares/${userId}`);

// ── Environments (global — not project-scoped) ──────────────────────────────
export const listEnvironments = () => request('GET', '/api/v1/environment/');
export const createEnvironment = (payload) => request('POST', '/api/v1/environment/', payload);
export const updateEnvironment = (environmentId, payload) =>
  request('PATCH', `/api/v1/environment/${environmentId}`, payload);
export const deleteEnvironment = (environmentId) =>
  request('DELETE', `/api/v1/environment/${environmentId}`);

// ── Secrets ───────────────────────────────────────────────────────────────
export const listSecrets = (projectId) => request('GET', `/api/v1/secret/${projectId}`);
export const createSecret = (projectId, payload) => request('POST', `/api/v1/secret/${projectId}`, payload);
export const updateSecret = (projectId, keyId, payload) =>
  request('PATCH', `/api/v1/secret/${projectId}/${keyId}`, payload);
export const deleteSecret = (projectId, keyId) => request('DELETE', `/api/v1/secret/${projectId}/${keyId}`);
export const setSecretValue = (projectId, keyId, payload) =>
  request('PUT', `/api/v1/secret/${projectId}/${keyId}/value`, payload);
export const bulkCreateSecrets = (projectId, payload) =>
  request('POST', `/api/v1/secret/${projectId}/bulk`, payload);
export const revealSecretValue = (projectId, keyId) =>
  request('GET', `/api/v1/secret/${projectId}/${keyId}/reveal`);
// Audit-log-only — no value is ever sent; fire this after a successful clipboard write.
export const logSecretCopy = (projectId, keyId) =>
  request('POST', `/api/v1/secret/${projectId}/${keyId}/copy`);

// ── Access keys ───────────────────────────────────────────────────────────
export const listAccessKeys = (projectId) => request('GET', `/api/v1/access_key/${projectId}`);
export const createAccessKey = (projectId, payload) =>
  request('POST', `/api/v1/access_key/${projectId}`, payload);
export const revokeAccessKey = (projectId, keyId) =>
  request('DELETE', `/api/v1/access_key/${projectId}/${keyId}`);

// ── Auth ─────────────────────────────────────────────────────────────────
// Best-effort only (see App.vue's doLogout) — Nebula's JWTs are stateless, this call exists purely
// to record an "auth.logout" nebula.audit row before the frontend discards its local session.
export const logout = () => request('POST', '/api/v1/auth/logout');

// ── Dashboard ────────────────────────────────────────────────────────────
export const getDashboardSummary = () => request('GET', '/api/v1/dashboard/summary');
export const getDashboardSeries = () => request('GET', '/api/v1/dashboard/series');

// ── Audit logs (server-side scoped: admin sees everything, others their own/editor Projects) ──
// Each returns an AuditLogPageResponse ({ items, total, page, page_size }) — page_size is capped
// server-side at nebula.audit.MAX_PAGE_SIZE (300), enforced again here so a caller can't request more.
function auditQuery({ search, page = 1, pageSize = 300 } = {}) {
  const params = new URLSearchParams({ page: String(page), page_size: String(Math.min(pageSize, 300)) });
  if (search) params.set('search', search);
  return `?${params.toString()}`;
}
export const listAuditActivity = (opts) => request('GET', `/api/v1/audit/activity${auditQuery(opts)}`);
export const listAuditApiCalls = (opts) => request('GET', `/api/v1/audit/api-calls${auditQuery(opts)}`);
export const listAuditFailedRetrievals = (opts) =>
  request('GET', `/api/v1/audit/failed-retrievals${auditQuery(opts)}`);

// ── Health ───────────────────────────────────────────────────────────────
export const getHealth = () => request('GET', '/api/v1/health/');
