// @ai-purpose: OIDC Authorization Code + PKCE flow against snakeNet ID (Authentik), no dependencies.
// @ai-context: Built on the Web Crypto API. beginLogin() builds a PKCE challenge, stashes the
//   verifier/state in sessionStorage and redirects to Authentik. On return to /reentry, isCallback()
//   detects the response and completeLogin() validates state and exchanges the code for tokens. The
//   Nebular-session handoff happens separately (composables/useAuth.js).
// @version: 1.0.0
// @author: Marc Fiedler <marc@snakenet.org>
// @date: 2026-08-05
import { OIDC } from '../config/oidc';

const STORE_KEY = 'nebular.oidc';

function base64Url(bytes) {
  const arr = new Uint8Array(bytes);
  let str = '';
  for (let i = 0; i < arr.length; i++) str += String.fromCharCode(arr[i]);
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function randomString(byteLength = 48) {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return base64Url(bytes);
}

async function sha256Base64Url(input) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return base64Url(digest);
}

/** Start the OIDC login: generate PKCE + state, persist them, and redirect to Authentik. */
export async function beginLogin() {
  const codeVerifier = randomString(48);
  const codeChallenge = await sha256Base64Url(codeVerifier);
  const state = randomString(24);
  const nonce = randomString(24);

  sessionStorage.setItem(STORE_KEY, JSON.stringify({ codeVerifier, state, nonce }));

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: OIDC.clientId,
    redirect_uri: OIDC.redirectUri,
    scope: OIDC.scope,
    state,
    nonce,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });
  window.location.assign(`${OIDC.authorizeEndpoint}?${params.toString()}`);
}

/** True when the current URL carries an OIDC authorization-code response. */
export function isCallback() {
  const p = new URLSearchParams(window.location.search);
  return p.has('code') && p.has('state');
}

/** Returns an Authentik error carried on the callback URL (e.g. access_denied), or null. */
export function callbackError() {
  const p = new URLSearchParams(window.location.search);
  if (p.has('error')) return p.get('error_description') || p.get('error');
  return null;
}

/** Complete the flow: validate state and exchange the code for tokens. */
export async function completeLogin() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('code');
  const returnedState = params.get('state');

  const stored = JSON.parse(sessionStorage.getItem(STORE_KEY) || 'null');
  if (!stored) throw new Error('Missing PKCE state — login was not started from this origin.');
  if (returnedState !== stored.state) throw new Error('OIDC state mismatch — aborting.');

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    redirect_uri: OIDC.redirectUri,
    client_id: OIDC.clientId,
    code_verifier: stored.codeVerifier,
  });

  let response;
  try {
    response = await fetch(OIDC.tokenEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });
  } catch {
    throw new Error('Could not reach the Authentik token endpoint (network/CORS).');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.error_description || data?.error || `Token exchange failed (HTTP ${response.status}).`);
  }

  sessionStorage.removeItem(STORE_KEY);
  return {
    idToken: data.id_token ?? null,
    accessToken: data.access_token ?? null,
    refreshToken: data.refresh_token ?? null,
  };
}

/** Exchange a refresh token for fresh tokens. Returns { accessToken, refreshToken }. */
export async function refreshTokens(refreshToken) {
  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    refresh_token: refreshToken,
    client_id: OIDC.clientId,
  });
  let response;
  try {
    response = await fetch(OIDC.tokenEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    });
  } catch {
    throw new Error('Could not reach the Authentik token endpoint (network/CORS).');
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.error_description || data?.error || `Token refresh failed (HTTP ${response.status}).`);
  }
  return { accessToken: data.access_token ?? null, refreshToken: data.refresh_token ?? null };
}

/** Strip the OIDC params from the URL without adding a history entry. */
export function clearCallbackParams() {
  const url = new URL(window.location.href);
  ['code', 'state', 'session_state', 'iss', 'error', 'error_description'].forEach((k) =>
    url.searchParams.delete(k)
  );
  history.replaceState(history.state, '', url.pathname + url.search + url.hash);
}
