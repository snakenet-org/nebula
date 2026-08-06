// @ai-purpose: App config composable — OIDC client id, token URL, login-screen feature flags, app
//   version.
// @ai-context: Single module-level reactive config, persisted to localStorage so synchronous
//   consumers (the OIDC PKCE flow needs clientId/tokenUrl before login; LoginView needs the
//   basic/OIDC toggles before login) have a value immediately on load. fetchConfig() is fired once
//   at startup (main.js) and refreshes the cache for next time — stale-while-revalidate, nothing
//   needs to await it. `version` backs App.vue's footer.
// @version: 1.1.0
// @author: Marc Fiedler <marc@snakenet.org>
// @date: 2026-08-06
import { reactive, readonly } from 'vue';

const STORAGE_KEY = 'nebula.config';
const EMPTY = {
  clientId: '',
  tokenUrl: '',
  basicLoginDisabled: false,
  oidcLoginDisabled: true,
  oidcLoginCaption: 'Sign in with snakeNet ID',
  version: '',
};

function load() {
  try {
    return { ...EMPTY, ...(JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') || {}) };
  } catch {
    return EMPTY;
  }
}

const state = reactive({ config: load() });

async function fetchConfig() {
  try {
    const response = await fetch('/api/v1/config/');
    if (!response.ok) return;
    const data = await response.json();
    state.config = {
      clientId: data.client_id,
      tokenUrl: data.token_url ?? '',
      basicLoginDisabled: data.basic_login_disabled,
      oidcLoginDisabled: data.oidc_login_disabled,
      oidcLoginCaption: data.oidc_login_caption,
      version: data.version ?? '',
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.config));
  } catch {
    // Offline/unreachable — keep whatever was persisted from the last successful fetch.
  }
}

export function useConfig() {
  return { state: readonly(state), fetchConfig };
}
