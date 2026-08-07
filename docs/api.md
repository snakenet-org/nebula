# API Reference

Base path for every route below: `/api/v1`. All request/response bodies are JSON.

## Authentication

Every route in this API — including the public ones — requires the header:

```
X-Nebula-Token: <NEBULA_TOKEN>
```

a site-wide shared secret set once when the container is spawned. It's the coarse "is this caller
even allowed to talk to this Nebula Vault instance" gate, checked before anything else. The public
routes (`/health`, `/ping`, `/config`, `/auth/*`) skip every *other* gate but still require this
header.

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

### 3. Project access key (`GET /vault/secret` only)

```
Authorization: Bearer nbv_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

A long-lived, Project-scoped credential generated from the UI (Project → Settings → API access
keys). Identifies *which Project*, not *which user* — meant for scripts/CI/containers pulling
secrets at deploy time, not for a human session.

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

## Access keys (`/access_key`) — human session required, owner/admin only

| Method | Path | Notes |
|---|---|---|
| GET | `/{project_id}` | Lists keys — `token_prefix` only, never the full token. |
| POST | `/{project_id}` | `{"name": "deploy-bot"}` → includes the raw `token` **once**, never again. |
| DELETE | `/{project_id}/{access_key_id}` | Revokes (soft — the row stays for audit, `revoked: true`). |

## Vault (`/vault`) — no human session

### `GET /vault/secret?key=<name>&environment=<name>`

Requires a project access key.

```
Authorization: Bearer nbv_...
X-Nebula-Token: ...
```

Case-insensitive match on both `key` and `environment`. Any lookup failure — unknown key, unknown
environment, or no value set for that pair — is a `404`, indistinguishably, so a caller can't
enumerate a Project's key names by probing.

```json
{ "key": "DATABASE_URL", "environment": "production", "value": "postgres://..." }
```

### `GET /vault/project`

Requires a project access key. Returns the name and description of the Project the presented key
resolves to.

```
Authorization: Bearer nbv_...
X-Nebula-Token: ...
```

```json
{ "name": "my-project", "description": "Internal tooling backend" }
```

### `GET /vault/status`

No project access key — access keys are strictly Project-scoped, and this isn't a Project-scoped
operation. Requires only `X-Nebula-Token`. A lightweight liveness/version/clock check for a machine
caller, not audit-logged.

```
X-Nebula-Token: ...
```

```json
{ "version": "2.5.0", "server_time": "2026-08-07T12:00:00Z" }
```
