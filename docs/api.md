# API Reference

Base path for every route below: `/api/v1`. All request/response bodies are JSON.

## Authentication

Every route in this API — **except the `/vault/*` routes below** — requires the header:

```
X-Nebula-Token: <NEBULA_TOKEN>
```

a site-wide shared secret set once when the container is spawned. It's the coarse "is this caller
even allowed to talk to this Nebula Vault instance" gate, checked before anything else. The public
routes (`/health`, `/ping`, `/config`, `/auth/*`) skip every *other* gate but still require this
header. The `/vault/*` routes (`GET /vault/secret`, `/vault/project`, `/vault/status`) are the one
exception — they never require `X-Nebula-Token`, only a project access key (see below).
`PUT /vault/secret` (changes a value) is a narrower exception to the exception: it requires **both**
a project access key **and** `X-Nebula-Token`, since it writes rather than reads.

Beyond that, three distinct credential kinds exist, and a route uses exactly one:

### 1. Human session (most routes)

```
Authorization: Bearer <JWT>
```

The JWT is either:
- A **locally minted HS256 token** from `POST /auth/login` (the optional bootstrap admin login), or
- An **Authentik RS256 access token**, obtained by the frontend's own OIDC PKCE flow and exchanged
  via `POST /auth/oidc`.

The server tells them apart from the JWT header's `alg` field — callers don't need to indicate
which kind they're presenting.

### 2. Local admin login

A special case of (1) — see `POST /auth/login` below. Exists as a fallback before any Authentik
group/user is configured, or for a fully self-hosted deployment that never wires up Authentik at
all (`NEBULA_OIDC_LOGIN_DISABLED=yes`, the default).

### 3. Project access key (`GET /vault/*` only)

