// @ai-purpose: Auth composable — holds the Nebula session and the two login paths.
// @ai-context: Single module-level reactive session, persisted to localStorage. setSession() stores
//   the AuthResponse (bearer token + X-Nebula-Token + identity/entitlements). loginLocal() posts
//   username/password to /api/v1/auth/login (the optional admin login); loginWithOidc() exchanges
//   Authentik tokens at /api/v1/auth/oidc and also stores the Authentik refresh_token. Both paths
//   stamp `authMethod` ('local'/'oidc') + `sessionStartedAt` on the session, since the two now
//   refresh completely differently:
//     - local: the session token itself (NEBULA_JWT_TTL, default 1h) is silently reissued by
//       Nebula's own POST /api/v1/auth/refresh (_doLocalRefresh) — the backend additionally accepts
//       it up to NEBULA_JWT_REFRESH_GRACE seconds (default 15min) past its own expiry, so a missed
//       proactive refresh (e.g. a backgrounded/frozen tab, same class of gap Gravity's own
//       heartbeat docs this for) doesn't force a full re-login. No absolute session-age cap.
//     - oidc: the bearer stays Authentik's own RS256 access token, refreshed via the standard OAuth
//       refresh_token grant against Authentik directly (services/oidc.js's refreshTokens() —
//       Nebula's backend mints nothing for OIDC, mirroring Satellite's own useAuth.js exactly). On
//       top of that, this composable caps a single OIDC session at OIDC_MAX_SESSION_AGE_MS (24h)
//       from its original login — once that's elapsed, silent refresh stops and the session is
//       dropped (full re-login via Authentik required), independent of how long Authentik's own
//       refresh token would otherwise still be valid for.
//   scheduleTokenRefresh() fires a background timer ~60s before the current access token expires
//   and silently swaps it via whichever path `authMethod` selects — the user is never interrupted.
//   refreshSession() does the same swap reactively on a 401 (services/api.js's fallback), also
//   dispatching by `authMethod`. The two mechanisms complement each other: the timer prevents 401s;
//   the 401 handler (plus, for local, the server's own grace window) is the safety net.
//   _refreshPromise is a shared lock — at most one refresh call (of either kind) is ever in flight
//   at a time regardless of which path triggered it (timer, 401 handler, or focus refresh).
// @version: 2.0.0
// @author: Marc Fiedler <marc@snakenet.org>
// @date: 2026-08-09
import { reactive, readonly } from 'vue';
import { refreshTokens } from '../services/oidc';

const STORAGE_KEY = 'nebula.session';
// Absolute cap on an OIDC session's lifetime, from its original login — after this, silent
// refresh stops even if Authentik's own refresh token is still valid.
const OIDC_MAX_SESSION_AGE_MS = 24 * 60 * 60 * 1000;
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

// A session persisted before `authMethod` existed has no such field — infer it from the presence
// of an Authentik refresh token, the only thing that ever distinguished the two paths before.
function authMethodOf(session) {
  if (!session) return null;
  return session.authMethod ?? (session.refreshToken ? 'oidc' : 'local');
}

function oidcSessionExpired(session) {
  return !session?.sessionStartedAt || Date.now() - session.sessionStartedAt > OIDC_MAX_SESSION_AGE_MS;
}

// Single shared refresh execution — coalesces concurrent callers onto the same Authentik exchange.
function _doOidcRefresh() {
  if (_refreshPromise) return _refreshPromise;
  _refreshPromise = (async () => {
    const session = state.session;
    if (!session?.refreshToken) {
      console.warn('[auth] No refresh token in session — cannot refresh. Re-login required.');
      return false;
    }
    if (oidcSessionExpired(session)) {
      console.warn('[auth] OIDC session exceeded its 24h max lifetime — re-login required.');
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

// Reissue a local (non-OIDC) session token via Nebula's own POST /api/v1/auth/refresh — the
// server accepts it up to NEBULA_JWT_REFRESH_GRACE seconds past its own expiry.
function _doLocalRefresh() {
  if (_refreshPromise) return _refreshPromise;
  _refreshPromise = (async () => {
    const session = state.session;
    if (!session?.token || !session?.nebulaToken) {
      console.warn('[auth] No local session to refresh — re-login required.');
      return false;
    }
    try {
      const response = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session.token}`,
          'X-Nebula-Token': session.nebulaToken,
        },
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.token) {
        console.warn('[auth] Local token refresh failed:', data?.detail ?? `HTTP ${response.status}`);
        return false;
      }
      state.session = { ...session, token: data.token };
      persist();
      scheduleTokenRefresh(data.token);
      return true;
    } catch (err) {
      console.warn('[auth] Local token refresh failed:', err?.message ?? err);
      return false;
    }
  })().finally(() => { _refreshPromise = null; });
  return _refreshPromise;
}

function _doRefresh() {
  return authMethodOf(state.session) === 'local' ? _doLocalRefresh() : _doOidcRefresh();
}

function scheduleTokenRefresh(token) {
  if (_refreshTimer) clearTimeout(_refreshTimer);
  _refreshTimer = null;
  const session = state.session;
  if (!session || !token) return;

  const method = authMethodOf(session);
  if (method === 'oidc' && (!session.refreshToken || oidcSessionExpired(session))) return;

  const exp = parseJwtExp(token);
  if (!exp) return;
  // Refresh 60s before expiry; floor at 10s so a nearly-expired token still gets one attempt.
  const delay = Math.max(exp - Date.now() - 60_000, 10_000);
  _refreshTimer = setTimeout(() => {
    _refreshTimer = null;
    _doRefresh();
  }, delay);
}

// Resume background refresh for any session persisted across a page reload.
if (state.session?.token) {
  if (authMethodOf(state.session) === 'oidc' && oidcSessionExpired(state.session)) {
    state.session = null;
    persist();
  } else {
    scheduleTokenRefresh(state.session.token);
  }
}

function setSession(result) {
  state.session = {
    token: result.token ?? null,
    nebulaToken: result.nebula_token ?? null,
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
    setSession(result);
    state.session = { ...state.session, authMethod: 'local', sessionStartedAt: Date.now() };
    persist();
    scheduleTokenRefresh(state.session.token);
    return state.session;
  }

  async function loginWithOidc(tokens) {
    const result = await postJson('/api/v1/auth/oidc', {
      access_token: tokens.accessToken,
      id_token: tokens.idToken,
    });
    setSession(result);
    state.session = {
      ...state.session,
      authMethod: 'oidc',
      sessionStartedAt: Date.now(),
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
