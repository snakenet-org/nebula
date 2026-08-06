// @ai-purpose: Auth composable — holds the Nebular session and the two login paths.
// @ai-context: Single module-level reactive session, persisted to localStorage. setSession() stores
//   the AuthResponse (bearer token + X-Nebular-Token + identity/entitlements). loginLocal() posts
//   username/password to /api/v1/auth/login (the optional admin login); loginWithOidc() exchanges
//   Authentik tokens at /api/v1/auth/oidc and also stores the Authentik refresh_token.
//   scheduleTokenRefresh() fires a background timer ~60s before the access token expires and
//   silently swaps it using the refresh token — the user is never interrupted. refreshSession()
//   handles the same swap reactively on 401 (services/api.js's fallback). The two mechanisms
//   complement each other: the timer prevents 401s; the 401 handler is the safety net.
//   _refreshPromise is a shared lock — at most one Authentik token exchange is ever in flight at a
//   time regardless of which path triggered it (timer, 401 handler, or focus refresh). Mirrors
//   Satellite's useAuth.js almost exactly, adapted for entitlements instead of a bare is_admin flag.
// @version: 1.0.0
// @author: Marc Fiedler <marc@snakenet.org>
// @date: 2026-08-05
import { reactive, readonly } from 'vue';
import { refreshTokens } from '../services/oidc';

const STORAGE_KEY = 'nebular.session';
let _refreshTimer = null;
// Shared in-flight promise — prevents concurrent refresh races across all callers.
let _refreshPromise = null;

function load() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
  } catch {
    return null;
  }
}

const state = reactive({ session: load() });

function persist() {
  if (state.session) localStorage.setItem(STORAGE_KEY, JSON.stringify(state.session));
  else localStorage.removeItem(STORAGE_KEY);
}

function parseJwtExp(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return payload.exp ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

// Single shared refresh execution — coalesces concurrent callers onto the same Authentik exchange.
function _doRefresh() {
  if (_refreshPromise) return _refreshPromise;
  _refreshPromise = (async () => {
    const session = state.session;
    if (!session?.refreshToken) {
      console.warn('[auth] No refresh token in session — cannot refresh. Re-login required.');
      return false;
    }
    try {
      const { accessToken, refreshToken: newRefreshToken } = await refreshTokens(session.refreshToken);
      if (!accessToken) {
        console.warn('[auth] Authentik did not return an access token in the refresh response.');
        return false;
      }
      state.session = { ...session, token: accessToken, refreshToken: newRefreshToken ?? session.refreshToken };
      persist();
      scheduleTokenRefresh(accessToken);
      return true;
    } catch (err) {
      console.warn('[auth] Token refresh failed:', err?.message ?? err);
      return false;
    }
  })().finally(() => { _refreshPromise = null; });
  return _refreshPromise;
}

function scheduleTokenRefresh(token) {
  if (_refreshTimer) clearTimeout(_refreshTimer);
  _refreshTimer = null;
  if (!state.session?.refreshToken || !token) return;
  const exp = parseJwtExp(token);
  if (!exp) return;
  // Refresh 60s before expiry; floor at 10s so a nearly-expired token still gets one attempt.
  const delay = Math.max(exp - Date.now() - 60_000, 10_000);
  _refreshTimer = setTimeout(() => {
    _refreshTimer = null;
    _doRefresh();
  }, delay);
}

// Resume background refresh for any OIDC session persisted across a page reload.
if (state.session?.refreshToken && state.session?.token) {
  scheduleTokenRefresh(state.session.token);
}

function setSession(result) {
  state.session = {
    token: result.token ?? null,
    nebularToken: result.nebular_token ?? null,
    user: {
      id: result.id ?? null,
      name: result.name ?? null,
      email: result.email ?? null,
      groups: result.groups ?? [],
      entitlements: result.entitlements ?? [],
      isAdmin: result.is_admin ?? false,
    },
  };
  persist();
  return state.session;
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(typeof data?.detail === 'string' ? data.detail : `Login failed (HTTP ${response.status}).`);
  }
  return data;
}

export function useAuth() {
  async function loginLocal(username, password) {
    const result = await postJson('/api/v1/auth/login', { username, password });
    return setSession(result);
  }

  async function loginWithOidc(tokens) {
    const result = await postJson('/api/v1/auth/oidc', {
      access_token: tokens.accessToken,
      id_token: tokens.idToken,
    });
    setSession(result);
    state.session = {
      ...state.session,
      oidcIdToken: tokens.idToken ?? null,
      refreshToken: tokens.refreshToken ?? null,
    };
    persist();
    scheduleTokenRefresh(state.session.token);
    return state.session;
  }

  function logout() {
    if (_refreshTimer) { clearTimeout(_refreshTimer); _refreshTimer = null; }
    state.session = null;
    persist();
  }

  function refreshSession() {
    return _doRefresh();
  }

  return { state: readonly(state), loginLocal, loginWithOidc, logout, refreshSession };
}
