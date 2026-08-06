// @ai-purpose: OIDC / OAuth2 (Authorization Code + PKCE) configuration for snakeNet ID (Authentik).
// @ai-context: All endpoints derive from `authority` (id.snakenet.io). `applicationSlug` selects the
//   Nebula application registered in Authentik. `clientId`/`enabled`/`caption`/`tokenEndpoint` are
//   live getters onto useConfig's cached backend value (GET /api/v1/config) so none of it needs to
//   be hardcoded or kept in sync by hand. The redirect URI is derived from the current browser
//   origin so the flow returns to wherever the SPA is served.
// @version: 1.0.0
// @author: Marc Fiedler <marc@snakenet.org>
// @date: 2026-08-05
import { useConfig } from '../composables/useConfig';

const authority = 'https://id.snakenet.io';
const applicationSlug = 'nebula';

export const OIDC = {
  // Master switch for the "Sign in with snakeNet ID" button, sourced from the backend.
  get enabled() {
    return !useConfig().state.config.oidcLoginDisabled;
  },

  // Caption shown on the Oauth login button, sourced from the backend.
  get caption() {
    return useConfig().state.config.oidcLoginCaption;
  },

  authority,
  // The Nebula Authentik application's client id, sourced from the backend (see useConfig.js).
  get clientId() {
    return useConfig().state.config.clientId;
  },

  // Derived from the current origin → register each origin's /reentry URI on the Authentik provider.
  redirectUri: `${window.location.origin}/reentry`,
  postLogoutRedirectUri: `${window.location.origin}/`,
  scope: 'openid profile email offline_access',

  authorizeEndpoint: `${authority}/application/o/authorize/`,
  get tokenEndpoint() {
    return useConfig().state.config.tokenUrl || `${authority}/application/o/token/`;
  },
  endSessionEndpoint: `${authority}/application/o/${applicationSlug}/end-session/`,

  // Nebula endpoint that trades an Authentik token for a Nebula session.
  exchangePath: '/api/v1/auth/oidc',
};
