# Architecture

## Overview

Nebular Vault is a single FastAPI process that serves both the JSON API (`/api/v1/*`) and the built
Vue 3 SPA (everything else, from `public/`). It's built the same way as the sibling snakeNet.org
services `singularity` and `satellite`: a `uv`-managed Python 3.14 backend, a Vite-built frontend
copied into the backend's `public/` folder at image build time, and Alembic-managed PostgreSQL
schema.

The one real architectural departure from those siblings: Nebular Vault's PostgreSQL instance runs
**inside the same container**, not as a separate service. See
[deployment.md](deployment.md#embedded-postgresql) for why and how.

```
Browser (Vue SPA)
   │  fetch() — X-Nebular-Token + Bearer <session JWT>
   ▼
FastAPI (main.py)
   ├── /api/v1/health, /ping, /config   — public, no auth
   ├── /api/v1/auth                     — public, validates credentials itself
   ├── /api/v1/project, /environment,
   │   /secret, /access_key             — session-authenticated (human)
   ├── /api/v1/vault                    — project-access-key authenticated (machine)
   └── /{full_path}                     — SPA static files + index.html fallback
   │
   ▼
nebular.projects / .environments / .secrets / .access_keys / .users   (business logic)
   │
   ▼
nebular.crypto   — encrypt_value/decrypt_value (the only code that touches plaintext)
   │
   ▼
PostgreSQL (embedded, 127.0.0.1-only)
```

## Backend module map (`src/nebular/`)

| Module | Responsibility |
|---|---|
| `config.py` | Typed settings singleton, read from `NEBULAR_*` env vars. `require_master_key()` is the one setting with no safe default. |
| `database.py` | Async SQLAlchemy engine/session factory (`get_session()` FastAPI dependency), `Base` for ORM models. |
| `security.py` | bcrypt password hashing + local HS256 session JWTs (the optional admin login). |
| `crypto.py` | Envelope encryption for secret values — `encrypt_value`/`decrypt_value`, Fernet key derived from `NEBULAR_MASTER_KEY`. The *only* module that should ever handle plaintext outside a request handler that already decrypted one for an authorized caller. |
| `entitlements.py` | Authentik group → entitlement mapping (`nebular-admin`/`nebular-user`), mirrors Gravity's `entitlements.py`. |
| `users.py` | User provisioning shared by both login paths (local admin + OIDC). |
| `projects.py` | Project CRUD, sharing, and the full permission matrix (`can_view`/`can_edit`/`can_reveal`/`can_manage_sharing`/`can_manage_access_keys`/`can_delete`). Every other module defers to this for "may this caller do X." |
| `environments.py` | Environment CRUD, scoped to a Project. |
| `secrets.py` | SecretKey/SecretValue CRUD — the encrypted key-value store itself, including the "apply to all environments" convenience. |
| `access_keys.py` | Project API access key generate/revoke/resolve — the credential `api/v1/vault.py` accepts. |
| `models/tables.py` | SQLAlchemy ORM — the whole schema in one file. |
| `models/*.py` (other) | Pydantic request/response models, one file per resource. |
| `api/endpoint.py` | `Endpoint` base router class + the auth gates (`X-Nebular-Token`, session JWT, `get_current_user`). |
| `api/v1/*.py` | Thin FastAPI routers — each one delegates to its matching business-logic module rather than embedding logic itself. |

## The permission model, end to end

Every Project-scoped route resolves the actor (`get_current_user`) and the target Project
(`nebular.projects.get_visible_project`) first. That lookup itself enforces `can_view` — a Project
that exists but isn't visible to the caller 404s, the same as one that doesn't exist at all, so a
Project id's existence can never be probed by an unrelated account.

From there, each mutating route checks the specific permission it needs before calling into the
business-logic module:

- **`can_edit`** (owner, admin, or a Viewer/Editor share with `role=editor`) — environments, keys,
  and values.
- **`can_reveal`** (owner or admin *only*, regardless of share role) — decrypting a value's
  plaintext. This is the one place Editor access stops short of Owner access: an Editor can rotate a
  secret without ever having been allowed to see the old value.
- **`can_manage_sharing`** / **`can_manage_access_keys`** / **`can_delete`** (owner or admin only).

None of this is re-derived per route by hand — every check is a bare function in `nebular.projects`
taking already-loaded objects, so the actual authorization logic lives in exactly one place.

## The three authentication modes

1. **Human session** (`Authorization: Bearer <JWT>` + `X-Nebular-Token`) — either a locally minted
   HS256 token (the optional admin login) or an Authentik RS256 token, told apart by the JWT
   header's `alg` (`api/endpoint.py::decode_any_token`). Used by every `/api/v1/project`,
   `/environment`, `/secret`, `/access_key` route.
2. **Local admin login** — a special case of (1): `POST /api/v1/auth/login` mints an HS256 token for
   the bootstrap admin account seeded from `NEBULAR_ADMIN_USER`/`_PASS` at first startup.
3. **Project access key** (`Authorization: Bearer nbv_...` + `X-Nebular-Token`, no JWT at all) — the
   machine-to-machine credential `GET /api/v1/vault/secret` accepts. Deliberately a separate code
   path (`nebular.access_keys.resolve_access_key`), not a JWT variant — it identifies a *Project*,
   not a *user*.

See [api.md](api.md) for the full route reference and [encryption.md](encryption.md) for how a
value actually gets from plaintext-in-the-browser to ciphertext-on-disk and back.

## Frontend

A lightweight Vue 3 SPA (`frontend/`), built with Vite and served by the same FastAPI process from
`public/`. No `vue-router` — a small hand-rolled path-based router in `App.vue` (mirroring
Satellite's own frontend, which has no `vue-router` dependency either). No client-side state
library beyond a couple of small reactive composables (`useAuth`, `useConfig`) — every view fetches
what it needs directly via `services/api.js`.