```
Authorization: Bearer nbv_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

A long-lived, Project-scoped credential generated from the UI (Project → Settings → API access
keys). Identifies *which Project*, not *which user* — meant for scripts/CI/containers pulling
secrets at deploy time, not for a human session. Required on **every** `/vault/*` route, including
`/vault/status` (a plain liveness check still needs to present a valid key, it's just never scoped
to the Project it happens to resolve) and `PUT /vault/secret` (which also additionally requires
`X-Nebula-Token` — see above).

The exact same credential also authenticates the built-in **MCP server** at `/mcp` (see its own
section near the end of this file) — the one difference there is that its bearer token may carry
**more than one** project access key at once, comma-separated, so a single MCP connection can be
scoped to several specific Projects simultaneously.

---

## Public routes

### `GET /health`
Liveness check. `{"status": "ok", "version": "1.0.0"}`

### `GET /ping`
Trivial connectivity check. `{"message": "pong"}`

### `GET /config`
Frontend bootstrap config — login-screen feature flags and the Authentik client id, fetched before
any credential exists.

### `POST /auth/login`
Local username/password login (the optional admin login).
```json
{ "username": "admin", "password": "..." }
```
→ `AuthResponse` (see below).

### `POST /auth/oidc`
Exchange an Authentik access token for a Nebula session.
```json
{ "access_token": "...", "id_token": "..." }
```
→ `AuthResponse`:
```json
{
  "message": "Auth success",
  "token": "...",
  "nebula_token": "...",
  "id": "uuid",
  "name": "...",
  "email": "...",
  "groups": ["nebula-admin"],
  "entitlements": ["admin"],
  "is_admin": true
}
```
`nebula_token` is the `X-Nebula-Token` value the frontend must echo on every subsequent call.

---

## Projects (`/project`) — human session required

| Method | Path | Requires | Notes |
|---|---|---|---|
| GET | `/` | logged in | Every Project the caller owns, is shared on, or (admin) all of them. |
| POST | `/` | logged in | Creates a Project owned by the caller. |
| GET | `/{project_id}` | `can_view` | 404 (not 403) if not visible. |
| PATCH | `/{project_id}` | `can_edit` | Rename / change description. |
| DELETE | `/{project_id}` | `can_delete` | Owner or admin only. Cascades everything. |
| GET | `/{project_id}/shares` | `can_manage_sharing` | Owner or admin only. |
| POST | `/{project_id}/shares` | `can_manage_sharing` | `{"username": "...", "role": "viewer"\|"editor"}` |
| PATCH | `/{project_id}/shares/{user_id}` | `can_manage_sharing` | Change a share's role. |
| DELETE | `/{project_id}/shares/{user_id}` | `can_manage_sharing` | Revoke access. |

`ProjectResponse.my_role` is one of `owner`/`admin`/`editor`/`viewer` — the frontend uses it to
decide which controls to show; the backend independently re-checks every permission on every call
regardless of what the client believes.

## Environments (`/environment`) — human session required

| Method | Path | Requires |
|---|---|---|
| GET | `/{project_id}` | `can_view` |
| POST | `/{project_id}` | `can_edit` — `{"name": "production"}` |
| DELETE | `/{project_id}/{environment_id}` | `can_edit` |

Environment names are unique per Project, case-insensitively.

## Secrets (`/secret`) — human session required

| Method | Path | Requires | Notes |
|---|---|---|---|
| GET | `/{project_id}` | `can_view` | Returns keys with per-environment **presence only** (never ciphertext/plaintext). |
| POST | `/{project_id}` | `can_edit` | `{"name": "DATABASE_URL", "description": "..."}` |
| PATCH | `/{project_id}/{key_id}` | `can_edit` | Rename / change description. |
| DELETE | `/{project_id}/{key_id}` | `can_edit` | |
| PUT | `/{project_id}/{key_id}/value` | `can_edit` | Set a value — see below. |
| GET | `/{project_id}/{key_id}/reveal?environment_id=` | `can_reveal` | **Owner/admin only.** Returns the decrypted plaintext. |

Setting a value:
```json
{ "value": "postgres://...", "environment_id": "uuid" }
```
or, to write the same value to every Environment the Project currently has:
```json
{ "value": "dev@snakenet.org", "apply_to_all_environments": true }
```

A key's `variable_type` is one of `secret` (anonymized, `can_reveal` required), `environment` (an
environment variable — never anonymized, its value ships straight in the `GET /{project_id}` list
response), or `certificate` (a whole uploaded file — e.g. a PEM certificate/key — anonymized and
`can_reveal`-gated exactly like `secret`; the frontend's file picker just reads the file as text and
sends it through the same `value` field a plain secret already uses). A certificate never rotates
automatically — it can only be renewed by overwriting its value with a fresh upload, via this same
`PUT .../value` route or `PUT /vault/secret` below.

## Access keys (`/access_key`) — human session required, owner/admin only

| Method | Path | Notes |
|---|---|---|
| GET | `/{project_id}` | Lists keys — `token_prefix` only, never the full token. |
| POST | `/{project_id}` | `{"name": "deploy-bot"}` → includes the raw `token` **once**, never again. |
| DELETE | `/{project_id}/{access_key_id}` | Revokes (soft — the row stays for audit, `revoked: true`). |

## Vault (`/vault`) — no human session

Every `GET` route below requires only a project access key (no `X-Nebula-Token`, no human JWT).
`PUT /vault/secret` additionally requires `X-Nebula-Token` — see Authentication above. Every call,
success or failure, is audit-logged (`nebula.audit`, actions `vault.retrieve` / `vault.update` /
`vault.environment` / `vault.project` / `vault.status`) and rolled up into the Dashboard's "API requests / day" and
"Failed attempts / day" charts.

### `GET /vault/secret?key=<name>&environment=<name>`

```
Authorization: Bearer nbv_...
```

Case-insensitive match on both `key` and `environment`. Any lookup failure — unknown key, unknown
environment, or no value set for that pair — is a `404`, indistinguishably, so a caller can't
enumerate a Project's key names by probing.

```json
{ "key": "DATABASE_URL", "environment": "production", "value": "postgres://..." }
```

### `PUT /vault/secret?key=<name>&environment=<name>`

Changes the value of an **existing** secret, variable, or certificate key — never creates one (same
404-on-any-lookup-miss shape as the `GET` route above). Requires **both** a project access key and
`X-Nebula-Token`:

```
Authorization: Bearer nbv_...
X-Nebula-Token: <NEBULA_TOKEN>
```

```json
{ "value": "postgres://..." }
```

→ `200` with the same shape as `GET /vault/secret`. Works identically regardless of the key's type —
a certificate's "value" is just its file's raw text content (e.g. a PEM-encoded certificate/key),
stored encrypted the same way a plain secret's value already is. A key that's a reference to another
key's value (see the Secrets section below) can't be changed here either — `409`, same as the human
API — its value can only be changed by editing the source key, in its own Project. Audited as
`vault.update`.

### `GET /vault/environment?environment=<name>`

Returns every key/value pair the access key's Project holds in one Environment, as a flat map.

```
Authorization: Bearer nbv_...
```

```json
{
  "project": "my-project",
  "environment": "production",
  "values": { "DATABASE_URL": "postgres://...", "LOG_LEVEL": "info" }
}
```

The `environment` match is case-insensitive. Every key type is included: secrets, environment
variables and certificates. A reference key returns its source key's current value, and a key with
no value set is left out instead of failing the call. An unknown environment is a `404`. An
environment that exists but has no keys in this Project returns `200` with an empty `values` map.
Each call writes one `vault.environment` audit row, which counts once in the Dashboard's
request charts, plus one `vault.environment.key` row per returned key, so each key's extraction
count stays accurate.

### `GET /vault/project`

Returns the name and description of the Project the presented key resolves to.

```
Authorization: Bearer nbv_...
```

```json
{ "name": "my-project", "description": "Internal tooling backend" }
```

### `GET /vault/status`

A lightweight liveness/version/clock check for a machine caller. Still requires a project access
key — it's a credential check only, the response carries nothing Project-specific.

```
Authorization: Bearer nbv_...
```

```json
{ "version": "2.5.0", "server_time": "2026-08-07T12:00:00Z" }
```

---

## MCP server (`/mcp`) — no human session

A built-in [Model Context Protocol](https://modelcontextprotocol.io) server (streamable HTTP
transport), for LLM clients rather than a REST caller. Authenticates the exact same way as
`/vault/*` — a project access key as a bearer token — except the token may be **one or more** keys,
comma-separated (`Authorization: Bearer nbv_aaa...,nbv_bbb...`), scoping one MCP connection to
several specific Projects at once. If any listed key fails to resolve, the whole connection is
rejected (fail-closed) rather than silently granting partial access. No `X-Nebula-Token` required,
same reasoning as `/vault/*`'s three GET routes.

Five tools, all resolving their `project`/`environment`/`key` arguments by human-readable name
(case-insensitive), never by internal id:

- **`list_projects`** — every Project the presented key(s) grant access to.
- **`list_environments`** — every Environment defined in this instance (a global taxonomy).
- **`find_secrets(project, query?, variable_type?, environment?)`** — search/list a Project's keys.
  Never returns a secret or certificate's plaintext — only metadata, plus an environment variable's
  own value (never masked, same as Nebula's UI).
- **`read_secret(project, environment, key)`** — reveal one key's plaintext.
- **`set_secret_value(project, environment, key, value)`** — change an *existing* key's value only
  (never creates one); refuses a reference key, same as `PUT /vault/secret`; fans out to every
  enabled GitHub sync target afterward.

Every call is audit-logged (`mcp.search` / `mcp.read` / `mcp.update`), attributed to whichever
access key granted access to the Project involved — visible in the Audit Logs page's "API calls"
tab alongside every `/vault/*` call.
